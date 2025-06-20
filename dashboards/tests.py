from django.urls import reverse
from rest_framework.test import APITestCase
from django.contrib.auth import get_user_model
from django.conf import settings


class DashboardViewTests(APITestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username='dash', password='pass')
        self.client.login(username='dash', password='pass')
        if 'testserver' not in settings.ALLOWED_HOSTS:
            settings.ALLOWED_HOSTS.append('testserver')

    def test_dashboard_view(self):
        url = reverse('dashboards:task_dashboard')
        response = self.client.get(url)
        print('status_code', response.status_code)
        self.assertEqual(response.status_code, 200)
        self.assertIn('Дашборд задач', response.content.decode())
        self.assertIn('priorityChart', response.content.decode())
        self.assertIn('projectChart', response.content.decode())
        self.assertIn('teamChart', response.content.decode())
