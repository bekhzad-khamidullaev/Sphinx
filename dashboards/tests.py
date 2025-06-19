from django.urls import reverse
from rest_framework.test import APITestCase
from django.contrib.auth import get_user_model


class DashboardViewTests(APITestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username='dash', password='pass')
        self.client.login(username='dash', password='pass')

    def test_dashboard_view(self):
        url = reverse('dashboards:task_dashboard')
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertIn('Дашборд задач', response.content.decode())
