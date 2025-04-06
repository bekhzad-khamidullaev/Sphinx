# filename: room/models.py
import uuid
from django.db import models
from django.conf import settings # Use settings.AUTH_USER_MODEL
from django.contrib.postgres.indexes import GinIndex
from django.contrib.postgres.search import SearchVectorField

# Assuming settings.AUTH_USER_MODEL refers to your User model
# from user_profiles.models import User # Keep if 'user_profiles.User' is correct
User = settings.AUTH_USER_MODEL

class Room(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False) # Use UUIDs for better scalability/security
    name = models.CharField(max_length=255)
    slug = models.SlugField(unique=True, max_length=100) # Ensure max_length for slugs
    private = models.BooleanField(default=False)
    participants = models.ManyToManyField(User, related_name='chat_rooms', blank=True) # Changed related_name to avoid clash if User has 'rooms'
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    # For simple archiving (hides for everyone). Per-user needs a M2M through model.
    is_archived = models.BooleanField(default=False)

    class Meta:
        ordering = ('-updated_at',) # Show recently active rooms first

    def __str__(self):
        return self.name

    def get_absolute_url(self):
        from django.urls import reverse
        return reverse('room:room', kwargs={'slug': self.slug})

    def get_online_users(self):
        # Placeholder: Logic to get online users (likely from Redis in consumer/view)
        # This might involve querying a Redis set associated with the room slug
        return self.participants.filter(is_online=True) # Requires is_online field on User/Profile or Redis check

    @property
    def unread_count(self, user):
        # Placeholder: Logic to count unread messages for a specific user
        # This would likely involve a UserReadTimestamp model or similar
        pass


class Message(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    room = models.ForeignKey(Room, related_name='messages', on_delete=models.CASCADE)
    user = models.ForeignKey(User, related_name='messages', on_delete=models.CASCADE)
    content = models.TextField(blank=True) # Allow blank content if there's a file
    file = models.FileField(upload_to='chat_files/%Y/%m/%d/', null=True, blank=True)
    date_added = models.DateTimeField(auto_now_add=True)
    edited_at = models.DateTimeField(null=True, blank=True)
    is_deleted = models.BooleanField(default=False) # Soft delete
    reply_to = models.ForeignKey('self', null=True, blank=True, on_delete=models.SET_NULL, related_name='replies')

    # For search
    search_vector = SearchVectorField(null=True, blank=True)

    class Meta:
        ordering = ('date_added',)
        indexes = [
            GinIndex(fields=['search_vector']), # Index for full-text search
            models.Index(fields=['room', 'date_added']), # Index for fetching messages efficiently
        ]

    def __str__(self):
        if self.is_deleted:
            return f"[Deleted Message in {self.room.name}]"
        if self.file:
             return f"{self.user.username} sent a file in {self.room.name}"
        return f"{self.user.username}: {self.content[:50]}"

    # TODO: Add save method override to update search_vector

class MessageReadStatus(models.Model):
    """ Tracks when a user last read messages in a room """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    room = models.ForeignKey(Room, on_delete=models.CASCADE)
    last_read_message = models.ForeignKey(Message, null=True, blank=True, on_delete=models.SET_NULL)
    last_read_timestamp = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ('user', 'room') # One status per user per room


class Reaction(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    message = models.ForeignKey(Message, related_name='reactions', on_delete=models.CASCADE)
    user = models.ForeignKey(User, related_name='reactions', on_delete=models.CASCADE)
    emoji = models.CharField(max_length=50) # Allow for unicode emojis
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('message', 'user', 'emoji') # User can only react once with the same emoji per message
        ordering = ('created_at',)

    def __str__(self):
        return f"{self.user.username} reacted with {self.emoji} to message {self.message.id}"