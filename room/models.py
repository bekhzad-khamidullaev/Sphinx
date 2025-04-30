# room/models.py
import uuid
import logging
from django.db import models
from django.conf import settings
from django.urls import reverse
from django.contrib.postgres.indexes import GinIndex # If using PostgreSQL
from django.contrib.postgres.search import SearchVectorField # If using PostgreSQL
from django.utils.translation import gettext_lazy as _
from django.utils import timezone

User = settings.AUTH_USER_MODEL
logger = logging.getLogger(__name__)

class Room(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=255, verbose_name=_("Название комнаты"))
    slug = models.SlugField(unique=True, max_length=100, verbose_name=_("Slug (URL)"))
    private = models.BooleanField(default=False, verbose_name=_("Приватная?"))
    participants = models.ManyToManyField(
        User, related_name='chat_rooms', blank=True, verbose_name=_("Участники")
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name=_("Создана"))
    updated_at = models.DateTimeField(auto_now=True, verbose_name=_("Обновлена"))
    is_archived = models.BooleanField(default=False, db_index=True, verbose_name=_("В архиве?"))

    class Meta:
        ordering = ('-updated_at',)
        verbose_name = _("Чат-комната")
        verbose_name_plural = _("Чат-комнаты")
        indexes = [
            models.Index(fields=['is_archived', 'private']),
        ]

    def __str__(self):
        return self.name

    def get_absolute_url(self):
        return reverse('room:room', kwargs={'slug': self.slug})

class Message(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    room = models.ForeignKey(Room, related_name='messages', on_delete=models.CASCADE, verbose_name=_("Комната"))
    user = models.ForeignKey(User, related_name='messages', on_delete=models.CASCADE, verbose_name=_("Пользователь"))
    content = models.TextField(blank=True, verbose_name=_("Содержание"))
    file = models.FileField(upload_to='chat_files/%Y/%m/%d/', null=True, blank=True, verbose_name=_("Файл"))
    date_added = models.DateTimeField(auto_now_add=True, db_index=True, verbose_name=_("Добавлено"))
    edited_at = models.DateTimeField(null=True, blank=True, verbose_name=_("Отредактировано"))
    is_deleted = models.BooleanField(default=False, db_index=True, verbose_name=_("Удалено?"))
    reply_to = models.ForeignKey('self', null=True, blank=True, on_delete=models.SET_NULL, related_name='replies', verbose_name=_("В ответ на"))
    # search_vector = SearchVectorField(null=True, blank=True, editable=False) # For PostgreSQL FTS

    class Meta:
        ordering = ('date_added',)
        verbose_name = _("Сообщение чата")
        verbose_name_plural = _("Сообщения чата")
        indexes = [
            # GinIndex(fields=['search_vector']), # If using PostgreSQL FTS
            models.Index(fields=['room', 'date_added']),
            models.Index(fields=['room', 'is_deleted', 'date_added']), # For fetching non-deleted messages
        ]

    def __str__(self):
        prefix = f"[{_('Удалено')}] " if self.is_deleted else ""
        user_name = self.user.username if self.user else _("System")
        content_preview = f"'{self.content[:30]}...'" if self.content else _("[Файл]")
        if self.is_deleted: content_preview = ""
        return f"{prefix}{user_name} ({self.date_added:%d.%m %H:%M}): {content_preview}"

class MessageReadStatus(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(User, on_delete=models.CASCADE, verbose_name=_("Пользователь"))
    room = models.ForeignKey(Room, on_delete=models.CASCADE, verbose_name=_("Комната"))
    last_read_message = models.ForeignKey(Message, null=True, blank=True, on_delete=models.SET_NULL, verbose_name=_("Последнее прочитанное"))
    last_read_timestamp = models.DateTimeField(auto_now=True, verbose_name=_("Время последнего прочтения"))

    class Meta:
        unique_together = ('user', 'room')
        verbose_name = _("Статус прочтения")
        verbose_name_plural = _("Статусы прочтения")
        indexes = [ models.Index(fields=['user', 'room']), ]

class Reaction(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    message = models.ForeignKey(Message, related_name='reactions', on_delete=models.CASCADE, verbose_name=_("Сообщение"))
    user = models.ForeignKey(User, related_name='reactions', on_delete=models.CASCADE, verbose_name=_("Пользователь"))
    emoji = models.CharField(max_length=50, verbose_name=_("Эмодзи"))
    created_at = models.DateTimeField(auto_now_add=True, verbose_name=_("Создано"))

    class Meta:
        unique_together = ('message', 'user', 'emoji')
        ordering = ('created_at',)
        verbose_name = _("Реакция")
        verbose_name_plural = _("Реакции")
        indexes = [ models.Index(fields=['message', 'emoji']), ]

    def __str__(self):
        user_name = self.user.username if self.user else '??'
        return f"{user_name} : {self.emoji}"