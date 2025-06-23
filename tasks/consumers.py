# tasks/consumers.py
# -*- coding: utf-8 -*-
import json
import logging
from channels.generic.websocket import AsyncWebsocketConsumer
from asgiref.sync import sync_to_async
from django.core.exceptions import ValidationError, ObjectDoesNotExist, PermissionDenied
from django.utils.translation import gettext_lazy as _
from channels.layers import get_channel_layer
from profiles.models import User
from .models import Task # TaskAssignment можно импортировать, если он используется в _check_task_permission или др.


logger = logging.getLogger(__name__)

class TaskConsumer(AsyncWebsocketConsumer):
    DEFAULT_GROUP_NAME_LIST = "tasks_list" # Группа для общего списка задач
    GROUP_NAME_DETAIL_PREFIX = "task_"     # Префикс для группы конкретной задачи

    async def connect(self):
        self.user = self.scope.get('user')
        if not self.user or not self.user.is_authenticated:
            await self.close()
            return

        self.task_id_str = self.scope['url_route']['kwargs'].get('task_id')
        self.subscribed_groups = set()

        # Всегда подписываемся на общий список задач
        await self.channel_layer.group_add(self.DEFAULT_GROUP_NAME_LIST, self.channel_name)
        self.subscribed_groups.add(self.DEFAULT_GROUP_NAME_LIST)
        
        # Если в URL есть task_id, подписываемся на детали этой задачи
        if self.task_id_str:
            try:
                task_id = int(self.task_id_str)
                # Опциональная проверка прав на просмотр перед подпиской на детали
                # if not await self._can_view_task(task_id, self.user): # _can_view_task нужно определить
                #     logger.warning(f"User {self.user.id} denied WS connection to task {task_id} details (no view perm).")
                # else:
                task_group_detail = f"{self.GROUP_NAME_DETAIL_PREFIX}{task_id}"
                await self.channel_layer.group_add(task_group_detail, self.channel_name)
                self.subscribed_groups.add(task_group_detail)
            except ValueError:
                logger.warning(f"TaskConsumer: Invalid task_id format '{self.task_id_str}' in URL.")
                # Можно решить закрыть соединение или просто не подписываться на детальную группу
        
        await self.accept()
        logger.info(f"TaskConsumer connected user {self.user.id} to groups: {list(self.subscribed_groups)}")

    async def disconnect(self, close_code):
        for group_name in self.subscribed_groups:
            await self.channel_layer.group_discard(group_name, self.channel_name)
        logger.info(f"TaskConsumer disconnected user {getattr(self.user, 'id', 'anon')} from groups: {list(self.subscribed_groups)}")

    @sync_to_async
    def _update_task_status_db(self, task_id: int, new_status: str, user_actor: User):
        try:
            task = Task.objects.get(id=task_id)
            if not task.can_change_status(user_actor, new_status):
                raise PermissionDenied(_("У вас нет прав на изменение статуса этой задачи."))
            
            if task.status == new_status: # Избегаем лишних сохранений и сигналов
                return task, False # Возвращаем задачу и флаг "не изменено"

            task.status = new_status
            # Предполагается, что модель Task.save() сама обрабатывает completion_date и другие связанные поля,
            # а также вызывает post_save сигнал, который инициирует рассылку обновлений.
            task.save(update_fields=['status', 'updated_at', 'completion_date']) # Явно указываем поля для оптимизации
            return task, True # Возвращаем задачу и флаг "изменено"
        except ObjectDoesNotExist:
            raise ObjectDoesNotExist(_("Задача с ID {task_id} не найдена.").format(task_id=task_id))
        except ValidationError as e:
            # Передаем словарь ошибок, если есть, или строку
            raise ValidationError(e.message_dict if hasattr(e, 'message_dict') else str(e))

    async def receive(self, text_data):
        if not self.user or not self.user.is_authenticated:
            await self.send_error(_("Требуется аутентификация."))
            return
        try:
            data = json.loads(text_data)
            message_type = data.get('type')

            if message_type == 'update_status':
                task_id = data.get('task_id')
                new_status = data.get('status')
                if task_id is None or new_status is None:
                    await self.send_error(_("Требуются ID задачи и новый статус.")); return
                
                task_instance, changed = await self._update_task_status_db(task_id, new_status, self.user)
                if changed:
                    await self.send(text_data=json.dumps({
                        'type': 'status_update_confirmation', 
                        'task_id': task_instance.id,
                        'new_status': task_instance.status, 
                        'status_display': task_instance.status_display,
                        'message': _("Статус задачи успешно обновлен."), 'success': True
                    }))
                else: # Статус не изменился
                    await self.send(text_data=json.dumps({
                        'type': 'status_update_no_change', 
                        'task_id': task_instance.id,
                        'new_status': task_instance.status, 
                        'status_display': task_instance.status_display,
                        'message': _("Статус задачи не изменился."), 'success': True 
                    }))
            else:
                logger.warning(f"TaskConsumer received unknown message type: {message_type} from user {self.user.id}")
                await self.send_error(_("Неизвестный тип сообщения: {message_type}").format(message_type=message_type))

        except json.JSONDecodeError: await self.send_error(_("Неверный JSON формат."))
        except ObjectDoesNotExist as e: await self.send_error(str(e), event_type='status_update_error')
        except PermissionDenied as e: await self.send_error(str(e), event_type='status_update_error')
        except ValidationError as e: await self.send_error(e.message_dict if hasattr(e, 'message_dict') else str(e), event_type='status_update_error')
        except Exception as e:
            logger.error(f"Error in TaskConsumer receive from user {self.user.id}: {e}", exc_info=True)
            await self.send_error(_("Произошла непредвиденная ошибка на сервере."))

    # Эти методы вызываются из Django (сигналы -> channel_layer.group_send)
    async def list_update(self, event): # Для общего списка задач (группа tasks_list)
        await self.send(text_data=json.dumps(event["message"]))

    async def task_update(self, event): # Для страницы деталей задачи (группа task_<id>)
        await self.send(text_data=json.dumps(event["message"]))
    
    # Если TaskConsumer должен реагировать на обновления проектов
    async def project_update(self, event):
        # Отправляем, если это обновление для project_list и TaskConsumer на него подписан (маловероятно)
        # или если логика требует реакции TaskConsumer на обновление проекта.
        # Обычно ProjectConsumer сам обрабатывает project_update для project_list
        if self.DEFAULT_GROUP_NAME_LIST in self.subscribed_groups: # Проверка, что это для списка
             logger.debug(f"TaskConsumer (list subscriber) received project_update: {event['message']}")
        # await self.send(text_data=json.dumps(event["message"])) # Раскомментировать, если нужно

    async def send_error(self, message, event_type="error_message"):
        await self.send(text_data=json.dumps({'type': event_type, 'message': message, 'success': False}))


