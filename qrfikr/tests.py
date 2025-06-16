from django.urls import reverse
from rest_framework.test import APITestCase
from rest_framework import status
from .models import QRCodeLink, Review
from checklists.models import Location, ChecklistPoint
from tasks.models import TaskCategory, Task
from django.contrib.auth import get_user_model

User = get_user_model()

class ReviewAPITests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='test', password='pass')
        self.client.login(username='test', password='pass')
        self.location = Location.objects.create(name='Loc', description='d')
        self.point = ChecklistPoint.objects.create(location=self.location, name='P1')
        self.category = TaskCategory.objects.create(name='Feedback')
        self.qr = QRCodeLink.objects.create(location=self.location, point=self.point, task_category=self.category)

    def test_create_review(self):
        url = reverse('qrfikr:review-list')
        data = {
            'qr_code_link': str(self.qr.id),
            'rating': 5,
            'text': 'Great'
        }
        response = self.client.post(url, data)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(Review.objects.count(), 1)

    def test_low_rating_creates_task(self):
        url = reverse('qrfikr:review-list')
        data = {
            'qr_code_link': str(self.qr.id),
            'rating': 2,
        }
        response = self.client.post(url, data)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(Task.objects.count(), 1)
