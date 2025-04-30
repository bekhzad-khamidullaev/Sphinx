# room/consumers.py
import json
import uuid
import base64
import logging
import asyncio # Import asyncio for gather
from collections import defaultdict # Use defaultdict for easier handling
from channels.generic.websocket import AsyncWebsocketConsumer
from channels.db import database_sync_to_async
from django.conf import settings
from django.core.files.base import ContentFile
from django.utils.translation import gettext as _
from django.db.models import Q
from django.utils.timezone import now
from django.db import models
from django.contrib.auth import get_user_model # Import get_user_model

# Models are imported after get_user_model potentially runs if needed at module level elsewhere
from .models import Room, Message, Reaction, MessageReadStatus
# utils.py is no longer needed for in-memory presence

logger = logging.getLogger(__name__)

# --- Message Types (Constants) ---
MSG_TYPE_MESSAGE = 'chat_message'
MSG_TYPE_EDIT = 'edit_message'
MSG_TYPE_DELETE = 'delete_message'
MSG_TYPE_REACTION = 'reaction_update'
MSG_TYPE_FILE = 'file_message'
MSG_TYPE_READ_STATUS = 'read_status_update' # Optional broadcast
MSG_TYPE_REPLY = 'reply_message'
MSG_TYPE_ONLINE_USERS = 'online_users'
MSG_TYPE_ERROR = 'error_message'
MSG_TYPE_OLDER_MESSAGES = 'older_messages' # For infinite scroll
MSG_TYPE_LOAD_OLDER = 'load_older_messages' # Client request type
MSG_TYPE_ACK = 'message_ack' # For message confirmation

