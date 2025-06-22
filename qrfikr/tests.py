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

        self.point = ChecklistPoint.objects.create(location=self.location, name='Point1')
        self.qr = QRCodeLink.objects.create(point=self.point)


    def test_create_review_forbidden(self):
        url = reverse('qrfikr:review-list')
        data = {
            'qr_code_link': str(self.qr.id),
            'rating': 5,
            'text': 'Great'
        }
        response = self.client.post(url, data)
        self.assertEqual(response.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)
        self.assertEqual(Review.objects.count(), 0)

    def test_admin_can_view_reviews(self):
        Review.objects.create(qr_code_link=self.qr, rating=4)
        admin = User.objects.create_superuser(
            username='admin', password='adminpass', email='admin@example.com'
        )
        self.client.login(username='admin', password='adminpass')
        url = reverse('qrfikr:review-list')
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 1)


class QRCodeLinkModelTests(APITestCase):
    def test_str_with_missing_point(self):
        location = Location.objects.create(name='OnlyLoc', description='d')
        qr = QRCodeLink.objects.create(location=location)
        self.assertEqual(str(qr), 'OnlyLoc')

class ReviewTaskCreationTests(APITestCase):
    def setUp(self):
        self.location = Location.objects.create(name='LocTask', description='d')
        self.point = ChecklistPoint.objects.create(location=self.location, name='P1')
        self.qr = QRCodeLink.objects.create(point=self.point)
        self.category = TaskCategory.objects.create(name='Service')

    def test_task_created_for_low_rating(self):
        Review.objects.create(qr_code_link=self.qr, rating=2, category=self.category)
        self.assertEqual(Task.objects.count(), 1)
        task = Task.objects.first()
        self.assertEqual(task.category, self.category)
        self.assertIn(self.point.name, task.title)

