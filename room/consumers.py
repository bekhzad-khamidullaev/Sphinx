# filename: room/consumers.py
import json
import uuid
from datetime import datetime
from django.conf import settings
from channels.generic.websocket import AsyncWebsocketConsumer
from channels.db import database_sync_to_async
from django.core.files.base import ContentFile
import base64 # For handling potential base64 encoded files via WebSocket
from django.utils.timesince import timesince # For relative timestamps if needed
from django.utils.timezone import now

# Assuming User model is correctly referenced
# from user_profiles.models import User
User = settings.AUTH_USER_MODEL
from .models import Room, Message, Reaction, MessageReadStatus
from .utils import get_redis_connection # Helper function to get redis connection (implement this)

# --- Define Message Types ---
MSG_TYPE_MESSAGE = 'chat_message'
MSG_TYPE_EDIT = 'edit_message'
MSG_TYPE_DELETE = 'delete_message'
MSG_TYPE_REACTION = 'reaction_update'
MSG_TYPE_FILE = 'file_message'
MSG_TYPE_READ_STATUS = 'read_status_update'
MSG_TYPE_REPLY = 'reply_message'
MSG_TYPE_USER_JOIN = 'user_join'
MSG_TYPE_USER_LEAVE = 'user_leave'
MSG_TYPE_ONLINE_USERS = 'online_users'
MSG_TYPE_ERROR = 'error_message'

class ChatConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        self.room_slug = self.scope['url_route']['kwargs']['room_name']
        self.room_group_name = f'chat_{self.room_slug}'
        self.user = self.scope['user']

        if not self.user.is_authenticated:
            await self.close()
            return

        # Fetch room and check permissions
        self.room = await self.get_room(self.room_slug)
        if not self.room:
            await self.close(code=404) # Room not found
            return
        if not await self.check_permissions(self.user, self.room):
             await self.close(code=403) # Forbidden
             return

        # Join room group
        await self.channel_layer.group_add(
            self.room_group_name,
            self.channel_name
        )
        await self.accept()

        # Handle online status
        await self.add_user_to_online_list()
        await self.broadcast_online_users()

        # Send confirmation or initial state if needed
        # await self.send_json({'type': 'connection_established', 'message': 'You are connected.'})

    async def disconnect(self, close_code):
        # Handle online status
        await self.remove_user_from_online_list()
        await self.broadcast_online_users()

        # Leave room group
        await self.channel_layer.group_discard(
            self.room_group_name,
            self.channel_name
        )

    async def receive(self, text_data):
        try:
            data = json.loads(text_data)
            message_type = data.get('type')
            handler = getattr(self, f'handle_{message_type}', self.handle_unknown_type)
            await handler(data)
        except json.JSONDecodeError:
            await self.send_error("Invalid JSON format.")
        except Exception as e:
            # Log the exception e
            print(f"Error processing message: {e}")
            await self.send_error("An error occurred processing your request.")

    # --- Message Handlers ---

    async def handle_chat_message(self, data):
        message_content = data.get('message', '').strip()
        if not message_content:
            return await self.send_error("Message content cannot be empty.")

        message = await self.save_message(
            user=self.user,
            room=self.room,
            content=message_content
        )
        await self.broadcast_message(message, MSG_TYPE_MESSAGE)

    async def handle_reply_message(self, data):
        message_content = data.get('message', '').strip()
        reply_to_id = data.get('reply_to_id')

        if not message_content or not reply_to_id:
            return await self.send_error("Missing content or reply_to_id.")

        try:
            reply_to_uuid = uuid.UUID(reply_to_id)
            reply_to_msg = await self.get_message(reply_to_uuid)
            if not reply_to_msg or reply_to_msg.room != self.room:
                 return await self.send_error("Invalid message to reply to.")
        except (ValueError, Message.DoesNotExist):
            return await self.send_error("Invalid reply_to_id.")

        message = await self.save_message(
            user=self.user,
            room=self.room,
            content=message_content,
            reply_to=reply_to_msg
        )
        await self.broadcast_message(message, MSG_TYPE_REPLY, include_reply_to=True)

    async def handle_edit_message(self, data):
        message_id = data.get('message_id')
        new_content = data.get('content', '').strip()

        if not message_id or not new_content:
            return await self.send_error("Missing message_id or content for edit.")

        try:
            message_uuid = uuid.UUID(message_id)
            message = await self.get_message(message_uuid)
            if not message or message.user != self.user or message.room != self.room:
                return await self.send_error("Permission denied or message not found.")
            if message.is_deleted:
                 return await self.send_error("Cannot edit a deleted message.")

            updated_message = await self.update_message_content(message, new_content)
            await self.broadcast_message(updated_message, MSG_TYPE_EDIT)
        except (ValueError, Message.DoesNotExist):
            await self.send_error("Invalid message_id.")

    async def handle_delete_message(self, data):
        message_id = data.get('message_id')
        if not message_id:
            return await self.send_error("Missing message_id for delete.")

        try:
            message_uuid = uuid.UUID(message_id)
            message = await self.get_message(message_uuid)
            # Allow deleting own messages, or maybe room admins later?
            if not message or message.user != self.user or message.room != self.room:
                return await self.send_error("Permission denied or message not found.")
            if message.is_deleted:
                return # Already deleted

            deleted_message = await self.mark_message_deleted(message)
            await self.broadcast_message(deleted_message, MSG_TYPE_DELETE)
        except (ValueError, Message.DoesNotExist):
            await self.send_error("Invalid message_id.")

    async def handle_add_reaction(self, data):
        message_id = data.get('message_id')
        emoji = data.get('emoji')

        if not message_id or not emoji:
            return await self.send_error("Missing message_id or emoji for reaction.")

        try:
            message_uuid = uuid.UUID(message_id)
            message = await self.get_message(message_uuid)
            if not message or message.room != self.room: # Ensure message is in the current room
                return await self.send_error("Message not found in this room.")
            if message.is_deleted:
                 return await self.send_error("Cannot react to a deleted message.")

            reaction, created = await self.add_or_update_reaction(message, self.user, emoji)
            reactions_summary = await self.get_reactions_summary(message)

            await self.channel_layer.group_send(
                self.room_group_name,
                {
                    'type': 'reaction_broadcast',
                    'message_id': str(message.id),
                    'reactions': reactions_summary
                }
            )
        except (ValueError, Message.DoesNotExist):
            await self.send_error("Invalid message_id.")

    async def handle_mark_read(self, data):
        # This might be triggered when a user focuses the chat window or scrolls
        last_visible_message_id = data.get('last_visible_message_id')
        if not last_visible_message_id:
            # Alternative: Mark all messages up to now as read
            await self.update_read_status_to_latest(self.user, self.room)
            return

        try:
            message_uuid = uuid.UUID(last_visible_message_id)
            message = await self.get_message(message_uuid)
            if message and message.room == self.room:
                await self.update_read_status(self.user, self.room, message)
                # Optionally broadcast read status update if needed by UI
                # await self.broadcast_read_status(self.user, self.room, message)
        except (ValueError, Message.DoesNotExist):
            await self.send_error("Invalid last_visible_message_id.")


    async def handle_send_file(self, data):
        file_data_base64 = data.get('file_data')
        filename = data.get('filename')
        content = data.get('content', '') # Optional caption

        if not file_data_base64 or not filename:
            return await self.send_error("Missing file data or filename.")

        try:
            # Decode base64 file data
            file_content = base64.b64decode(file_data_base64)
            django_file = ContentFile(file_content, name=filename)

            message = await self.save_message(
                user=self.user,
                room=self.room,
                content=content, # Caption
                file=django_file
            )
            # Broadcast file message (might need specific handling on client)
            await self.broadcast_message(message, MSG_TYPE_FILE, include_file_info=True)

        except (TypeError, ValueError) as e:
             # Error decoding base64 or invalid data
             print(f"File decode/save error: {e}")
             await self.send_error("Invalid file data provided.")
        except Exception as e:
            print(f"Error saving file message: {e}")
            await self.send_error("Could not save file message.")


    async def handle_unknown_type(self, data):
        await self.send_error(f"Unknown message type received: {data.get('type')}")

    # --- Broadcasting Methods ---

    async def broadcast_message(self, message, message_type, include_reply_to=False, include_file_info=False):
        """ Broadcasts a message to the room group. """
        message_data = await self.serialize_message(message, include_reply_to, include_file_info)

        await self.channel_layer.group_send(
            self.room_group_name,
            {
                'type': 'chat_broadcast', # Corresponds to chat_broadcast method below
                'message_type': message_type,
                'message': message_data,
            }
        )

    async def chat_broadcast(self, event):
        """ Sends message data received from the group to the WebSocket client. """
        await self.send_json({
            'type': event['message_type'],
            'payload': event['message']
        })

    async def reaction_broadcast(self, event):
        """ Sends reaction updates received from the group. """
        await self.send_json({
            'type': MSG_TYPE_REACTION,
            'payload': {
                'message_id': event['message_id'],
                'reactions': event['reactions']
            }
        })

    async def online_status_broadcast(self, event):
         """ Sends online user list updates. """
         await self.send_json({
            'type': MSG_TYPE_ONLINE_USERS,
            'payload': {'users': event['users']}
         })


    # --- Database Interaction (Async Helpers) ---

    @database_sync_to_async
    def get_room(self, slug):
        try:
            return Room.objects.get(slug=slug)
        except Room.DoesNotExist:
            return None

    @database_sync_to_async
    def check_permissions(self, user, room):
        if not room.private:
            return True
        return room.participants.filter(pk=user.pk).exists()

    @database_sync_to_async
    def get_message(self, message_id):
        try:
            return Message.objects.select_related('user', 'reply_to__user').get(id=message_id)
        except Message.DoesNotExist:
            return None

    @database_sync_to_async
    def save_message(self, user, room, content='', file=None, reply_to=None):
        # TODO: Add SearchVector update logic here if using PostgreSQL FTS
        return Message.objects.create(
            user=user,
            room=room,
            content=content,
            file=file,
            reply_to=reply_to
        )

    @database_sync_to_async
    def update_message_content(self, message, new_content):
        message.content = new_content
        message.edited_at = now()
        # TODO: Update SearchVector if needed
        message.save(update_fields=['content', 'edited_at'])
        return message

    @database_sync_to_async
    def mark_message_deleted(self, message):
        message.is_deleted = True
        message.content = "" # Clear content on delete
        message.file = None # Remove file reference if any (or handle deletion from storage)
        # TODO: Update SearchVector if needed
        message.save(update_fields=['is_deleted', 'content', 'file'])
        # Optionally delete associated reactions
        # Reaction.objects.filter(message=message).delete()
        return message

    # @database_sync_to_async
    def add_or_update_reaction(self, message, user, emoji):
        # Simple toggle: if reaction exists, remove it. Otherwise, add it.
        reaction, created = Reaction.objects.get_or_create(
            message=message,
            user=user,
            emoji=emoji,
            defaults={'emoji': emoji} # Ensure emoji is saved on create
        )
        if not created:
            reaction.delete() # User clicked existing reaction, so remove it
            return None, False # Indicate reaction removed
        return reaction, True # Indicate reaction added

    @database_sync_to_async
    def get_reactions_summary(self, message):
        # ... (implementation as before) ...
        reactions = Reaction.objects.filter(message=message).select_related('user')
        summary = {}
        for r in reactions:
            if r.emoji not in summary:
                summary[r.emoji] = {'count': 0, 'users': []}
            summary[r.emoji]['count'] += 1
            summary[r.emoji]['users'].append(r.user.username)
        return summary

    @database_sync_to_async
    def update_read_status(self, user, room, message):
         MessageReadStatus.objects.update_or_create(
            user=user,
            room=room,
            defaults={'last_read_message': message}
         )

    @database_sync_to_async
    def update_read_status_to_latest(self, user, room):
        latest_message = Message.objects.filter(room=room).order_by('-date_added').first()
        if latest_message:
            self.update_read_status(user, room, latest_message)


    async def serialize_message(self, message, include_reply_to=False, include_file_info=False):
        """ Serializes a Message object into a dictionary for JSON. """
        # Ensure related user is loaded (ideally selected_related earlier)
        try:
            user_info = {'username': message.user.username, 'id': message.user.id}
        except User.DoesNotExist:
             user_info = {'username': '[deleted user]', 'id': None}

        # Fetch reactions summary asynchronously
        reactions_summary = await self.get_reactions_summary(message) # This await requires serialize_message to be async

        data = {
            'id': str(message.id),
            'user': user_info,
            'room': str(message.room.slug),
            'content': message.content if not message.is_deleted else "Message deleted",
            'timestamp': message.date_added.isoformat(),
            'edited_at': message.edited_at.isoformat() if message.edited_at else None,
            'is_deleted': message.is_deleted,
            'reactions': reactions_summary
        }

        # Handle reply_to serialization (potentially sync DB access)
        reply_to_data = None
        if include_reply_to and message.reply_to:
            try:
                reply_user_info = {'username': message.reply_to.user.username}
            except User.DoesNotExist:
                reply_user_info = {'username': '[deleted user]'}

            reply_to_data = {
                'id': str(message.reply_to.id),
                'user': reply_user_info,
                'content': message.reply_to.content[:50] + '...' if not message.reply_to.is_deleted else "Original message deleted",
            }
        data['reply_to'] = reply_to_data

        # Handle file serialization (potentially sync storage/DB access)
        file_data = None
        if include_file_info and message.file:
             try:
                 file_url = message.file.url
                 file_name = message.file.name.split('/')[-1]
                 file_data = {
                    'url': file_url,
                    'name': file_name,
                 }
             except Exception as e:
                 print(f"Error getting file URL/Name for message {message.id}: {e}")
                 file_data = {'url': '#', 'name': 'File unavailable'}
        data['file'] = file_data

        return data
    # --- Online Status (Redis) ---

    async def get_redis_key(self):
        return f"online_users:{self.room_slug}"

    async def add_user_to_online_list(self):
        redis_conn = await get_redis_connection() # Implement get_redis_connection()
        if redis_conn:
            await redis_conn.sadd(await self.get_redis_key(), self.user.username) # Store username or ID
            await redis_conn.close()

    async def remove_user_from_online_list(self):
        redis_conn = await get_redis_connection()
        if redis_conn:
            await redis_conn.srem(await self.get_redis_key(), self.user.username)
            await redis_conn.close()

    async def get_online_users_list(self):
        redis_conn = await get_redis_connection()
        users = []
        if redis_conn:
            user_bytes = await redis_conn.smembers(await self.get_redis_key())
            users = [user.decode('utf-8') for user in user_bytes]
            await redis_conn.close()
        return users

    async def broadcast_online_users(self):
        online_users = await self.get_online_users_list()
        await self.channel_layer.group_send(
            self.room_group_name,
            {
                'type': 'online_status_broadcast', # Corresponds to method below
                'users': online_users
            }
        )

    # --- Error Handling ---
    async def send_error(self, message):
        """ Sends an error message back to the specific client. """
        await self.send_json({
            'type': MSG_TYPE_ERROR,
            'payload': {'message': message}
        })