class ChatConsumer(AsyncWebsocketConsumer):
    # --- In-Memory Storage for Online Users (Class Variable) ---
    # WARNING: This is NOT shared across multiple worker processes!
    online_users_by_room = defaultdict(set)
    # ---

    async def connect(self):
        self.room_slug = self.scope['url_route']['kwargs']['room_name']
        self.room_group_name = f'chat_{self.room_slug}'
        self.user = self.scope['user']

        if not self.user or not self.user.is_authenticated:
            logger.warning(f"Unauthenticated user tried to connect to room {self.room_slug}.")
            await self.close()
            return

        logger.info(f"User {self.user.username} connecting to room {self.room_slug}...")
        self.room = await self.get_room(self.room_slug)
        if not self.room or self.room.is_archived:
            logger.warning(f"Connection rejected: Room {self.room_slug} not found or archived.")
            await self.close(code=4004)
            return
        if not await self.check_permissions(self.user, self.room):
             logger.warning(f"User {self.user.username} permission denied for room {self.room_slug}.")
             await self.close(code=4003)
             return

        await self.channel_layer.group_add(self.room_group_name, self.channel_name)
        await self.accept()
        logger.info(f"User {self.user.username} ACCEPTED connection to room {self.room_slug}")

        # --- Use In-Memory Online Status ---
        await self.add_user_to_online_list()
        await self.broadcast_online_users()
        # ---

    async def disconnect(self, close_code):
        logger.info(f"User {getattr(self.user, 'username', 'anonymous')} disconnecting from room {self.room_slug}, code: {close_code}")
        if hasattr(self, 'user') and self.user.is_authenticated and hasattr(self, 'room_group_name'):
            # --- Use In-Memory Online Status ---
            await self.remove_user_from_online_list()
            await self.broadcast_online_users()
            # ---
            await self.channel_layer.group_discard(self.room_group_name, self.channel_name)
        logger.info(f"User {getattr(self.user, 'username', 'anonymous')} disconnected fully from {self.room_slug}")

    async def receive(self, text_data):
        try:
            data = json.loads(text_data)
            message_type = data.get('type')
            if not message_type:
                raise ValueError("Message type not provided.")
            logger.debug(f"Receive type '{message_type}' from {self.user.username} in {self.room_slug}")

            handler = getattr(self, f'handle_{message_type}', self.handle_unknown_type)
            await handler(data.get('payload', {})) # Pass payload to handler
        except json.JSONDecodeError:
            logger.error(f"Invalid JSON from {self.user.username}: {text_data}")
            await self.send_error("Invalid JSON format.")
        except Exception as e:
            logger.exception(f"Error processing message from {self.user.username} in {self.room_slug}: {e}. Data: {text_data}")
            await self.send_error("An error occurred.")


    # --- Message Handlers ---
    async def handle_chat_message(self, payload):
        content = payload.get('content', '').strip() # Consumer expects 'content' key
        client_msg_id = payload.get('client_id')
        if not content: return await self.send_error("Message content empty.", client_msg_id)

        message = await self.save_message(user=self.user, room=self.room, content=content)
        logger.info(f"Message {message.id} saved successfully for room {self.room_slug}. Attempting broadcast...") # LOG 1
        await self.broadcast_message(message, MSG_TYPE_MESSAGE, client_msg_id=client_msg_id)

    async def handle_reply_message(self, payload):
        content = payload.get('content', '').strip() # Consumer expects 'content' key
        reply_to_id = payload.get('reply_to_id')
        client_msg_id = payload.get('client_id')
        if not content or not reply_to_id: return await self.send_error("Missing data for reply.", client_msg_id)

        try:
            reply_to_msg = await self.get_message(uuid.UUID(reply_to_id))
            if not reply_to_msg or reply_to_msg.room != self.room: raise Message.DoesNotExist
        except (ValueError, Message.DoesNotExist): return await self.send_error("Invalid message to reply to.", client_msg_id)

        message = await self.save_message(user=self.user, room=self.room, content=content, reply_to=reply_to_msg)
        await self.broadcast_message(message, MSG_TYPE_REPLY, include_reply_to=True, client_msg_id=client_msg_id)

    async def handle_edit_message(self, payload):
        message_id = payload.get('message_id')
        new_content = payload.get('content', '').strip() # Consumer expects 'content' key
        if not message_id or not new_content: return await self.send_error("Missing data for edit.")

        try:
            message = await self.get_message(uuid.UUID(message_id))
            if not message or message.user != self.user or message.room != self.room or message.is_deleted:
                return await self.send_error("Cannot edit this message.")
            updated_message = await self.update_message_content(message, new_content)
            await self.broadcast_message(updated_message, MSG_TYPE_EDIT)
        except (ValueError, Message.DoesNotExist): await self.send_error("Invalid message ID for edit.")

    async def handle_delete_message(self, payload):
        message_id = payload.get('message_id')
        if not message_id: return await self.send_error("Missing message ID for delete.")

        try:
            message = await self.get_message(uuid.UUID(message_id))
            if not message or message.user != self.user or message.room != self.room or message.is_deleted:
                return await self.send_error("Cannot delete this message.")
            deleted_message = await self.mark_message_deleted(message)
            await self.broadcast_message(deleted_message, MSG_TYPE_DELETE)
        except (ValueError, Message.DoesNotExist): await self.send_error("Invalid message ID for delete.")

    async def handle_add_reaction(self, payload):
        message_id = payload.get('message_id')
        emoji = payload.get('emoji', '').strip()
        if not message_id or not emoji or len(emoji) > 10: return await self.send_error("Invalid reaction data.")

        try:
            message = await self.get_message(uuid.UUID(message_id))
            if not message or message.room != self.room or message.is_deleted:
                return await self.send_error("Cannot react to this message.")

            await self.add_or_update_reaction(message, self.user, emoji) # Toggle reaction
            reactions_summary = await self.get_reactions_summary(message) # Get updated summary

            await self.channel_layer.group_send(
                self.room_group_name,
                {
                    'type': 'reaction_broadcast',
                    'message_id': str(message.id),
                    'reactions': reactions_summary
                }
            )
        except (ValueError, Message.DoesNotExist): await self.send_error("Invalid message ID for reaction.")

    async def handle_mark_read(self, payload):
        last_id = payload.get('last_visible_message_id')
        if not last_id:
            logger.debug(f"Marking all as read for user {self.user.id} in room {self.room_slug}")
            await self.update_read_status_to_latest(self.user, self.room)
            # Optionally broadcast this status if needed by other clients
            # await self.broadcast_read_status(...)
            return

        try:
            message = await self.get_message(uuid.UUID(last_id))
            if message and message.room == self.room:
                logger.debug(f"Marking read up to {message.id} for user {self.user.id} in room {self.room_slug}")
                await self.update_read_status(self.user, self.room, message)
                # Optionally broadcast this status
                # await self.broadcast_read_status(...)
            else:
                 logger.warning(f"Mark read failed: Message {last_id} not found or not in room {self.room_slug}.")
                 await self.send_error("Invalid last visible message ID.")
        except (ValueError, Message.DoesNotExist):
            logger.warning(f"Mark read failed: Invalid UUID format '{last_id}'.")
            await self.send_error("Invalid message ID format for mark read.")

    async def handle_send_file(self, payload):
        file_data_base64 = payload.get('file_data')
        filename = payload.get('filename')
        content = payload.get('content', '') # Optional caption (use 'content' key)
        client_msg_id = payload.get('client_id')

        if not file_data_base64 or not filename: return await self.send_error("Missing file data.", client_msg_id)
        # TODO: Add robust file size and type validation here before decoding/saving

        try:
            file_content = base64.b64decode(file_data_base64)
            django_file = ContentFile(file_content, name=filename)
            message = await self.save_message(user=self.user, room=self.room, content=content, file=django_file)
            await self.broadcast_message(message, MSG_TYPE_FILE, include_file_info=True, client_msg_id=client_msg_id)
        except (TypeError, ValueError) as e:
             logger.error(f"File decode error from user {self.user.username}: {e}")
             await self.send_error("Invalid file data provided.", client_msg_id)
        except Exception as e:
            logger.exception(f"Error saving file message from {self.user.username}: {e}")
            await self.send_error("Could not process file.", client_msg_id)

    async def handle_load_older_messages(self, payload):
        """Handles request from client to load older messages."""
        before_message_id = payload.get('before_message_id')
        limit = 20 # Number of older messages to fetch

        try:
            before_message = None
            if before_message_id:
                before_message = await self.get_message(uuid.UUID(before_message_id))
                if not before_message or before_message.room != self.room:
                     return await self.send_error("Invalid 'before_message_id'.")

            older_messages = await self.get_older_messages(self.room, limit, before_message)

            serialized_messages = []
            for msg in older_messages:
                serialized_messages.append(await self.serialize_message(msg, include_reply_to=True, include_file_info=True))

            await self.send(text_data=json.dumps({ # Use send/dumps
                'type': MSG_TYPE_OLDER_MESSAGES,
                'payload': {
                    'messages': serialized_messages,
                    'has_more': len(older_messages) == limit
                }
            }))
        except (ValueError, Message.DoesNotExist):
            await self.send_error("Invalid 'before_message_id'.")
        except Exception as e:
            logger.exception(f"Error loading older messages for room {self.room_slug}: {e}")
            await self.send_error("Could not load older messages.")

    async def handle_unknown_type(self, payload):
        await self.send_error(f"Unknown message type received.")

    # --- Broadcasting Methods ---
    async def broadcast_message(self, message, message_type, include_reply_to=False, include_file_info=False, client_msg_id=None):
        """ Broadcasts a message, optionally includes client_id for acknowledgement """
        logger.debug(f"Serializing message {message.id} for broadcast...") # LOG 2
        message_data = await self.serialize_message(message, include_reply_to, include_file_info)
        # Log serialized data only if needed for intense debugging (can be large)
        # logger.debug(f"Message {message.id} serialized: {json.dumps(message_data, indent=2)}") # LOG 3
        broadcast_data = {
            'type': 'chat_broadcast',
            'message_type': message_type,
            'message': message_data,
            'sender_channel_name': self.channel_name
        }
        if client_msg_id:
            broadcast_data['client_id'] = client_msg_id

        logger.info(f"Broadcasting message {message.id} (type: {message_type}) to group {self.room_group_name}") # LOG 4
        try:
            await self.channel_layer.group_send(self.room_group_name, broadcast_data)
            logger.info(f"Successfully sent message {message.id} to channel layer group {self.room_group_name}") # LOG 5
        except Exception as e:
             logger.exception(f"!!! Error sending message {message.id} to channel layer group {self.room_group_name}: {e}") # LOG 6

    async def chat_broadcast(self, event):
        """ Sends message data received from the group to this specific WebSocket client. """
        logger.info(f"Consumer {self.channel_name} received broadcast event type {event.get('message_type')} for message {event.get('message',{}).get('id')} in group {self.room_group_name}") # LOG 7
        payload = event['message']
        # If client_id was part of the broadcast, add it to the payload sent back
        if 'client_id' in event:
             payload['client_id'] = event['client_id']

        send_to_client = True
        # Don't send regular message back to sender if no client_id for ACK
        if self.channel_name == event.get('sender_channel_name') and not event.get('client_id'):
             logger.debug(f"Skipping broadcast to self for message {payload.get('id')} (no client_id ack needed)")
             send_to_client = False

        if send_to_client:
            # Check if it's an ACK for the original sender
            if self.channel_name == event.get('sender_channel_name') and event.get('client_id'):
                 logger.debug(f"Sending ACK for client_id {event['client_id']} to {self.channel_name}")
                 try:
                     await self.send(text_data=json.dumps({ # Use send/dumps
                         'type': MSG_TYPE_ACK,
                         'payload': {
                             'client_id': event['client_id'],
                             'server_id': payload['id'],
                             'timestamp': payload['timestamp']
                         }
                     }))
                 except Exception as e:
                     logger.exception(f"!!! Error sending ACK to client {self.channel_name}: {e}")
            else:
                 # Send regular message to other clients
                 logger.info(f"Sending message {payload.get('id')} type {event['message_type']} to client {self.channel_name}") # LOG 8
                 try:
                      await self.send(text_data=json.dumps({'type': event['message_type'], 'payload': payload})) # Use send/dumps
                      logger.info(f"Successfully sent message {payload.get('id')} to client {self.channel_name}") # LOG 9
                 except Exception as e:
                      logger.exception(f"!!! Error sending message {payload.get('id')} to client {self.channel_name}: {e}") # LOG 10

    async def reaction_broadcast(self, event):
         logger.debug(f"Sending reaction update for message {event['message_id']} to {self.channel_name}")
         await self.send(text_data=json.dumps({ # Use send/dumps
             'type': MSG_TYPE_REACTION,
             'payload': {'message_id': event['message_id'],'reactions': event['reactions']}
         }))

    async def online_status_broadcast(self, event):
         logger.debug(f"Sending online users list {event['users']} to {self.channel_name}")
         await self.send(text_data=json.dumps({ # Use send/dumps
            'type': MSG_TYPE_ONLINE_USERS,
            'payload': {'users': event['users']} # Send list of user data dicts
         }))


    # --- Database Interaction (Async Helpers) ---
    @database_sync_to_async
    def get_room(self, slug):
        """ Gets Room object or None, prefetches participants """
        try:
            return Room.objects.prefetch_related('participants').get(slug=slug)
        except Room.DoesNotExist:
            logger.warning(f"Room with slug '{slug}' not found in get_room.")
            return None

    @database_sync_to_async
    def check_permissions(self, user, room):
        """ Checks if user can access the room """
        if not room: return False
        if not room.private: return True
        # Use exists() for efficiency on the prefetched relation
        return room.participants.filter(pk=user.pk).exists()

    @database_sync_to_async
    def get_message(self, message_id):
        """ Gets a specific message by UUID, selecting related fields """
        try:
            # Select related user and reply info needed for serialization/logic
            return Message.objects.select_related('user', 'reply_to__user').get(id=message_id)
        except (Message.DoesNotExist, ValueError): # Catch invalid UUIDs too
             logger.warning(f"Message with ID '{message_id}' not found or invalid UUID in get_message.")
             return None

    @database_sync_to_async
    def save_message(self, user, room, content='', file=None, reply_to=None):
        """ Creates and saves a new message """
        logger.debug(f"Saving message for user {user.id} in room {room.id}. ReplyTo: {reply_to.id if reply_to else None}")
        # TODO: Add SearchVector update logic here if using PostgreSQL FTS
        msg = Message.objects.create(
            user=user, room=room, content=content, file=file, reply_to=reply_to
        )
        logger.info(f"Message {msg.id} created.")
        return msg

    @database_sync_to_async
    def update_message_content(self, message, new_content):
        """ Updates the content and edited_at timestamp of a message """
        logger.debug(f"Updating content for message {message.id}")
        message.content = new_content
        message.edited_at = now()
        # TODO: Update SearchVector if needed
        message.save(update_fields=['content', 'edited_at'])
        logger.info(f"Message {message.id} content updated.")
        return message

    @database_sync_to_async
    def mark_message_deleted(self, message):
        """ Marks a message as deleted (soft delete) """
        logger.debug(f"Marking message {message.id} as deleted")
        message.is_deleted = True
        message.content = "" # Clear content
        if message.file: # Check if file exists before deleting
            try:
                 message.file.delete(save=False) # Delete file from storage
                 message.file = None # Clear file field
            except Exception as e:
                 logger.error(f"Could not delete file for deleted message {message.id}: {e}")
        # TODO: Update SearchVector if needed
        message.save(update_fields=['is_deleted', 'content', 'file'])
        # Optionally delete associated reactions?
        # Reaction.objects.filter(message=message).delete()
        logger.info(f"Message {message.id} marked as deleted.")
        return message

    @database_sync_to_async
    def add_or_update_reaction(self, message, user, emoji):
        """ Adds or removes a reaction from a message for a user (toggle). """
        reaction, created = Reaction.objects.get_or_create(
            message=message, user=user, emoji=emoji,
            defaults={'emoji': emoji} # Ensure emoji is set on create
        )
        if not created:
            logger.debug(f"Removing reaction '{emoji}' by user {user.id} from message {message.id}")
            reaction.delete()
            return None, False # Removed
        logger.debug(f"Added reaction '{emoji}' by user {user.id} to message {message.id}")
        return reaction, True # Added

    @database_sync_to_async
    def get_reactions_summary(self, message):
        """ Gets a summary of reactions (emoji -> {count, users}) for a message. """
        # Efficiently fetch counts and usernames grouped by emoji
        reactions_data = Reaction.objects.filter(message=message) \
                                     .values('emoji', 'user__username') \
                                     .order_by('emoji') # Order for consistent grouping
        summary = {}
        for r in reactions_data:
            emoji = r['emoji']
            username = r['user__username']
            if emoji not in summary:
                summary[emoji] = {'count': 0, 'users': []}
            summary[emoji]['count'] += 1
            summary[emoji]['users'].append(username) # Store usernames
        # logger.debug(f"Generated reactions summary for message {message.id}: {summary}")
        return summary

    @database_sync_to_async
    def update_read_status(self, user, room, message):
         """ Updates the last read message for a user in a room. """
         logger.debug(f"Updating read status for user {user.id} in room {room.id} to message {message.id}")
         status, created = MessageReadStatus.objects.update_or_create(
            user=user, room=room,
            defaults={'last_read_message': message}
         )
         logger.debug(f"Read status {'created' if created else 'updated'} for user {user.id}, room {room.id}.")

    @database_sync_to_async
    def update_read_status_to_latest(self, user, room):
        """ Updates the last read message to the latest message in the room. """
        latest_message = Message.objects.filter(room=room, is_deleted=False).order_by('-date_added').first()
        if latest_message:
             status, created = MessageReadStatus.objects.update_or_create(
                 user=user, room=room,
                 defaults={'last_read_message': latest_message}
             )
             logger.info(f"Read status {'created' if created else 'updated'} to latest message {latest_message.id} for user {user.id}, room {room.id}.")
        else:
             logger.debug(f"No messages in room {room.id}, cannot update read status to latest for user {user.id}")

    @database_sync_to_async
    def get_older_messages(self, room, limit, before_message=None):
        """ Fetches older messages before a specific message. """
        queryset = Message.objects.filter(room=room, is_deleted=False)
        if before_message:
            queryset = queryset.filter(date_added__lt=before_message.date_added)
        # Fetch and reverse to maintain chronological order within the batch
        older_messages = list(
            queryset.select_related('user', 'reply_to__user')
                    .prefetch_related('reactions__user') # Prefetch reactions for older messages too
                    .order_by('-date_added')[:limit]
        )[::-1]
        logger.debug(f"Fetched {len(older_messages)} older messages for room {room.slug} before {before_message.id if before_message else 'start'}")
        return older_messages

    @database_sync_to_async
    def get_online_user_data(self, user_ids):
         """ Fetches user data (id, username, avatar) for a list of integer IDs. """
         if not user_ids: return []
         # Ensure we only query with actual integers if somehow non-integers get in
         int_user_ids = [uid for uid in user_ids if isinstance(uid, int)]
         if not int_user_ids: return []

         UserModel = get_user_model() # Get the User model class here
         users = UserModel.objects.filter(id__in=int_user_ids, is_active=True).values('id', 'username', 'image')

         user_data_list = []
         media_url = getattr(settings, 'MEDIA_URL', '/media/')
         for user in users:
              # Construct avatar URL carefully
              avatar_url = f"{media_url}{user['image']}" if user.get('image') else None
              user_data_list.append({'id': user['id'],'username': user['username'],'avatar_url': avatar_url})
         return user_data_list


    # --- Serialization ---
    async def serialize_message(self, message, include_reply_to=False, include_file_info=False):
        """ Asynchronously serializes a Message object for WebSocket transmission. """
        @database_sync_to_async
        def get_user_info(user_id):
             """ Safely gets user info, handling DoesNotExist. """
             if not user_id: return {'username': _('[удаленный пользователь]'), 'id': None, 'avatar_url': None}
             UserModel = get_user_model()
             try:
                 user = UserModel.objects.values('id', 'username', 'image').get(pk=user_id) # Fetch only needed fields
                 media_url = getattr(settings, 'MEDIA_URL', '/media/')
                 avatar_url = f"{media_url}{user['image']}" if user.get('image') else None
                 return {'username': user['username'], 'id': user['id'], 'avatar_url': avatar_url}
             except UserModel.DoesNotExist:
                 logger.warning(f"User with ID {user_id} not found during message serialization.")
                 return {'username': _('[удаленный пользователь]'), 'id': user_id, 'avatar_url': None}

        @database_sync_to_async
        def get_reply_info(reply_msg_id):
            """ Safely gets reply info, handling DoesNotExist. """
            if not reply_msg_id: return None
            UserModel = get_user_model() # Define UserModel inside if not available globally
            try:
                reply_msg = Message.objects.select_related('user').only('id', 'user_id', 'user__username', 'content', 'file', 'is_deleted').get(pk=reply_msg_id)
                reply_user = reply_msg.user # Access related user
                reply_user_info = {'username': reply_user.username if reply_user else _('[удаленный пользователь]')}
                return {
                    'id': str(reply_msg.id), 'user': reply_user_info,
                    'content': reply_msg.content[:50] + '...' if not reply_msg.is_deleted else _("[удалено]"),
                    'is_deleted': reply_msg.is_deleted,
                    'has_file': bool(reply_msg.file)
                }
            except Message.DoesNotExist:
                logger.warning(f"Reply message with ID {reply_msg_id} not found during serialization.")
                return {'id': str(reply_msg_id), 'content': _("[не найдено]"), 'is_deleted': True}
            except Exception as e: # Catch other potential errors like User.DoesNotExist if relation broken
                 logger.error(f"Error fetching reply info for message {reply_msg_id}: {e}")
                 return {'id': str(reply_msg_id), 'content': _("[ошибка загрузки ответа]"), 'is_deleted': True}


        @database_sync_to_async
        def get_file_info(msg_pk):
            """ Safely gets file info, handling storage/db errors. """
            try:
                # Fetch the message again just to get the file field reliably
                msg_with_file = Message.objects.only('file').get(pk=msg_pk)
                file_field = msg_with_file.file
                if not file_field or not file_field.name: return None # Check if file exists and has a name

                # Attempt to get properties, handle potential exceptions
                try: size = file_field.size
                except Exception: size = None
                try: url = file_field.url
                except Exception: url = '#' # Fallback URL

                name = file_field.name.split('/')[-1]
                return {'url': url, 'name': name, 'size': size}

            except Message.DoesNotExist:
                logger.warning(f"Message {msg_pk} not found when getting file info.")
                return None
            except Exception as e:
                logger.error(f"Unexpected error getting file info for msg {msg_pk}: {e}")
                return {'url': '#', 'name': _('Файл недоступен'), 'size': None}

        # Use message attributes directly where possible to reduce async calls
        user_id = message.user_id
        reply_to_id = message.reply_to_id if include_reply_to else None
        message_pk = message.pk
        has_file = bool(message.file) # Check if file field has a value

        # Prepare awaitables
        tasks_to_gather = [
            get_user_info(user_id),
            self.get_reactions_summary(message) # Already async
        ]
        if reply_to_id:
            tasks_to_gather.append(get_reply_info(reply_to_id))
        else:
            tasks_to_gather.append(asyncio.sleep(0, result=None)) # Placeholder if no reply

        if include_file_info and has_file:
            tasks_to_gather.append(get_file_info(message_pk))
        else:
             tasks_to_gather.append(asyncio.sleep(0, result=None)) # Placeholder if no file

        # Fetch data concurrently
        user_info, reactions_summary, reply_info, file_info = await asyncio.gather(*tasks_to_gather)

        return {
            'id': str(message.id),
            'user': user_info,
            'room': self.room_slug,
            'content': message.content if not message.is_deleted else _("Сообщение удалено"),
            'timestamp': message.date_added.isoformat(),
            'edited_at': message.edited_at.isoformat() if message.edited_at else None,
            'is_deleted': message.is_deleted,
            'reactions': reactions_summary or {}, # Ensure reactions is always a dict
            'reply_to': reply_info,
            'file': file_info,
        }


    # --- Online Status (In-Memory) ---
    async def get_redis_key(self): # Renamed for clarity, though not using Redis now
         """ Generates a unique key for the room's online user set (in-memory). """
         safe_slug = "".join(c if c.isalnum() or c in ['-', '_'] else '_' for c in self.room_slug)
         return f"inmemory_online_users:{safe_slug}" # Prefix clearly indicates in-memory

    async def add_user_to_online_list(self):
        """ Adds user ID to the in-memory set for the current room. """
        # No await needed for class variable access
        ChatConsumer.online_users_by_room[self.room_slug].add(self.user.id)
        logger.debug(f"User {self.user.id} added to in-memory online list for room {self.room_slug}. Current: {ChatConsumer.online_users_by_room[self.room_slug]}")

    async def remove_user_from_online_list(self):
        """ Removes user ID from the in-memory set for the current room. """
        if self.room_slug in ChatConsumer.online_users_by_room:
            ChatConsumer.online_users_by_room[self.room_slug].discard(self.user.id)
            if not ChatConsumer.online_users_by_room[self.room_slug]:
                # Clean up empty room entries from the dictionary
                try:
                    del ChatConsumer.online_users_by_room[self.room_slug]
                    logger.debug(f"Removed empty online set for room {self.room_slug}")
                except KeyError: pass # Already removed, ignore
            else:
                 logger.debug(f"User {self.user.id} removed from in-memory online list for room {self.room_slug}. Remaining: {ChatConsumer.online_users_by_room.get(self.room_slug)}")

    async def get_online_users_list(self):
        """ Gets user data for users currently marked as online in this room (in-memory). """
        user_ids = ChatConsumer.online_users_by_room.get(self.room_slug, set())
        online_user_details = []
        if user_ids:
             # Fetch user details from DB based on IDs
            online_user_details = await self.get_online_user_data(list(user_ids)) # Pass list of IDs
        logger.debug(f"Fetched online user details for room {self.room_slug}: {len(online_user_details)} users")
        return online_user_details

    async def broadcast_online_users(self):
        """ Broadcasts the current list of online users to the room group. """
        # Note: This list is only accurate for users connected to THIS worker process.
        online_users = await self.get_online_users_list()
        await self.channel_layer.group_send(
            self.room_group_name,
            {'type': 'online_status_broadcast', 'users': online_users }
        )
        logger.debug(f"Broadcasted online users for room {self.room_slug}: {len(online_users)} users")


    # --- Error Handling ---
    async def send_error(self, message, client_msg_id=None):
        """ Sends an error message back to the specific client. """
        payload = {'message': message}
        if client_msg_id: payload['client_id'] = client_msg_id
        logger.warning(f"Sending error to {self.user.username} in room {self.room_slug}: {message}")
        try:
            await self.send(text_data=json.dumps({'type': MSG_TYPE_ERROR, 'payload': payload})) # Use send/dumps
        except Exception as e:
             logger.error(f"Failed to send error message to client {self.channel_name}: {e}")


