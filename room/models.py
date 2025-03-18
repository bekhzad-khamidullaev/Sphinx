from user_profiles.models import User  # Assuming you have a User model
from django.db import models

class Room(models.Model):
    name = models.CharField(max_length=255)
    slug = models.SlugField(unique=True)
    private = models.BooleanField(default=False)
    participants = models.ManyToManyField(User, related_name='rooms', blank=True)

    def __str__(self):
        return self.name

class Message(models.Model):
    room = models.ForeignKey(Room, related_name='messages', on_delete=models.CASCADE)
    user = models.ForeignKey(User, related_name='messages', on_delete=models.CASCADE)
    content = models.TextField()
    date_added = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ('date_added',)

    def __str__(self):
        return f"{self.user.username}: {self.content[:50]}"