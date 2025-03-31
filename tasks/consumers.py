import json
from channels.generic.websocket import AsyncWebsocketConsumer
from asgiref.sync import sync_to_async
from .models import Task
from django.core.exceptions import ValidationError

class GenericConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        self.group_name = self.scope["url_route"]["kwargs"]["group"]
        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.accept()

    async def disconnect(self, close_code):
        await self.channel_layer.group_discard(self.group_name, self.channel_name)

    async def receive(self, text_data):
        data = json.loads(text_data)
        await self.channel_layer.group_send(self.group_name, {"type": "updateData", "message": data})

    async def updateData(self, event):
        await self.send(text_data=json.dumps(event["message"]))


class TaskConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        self.room_group_name = 'task_updates'
        await self.channel_layer.group_add(self.room_group_name, self.channel_name)
        await self.accept()

    async def disconnect(self, close_code):
        await self.channel_layer.group_discard(self.room_group_name, self.channel_name)

    async def receive(self, text_data):
        try:
            data = json.loads(text_data)
            task_id = data['task_id']
            new_status = data['status']

            # Получаем задачу и обновляем её статус
            task = await sync_to_async(Task.objects.get)(id=task_id)
            task.status = new_status

            # Сохраняем задачу с обработкой ValidationError
            await sync_to_async(task.save)()

            # Отправляем обновление статуса всем в группе
            await self.channel_layer.group_send(
                self.room_group_name,
                {
                    'type': 'task_status_update',
                    'task_id': task.id,
                    'new_status': task.status,
                    'success': True
                }
            )

        except ValidationError as e:
            # Отправляем сообщение об ошибке на фронт
            await self.send(text_data=json.dumps({
                'type': 'error',
                'message': str(e.messages[0])  # Первое сообщение об ошибке
            }))
        except Task.DoesNotExist:
            await self.send(text_data=json.dumps({
                'type': 'error',
                'message': 'Задача не найдена.'
            }))
        except Exception as e:
            await self.send(text_data=json.dumps({
                'type': 'error',
                'message': f'Произошла ошибка: {str(e)}'
            }))

    async def task_status_update(self, event):
        # Отправляем обновление статуса задачи клиенту
        task_id = event['task_id']
        new_status = event['new_status']
        await self.send(text_data=json.dumps({
            'type': 'status_update',
            'task_id': task_id,
            'new_status': new_status,
            'success': True
        }))

class CategoryConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        user = self.scope["user"]
        self.group_name = f"category_{user.id}"
        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.accept()

    async def disconnect(self, close_code):
        await self.channel_layer.group_discard(self.group_name, self.channel_name)

    async def receive(self, text_data):
        data = json.loads(text_data)
        await self.channel_layer.group_send(self.group_name, {"type": "updateCategories", "message": data})

    async def updateCategories(self, event):
        await self.send(text_data=json.dumps(event["message"]))


class SubcategoryConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        user = self.scope["user"]
        self.group_name = f"subcategory_{user.id}"
        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.accept()

    async def disconnect(self, close_code):
        await self.channel_layer.group_discard(self.group_name, self.channel_name)

    async def receive(self, text_data):
        data = json.loads(text_data)
        await self.channel_layer.group_send(self.group_name, {"type": "updateSubcategories", "message": data})

    async def updateSubcategories(self, event):
        await self.send(text_data=json.dumps(event["message"]))
        

class ProjectConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        user = self.scope["user"]
        self.group_name = f"project_{user.id}"
        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.accept()

    async def disconnect(self, close_code):
        await self.channel_layer.group_discard(self.group_name, self.channel_name)

    async def receive(self, text_data):
        data = json.loads(text_data)
        await self.channel_layer.group_send(self.group_name, {"type": "updateProjects", "message": data})

    async def updateProjects(self, event):
        await self.send(text_data=json.dumps(event["message"]))


class TeamConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        user = self.scope["user"]
        self.group_name = f"team_{user.id}"
        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.accept()

    async def disconnect(self, close_code):
        await self.channel_layer.group_discard(self.group_name, self.channel_name)

    async def receive(self, text_data):
        data = json.loads(text_data)
        await self.channel_layer.group_send(self.group_name, {"type": "updateTeams", "message": data})

    async def updateTeams(self, event):
        await self.send(text_data=json.dumps(event["message"]))


class UserConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        user = self.scope["user"]
        self.group_name = f"user_{user.id}"
        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.accept()

    async def disconnect(self, close_code):
        await self.channel_layer.group_discard(self.group_name, self.channel_name)

    async def receive(self, text_data):
        data = json.loads(text_data)
        await self.channel_layer.group_send(self.group_name, {"type": "updateUsers", "message": data})

    async def updateUsers(self, event):
        await self.send(text_data=json.dumps(event["message"]))


class TaskCommentConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        # Получаем ID задачи из URL
        # URL будет выглядеть примерно так: /ws/tasks/<task_id>/comments/
        self.task_id = self.scope['url_route']['kwargs'].get('task_id')
        self.user = self.scope.get('user')

        if not self.task_id or not self.user or not self.user.is_authenticated:
            # Отклоняем соединение, если ID задачи нет или пользователь не аутентифицирован
            logger.warning(f"WebSocket Comment connection rejected: No task_id or user not authenticated. Scope: {self.scope}")
            await self.close()
            return

        # Проверка прав доступа к задаче (опционально, но рекомендуется)
        has_perm = await self.check_task_permission()
        if not has_perm:
             logger.warning(f"WebSocket Comment connection rejected: User {self.user.username} has no view permission for task {self.task_id}.")
             await self.close()
             return

        # Создаем имя группы для этой задачи
        self.room_group_name = f'task_comments_{self.task_id}'
        logger.info(f"WebSocket connecting user {self.user.username} to {self.room_group_name}")

        # Присоединяемся к группе
        await self.channel_layer.group_add(
            self.room_group_name,
            self.channel_name
        )

        await self.accept()
        logger.info(f"WebSocket connection accepted for user {self.user.username} to {self.room_group_name}")

    async def disconnect(self, close_code):
        # Отсоединяемся от группы при разрыве соединения
        if hasattr(self, 'room_group_name'):
            logger.info(f"WebSocket disconnecting user {self.user.username} from {self.room_group_name}")
            await self.channel_layer.group_discard(
                self.room_group_name,
                self.channel_name
            )

    # Метод для получения сообщений от WebSocket (от клиента) - пока не используется
    # async def receive(self, text_data):
    #     pass

    # --- Метод для отправки нового комментария клиентам ---
    # Имя этого метода должно совпадать с ключом 'type' в group_send
    async def comment_message(self, event):
        """Отправляет данные нового комментария подключенному клиенту."""
        message_data = event['message']
        logger.debug(f"Sending comment message via WebSocket to group {self.room_group_name}: {message_data}")

        # Отправляем сообщение в WebSocket
        await self.send(text_data=json.dumps({
            'type': 'new_comment', # Указываем тип сообщения для JS
            'comment': message_data # Данные комментария
        }))

    @sync_to_async
    def check_task_permission(self):
        """Проверяет право пользователя на просмотр задачи."""
        try:
            task = Task.objects.get(pk=self.task_id)
            return task.has_permission(self.user, 'view') # Проверяем право на просмотр
        except Task.DoesNotExist:
            return False
        except Exception as e:
            logger.error(f"Error checking task permission in WebSocket for task {self.task_id}: {e}")
            return False