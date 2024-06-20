from django.db import models
from django.contrib.auth.models import AbstractUser
from django.conf import settings

class User(AbstractUser):
    # profile = models.OneToOneField('UserProfile', on_delete=models.CASCADE, related_name='user_profile', null=True, blank=True)
    image = models.ImageField(default='', upload_to='static/images/profile_pics/')

class UserProfile(models.Model):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='user_profile')
    # image = models.ImageField(upload_to='static/images/profile_pics/')

    def __str__(self):
        return self.user.username
