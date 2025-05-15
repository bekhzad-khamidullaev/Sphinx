# room/consumers.py
import json
import uuid
import base64
import logging
import asyncio
from channels.generic.websocket import AsyncWebsocketConsumer
from channels.db import database_sync_to_async
from django.conf import settings
from django.core.files.base import ContentFile
from django.utils.translation import gettext as _
from django.utils import timezone
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError as DjangoValidationError
from django.conf import settings
from .models import Room, Message, Reaction, MessageReadStatus
from .utils import get_redis_connection, get_room_online_users_redis_key, FileUploadValidator
from .serializers import BasicUserSerializer, MessageSerializer # Используем сериализаторы для данных

logger = logging.getLogger(__name__)
# User = get_user_model()

User = settings.AUTH_USER_MODEL

# --- Message Types (Константы для типов сообщений WebSocket) ---
# Клиент -> Сервер
MSG_TYPE_CLIENT_SEND_MESSAGE = 'send_message'
MSG_TYPE_CLIENT_EDIT_MESSAGE = 'edit_message'
MSG_TYPE_CLIENT_DELETE_MESSAGE = 'delete_message'
MSG_TYPE_CLIENT_ADD_REACTION = 'add_reaction'
MSG_TYPE_CLIENT_REMOVE_REACTION = 'remove_reaction' # Явное удаление реакции
MSG_TYPE_CLIENT_SEND_FILE = 'send_file'
MSG_TYPE_CLIENT_MARK_READ = 'mark_read'
MSG_TYPE_CLIENT_LOAD_OLDER = 'load_older_messages'
MSG_TYPE_CLIENT_TYPING = 'typing_status' # Пользователь печатает

# Сервер -> Клиент
MSG_TYPE_SERVER_NEW_MESSAGE = 'new_message'
MSG_TYPE_SERVER_UPDATE_MESSAGE = 'update_message' # Для редактирования и удаления (с флагом is_deleted)
MSG_TYPE_SERVER_REACTION_UPDATE = 'reaction_update'
MSG_TYPE_SERVER_ONLINE_USERS = 'online_users_update'
MSG_TYPE_SERVER_OLDER_MESSAGES = 'older_messages_list'
MSG_TYPE_SERVER_MESSAGE_ACK = 'message_ack' # Подтверждение получения сообщения сервером
MSG_TYPE_SERVER_ERROR = 'error_notification'
MSG_TYPE_SERVER_TYPING_UPDATE = 'typing_update' # Рассылка статуса "печатает"

