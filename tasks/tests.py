from django.test import TestCase
from django.urls import reverse
from django.contrib.auth import get_user_model

from room.models import Room
from tasks.models import Project, Task

User = get_user_model()

class TaskChatIntegrationTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username='user', email='user@example.com', password='pass'
        )
        self.project = Project.objects.create(name='Test Project', owner=self.user)

    def test_get_chat_room_creates_room(self):
        task = Task.objects.create(project=self.project, title='Chat task', created_by=self.user)
        room = task.get_chat_room()
        self.assertIsInstance(room, Room)
        self.assertEqual(room.slug, f'task-{task.pk}')
        self.assertEqual(room.creator, self.user)
        self.assertTrue(room.participants.filter(pk=self.user.pk).exists())
        room_again = task.get_chat_room()
        self.assertEqual(room_again.pk, room.pk)
        self.assertEqual(Room.objects.filter(slug=room.slug).count(), 1)

    def test_get_chat_room_url(self):
        task = Task.objects.create(project=self.project, title='URL task', created_by=self.user)
        self.assertEqual(task.get_chat_room_url(), task.get_chat_room().get_absolute_url())

    def test_task_detail_context_contains_chat_room_url(self):
        task = Task.objects.create(project=self.project, title='Detail task', created_by=self.user)
        self.client.login(username='user', password='pass')
        response = self.client.get(reverse('tasks:task_detail', args=[task.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['chat_room_url'], task.get_chat_room_url())

    def test_room_detail_related_task(self):
        task = Task.objects.create(project=self.project, title='Room task', created_by=self.user)
        task_room = task.get_chat_room()
        self.client.login(username='user', password='pass')
        response = self.client.get(reverse('room:room', kwargs={'slug': task_room.slug}))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['related_task'], task)