class TaskCommentConsumer(AsyncWebsocketConsumer):
    @sync_to_async
    def _can_view_task_for_comments(self, task_id: int, user: User):
        try:
            task = Task.objects.get(pk=task_id)
            return task.can_view(user)
        except Task.DoesNotExist:
            return False
        except Exception as e:
            logger.error(f"Error in _can_view_task_for_comments (task {task_id}, user {user.id}): {e}", exc_info=True)
            return False

    async def connect(self):
        self.user = self.scope.get('user')
        self.task_id_str = self.scope['url_route']['kwargs'].get('task_id')

        if not self.task_id_str or not self.user or not self.user.is_authenticated:
            await self.close(); return
        
        try: self.task_id = int(self.task_id_str)
        except ValueError: logger.warning(f"TaskCommentConsumer: Invalid task_id '{self.task_id_str}'."); await self.close(); return
        
        if not await self._can_view_task_for_comments(self.task_id, self.user):
            logger.warning(f"TaskCommentConsumer: User {self.user.id} rejected for task {self.task_id} comments (no view perm).")
            await self.close(); return

        self.room_group_name = f'task_comments_{self.task_id}'
        await self.channel_layer.group_add(self.room_group_name, self.channel_name)
        await self.accept()
        logger.info(f"TaskCommentConsumer connected user {self.user.username} to {self.room_group_name}")

    async def disconnect(self, close_code):
        if hasattr(self, 'room_group_name'):
            await self.channel_layer.group_discard(self.room_group_name, self.channel_name)

    async def comment_message(self, event): # Тип сообщения от сигнала TaskComment.save
        # Клиент ожидает 'new_comment' с полезной нагрузкой 'comment'
        await self.send(text_data=json.dumps({'type': 'new_comment', 'comment': event['message']}))


# --- Базовый консьюмер для обновлений моделей (Project, Category, SubCategory из tasks) ---
class ModelUpdateConsumerBase(AsyncWebsocketConsumer):
    group_name_prefix = "unknown_tasks_model"
    item_id_kwarg_name_in_url = "item_id" # Общее имя для kwargs ID объекта в URL
                                       # Заменить в наследниках на project_id, category_id и т.д.

    async def connect(self):
        self.user = self.scope.get("user")
        # Можно добавить проверку аутентификации, если каналы не публичные
        # if not self.user or not self.user.is_authenticated:
        #     await self.close()
        #     return

        self.item_id = self.scope['url_route']['kwargs'].get(self.item_id_kwarg_name_in_url)

        if self.item_id: # Подписка на конкретный объект
            self.room_group_name = f"{self.group_name_prefix}_{self.item_id}"
        else: # Подписка на список объектов
            self.room_group_name = f"{self.group_name_prefix}_list"
            
        await self.channel_layer.group_add(self.room_group_name, self.channel_name)
        await self.accept()
        logger.info(f"{self.__class__.__name__} connected user {getattr(self.user, 'id', 'anon')} to {self.room_group_name}")

    async def disconnect(self, close_code):
        if hasattr(self, 'room_group_name'):
            await self.channel_layer.group_discard(self.room_group_name, self.channel_name)

    # Эти методы должны соответствовать 'type' из сообщений, отправляемых сигналами моделей tasks
    async def project_update(self, event):
        await self.send(text_data=json.dumps(event["message"]))

    async def category_update(self, event):
        await self.send(text_data=json.dumps(event["message"]))

    async def subcategory_update(self, event):
        await self.send(text_data=json.dumps(event["message"]))


class ProjectConsumer(ModelUpdateConsumerBase):
    group_name_prefix = "projects"
    item_id_kwarg_name_in_url = "project_id" # Если есть URL типа /ws/project/<project_id>/

class CategoryConsumer(ModelUpdateConsumerBase):
    group_name_prefix = "categories"
    item_id_kwarg_name_in_url = "category_id"

class SubcategoryConsumer(ModelUpdateConsumerBase):
    group_name_prefix = "subcategories"
    item_id_kwarg_name_in_url = "subcategory_id"