# --- User Search Consumer (remains largely the same, maybe add pagination/limits) ---
class UserSearchConsumer(AsyncWebsocketConsumer):
    # ... (keep existing implementation, maybe add limits)
    async def connect(self):
        # Consider authentication for this endpoint too
        if not self.scope['user'].is_authenticated:
             await self.close()
             return
        self.room_group_name = f"user_search_{self.scope['user'].id}" # User-specific group? Or just direct send?
        await self.channel_layer.group_add(self.room_group_name, self.channel_name)
        await self.accept()

    async def disconnect(self, close_code):
        await self.channel_layer.group_discard(self.room_group_name, self.channel_name)

    @database_sync_to_async # Ensure DB access is async
    def search_users(self, query):
         # Add limits and potentially more filtering
         return list(User.objects.filter(username__icontains=query).values('id', 'username')[:10]) # Limit results


    async def receive(self, text_data):
        try:
            data = json.loads(text_data)
            query = data.get('query', '')
            if len(query) < 2: # Basic query length check
                 users = []
            else:
                 users = await self.search_users(query)

            # Send results directly back to the requesting user
            await self.send(text_data=json.dumps({
                'type': 'user_search_results',
                'payload': {'users': users}
            }))
        except json.JSONDecodeError:
             await self.send(text_data=json.dumps({'error': 'Invalid JSON'}))
        except Exception as e:
             print(f"User search error: {e}")
             await self.send(text_data=json.dumps({'error': 'Search failed'}))