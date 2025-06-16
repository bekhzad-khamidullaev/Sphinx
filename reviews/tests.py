from django.urls import reverse
from rest_framework.test import APITestCase
from rest_framework import status
from .models import Review

class ReviewAPITests(APITestCase):
    def test_create_review(self):
        url = reverse('review-list')
        data = {
            'restaurant_name': 'Test Place',
            'user_name': 'John',
            'rating': 4,
            'comment': 'Nice'
        }
        response = self.client.post(url, data)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(Review.objects.count(), 1)