# --- Consumer ---
class ChatConsumer(AsyncWebsocketConsumer):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.user = None
        self.room_slug = None
        self.room_id = None
        self.room_group_name = None
        self.redis_conn = None
        self.is_connected_and_authenticated = False

    async def connect(self):
        self.user = self.scope.get('user')
        if not self.user or not self.user.is_authenticated:
            logger.warning("Unauthenticated user connection attempt.")
            await self.close(code=4001) # Код для неавторизованного доступа
            return

        self.room_slug = self.scope['url_route']['kwargs']['room_name']
        self.room_group_name = f'chat_{self.room_slug}' # Имя группы для Channels

        self.redis_conn = await get_redis_connection()
        if not self.redis_conn:
            logger.error(f"Failed to get Redis connection for user {self.user.username} in room {self.room_slug}.")
            await self.close(code=1011) # Внутренняя ошибка сервера
            return

        room_obj = await self._get_room_from_db(self.room_slug)
        if not room_obj:
            logger.warning(f"Room {self.room_slug} not found or archived. User: {self.user.username}")
            await self.close(code=4004) # Код для "не найдено"
            return
        self.room_id = room_obj.id # Сохраняем ID комнаты для удобства

        can_access = await self._check_room_access(room_obj, self.user)
        if not can_access:
            logger.warning(f"Access denied for user {self.user.username} to room {self.room_slug}.")
            await self.close(code=4003) # Код для "запрещено"
            return

        await self.channel_layer.group_add(self.room_group_name, self.channel_name)
        await self.accept()
        self.is_connected_and_authenticated = True
        logger.info(f"User {self.user.username} (channel: {self.channel_name}) connected to room {self.room_slug}.")

        await self._add_user_to_online_list_redis()
        await self._broadcast_online_users_to_group()
        # Отправить текущему пользователю полный список онлайн пользователей при подключении
        # await self._send_current_online_users_to_client(self.channel_name)


    async def disconnect(self, close_code):
        logger.info(f"User {getattr(self.user, 'username', 'Anonymous')} (channel: {self.channel_name}) disconnecting from room {self.room_slug}, code: {close_code}")
        if self.is_connected_and_authenticated:
            if self.redis_conn:
                await self._remove_user_from_online_list_redis()
                await self._broadcast_online_users_to_group()
            if self.room_group_name and self.channel_name:
                await self.channel_layer.group_discard(self.room_group_name, self.channel_name)
        # Пул соединений Redis сам управляет закрытием соединений
        logger.info(f"User {getattr(self.user, 'username', 'Anonymous')} disconnected fully from {self.room_slug}.")


    async def receive(self, text_data):
        if not self.is_connected_and_authenticated:
            logger.warning(f"Message received from non-authenticated/disconnected channel {self.channel_name}")
            return

        try:
            data = json.loads(text_data)
            message_type = data.get('type')
            payload = data.get('payload', {})
            client_msg_id = payload.get('client_id') # Для ACK

            if not message_type:
                raise ValueError("Message type not provided in incoming WebSocket data.")

            logger.debug(f"Received type '{message_type}' from {self.user.username} in {self.room_slug}. Payload: {payload}")

            handler_name = f'handle_client_{message_type}'
            handler = getattr(self, handler_name, self._handle_unknown_client_type)
            await handler(payload, client_msg_id)

        except json.JSONDecodeError:
            logger.error(f"Invalid JSON from {self.user.username}: {text_data}")
            await self._send_error_to_client("Invalid JSON format.")
        except ValueError as e: # Для наших кастомных ошибок
            logger.warning(f"ValueError processing message from {self.user.username}: {e}")
            await self._send_error_to_client(str(e), client_msg_id)
        except DjangoValidationError as e: # Для ошибок валидации Django (например, из FileUploadValidator)
            logger.warning(f"DjangoValidationError from {self.user.username}: {e.messages}")
            await self._send_error_to_client(". ".join(e.messages), client_msg_id)
        except Exception as e:
            logger.exception(f"Unhandled error processing message from {self.user.username} in {self.room_slug}: {e}. Data: {text_data}")
            await self._send_error_to_client(_("Произошла внутренняя ошибка сервера."), client_msg_id)

    # --- Database Access Methods (Async Wrappers) ---
    @database_sync_to_async
    def _get_room_from_db(self, slug: str):
        try:
            return Room.objects.select_related(None).only('id', 'private', 'is_archived').get(slug=slug, is_archived=False)
        except Room.DoesNotExist:
            return None

    @database_sync_to_async
    def _check_room_access(self, room: Room, user: User) -> bool:
        if not room.private:
            return True
        return room.participants.filter(pk=user.pk).exists()

    @database_sync_to_async
    def _save_message_to_db(self, content: str, file_obj=None, reply_to_id=None) -> Message | None:
        reply_to_msg = None
        if reply_to_id:
            try:
                reply_to_msg = Message.objects.only('id', 'room_id').get(id=reply_to_id, room_id=self.room_id, is_deleted=False)
            except Message.DoesNotExist:
                logger.warning(f"Reply message {reply_to_id} not found or deleted.")
                return None # Или бросить исключение, которое обработается в receive

        new_message = Message.objects.create(
            room_id=self.room_id,
            user=self.user,
            content=content,
            file=file_obj,
            reply_to=reply_to_msg
        )
        # Room.last_activity_at обновляется через сигнал/save() модели Message
        return new_message

    @database_sync_to_async
    def _get_message_from_db(self, message_id: uuid.UUID) -> Message | None:
        try:
            # Предзагружаем связанные объекты для сериализации
            return Message.objects.select_related('user', 'reply_to__user').prefetch_related('reactions__user').get(id=message_id, room_id=self.room_id)
        except Message.DoesNotExist:
            return None

    @database_sync_to_async
    def _edit_message_in_db(self, message: Message, new_content: str) -> Message:
        message.content = new_content
        message.edited_at = timezone.now()
        message.save(update_fields=['content', 'edited_at'])
        return message

    @database_sync_to_async
    def _delete_message_in_db(self, message: Message) -> Message:
        message.is_deleted = True
        message.content = "" # Очищаем контент
        if message.file:
            try:
                message.file.delete(save=False) # Удаляем файл из хранилища
            except Exception as e_file:
                logger.error(f"Could not delete file for deleted message {message.id}: {e_file}")
            message.file = None # Очищаем поле файла
        message.save(update_fields=['is_deleted', 'content', 'file'])
        # Можно также удалить связанные реакции
        # Reaction.objects.filter(message=message).delete()
        return message

    @database_sync_to_async
    def _toggle_reaction_on_db(self, message: Message, emoji: str, add: bool) -> tuple[dict | None, bool]:
        """
        Добавляет или удаляет реакцию.
        Возвращает словарь с обновленными реакциями для сообщения и флаг, было ли изменение.
        """
        current_reaction = Reaction.objects.filter(message=message, user=self.user, emoji=emoji).first()
        changed = False
        if add:
            if not current_reaction:
                Reaction.objects.create(message=message, user=self.user, emoji=emoji)
                changed = True
        else: # remove
            if current_reaction:
                current_reaction.delete()
                changed = True

        if changed:
            return self._get_reactions_summary_for_message(message), True
        return None, False


    @database_sync_to_async
    def _get_reactions_summary_for_message(self, message: Message) -> dict:
        # Этот метод вызывается как часть _toggle_reaction_on_db
        # или для сериализации сообщения
        summary = {}
        reactions_qs = Reaction.objects.filter(message=message).select_related('user').order_by('created_at')
        for r in reactions_qs:
            emoji_val = r.emoji
            if emoji_val not in summary:
                summary[emoji_val] = {'count': 0, 'users': [], 'reacted_by_current_user': False}
            summary[emoji_val]['count'] += 1
            summary[emoji_val]['users'].append(r.user.username) # Или BasicUserSerializer(r.user).data для большей инфо
            if self.user == r.user: # Проверка для текущего пользователя консьюмера
                 summary[emoji_val]['reacted_by_current_user'] = True
        return summary

    @database_sync_to_async
    def _update_read_status_in_db(self, last_message_id: uuid.UUID | None):
        last_message_obj = None
        if last_message_id:
            try:
                last_message_obj = Message.objects.only('id').get(id=last_message_id, room_id=self.room_id)
            except Message.DoesNotExist:
                logger.warning(f"Mark read: Message {last_message_id} not found in room {self.room_slug}.")
                raise ValueError(_("Сообщение для отметки о прочтении не найдено."))
        else: # Если last_message_id не передан, считаем все сообщения в комнате прочитанными
            last_message_obj = Message.objects.filter(room_id=self.room_id, is_deleted=False).order_by('-date_added').only('id').first()

        if last_message_obj: # Если есть что отмечать
            MessageReadStatus.objects.update_or_create(
                user=self.user, room_id=self.room_id,
                defaults={'last_read_message': last_message_obj, 'last_read_timestamp': timezone.now()}
            )
        else: # Если сообщений в комнате нет, но пользователь зашел - создаем статус без сообщения
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
                # Получаем date_added для сообщения, относительно которого ищем более старые
                before_message_date = Message.objects.only('date_added').get(id=before_message_id, room_id=self.room_id).date_added
                qs = qs.filter(date_added__lt=before_message_date)
            except (Message.DoesNotExist, ValueError):
                # Если ID невалидный или сообщение не найдено, возвращаем пустой список
                return [], False

        # Загружаем сообщения, включая связанные данные для сериализации
        messages = list(
            qs.select_related('user', 'reply_to__user')
              .prefetch_related('reactions__user') # Для подсчета реакций при сериализации
              .order_by('-date_added')[:limit]
        )
        has_more = len(messages) == limit
        return messages[::-1], has_more # Возвращаем в хронологическом порядке


    # --- Redis Online Status Methods ---
    async def _add_user_to_online_list_redis(self):
        key = get_room_online_users_redis_key(self.room_slug)
        # Добавляем ID пользователя и время последнего пинга (можно использовать для удаления "мертвых" сессий)
        await self.redis_conn.hset(key, str(self.user.id), timezone.now().isoformat())
        await self.redis_conn.expire(key, 3600 * 24) # Ключ комнаты будет жить сутки, если в ней есть кто-то
        logger.debug(f"User {self.user.id} added/updated in online list for room {self.room_slug} (Redis HASH).")

    async def _remove_user_from_online_list_redis(self):
        key = get_room_online_users_redis_key(self.room_slug)
        await self.redis_conn.hdel(key, str(self.user.id))
        logger.debug(f"User {self.user.id} removed from online list for room {self.room_slug} (Redis HASH).")

    @database_sync_to_async
    def _get_users_details_from_db(self, user_ids: list[int]) -> list[dict]:
        if not user_ids: return []
        users = User.objects.filter(id__in=user_ids, is_active=True)
        # Используем BasicUserSerializer, который уже есть
        return BasicUserSerializer(users, many=True, context={'request': self.scope.get('request')}).data


    async def _get_online_user_ids_from_redis(self) -> list[int]:
        key = get_room_online_users_redis_key(self.room_slug)
        online_users_timestamps = await self.redis_conn.hgetall(key) # { 'user_id_str': 'timestamp_str', ... }
        
        # Опционально: очистка старых записей, если пользователь давно не пинговал
        # Например, если timestamp > 10 минут назад, удаляем
        # current_time = timezone.now()
        # user_ids_to_keep = []
        # for user_id_str, timestamp_str in online_users_timestamps.items():
        #     try:
        #         last_ping = timezone.datetime.fromisoformat(timestamp_str)
        #         if (current_time - last_ping).total_seconds() < 600: # 10 минут
        #             user_ids_to_keep.append(int(user_id_str))
        #         else:
        #             await self.redis_conn.hdel(key, user_id_str) # Удаляем старую запись
        #     except (ValueError, TypeError): # Невалидный user_id или timestamp
        #         await self.redis_conn.hdel(key, user_id_str)
        # return user_ids_to_keep

        # Простая версия: просто берем все ID из HASH
        user_ids_int = []
        for user_id_str in online_users_timestamps.keys():
            try: user_ids_int.append(int(user_id_str))
            except ValueError: pass # Игнорируем нечисловые ключи, если вдруг появятся
        return user_ids_int


    # --- Serialization ---
    async def _serialize_message_for_broadcast(self, message: Message) -> dict:
        # Сериализация сообщения для отправки клиентам.
        # MessageSerializer требует request в контексте для `reacted_by_current_user`
        # Но для broadcast это не нужно, так как сообщение идет ко всем.
        # Мы можем вручную собрать нужные данные или адаптировать сериализатор.
        # Простой вариант: собрать вручную, используя части из MessageSerializer.

        # Собираем информацию о пользователе
        user_data = await database_sync_to_async(lambda: BasicUserSerializer(message.user).data)()

        # Собираем информацию об ответе (если есть)
        reply_data = None
        if message.reply_to:
            reply_user_data = await database_sync_to_async(lambda: BasicUserSerializer(message.reply_to.user).data)()
            reply_data = {
                'id': str(message.reply_to.id),
                'user': reply_user_data,
                'content_preview': message.reply_to.content[:70] + '...' if message.reply_to.content and len(message.reply_to.content) > 70 else message.reply_to.content,
                'has_file': bool(message.reply_to.file),
                'is_deleted': message.reply_to.is_deleted,
            }

        # Собираем информацию о файле (если есть)
        file_data = None
        if message.file:
            try:
                file_data = {'url': message.file.url, 'name': message.get_filename(), 'size': message.file.size}
            except Exception: # Если файл недоступен
                file_data = {'url': '#', 'name': _('Файл недоступен'), 'size': None}

        # Собираем реакции
        reactions_summary = await self._get_reactions_summary_for_message(message)

        return {
            'id': str(message.id),
            'user': user_data,
            'room_slug': self.room_slug, # или message.room.slug, если объект комнаты есть
            'content': message.content if not message.is_deleted else _("Сообщение удалено"),
            'file': file_data,
            'timestamp': message.date_added.isoformat(), # Используем date_added, так как это время создания
            'edited_at': message.edited_at.isoformat() if message.edited_at else None,
            'is_deleted': message.is_deleted,
            'reply_to': reply_data,
            'reactions': reactions_summary,
        }


    # --- WebSocket Send Helpers ---
    async def _send_to_client(self, message_type: str, payload: dict, client_msg_id: str | None = None):
        """ Отправляет данные конкретному этому клиенту (self.send). """
        data_to_send = {'type': message_type, 'payload': payload}
        if client_msg_id and message_type == MSG_TYPE_SERVER_MESSAGE_ACK:
            # У ACK client_id должен быть на верхнем уровне, а не в payload
            data_to_send['client_id'] = client_msg_id
            # Для ACK payload содержит server_id и timestamp
        elif client_msg_id: # Для других сообщений, если client_id нужен в payload
             payload['client_id'] = client_msg_id

        await self.send(text_data=json.dumps(data_to_send))

    async def _send_error_to_client(self, error_message: str, client_msg_id: str | None = None):
        logger.warning(f"Sending error to client {self.user.username}: {error_message}")
        await self._send_to_client(MSG_TYPE_SERVER_ERROR, {'message': error_message}, client_msg_id=client_msg_id)

    # --- Broadcast and Group Send Methods ---
    async def _broadcast_message_object_to_group(self, message_type: str, message_obj: Message, client_msg_id_ack: str | None = None):
        """ Сериализует объект сообщения и рассылает его группе. """
        serialized_message_data = await self._serialize_message_for_broadcast(message_obj)
        
        group_payload = {
            'type': 'chat_message_event', # Имя метода-обработчика в консьюмере для group_send
            'event_type': message_type,    # Фактический тип для клиента (new_message, update_message)
            'message_data': serialized_message_data,
            'sender_channel_name': self.channel_name,
        }
        if client_msg_id_ack: # Для отправки ACK обратно оригинальному отправителю
            group_payload['client_id_ack'] = client_msg_id_ack
        
        await self.channel_layer.group_send(self.room_group_name, group_payload)

    # Этот метод будет вызван Channels при получении сообщения от группы
    async def chat_message_event(self, event: dict):
        """ Обрабатывает события сообщений, полученные от группы Channels. """
        event_type = event['event_type']
        message_data = event['message_data']
        sender_channel_name = event['sender_channel_name']
        client_id_ack = event.get('client_id_ack')

        # Если это сообщение от текущего пользователя и есть client_id_ack, отправляем ACK
        if self.channel_name == sender_channel_name and client_id_ack:
            await self._send_to_client(
                MSG_TYPE_SERVER_MESSAGE_ACK,
                {'server_id': message_data['id'], 'timestamp': message_data['timestamp']},
                client_msg_id=client_id_ack # ACK должен содержать client_id верхнего уровня
            )
        # Отправляем основное сообщение всем клиентам в группе (включая отправителя, если он должен видеть серверную версию)
        # Можно добавить условие `if self.channel_name != sender_channel_name or client_id_ack:`
        # если не хотим дублировать сообщение отправителю, если он уже сделал optimistic update.
        # Но для простоты и консистентности (клиент всегда получает серверную версию) - отправляем всем.
        await self._send_to_client(event_type, message_data)


    async def _broadcast_reaction_update_to_group(self, message_id: uuid.UUID, reactions_summary: dict):
        await self.channel_layer.group_send(
            self.room_group_name,
            {
                'type': 'reaction_update_event', # Метод-обработчик в консьюмере
                'message_id': str(message_id),
                'reactions': reactions_summary,
                'sender_channel_name': self.channel_name, # Чтобы не отправлять себе, если не нужно
            }
        )
    # Обработчик для reaction_update_event
    async def reaction_update_event(self, event: dict):
        # if self.channel_name == event['sender_channel_name']: # Не отправлять себе
        # return
        await self._send_to_client(
            MSG_TYPE_SERVER_REACTION_UPDATE,
            {'message_id': event['message_id'], 'reactions': event['reactions']}
        )


    async def _broadcast_online_users_to_group(self):
        online_user_ids = await self._get_online_user_ids_from_redis()
        if not online_user_ids: # Если список пуст, все равно отправляем пустой список
            user_details_list = []
        else:
            user_details_list = await self._get_users_details_from_db(online_user_ids)

        await self.channel_layer.group_send(
            self.room_group_name,
            {
                'type': 'online_users_event', # Метод-обработчик в консьюмере
                'users': user_details_list
            }
        )
    # Обработчик для online_users_event
    async def online_users_event(self, event: dict):
        await self._send_to_client(MSG_TYPE_SERVER_ONLINE_USERS, {'users': event['users']})

    async def _broadcast_typing_status_to_group(self, is_typing: bool):
        user_info = await database_sync_to_async(lambda: BasicUserSerializer(self.user).data)()
        await self.channel_layer.group_send(
            self.room_group_name,
            {
                'type': 'typing_status_event',
                'user_info': user_info,
                'is_typing': is_typing,
                'sender_channel_name': self.channel_name,
            }
        )
    # Обработчик для typing_status_event
    async def typing_status_event(self, event: dict):
        if self.channel_name == event['sender_channel_name']: # Не отправлять себе
            return
        await self._send_to_client(
            MSG_TYPE_SERVER_TYPING_UPDATE,
            {'user': event['user_info'], 'is_typing': event['is_typing']}
        )


    # --- Client Message Handlers (handle_client_*) ---
    async def _handle_unknown_client_type(self, payload: dict, client_msg_id: str | None):
        logger.warning(f"Received unknown message type from {self.user.username}.")
        await self._send_error_to_client(_("Неизвестный тип сообщения."), client_msg_id)

    async def handle_client_send_message(self, payload: dict, client_msg_id: str | None):
        content = payload.get('content', '').strip()
        reply_to_id_str = payload.get('reply_to_id')
        reply_to_id = uuid.UUID(reply_to_id_str) if reply_to_id_str else None

        if not content:
            raise ValueError(_("Сообщение не может быть пустым.")) # Это будет поймано в receive

        new_message = await self._save_message_to_db(content, reply_to_id=reply_to_id)
        if not new_message: # Например, если reply_to_id невалидный
             raise ValueError(_("Не удалось создать сообщение, возможно, сообщение для ответа не найдено."))

        await self._broadcast_message_object_to_group(MSG_TYPE_SERVER_NEW_MESSAGE, new_message, client_msg_id_ack=client_msg_id)

    async def handle_client_edit_message(self, payload: dict, client_msg_id: str | None):
        message_id_str = payload.get('message_id')
        new_content = payload.get('content', '').strip()

        if not message_id_str or not new_content:
            raise ValueError(_("Отсутствует ID сообщения или новый текст для редактирования."))
        try: message_id = uuid.UUID(message_id_str)
        except ValueError: raise ValueError(_("Некорректный ID сообщения."))

        message_obj = await self._get_message_from_db(message_id)
        if not message_obj:
            raise ValueError(_("Сообщение для редактирования не найдено."))
        if message_obj.user != self.user and not self.user.is_staff: # Проверка прав
            raise ValueError(_("Вы не можете редактировать это сообщение."))
        if message_obj.is_deleted:
            raise ValueError(_("Нельзя редактировать удаленное сообщение."))

        edited_message = await self._edit_message_in_db(message_obj, new_content)
        await self._broadcast_message_object_to_group(MSG_TYPE_SERVER_UPDATE_MESSAGE, edited_message, client_msg_id_ack=client_msg_id)

    async def handle_client_delete_message(self, payload: dict, client_msg_id: str | None):
        message_id_str = payload.get('message_id')
        if not message_id_str: raise ValueError(_("Отсутствует ID сообщения для удаления."))
        try: message_id = uuid.UUID(message_id_str)
        except ValueError: raise ValueError(_("Некорректный ID сообщения."))

        message_obj = await self._get_message_from_db(message_id)
        if not message_obj:
            raise ValueError(_("Сообщение для удаления не найдено."))
        if message_obj.user != self.user and not self.user.is_staff: # Проверка прав
            raise ValueError(_("Вы не можете удалить это сообщение."))
        # if message_obj.is_deleted: # Можно не проверять, просто повторно "удалит"
        #     raise ValueError(_("Сообщение уже удалено."))

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

        reactions_summary, changed = await self._toggle_reaction_on_db(message_obj, emoji, add=True)
        if changed and reactions_summary is not None:
            await self._broadcast_reaction_update_to_group(message_id, reactions_summary)
        # ACK можно отправить, если клиент его ожидает

    async def handle_client_remove_reaction(self, payload: dict, client_msg_id: str | None):
        message_id_str = payload.get('message_id')
        emoji = payload.get('emoji', '').strip()
        if not message_id_str or not emoji: raise ValueError(_("Отсутствует ID сообщения или эмодзи для удаления реакции."))
        try: message_id = uuid.UUID(message_id_str)
        except ValueError: raise ValueError(_("Некорректный ID сообщения."))

        message_obj = await self._get_message_from_db(message_id)
        # Проверка на существование сообщения не так критична для удаления реакции,
        # но если сообщение удалено, то и реакций на него быть не должно.
        if not message_obj:
             logger.debug(f"Attempt to remove reaction from non-existent/deleted message {message_id_str}")
             return # Тихо завершаем, если сообщения нет

        reactions_summary, changed = await self._toggle_reaction_on_db(message_obj, emoji, add=False)
        if changed and reactions_summary is not None:
            await self._broadcast_reaction_update_to_group(message_id, reactions_summary)

    async def handle_client_send_file(self, payload: dict, client_msg_id: str | None):
        file_data_base64 = payload.get('file_data')
        filename = payload.get('filename')
        content = payload.get('content', '') # Опциональный текст к файлу

        # Валидация файла
        validator = FileUploadValidator(file_data_base64, filename)
        # validate() бросит DjangoValidationError если что-то не так,
        # которое будет поймано в self.receive
        decoded_file_content = validator.validate()

        django_file = ContentFile(decoded_file_content, name=filename)
        new_message = await self._save_message_to_db(content=content, file_obj=django_file)
        if not new_message:
            raise ValueError(_("Не удалось сохранить сообщение с файлом.")) # Например, из-за ошибки БД

        await self._broadcast_message_object_to_group(MSG_TYPE_SERVER_NEW_MESSAGE, new_message, client_msg_id_ack=client_msg_id)


    async def handle_client_mark_read(self, payload: dict, client_msg_id: str | None):
        last_message_id_str = payload.get('last_visible_message_id')
        last_message_id = uuid.UUID(last_message_id_str) if last_message_id_str else None
        try:
            await self._update_read_status_in_db(last_message_id)
            # Можно отправить подтверждение клиенту, если он этого ожидает
            # await self._send_to_client('mark_read_ack', {'status': 'success'}, client_msg_id)
            logger.debug(f"User {self.user.username} marked read up to {last_message_id_str or 'latest'} in room {self.room_slug}")
        except ValueError as e: # От _update_read_status_in_db, если сообщение не найдено
            await self._send_error_to_client(str(e), client_msg_id)


    async def handle_client_load_older(self, payload: dict, client_msg_id: str | None):
        before_message_id_str = payload.get('before_message_id')
        limit = int(payload.get('limit', settings.CHAT_MESSAGES_PAGE_SIZE))

        older_messages, has_more = await self._get_older_messages_from_db(limit, before_message_id_str)

        serialized_messages = []
        for msg_obj in older_messages:
            serialized_messages.append(await self._serialize_message_for_broadcast(msg_obj))

        await self._send_to_client(
            MSG_TYPE_SERVER_OLDER_MESSAGES,
            {'messages': serialized_messages, 'has_more': has_more},
            client_msg_id=client_msg_id # Если клиент ждет ответа на конкретный запрос
        )

    async def handle_client_typing_status(self, payload: dict, client_msg_id: str | None):
        is_typing = bool(payload.get('is_typing', False))
        # Рассылаем всем в группе, кроме себя
        await self._broadcast_typing_status_to_group(is_typing)
        # ACK здесь обычно не нужен