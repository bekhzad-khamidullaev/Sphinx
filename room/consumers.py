# room/consumers.py
import json
import uuid
import base64
import logging
from channels.generic.websocket import AsyncWebsocketConsumer
from channels.db import database_sync_to_async
from django.conf import settings
from django.core.files.base import ContentFile
from django.utils.translation import gettext as _
from django.db.models import Q


User = settings.AUTH_USER_MODEL
from .models import Room, Message, Reaction, MessageReadStatus
from .utils import get_redis_connection # Assumes utils.py exists

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

class ChatConsumer(AsyncWebsocketConsumer):
    # ... (connect, disconnect, receive methods largely the same as previous version) ...
    # ... (Need robust error handling in receive) ...
    async def connect(self):
        self.room_slug = self.scope['url_route']['kwargs']['room_name']
        self.room_group_name = f'chat_{self.room_slug}'
        self.user = self.scope['user']

        if not self.user or not self.user.is_authenticated:
            await self.close()
            return

        logger.info(f"User {self.user.username} connecting to room {self.room_slug}...")
        self.room = await self.get_room(self.room_slug)
        if not self.room or self.room.is_archived: # Check if archived
            await self.close(code=4004)
            return
        if not await self.check_permissions(self.user, self.room):
             await self.close(code=4003)
             return

        await self.channel_layer.group_add(self.room_group_name, self.channel_name)
        await self.accept()
        logger.info(f"User {self.user.username} ACCEPTED connection to room {self.room_slug}")

        await self.add_user_to_online_list()
        await self.broadcast_online_users()
        # Optionally send recent message history on connect?

    async def disconnect(self, close_code):
        logger.info(f"User {getattr(self.user, 'username', 'anonymous')} disconnecting from room {self.room_slug}, code: {close_code}")
        if hasattr(self, 'user') and self.user.is_authenticated and hasattr(self, 'room_group_name'):
            await self.remove_user_from_online_list()
            await self.broadcast_online_users()
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
        content = payload.get('content', '').strip()
        client_msg_id = payload.get('client_id') # Optional ID from client for ack
        if not content: return await self.send_error("Message content empty.", client_msg_id)

        message = await self.save_message(user=self.user, room=self.room, content=content)
        await self.broadcast_message(message, MSG_TYPE_MESSAGE, client_msg_id=client_msg_id)

    async def handle_reply_message(self, payload):
        content = payload.get('content', '').strip()
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
        new_content = payload.get('content', '').strip()
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

            await self.add_or_update_reaction(message, self.user, emoji)
            reactions_summary = await self.get_reactions_summary(message)
            await self.channel_layer.group_send(self.room_group_name, {
                'type': 'reaction_broadcast', 'message_id': str(message.id), 'reactions': reactions_summary
            })
        except (ValueError, Message.DoesNotExist): await self.send_error("Invalid message ID for reaction.")

    async def handle_mark_read(self, payload):
        last_id = payload.get('last_visible_message_id')
        if not last_id:
            await self.update_read_status_to_latest(self.user, self.room)
        else:
            try:
                message = await self.get_message(uuid.UUID(last_id))
                if message and message.room == self.room:
                    await self.update_read_status(self.user, self.room, message)
                else: await self.send_error("Invalid last visible message ID.")
            except (ValueError, Message.DoesNotExist): await self.send_error("Invalid message ID format for mark read.")

    async def handle_send_file(self, payload):
        # Requires frontend to send base64 data or handle upload separately (better)
        file_data_base64 = payload.get('file_data')
        filename = payload.get('filename')
        content = payload.get('content', '')
        client_msg_id = payload.get('client_id')

        if not file_data_base64 or not filename: return await self.send_error("Missing file data.", client_msg_id)
        # Add file size/type validation

        try:
            file_content = base64.b64decode(file_data_base64)
            django_file = ContentFile(file_content, name=filename)
            message = await self.save_message(user=self.user, room=self.room, content=content, file=django_file)
            await self.broadcast_message(message, MSG_TYPE_FILE, include_file_info=True, client_msg_id=client_msg_id)
        except Exception as e:
            logger.exception(f"Error handling send_file from {self.user.username}: {e}")
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
                # Serialize each message (consider optimizing multiple serializations)
                serialized_messages.append(await self.serialize_message(msg, include_reply_to=True, include_file_info=True))

            await self.send_json({
                'type': MSG_TYPE_OLDER_MESSAGES,
                'payload': {
                    'messages': serialized_messages,
                    'has_more': len(older_messages) == limit # Simple check if more might exist
                }
            })
        except (ValueError, Message.DoesNotExist):
            await self.send_error("Invalid 'before_message_id'.")
        except Exception as e:
            logger.exception(f"Error loading older messages for room {self.room_slug}: {e}")
            await self.send_error("Could not load older messages.")


    async def handle_unknown_type(self, payload):
        # Payload is not used here, but kept for consistency
        await self.send_error(f"Unknown message type received.")

    # --- Broadcasting Methods ---
    # (chat_broadcast, reaction_broadcast, online_status_broadcast as before)
    async def broadcast_message(self, message, message_type, include_reply_to=False, include_file_info=False, client_msg_id=None):
        """ Broadcasts a message, optionally includes client_id for acknowledgement """
        message_data = await self.serialize_message(message, include_reply_to, include_file_info)
        broadcast_data = {
            'type': 'chat_broadcast',
            'message_type': message_type,
            'message': message_data,
            'sender_channel_name': self.channel_name
        }
        # Include client_id if provided, so sender can match confirmation
        if client_msg_id:
            broadcast_data['client_id'] = client_msg_id

        await self.channel_layer.group_send(self.room_group_name, broadcast_data)

    async def chat_broadcast(self, event):
        """ Sends message data received from the group to the WebSocket client. """
        payload = event['message']
        # If client_id was part of the broadcast, send it back
        if 'client_id' in event:
             payload['client_id'] = event['client_id']

        # Don't send back to sender if sender_channel_name matches
        if self.channel_name != event.get('sender_channel_name'):
             await self.send_json({
                 'type': event['message_type'],
                 'payload': payload
             })
        else:
            # Optionally send a confirmation only to the sender
            if 'client_id' in event:
                 await self.send_json({
                     'type': 'message_ack', # Acknowledge sender's message
                     'payload': {
                         'client_id': event['client_id'],
                         'server_id': payload['id'], # Confirm server ID
                         'timestamp': payload['timestamp']
                     }
                 })
            logger.debug(f"Skipping broadcast to self for message {payload.get('id')}")


    async def reaction_broadcast(self, event):
         await self.send_json({
             'type': MSG_TYPE_REACTION,
             'payload': {'message_id': event['message_id'],'reactions': event['reactions']}
         })

    async def online_status_broadcast(self, event):
         await self.send_json({
            'type': MSG_TYPE_ONLINE_USERS,
            'payload': {'users': event['users']} # Send list of usernames/IDs
         })


    # --- Database Interaction ---
    # (@database_sync_to_async methods: get_room, check_permissions, get_message,
    # save_message, update_message_content, mark_message_deleted,
    # add_or_update_reaction, get_reactions_summary, update_read_status,
    # update_read_status_to_latest, get_online_usernames remain mostly the same
    # ensure they handle potential DoesNotExist errors gracefully)
    @database_sync_to_async
    def get_older_messages(self, room, limit, before_message=None):
        """ Fetches older messages before a specific message. """
        queryset = Message.objects.filter(room=room, is_deleted=False)
        if before_message:
            queryset = queryset.filter(date_added__lt=before_message.date_added)

        return list(
            queryset.select_related('user', 'reply_to__user')
                    .prefetch_related('reactions__user')
                    .order_by('-date_added')[:limit]
        )[::-1] # Fetch latest first then reverse to get oldest first in the batch


    async def serialize_message(self, message, include_reply_to=False, include_file_info=False):
       # ... (Serialization logic as before, using async helpers for related data) ...
        @database_sync_to_async
        def get_user_info(user):
            # ... (implementation) ...
             if not user: return {'username': _('[удаленный пользователь]'), 'id': None, 'avatar_url': None} # Add avatar
             return {'username': user.username, 'id': user.id, 'avatar_url': user.image.url if user.image else None}


        @database_sync_to_async
        def get_reply_info(reply_msg):
            # ... (implementation) ...
            if not reply_msg: return None
            try: reply_user = reply_msg.user
            except User.DoesNotExist: reply_user = None
            reply_user_info = {'username': reply_user.username if reply_user else _('[удаленный пользователь]')}
            return {
                'id': str(reply_msg.id), 'user': reply_user_info,
                'content': reply_msg.content[:50] + '...' if not reply_msg.is_deleted else _("[удалено]"),
                'is_deleted': reply_msg.is_deleted,
                'has_file': bool(reply_msg.file)
            }

        @database_sync_to_async
        def get_file_info(file_field):
             if not file_field: return None
             try: return {'url': file_field.url, 'name': file_field.name.split('/')[-1], 'size': file_field.size} # Add size
             except Exception as e: logger.error(f"Error getting file info: {e}"); return {'url': '#', 'name': _('Файл недоступен'), 'size': 0}

        # Fetch concurrently
        user_info_task = get_user_info(message.user)
        reactions_summary_task = self.get_reactions_summary(message)
        reply_info_task = get_reply_info(message.reply_to) if include_reply_to else None
        file_info_task = get_file_info(message.file) if include_file_info else None

        user_info, reactions_summary, reply_info, file_info = await asyncio.gather(
            user_info_task, reactions_summary_task, reply_info_task, file_info_task
        )

        return {
            'id': str(message.id), 'user': user_info, 'room': self.room_slug,
            'content': message.content if not message.is_deleted else _("Сообщение удалено"),
            'timestamp': message.date_added.isoformat(),
            'edited_at': message.edited_at.isoformat() if message.edited_at else None,
            'is_deleted': message.is_deleted, 'reactions': reactions_summary,
            'reply_to': reply_info, 'file': file_info,
        }

    # --- Online Status (Redis) ---
    # (get_redis_key, add_user_to_online_list, remove_user_from_online_list,
    #  get_online_users_list, broadcast_online_users as before, using user IDs)
    async def get_redis_key(self): # ... implementation ...
         safe_slug = "".join(c if c.isalnum() or c in ['-', '_'] else '_' for c in self.room_slug)
         return f"online_users:{safe_slug}"

    async def add_user_to_online_list(self): # ... implementation ...
        redis_conn = await get_redis_connection()
        if redis_conn:
            try: await redis_conn.sadd(await self.get_redis_key(), str(self.user.id))
            except Exception as e: logger.error(f"Redis SADD error: {e}")
            finally: await redis_conn.close()

    async def remove_user_from_online_list(self): # ... implementation ...
        redis_conn = await get_redis_connection()
        if redis_conn:
            try: await redis_conn.srem(await self.get_redis_key(), str(self.user.id))
            except Exception as e: logger.error(f"Redis SREM error: {e}")
            finally: await redis_conn.close()

    @database_sync_to_async
    def get_online_user_data(self, user_ids):
         # Fetch minimal data needed for display
         int_user_ids = [int(uid) for uid in user_ids if uid.isdigit()]
         users = User.objects.filter(id__in=int_user_ids).values('id', 'username', 'image') # Add image
         # Convert image field to URL
         for user in users:
             user['avatar_url'] = settings.MEDIA_URL + user['image'] if user.get('image') else None # Adjust static/media path if needed
             user.pop('image', None) # Remove original image field name
         return list(users)

    async def get_online_users_list(self):
        redis_conn = await get_redis_connection()
        user_ids = []
        if redis_conn:
            try:
                user_id_bytes = await redis_conn.smembers(await self.get_redis_key())
                user_ids = [uid.decode('utf-8') for uid in user_id_bytes]
            except Exception as e: logger.error(f"Redis SMEMBERS error: {e}")
            finally: await redis_conn.close()
        # Fetch user details from DB based on IDs
        online_user_details = await self.get_online_user_data(user_ids)
        return online_user_details

    async def broadcast_online_users(self): # ... implementation ...
        online_users = await self.get_online_users_list()
        await self.channel_layer.group_send(
            self.room_group_name, {'type': 'online_status_broadcast', 'users': online_users }
        )


    # --- Error Handling ---
    async def send_error(self, message, client_msg_id=None):
        payload = {'message': message}
        if client_msg_id:
            payload['client_id'] = client_msg_id # Help client identify which request failed
        logger.warning(f"Sending error to {self.user.username}: {message}")
        await self.send_json({'type': MSG_TYPE_ERROR, 'payload': payload})

