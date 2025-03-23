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
        

class CampaignConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        user = self.scope["user"]
        self.group_name = f"campaign_{user.id}"
        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.accept()

    async def disconnect(self, close_code):
        await self.channel_layer.group_discard(self.group_name, self.channel_name)

    async def receive(self, text_data):
        data = json.loads(text_data)
        await self.channel_layer.group_send(self.group_name, {"type": "updateCampaigns", "message": data})

    async def updateCampaigns(self, event):
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
    