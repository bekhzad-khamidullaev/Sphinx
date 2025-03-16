import json
from user_profiles.models import User
from channels.generic.websocket import AsyncWebsocketConsumer
from asgiref.sync import sync_to_async
from .models import Room, Message

class ChatConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        # Get room name from URL kwargs
        self.room_name = self.scope['url_route']['kwargs']['room_name']
        self.room_group_name = f'chat_{self.room_name}'

        # Fetch room and check if it's private and if user is a participant
        room = await sync_to_async(Room.objects.get)(slug=self.room_name)

        if room.private:
            user = self.scope['user']
            if not await self.is_participant(user, room):
                # If the user is not a participant of a private room, deny access
                await self.close()
                return

        # Add the user to the room group
        await self.channel_layer.group_add(
            self.room_group_name,
            self.channel_name
        )

        await self.accept()

    async def disconnect(self, close_code):
        # Remove the user from the room group
        await self.channel_layer.group_discard(
            self.room_group_name,
            self.channel_name
        )

    async def receive(self, text_data):
        # Parse the incoming message
        data = json.loads(text_data)
        message = data.get('message')
        username = data.get('username')
        room_slug = data.get('room')

        if not message or not username or not room_slug:
            return  # You can add a better response for invalid messages if needed

        # Save message to the database
        await self.save_message(username, room_slug, message)

        # Send the message to the room group
        await self.channel_layer.group_send(
            self.room_group_name,
            {
                'type': 'chat_message',
                'message': message,
                'username': username
            }
        )

    async def chat_message(self, event):
        # Extract message and username from event
        message = event['message']
        username = event['username']

        # Send the message to the WebSocket
        await self.send(text_data=json.dumps({
            'message': message,
            'username': username
        }))

    @sync_to_async
    def save_message(self, username, room_slug, message):
        try:
            user = User.objects.get(username=username)
            room = Room.objects.get(slug=room_slug)
            Message.objects.create(user=user, room=room, content=message)
        except (User.DoesNotExist, Room.DoesNotExist) as e:
            print(f"Error saving message: {e}")
            return False
        return True

    @sync_to_async
    def is_participant(self, user, room):
        return user in room.participants.all()


class UserSearchConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        # Ожидаем подключения
        self.room_group_name = "search_room"
        await self.channel_layer.group_add(
            self.room_group_name,
            self.channel_name
        )
        await self.accept()

    async def disconnect(self, close_code):
        # Закрываем соединение
        await self.channel_layer.group_discard(
            self.room_group_name,
            self.channel_name
        )

    async def receive(self, text_data):
        data = json.loads(text_data)
        query = data.get('query', '')

        # Поиск пользователей по имени
        users = User.objects.filter(username__icontains=query).values('username')

        # Отправляем найденных пользователей обратно
        await self.send(text_data=json.dumps({
            'users': list(users)
        }))