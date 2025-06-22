# room/consumers.py
import json
import uuid
import base64
import logging
from channels.generic.websocket import AsyncWebsocketConsumer
from channels.db import database_sync_to_async
from django.conf import settings
from django.core.files.base import ContentFile
from django.contrib.auth import get_user_model
from django.utils.translation import gettext as _
from django.utils import timezone
from django.core.exceptions import ValidationError as DjangoValidationError

from .models import Room, Message, Reaction, MessageReadStatus
from .utils import get_redis_connection, get_room_online_users_redis_key, FileUploadValidator
from .serializers import BasicUserSerializer # Используем сериализаторы для данных

logger = logging.getLogger(__name__)
User = get_user_model()

# --- Константы типов сообщений WebSocket ---
MSG_TYPE_CLIENT_SEND_MESSAGE = 'send_message'
MSG_TYPE_CLIENT_EDIT_MESSAGE = 'edit_message'
MSG_TYPE_CLIENT_DELETE_MESSAGE = 'delete_message'
MSG_TYPE_CLIENT_ADD_REACTION = 'add_reaction'
MSG_TYPE_CLIENT_REMOVE_REACTION = 'remove_reaction'
MSG_TYPE_CLIENT_SEND_FILE = 'send_file'
MSG_TYPE_CLIENT_MARK_READ = 'mark_read'
MSG_TYPE_CLIENT_LOAD_OLDER = 'load_older_messages'
MSG_TYPE_CLIENT_TYPING = 'typing_status'

MSG_TYPE_SERVER_NEW_MESSAGE = 'new_message'
MSG_TYPE_SERVER_UPDATE_MESSAGE = 'update_message'
MSG_TYPE_SERVER_REACTION_UPDATE = 'reaction_update'
MSG_TYPE_SERVER_ONLINE_USERS = 'online_users_update'
MSG_TYPE_SERVER_OLDER_MESSAGES = 'older_messages_list'
MSG_TYPE_SERVER_MESSAGE_ACK = 'message_ack'
MSG_TYPE_SERVER_ERROR = 'error_notification'
MSG_TYPE_SERVER_TYPING_UPDATE = 'typing_update'


