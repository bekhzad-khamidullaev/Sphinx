from django.urls import reverse
from rest_framework.test import APITestCase
from rest_framework import status
from django.contrib.auth import get_user_model

User = get_user_model()

class AuthTests(APITestCase):
    def test_registration_and_login(self):
        reg_url = reverse('user_profiles:api-register')
        data = {
            'username': 'newuser',
            'password': 'password123',
            'password2': 'password123',
            'email': 'new@example.com'
        }
        response = self.client.post(reg_url, data)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(User.objects.filter(username='newuser').count(), 1)

        token_url = reverse('user_profiles:token_obtain_pair')
        login_resp = self.client.post(token_url, {'username': 'newuser', 'password': 'password123'})
        self.assertEqual(login_resp.status_code, status.HTTP_200_OK)
        self.assertIn('access', login_resp.data)

    def test_unauthorized_access(self):
        task_url = reverse('tasks:task-api-list')
        response = self.client.get(task_url)
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