# --- User Search Consumer ---
class UserSearchConsumer(AsyncWebsocketConsumer):
    """ Handles WebSocket requests for searching users. """
    async def connect(self):
        self.user = self.scope['user']
        if not self.user or not self.user.is_authenticated:
             await self.close()
             return
        await self.accept()
        logger.info(f"UserSearchConsumer connected for user {self.user.username}")

    async def disconnect(self, close_code):
        logger.info(f"UserSearchConsumer disconnected for user {self.user.username}")

    @database_sync_to_async
    def search_users_db(self, query):
         """ Performs the actual database query for users. """
         logger.debug(f"Searching users in DB for query: '{query}'")
         UserModel = get_user_model() # Get User model correctly
         search_filter = (
             Q(username__icontains=query) | Q(first_name__icontains=query) |
             Q(last_name__icontains=query) | Q(email__icontains=query)
         )
         return list(
             UserModel.objects.filter(is_active=True).filter(search_filter)
                 .values('id', 'username', 'first_name', 'last_name', 'image')[:15] # Limit results, include image
         )

    async def receive(self, text_data):
        try:
            data = json.loads(text_data)
            query = data.get('query', '').strip()
            logger.debug(f"User {self.user.username} searching for: '{query}'")

            if len(query) < 1: # Minimum query length
                 users_data = []
            else:
                 users_data = await self.search_users_db(query)
                 # Process results to add display_name and avatar_url
                 media_url = getattr(settings, 'MEDIA_URL', '/media/')
                 for user in users_data:
                      user['display_name'] = f"{user.get('first_name', '')} {user.get('last_name', '')}".strip() or user['username']
                      user['avatar_url'] = f"{media_url}{user['image']}" if user.get('image') else None
                      user.pop('image', None) # Remove original image field name

            logger.debug(f"Found {len(users_data)} users for query '{query}'")
            await self.send(text_data=json.dumps({ # Use send/dumps
                'type': 'user_search_results',
                'payload': {'users': users_data}
            }))
        except json.JSONDecodeError:
             logger.error(f"Invalid JSON received in UserSearchConsumer: {text_data}")
             await self.send(text_data=json.dumps({'error': 'Invalid JSON'})) # Use send/dumps
        except Exception as e:
             logger.exception(f"User search error for user {self.user.username}: {e}")
             await self.send(text_data=json.dumps({'error': 'Search failed'})) # Use send/dumps