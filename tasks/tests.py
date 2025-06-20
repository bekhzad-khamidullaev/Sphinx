from django.test import TestCase
from django.urls import reverse
from django.contrib.auth import get_user_model
from channels.layers import get_channel_layer
from asgiref.sync import async_to_sync

from room.models import Room
from tasks.models import Project, Task, TaskComment

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


class TaskDueDateTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='dueuser', password='pass')
        self.project = Project.objects.create(name='DD Project', owner=self.user)

    def test_due_date_auto_set_high_priority(self):
        task = Task.objects.create(project=self.project, title='HP', created_by=self.user,
                                   priority=Task.TaskPriority.HIGH)
        self.assertIsNotNone(task.due_date)
        self.assertEqual((task.due_date - task.start_date).days, 1)


class TaskCommentSignalTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='commuser', password='pass')
        self.project = Project.objects.create(name='WS Project', owner=self.user)
        self.task = Task.objects.create(project=self.project, title='WS Task', created_by=self.user)

    def test_comment_creation_triggers_ws_message(self):
        channel_layer = get_channel_layer()
        TaskComment.objects.create(task=self.task, author=self.user, text='Ping')
        message = async_to_sync(channel_layer.receive)(f'task_comments_{self.task.id}')
        self.assertEqual(message['type'], 'comment_message')
        self.assertEqual(message['message']['text'], 'Ping')
        self.assertEqual(message['message']['task_id'], self.task.id)
        self.assertEqual(message['message']['author']['id'], self.user.id)
