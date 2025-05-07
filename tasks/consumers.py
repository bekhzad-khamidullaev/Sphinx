# tasks/consumers.py
# -*- coding: utf-8 -*-

import json
import logging
from channels.generic.websocket import AsyncWebsocketConsumer
from asgiref.sync import sync_to_async # Для вызова синхронного кода Django ORM
from django.contrib.auth.models import AnonymousUser # Для проверки пользователя
from django.core.exceptions import ValidationError, ObjectDoesNotExist

from .models import Task, TaskComment # Импортируем модели
# user_profiles.models.User нужен для проверки прав и информации об авторе
try:
    from user_profiles.models import User
except ImportError:
    from django.contrib.auth import get_user_model
    User = get_user_model()


logger = logging.getLogger(__name__)

class GenericModelConsumer(AsyncWebsocketConsumer):
    """
    Базовый потребитель для подписки на обновления моделей.
    Имя группы формируется как 'modelname_list' или 'modelname_pk'.
    Тип события в group_send должен соответствовать методу здесь,
    например, group_send(..., {"type": "model_update_event", ...})
    """
    model_name_plural = "items" # Переопределить в дочернем классе (e.g., "tasks", "projects")
    model_pk_param_name = "pk" # Имя параметра PK в URL, если есть

    async def connect(self):
        self.user = self.scope.get("user", AnonymousUser())
        # Пока разрешаем анонимным пользователям подключаться для публичных списков,
        # но для действий или приватных данных потребуется аутентификация.
        # if not self.user or not self.user.is_authenticated:
        #     await self.close()
        #     return

        pk_value = self.scope["url_route"]["kwargs"].get(self.model_pk_param_name)
        if pk_value:
            self.group_name = f"{self.model_name_plural}_{pk_value}" # Группа для конкретного объекта
        else:
            self.group_name = f"{self.model_name_plural}_list" # Группа для списка объектов

        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.accept()
        logger.info(f"{self.__class__.__name__} connected user {self.user.pk or 'anonymous'} to group: {self.group_name}")

    async def disconnect(self, close_code):
        if hasattr(self, 'group_name'):
            await self.channel_layer.group_discard(self.group_name, self.channel_name)
            logger.info(f"{self.__class__.__name__} disconnected user from group: {self.group_name}")

    async def model_update_event(self, event):
        """
        Обработчик для событий типа 'model_update_event'.
        Имя этого метода должно совпадать с 'type' в channel_layer.group_send.
        Например, type: "project_update" -> async def project_update(self, event):
        """
        message = event.get("message", {})
        # Можно добавить проверку прав пользователя перед отправкой, если это необходимо
        # if await self.has_permission_for_message(message):
        await self.send(text_data=json.dumps(message))

    # Динамические обработчики для разных моделей, если Consumer один на всех
    async def task_update(self, event): await self.model_update_event(event)
    async def list_update(self, event): await self.model_update_event(event) # Для списков задач
    async def project_update(self, event): await self.model_update_event(event)
    async def category_update(self, event): await self.model_update_event(event)
    async def subcategory_update(self, event): await self.model_update_event(event)
    # ... другие модели ...

    # Пример обработки входящего сообщения от клиента (если нужно)
    async def receive(self, text_data):
        if not self.user or not self.user.is_authenticated:
            await self.send_error("Authentication required to send messages.")
            return

        try:
            data = json.loads(text_data)
            action = data.get("action")
            payload = data.get("payload")

            if action == "update_task_status" and self.model_name_plural == "tasks": # Пример для задач
                task_id = payload.get("task_id")
                new_status = payload.get("status")
                if task_id and new_status:
                    await self.handle_client_task_status_update(task_id, new_status)
                else:
                    await self.send_error("Task ID and new status are required.")
            else:
                logger.warning(f"{self.__class__.__name__} received unknown action '{action}' or for wrong model.")
                await self.send_error(f"Unknown action: {action}")

        except json.JSONDecodeError:
            await self.send_error("Invalid JSON format.")
        except Exception as e:
            logger.error(f"Error in {self.__class__.__name__} receive: {e}")
            await self.send_error(f"An unexpected server error occurred.")

    @sync_to_async
    def _update_task_status_from_client(self, task_id, new_status, user_id):
        try:
            task = Task.objects.get(id=task_id)
            user = User.objects.get(id=user_id) # Получаем пользователя для проверки прав

            if not task.has_permission(user, 'change_status'):
                raise PermissionError("You do not have permission to change status for this task.")
            
            # Проверка валидности статуса (из модели или списка)
            valid_statuses = dict(Task.StatusChoices.choices).keys()
            if new_status not in valid_statuses:
                raise ValueError(f"Invalid status: {new_status}")

            task.status = new_status
            # Модель Task.save() должна обработать completion_date и т.д.
            task.save(update_fields=['status', 'updated_at', 'completion_date'])
            # Сигнал post_save Task отправит уведомления другим клиентам
            return True, None # Success, no error message
        except ObjectDoesNotExist:
            return False, "Task not found."
        except PermissionError as e:
            return False, str(e)
        except ValueError as e: # Для невалидного статуса
            return False, str(e)
        except Exception as e:
            logger.error(f"Error updating task status from client request: {e}")
            return False, "Server error during status update."


    async def handle_client_task_status_update(self, task_id, new_status):
        """ Обрабатывает запрос на изменение статуса задачи от клиента. """
        success, error_message = await self._update_task_status_from_client(task_id, new_status, self.user.id)
        if success:
            # Отправляем подтверждение клиенту, который инициировал изменение
            # Остальные клиенты получат обновление через сигнал post_save модели Task
            await self.send(text_data=json.dumps({
                'type': 'status_update_confirmation', # Тип для JS клиента
                'task_id': task_id,
                'new_status': new_status,
                'success': True
            }))
        else:
            await self.send_error(error_message, event_type='status_update_error')


    async def send_error(self, message, event_type="error_message"):
        await self.send(text_data=json.dumps({
            'type': event_type, # Тип для JS клиента
            'message': message,
            'success': False
        }))


