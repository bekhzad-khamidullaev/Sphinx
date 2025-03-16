import json
from channels.generic.websocket import AsyncWebsocketConsumer


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
    """WebSocket consumer для обновлений задач в реальном времени."""

    async def connect(self):
        """Подключение пользователя к WebSocket-группе 'tasks'."""
        await self.channel_layer.group_add("tasks", self.channel_name)
        await self.accept()

    async def disconnect(self, close_code):
        """Отключение пользователя и выход из группы."""
        await self.channel_layer.group_discard("tasks", self.channel_name)

    async def receive(self, text_data):
        """Получает данные от клиента и передает их в WebSocket-группу."""
        try:
            data = json.loads(text_data)
            await self.channel_layer.group_send(
                "tasks",
                {"type": "task_update", "message": data}
            )
        except json.JSONDecodeError:
            await self.send(text_data=json.dumps({"error": "Invalid JSON format"}))

    async def task_update(self, event):
        """Отправляет обновления задач всем подключенным пользователям."""
        await self.send(text_data=json.dumps(event["message"]))


class CampaignConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        await self.channel_layer.group_add("campaigns", self.channel_name)
        await self.accept()

    async def disconnect(self, close_code):
        await self.channel_layer.group_discard("campaigns", self.channel_name)

    async def receive(self, text_data):
        data = json.loads(text_data)
        await self.channel_layer.group_send("campaigns", {"type": "updateCampaigns", "message": data})

    async def updateCampaigns(self, event):
        await self.send(text_data=json.dumps(event["message"]))


class TeamConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        await self.channel_layer.group_add("teams", self.channel_name)
        await self.accept()

    async def disconnect(self, close_code):
        await self.channel_layer.group_discard("teams", self.channel_name)

    async def receive(self, text_data):
        data = json.loads(text_data)
        await self.channel_layer.group_send("teams", {"type": "updateTeams", "message": data})

    async def updateTeams(self, event):
        await self.send(text_data=json.dumps(event["message"]))


class UserConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        await self.channel_layer.group_add("users", self.channel_name)
        await self.accept()

    async def disconnect(self, close_code):
        await self.channel_layer.group_discard("users", self.channel_name)

    async def receive(self, text_data):
        data = json.loads(text_data)
        await self.channel_layer.group_send("users", {"type": "updateUsers", "message": data})

    async def updateUsers(self, event):
        await self.send(text_data=json.dumps(event["message"]))