# --- User Search Consumer ---
class UserSearchConsumer(AsyncWebsocketConsumer):
    """ Handles WebSocket requests for searching users. """
    async def connect(self):
        self.user = self.scope['user']
        if not self.user or not self.user.is_authenticated:
             await self.close()
             return
        # No group needed, just send back results directly
        await self.accept()
        logger.info(f"UserSearchConsumer connected for user {self.user.username}")

    async def disconnect(self, close_code):
        logger.info(f"UserSearchConsumer disconnected for user {self.user.username}")
        pass # No group cleanup needed

    @database_sync_to_async
    def search_users_db(self, query):
         """ Performs the actual database query for users. """
         logger.debug(f"Searching users in DB for query: '{query}'")
         # More robust search across multiple fields
         search_filter = (
             Q(username__icontains=query) |
             Q(first_name__icontains=query) |
             Q(last_name__icontains=query) |
             Q(email__icontains=query)
         )
         # Return data needed by frontend (e.g., id, username, maybe display_name)
         # Ensure User model is correctly imported at the top of the file
         return list(
             User.objects.filter(is_active=True).filter(search_filter)
                 .values('id', 'username', 'first_name', 'last_name')[:15] # Limit results
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
                 # Add display_name if User model has it
                 for user in users_data:
                      user['display_name'] = f"{user.get('first_name', '')} {user.get('last_name', '')}".strip() or user['username']

            logger.debug(f"Found {len(users_data)} users for query '{query}'")
            await self.send(text_data=json.dumps({
                'type': 'user_search_results',
                'payload': {'users': users_data}
            }))
        except json.JSONDecodeError:
             logger.error(f"Invalid JSON received in UserSearchConsumer: {text_data}")
             await self.send(text_data=json.dumps({'error': 'Invalid JSON'}))
        except Exception as e:
             logger.exception(f"User search error for user {self.user.username}: {e}")
             await self.send(text_data=json.dumps({'error': 'Search failed'}))