class TaskConsumer(GenericModelConsumer):
    model_name_plural = "tasks"
    model_pk_param_name = "task_id" # Соответствует <task_id> в URL

class ProjectConsumer(GenericModelConsumer):
    model_name_plural = "projects"
    model_pk_param_name = "project_id"

class CategoryConsumer(GenericModelConsumer):
    model_name_plural = "categories"
    model_pk_param_name = "category_id"

class SubcategoryConsumer(GenericModelConsumer):
    model_name_plural = "subcategories"
    model_pk_param_name = "subcategory_id"


# Отдельный консьюмер для комментариев к задачам
class TaskCommentConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        self.task_id = self.scope['url_route']['kwargs'].get('task_id')
        self.user = self.scope.get("user", AnonymousUser())

        if not self.task_id:
            logger.warning("TaskCommentConsumer connection rejected: No task_id in URL.")
            await self.close()
            return
        
        # Проверка, может ли пользователь просматривать задачу (и, следовательно, комментарии)
        # Если комментарии публичны для всех, кто видит задачу, этого достаточно.
        # Если права на комментирование/просмотр комментариев более гранулярные, нужна доп. проверка.
        can_view_task = await self.check_task_view_permission()
        if not can_view_task:
             logger.warning(f"TaskCommentConsumer connection rejected: User {self.user.pk or 'anonymous'} lacks view permission for task {self.task_id}.")
             await self.close()
             return

        self.room_group_name = f'task_comments_{self.task_id}'
        await self.channel_layer.group_add(self.room_group_name, self.channel_name)
        await self.accept()
        logger.info(f"TaskCommentConsumer connected user {self.user.pk or 'anonymous'} to comment group: {self.room_group_name}")

    async def disconnect(self, close_code):
        if hasattr(self, 'room_group_name'):
            await self.channel_layer.group_discard(self.room_group_name, self.channel_name)
            logger.info(f"TaskCommentConsumer disconnected user from comment group: {self.room_group_name}")

    @sync_to_async
    def check_task_view_permission(self):
        try:
            task = Task.objects.get(pk=self.task_id)
            # Если пользователь анонимный, но задача, например, публичная
            if isinstance(self.user, AnonymousUser):
                # Здесь должна быть логика проверки, является ли задача публичной
                # return task.is_public  # Пример
                return False # По умолчанию анонимам запрещаем
            return task.has_permission(self.user, 'view')
        except Task.DoesNotExist:
            return False
        except Exception as e:
            logger.error(f"Error checking task view permission in TaskCommentConsumer for task {self.task_id}: {e}")
            return False

    # Этот метод будет вызван, когда сигнал post_save для TaskComment отправит сообщение в группу
    async def comment_message(self, event):
        message_data = event['message'] # Данные из сигнала (см. signals.py)
        # Отправляем сообщение клиенту
        await self.send(text_data=json.dumps({
            'type': 'new_comment', # Тип для JS клиента, чтобы он знал, как обработать это сообщение
            'comment': message_data
        }))

    # Клиент может отправлять сообщения (например, "is_typing"), но для простоты пока не реализуем
    # async def receive(self, text_data):
    #     pass