class ChatConsumer(AsyncWebsocketConsumer):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.user = None # Будет установлен в connect
        self.room_slug = None
        self.room_id = None # UUID комнаты из БД
        self.room_group_name = None # Для Channels group
        self.redis_conn = None
        self.is_connected_and_authenticated = False

    async def connect(self):
        self.user = self.scope.get('user')
        if not self.user or not self.user.is_authenticated:
            logger.warning("WS: Unauthenticated connection attempt.")
            await self.close(code=4001) # Код "Unauthorized"
            return

        self.room_slug = self.scope['url_route']['kwargs']['room_name']
        self.room_group_name = f'chat_{self.room_slug}'

        self.redis_conn = await get_redis_connection()
        if not self.redis_conn:
            logger.error(f"WS: Failed to get Redis for user {self.user.username} in room {self.room_slug}.")
            await self.close(code=1011) # Internal server error
            return

        room_obj = await self._get_room_from_db(self.room_slug)
        if not room_obj:
            logger.warning(f"WS: Room {self.room_slug} not found or archived. User: {self.user.username}")
            await self.close(code=4004) # Not Found
            return
        self.room_id = room_obj.id

        can_access = await self._check_room_access(room_obj, self.user)
        if not can_access:
            logger.warning(f"WS: Access denied for {self.user.username} to room {self.room_slug}.")
            await self.close(code=4003) # Forbidden
            return

        await self.channel_layer.group_add(self.room_group_name, self.channel_name)
        await self.accept()
        self.is_connected_and_authenticated = True
        logger.info(f"WS: User {self.user.username} (channel: {self.channel_name}) connected to room {self.room_slug}.")

        await self._add_user_to_online_list_redis()
        await self._broadcast_online_users_to_group()
        # Можно добавить отправку начального статуса прочтения этому пользователю, если нужно
        # await self._send_initial_read_status_for_room()

    async def disconnect(self, close_code):
        logger.info(f"WS: User {getattr(self.user, 'username', 'Anon')} (channel: {self.channel_name}) disconnecting from {self.room_slug}, code: {close_code}")
        if self.is_connected_and_authenticated:
            if self.redis_conn:
                await self._remove_user_from_online_list_redis()
                await self._broadcast_online_users_to_group()
            if self.room_group_name and self.channel_name:
                await self.channel_layer.group_discard(self.room_group_name, self.channel_name)
        logger.info(f"WS: User {getattr(self.user, 'username', 'Anon')} disconnected fully from {self.room_slug}.")

    async def receive(self, text_data):
        if not self.is_connected_and_authenticated:
            logger.warning(f"WS: Message received from non-auth/disconnected channel {self.channel_name}")
            return
        try:
            data = json.loads(text_data)
            message_type = data.get('type')
            payload = data.get('payload', {})
            client_msg_id = payload.get('client_id') # Для ACK

            if not message_type:
                raise ValueError(_("Тип сообщения не указан."))

            logger.debug(f"WS RX: Type '{message_type}' from {self.user.username} in {self.room_slug}. Payload: {json.dumps(payload, ensure_ascii=False, indent=2)}")
            handler_name = f'handle_client_{message_type}'
            handler = getattr(self, handler_name, self._handle_unknown_client_type)
            await handler(payload, client_msg_id)

        except json.JSONDecodeError:
            logger.error(f"WS: Invalid JSON from {self.user.username}: {text_data}")
            await self._send_error_to_client(_("Некорректный формат JSON."))
        except ValueError as e:
            logger.warning(f"WS: ValueError processing message from {self.user.username}: {e}")
            await self._send_error_to_client(str(e), client_msg_id)
        except DjangoValidationError as e:
            logger.warning(f"WS: DjangoValidationError from {self.user.username}: {e.messages}")
            await self._send_error_to_client(". ".join(e.messages), client_msg_id) # Сообщения могут быть списком
        except Exception as e:
            logger.exception(f"WS: Unhandled error processing message from {self.user.username} in {self.room_slug}: {e}. Data: {text_data}")
            await self._send_error_to_client(_("Произошла внутренняя ошибка сервера."), client_msg_id)

    # --- Database Access Methods ---
    @database_sync_to_async
    def _get_room_from_db(self, slug: str) -> Room | None:
        try:
            # only('id', 'private', 'is_archived', 'creator_id') - оптимизация, если не нужны все поля
            return Room.objects.get(slug=slug, is_archived=False)
        except Room.DoesNotExist:
            return None

    @database_sync_to_async
    def _check_room_access(self, room: Room, user_instance: User) -> bool:
        if not room.private:
            return True
        return room.creator_id == user_instance.id or room.participants.filter(pk=user_instance.pk).exists()

    @database_sync_to_async
    def _get_user_basic_data(self, user_instance: User) -> dict:
        # `self.scope` может не содержать полноценный `request` объект, как в DRF.
        # `BasicUserSerializer` должен уметь работать без `request` для `avatar_url`
        # или мы должны передавать `None` и обрабатывать это в сериализаторе.
        return BasicUserSerializer(user_instance, context={'request': self.scope.get('request')}).data


    async def _serialize_message_for_broadcast(self, message: Message) -> dict:
        user_data = await self._get_user_basic_data(message.user)
        reply_data = None
        if message.reply_to:
            reply_user_data = await self._get_user_basic_data(message.reply_to.user) if message.reply_to.user else None
            reply_data = {
                'id': str(message.reply_to.id),
                'user': reply_user_data,
                'content_preview': message.reply_to.content[:70] + '...' if message.reply_to.content and len(message.reply_to.content) > 70 else (_("[Файл]") if message.reply_to.file else ""),
                'has_file': bool(message.reply_to.file),
                'is_deleted': message.reply_to.is_deleted,
            }
        file_data = None
        if message.file and hasattr(message.file, 'url'):
            try:
                file_data = {'url': message.file.url, 'name': message.get_filename(), 'size': message.file.size}
            except ValueError:
                logger.warning(f"WS: File for message {message.id} not found at path: {message.file.name}")
                file_data = {'url': '#', 'name': _('Файл недоступен'), 'size': None}
            except Exception as e:
                logger.error(f"WS: Error getting file info for message {message.id}: {e}")
                file_data = {'url': '#', 'name': _('Ошибка файла'), 'size': None}

        reactions_summary = await self._get_reactions_summary_for_message(message, self.user)

        return {
            'id': str(message.id),
            'user': user_data,
            'room_slug': self.room_slug,
            'content': message.content if not message.is_deleted else (_("Сообщение удалено") if message.is_deleted else ""),
            'file': file_data,
            'timestamp': message.date_added.isoformat(),
            'edited_at': message.edited_at.isoformat() if message.edited_at else None,
            'is_deleted': message.is_deleted,
            'reply_to': reply_data,
            'reactions': reactions_summary,
        }

    @database_sync_to_async
    def _get_users_details_from_db(self, user_ids: list[int]) -> list[dict]:
        if not user_ids: return []
        users = User.objects.filter(id__in=user_ids, is_active=True)
        return BasicUserSerializer(users, many=True, context={'request': self.scope.get('request')}).data

    @database_sync_to_async
    def _save_message_to_db(self, content: str, file_obj=None, reply_to_id=None) -> Message | None:
        reply_to_msg = None
        if reply_to_id:
            try:
                reply_to_msg = Message.objects.select_related('user').only('id', 'room_id', 'user__id', 'user__username', 'content', 'file', 'is_deleted').get(id=reply_to_id, room_id=self.room_id, is_deleted=False)
            except Message.DoesNotExist:
                logger.warning(f"WS: Reply message {reply_to_id} not found or deleted.")
                return None
        new_message = Message.objects.create(
            room_id=self.room_id, user=self.user, content=content, file=file_obj, reply_to=reply_to_msg
        )
        return new_message

    @database_sync_to_async
    def _get_message_from_db(self, message_id: uuid.UUID) -> Message | None:
        try:
            return Message.objects.select_related('user', 'reply_to__user').prefetch_related('reactions__user').get(id=message_id, room_id=self.room_id)
        except Message.DoesNotExist:
            return None

    @database_sync_to_async
    def _edit_message_in_db(self, message: Message, new_content: str) -> Message:
        message.content = new_content
        message.edited_at = timezone.now()
        message.save(update_fields=['content', 'edited_at', 'updated_at']) # Добавил updated_at
        return message

    @database_sync_to_async
    def _delete_message_in_db(self, message: Message) -> Message:
        message.is_deleted = True
        message.content = ""
        if message.file:
            try: message.file.delete(save=False)
            except Exception as e_file: logger.error(f"WS: Could not delete file for message {message.id}: {e_file}")
            message.file = None
        message.save(update_fields=['is_deleted', 'content', 'file', 'updated_at']) # Добавил updated_at
        Reaction.objects.filter(message=message).delete() # Удаляем реакции при удалении сообщения
        return message

    @database_sync_to_async
    def _toggle_reaction_on_db(self, message: Message, emoji: str, add: bool, user_instance: User) -> tuple[dict | None, bool]:
        current_reaction = Reaction.objects.filter(message=message, user=user_instance, emoji=emoji).first()
        changed = False
        if add:
            if not current_reaction:
                Reaction.objects.create(message=message, user=user_instance, emoji=emoji)
                changed = True
        else:
            if current_reaction:
                current_reaction.delete()
                changed = True
        if changed:
            return self._get_reactions_summary_for_message(message, user_instance), True
        return None, False

    @database_sync_to_async
    def _get_reactions_summary_for_message(self, message: Message, current_user_instance: User) -> dict:
        summary = {}
        reactions_qs = Reaction.objects.filter(message=message).select_related('user').order_by('created_at')
        serializer_context = {'request': self.scope.get('request')}
        for r in reactions_qs:
            emoji_val = r.emoji
            if emoji_val not in summary:
                summary[emoji_val] = {'count': 0, 'users': [], 'reacted_by_current_user': False}
            summary[emoji_val]['count'] += 1
            summary[emoji_val]['users'].append(BasicUserSerializer(r.user, context=serializer_context).data)
            if current_user_instance == r.user:
                 summary[emoji_val]['reacted_by_current_user'] = True
        return summary

    @database_sync_to_async
    def _update_read_status_in_db(self, last_message_id: uuid.UUID | None):
        last_message_obj = None
        if last_message_id:
            try: last_message_obj = Message.objects.only('id').get(id=last_message_id, room_id=self.room_id)
            except Message.DoesNotExist:
                logger.warning(f"WS: Mark read - Message {last_message_id} not found in room {self.room_slug}.")
                raise ValueError(_("Сообщение для отметки о прочтении не найдено."))
        else:
            last_message_obj = Message.objects.filter(room_id=self.room_id, is_deleted=False).order_by('-date_added').only('id').first()

        if last_message_obj:
            MessageReadStatus.objects.update_or_create(
                user=self.user, room_id=self.room_id,
                defaults={'last_read_message': last_message_obj, 'last_read_timestamp': timezone.now()}
            )
        else: # Если сообщений в комнате нет, все равно обновляем/создаем статус с текущим временем
            MessageReadStatus.objects.update_or_create(
                user=self.user, room_id=self.room_id,
                defaults={'last_read_message': None, 'last_read_timestamp': timezone.now()}
            )

    @database_sync_to_async
    def _get_older_messages_from_db(self, limit: int, before_message_id_str: str | None) -> tuple[list[Message], bool]:
        qs = Message.objects.filter(room_id=self.room_id, is_deleted=False)
        if before_message_id_str:
            try:
                before_message_id = uuid.UUID(before_message_id_str)
                before_message = Message.objects.only('date_added', 'id').get(id=before_message_id, room_id=self.room_id)
                # Ищем сообщения строго раньше по времени ИЛИ с меньшим ID, если время совпадает (для уникальности)
                qs = qs.filter(Q(date_added__lt=before_message.date_added) | Q(date_added=before_message.date_added, id__lt=before_message.id))
            except (Message.DoesNotExist, ValueError): return [], False

        messages = list(
            qs.select_related('user', 'reply_to__user')
              .prefetch_related('reactions__user')
              .order_by('-date_added', '-id')[:limit] # Добавил -id для стабильной пагинации
        )
        has_more = qs.filter(Q(date_added__lt=messages[-1].date_added) | Q(date_added=messages[-1].date_added, id__lt=messages[-1].id)).exists() if messages else False
        return messages[::-1], has_more

    # --- Redis Online Status Methods ---
    async def _add_user_to_online_list_redis(self):
        key = get_room_online_users_redis_key(self.room_slug)
        await self.redis_conn.hset(key, str(self.user.id), timezone.now().isoformat())
        await self.redis_conn.expire(key, 3600 * 24) # Ключ будет жить сутки
        logger.debug(f"WS: User {self.user.id} added/updated in online list for room {self.room_slug}.")

    async def _remove_user_from_online_list_redis(self):
        key = get_room_online_users_redis_key(self.room_slug)
        await self.redis_conn.hdel(key, str(self.user.id))
        logger.debug(f"WS: User {self.user.id} removed from online list for room {self.room_slug}.")

    async def _get_online_user_ids_from_redis(self) -> list[int]:
        key = get_room_online_users_redis_key(self.room_slug)
        online_users_timestamps = await self.redis_conn.hgetall(key)
        # Опциональная очистка "мертвых" сессий, если timestamp не обновляется регулярно heartbeat'ом
        # current_time = timezone.now()
        # valid_user_ids = []
        # for user_id_str, timestamp_str in online_users_timestamps.items():
        #     try:
        #         last_activity = timezone.datetime.fromisoformat(timestamp_str)
        #         if (current_time - last_activity).total_seconds() < getattr(settings, 'CHAT_USER_INACTIVITY_TIMEOUT', 600): # 10 минут
        #             valid_user_ids.append(int(user_id_str))
        #         else:
        #             await self.redis_conn.hdel(key, user_id_str) # Удаляем неактивного
        #             logger.debug(f"WS: Removed inactive user {user_id_str} from room {self.room_slug} online list.")
        #     except (ValueError, TypeError):
        #         await self.redis_conn.hdel(key, user_id_str) # Удаляем с невалидным timestamp
        # return valid_user_ids
        
        # Простая версия без очистки по таймауту неактивности (только по disconnect)
        user_ids_int = []
        for user_id_str in online_users_timestamps.keys():
            try: user_ids_int.append(int(user_id_str))
            except ValueError: pass
        return user_ids_int


    # --- WebSocket Send Helpers ---
    async def _send_to_client(self, message_type: str, payload: dict, client_msg_id: str | None = None):
        data_to_send = {'type': message_type, 'payload': payload}
        if client_msg_id and message_type == MSG_TYPE_SERVER_MESSAGE_ACK:
            data_to_send['client_id'] = client_msg_id
        elif client_msg_id: # Для других ответов на конкретный запрос клиента
             payload['client_id'] = client_msg_id # Помещаем в payload, если это ожидается клиентом
        await self.send(text_data=json.dumps(data_to_send))

    async def _send_error_to_client(self, error_message: str, client_msg_id: str | None = None):
        logger.warning(f"WS: Sending error to client {getattr(self.user, 'username', 'N/A')}: {error_message}")
        await self._send_to_client(MSG_TYPE_SERVER_ERROR, {'message': error_message}, client_msg_id=client_msg_id)

    # --- Broadcast and Group Send Methods ---
    async def _broadcast_message_object_to_group(self, message_type: str, message_obj: Message, client_msg_id_ack: str | None = None):
        serialized_message_data = await self._serialize_message_for_broadcast(message_obj)
        group_payload = {
            'type': 'chat_message_event',
            'event_type': message_type,
            'message_data': serialized_message_data,
            'sender_channel_name': self.channel_name,
        }
        if client_msg_id_ack:
            group_payload['client_id_ack'] = client_msg_id_ack
        await self.channel_layer.group_send(self.room_group_name, group_payload)

    async def chat_message_event(self, event: dict):
        event_type = event['event_type']
        message_data = event['message_data']
        sender_channel_name = event['sender_channel_name']
        client_id_ack = event.get('client_id_ack')

        if self.channel_name == sender_channel_name and client_id_ack:
            await self._send_to_client(
                MSG_TYPE_SERVER_MESSAGE_ACK,
                {'server_id': message_data['id'], 'timestamp': message_data['timestamp']},
                client_msg_id=client_id_ack
            )
        # Отправляем сообщение всем в группе (включая отправителя, если он должен видеть "серверную" версию)
        # Клиент может решить, использовать ли это сообщение для обновления или игнорировать, если уже сделал optimistic update
        await self._send_to_client(event_type, message_data)


    async def _broadcast_reaction_update_to_group(self, message_id: uuid.UUID, reactions_summary: dict):
        await self.channel_layer.group_send(
            self.room_group_name,
            {
                'type': 'reaction_update_event',
                'message_id': str(message_id),
                'reactions': reactions_summary,
                # 'sender_channel_name': self.channel_name, # Можно не отправлять себе, если клиент сам обновляет
            }
        )

    async def reaction_update_event(self, event: dict):
        # if self.channel_name == event.get('sender_channel_name'): return # Опционально
        await self._send_to_client(
            MSG_TYPE_SERVER_REACTION_UPDATE,
            {'message_id': event['message_id'], 'reactions': event['reactions']}
        )

    async def _broadcast_online_users_to_group(self):
        online_user_ids = await self._get_online_user_ids_from_redis()
        user_details_list = await self._get_users_details_from_db(online_user_ids) if online_user_ids else []
        await self.channel_layer.group_send(
            self.room_group_name,
            {'type': 'online_users_event', 'users': user_details_list}
        )

    async def online_users_event(self, event: dict):
        await self._send_to_client(MSG_TYPE_SERVER_ONLINE_USERS, {'users': event['users']})

    async def _broadcast_typing_status_to_group(self, is_typing: bool):
        user_info = await self._get_user_basic_data(self.user)
        await self.channel_layer.group_send(
            self.room_group_name,
            {
                'type': 'typing_status_event',
                'user_info': user_info,
                'is_typing': is_typing,
                'sender_channel_name': self.channel_name,
            }
        )

    async def typing_status_event(self, event: dict):
        if self.channel_name == event['sender_channel_name']: return # Не отправлять себе
        await self._send_to_client(
            MSG_TYPE_SERVER_TYPING_UPDATE,
            {'user': event['user_info'], 'is_typing': event['is_typing']}
        )

    # --- Client Message Handlers ---
    async def _handle_unknown_client_type(self, payload: dict, client_msg_id: str | None):
        logger.warning(f"WS: Received unknown message type from {self.user.username}.")
        await self._send_error_to_client(_("Неизвестный тип сообщения."), client_msg_id)

    async def handle_client_send_message(self, payload: dict, client_msg_id: str | None):
        content = payload.get('content', '').strip()
        reply_to_id_str = payload.get('reply_to_id')
        reply_to_id = uuid.UUID(reply_to_id_str) if reply_to_id_str else None

        if not content: # Файлы отправляются через handle_client_send_file
            raise ValueError(_("Сообщение не может быть пустым."))

        new_message = await self._save_message_to_db(content, reply_to_id=reply_to_id)
        if not new_message:
            raise ValueError(_("Не удалось создать сообщение, возможно, сообщение для ответа не найдено."))
        await self._broadcast_message_object_to_group(MSG_TYPE_SERVER_NEW_MESSAGE, new_message, client_msg_id_ack=client_msg_id)

    async def handle_client_edit_message(self, payload: dict, client_msg_id: str | None):
        message_id_str = payload.get('message_id')
        new_content = payload.get('content', '').strip()

        if not message_id_str: raise ValueError(_("Отсутствует ID сообщения для редактирования."))
        if not new_content: raise ValueError(_("Новый текст сообщения не может быть пустым.")) # Редактирование в пустое?
        try: message_id = uuid.UUID(message_id_str)
        except ValueError: raise ValueError(_("Некорректный ID сообщения."))

        message_obj = await self._get_message_from_db(message_id)
        if not message_obj: raise ValueError(_("Сообщение для редактирования не найдено."))
        if message_obj.user_id != self.user.id and not self.user.is_staff: # Сравниваем ID
            raise ValueError(_("Вы не можете редактировать это сообщение."))
        if message_obj.is_deleted: raise ValueError(_("Нельзя редактировать удаленное сообщение."))

        edited_message = await self._edit_message_in_db(message_obj, new_content)
        await self._broadcast_message_object_to_group(MSG_TYPE_SERVER_UPDATE_MESSAGE, edited_message, client_msg_id_ack=client_msg_id)

    async def handle_client_delete_message(self, payload: dict, client_msg_id: str | None):
        message_id_str = payload.get('message_id')
        if not message_id_str: raise ValueError(_("Отсутствует ID сообщения для удаления."))
        try: message_id = uuid.UUID(message_id_str)
        except ValueError: raise ValueError(_("Некорректный ID сообщения."))

        message_obj = await self._get_message_from_db(message_id)
        if not message_obj: raise ValueError(_("Сообщение для удаления не найдено."))
        if message_obj.user_id != self.user.id and not self.user.is_staff: # Сравниваем ID
            raise ValueError(_("Вы не можете удалить это сообщение."))

        deleted_message = await self._delete_message_in_db(message_obj)
        await self._broadcast_message_object_to_group(MSG_TYPE_SERVER_UPDATE_MESSAGE, deleted_message, client_msg_id_ack=client_msg_id)

    async def handle_client_add_reaction(self, payload: dict, client_msg_id: str | None):
        message_id_str = payload.get('message_id')
        emoji = payload.get('emoji', '').strip()
        if not message_id_str or not emoji: raise ValueError(_("Отсутствует ID сообщения или эмодзи для реакции."))
        try: message_id = uuid.UUID(message_id_str)
        except ValueError: raise ValueError(_("Некорректный ID сообщения."))

        message_obj = await self._get_message_from_db(message_id)
        if not message_obj or message_obj.is_deleted:
            raise ValueError(_("Нельзя отреагировать на это сообщение."))

        reactions_summary, changed = await self._toggle_reaction_on_db(message_obj, emoji, add=True, user_instance=self.user)
        if changed and reactions_summary is not None:
            await self._broadcast_reaction_update_to_group(message_id, reactions_summary)

    async def handle_client_remove_reaction(self, payload: dict, client_msg_id: str | None):
        message_id_str = payload.get('message_id')
        emoji = payload.get('emoji', '').strip()
        if not message_id_str or not emoji: raise ValueError(_("Отсутствует ID сообщения или эмодзи для удаления реакции."))
        try: message_id = uuid.UUID(message_id_str)
        except ValueError: raise ValueError(_("Некорректный ID сообщения."))

        message_obj = await self._get_message_from_db(message_id)
        if not message_obj:
            logger.debug(f"WS: Attempt to remove reaction from non-existent/deleted message {message_id_str}")
            return

        reactions_summary, changed = await self._toggle_reaction_on_db(message_obj, emoji, add=False, user_instance=self.user)
        if changed and reactions_summary is not None:
            await self._broadcast_reaction_update_to_group(message_id, reactions_summary)

    async def handle_client_send_file(self, payload: dict, client_msg_id: str | None):
        file_data_base64 = payload.get('file_data')
        filename = payload.get('filename')
        content = payload.get('content', '') # Опциональный текст к файлу
        reply_to_id_str = payload.get('reply_to_id')
        reply_to_id = uuid.UUID(reply_to_id_str) if reply_to_id_str else None

        if not file_data_base64 or not filename:
            raise ValueError(_("Отсутствуют данные файла или имя файла для отправки."))

        validator = FileUploadValidator(file_data_base64, filename)
        decoded_file_content = validator.validate() # Может выбросить DjangoValidationError

        django_file = ContentFile(decoded_file_content, name=filename)
        new_message = await self._save_message_to_db(content=content, file_obj=django_file, reply_to_id=reply_to_id)
        if not new_message:
            raise ValueError(_("Не удалось сохранить сообщение с файлом."))

        await self._broadcast_message_object_to_group(MSG_TYPE_SERVER_NEW_MESSAGE, new_message, client_msg_id_ack=client_msg_id)

    async def handle_client_mark_read(self, payload: dict, client_msg_id: str | None):
        last_message_id_str = payload.get('last_visible_message_id')
        last_message_id = uuid.UUID(last_message_id_str) if last_message_id_str else None
        try:
            await self._update_read_status_in_db(last_message_id)
            logger.debug(f"WS: User {self.user.username} marked read up to {last_message_id_str or 'latest'} in room {self.room_slug}")
        except ValueError as e: # От _update_read_status_in_db, если сообщение не найдено
            await self._send_error_to_client(str(e), client_msg_id)

    async def handle_client_load_older(self, payload: dict, client_msg_id: str | None):
        before_message_id_str = payload.get('before_message_id')
        limit = int(payload.get('limit', getattr(settings, 'CHAT_MESSAGES_PAGE_SIZE', 50)))

        older_messages, has_more = await self._get_older_messages_from_db(limit, before_message_id_str)
        serialized_messages = []
        for msg_obj in older_messages:
            serialized_messages.append(await self._serialize_message_for_broadcast(msg_obj))

        await self._send_to_client(
            MSG_TYPE_SERVER_OLDER_MESSAGES,
            {'messages': serialized_messages, 'has_more': has_more},
            client_msg_id=client_msg_id
        )

    async def handle_client_typing_status(self, payload: dict, client_msg_id: str | None):
        is_typing = bool(payload.get('is_typing', False))
        await self._broadcast_typing_status_to_group(is_typing)