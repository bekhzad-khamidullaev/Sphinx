# room/models.py
import uuid
import os
from django.db import models
from django.conf import settings
from django.urls import reverse
from django.utils.translation import gettext_lazy as _
from django.utils import timezone
# from django.contrib.postgres.indexes import GinIndex # Если PostgreSQL и FTS
# from django.contrib.postgres.search import SearchVectorField

User = settings.AUTH_USER_MODEL

class Room(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(_("Название комнаты"), max_length=100)
    slug = models.SlugField(_("Slug (URL)"), unique=True, max_length=110, db_index=True)
    private = models.BooleanField(_("Приватная?"), default=False, db_index=True)
    participants = models.ManyToManyField(
        User,
        related_name='chat_rooms',
        blank=True,
        verbose_name=_("Участники")
    )
    creator = models.ForeignKey(
        User,
        related_name='created_chat_rooms',
        on_delete=models.SET_NULL, # Или models.CASCADE если создатель важен
        null=True, blank=True,
        verbose_name=_("Создатель")
    )
    created_at = models.DateTimeField(_("Создана"), auto_now_add=True)
    updated_at = models.DateTimeField(_("Обновлена"), auto_now=True) # Обновляется при каждом сохранении
    last_activity_at = models.DateTimeField(_("Последняя активность"), default=timezone.now, db_index=True) # Обновляется при новом сообщении
    is_archived = models.BooleanField(_("В архиве?"), default=False, db_index=True)

    class Meta:
        ordering = ('-last_activity_at',) # Сначала комнаты с последней активностью
        verbose_name = _("Чат-комната")
        verbose_name_plural = _("Чат-комнаты")
        indexes = [
            models.Index(fields=['is_archived', 'private', '-last_activity_at']),
        ]

    def __str__(self):
        return self.name

    def get_absolute_url(self):
        return reverse('room:room', kwargs={'slug': self.slug})

    def update_last_activity(self):
        self.last_activity_at = timezone.now()
        self.save(update_fields=['last_activity_at'])


class Message(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    room = models.ForeignKey(Room, related_name='messages', on_delete=models.CASCADE, verbose_name=_("Комната"))
    user = models.ForeignKey(User, related_name='messages', on_delete=models.CASCADE, verbose_name=_("Пользователь"))
    content = models.TextField(_("Содержание"), blank=True)
    file = models.FileField(_("Файл"), upload_to='chat_files/%Y/%m/%d/', null=True, blank=True)
    date_added = models.DateTimeField(_("Добавлено"), default=timezone.now, db_index=True) # default=timezone.now для консистентности
    edited_at = models.DateTimeField(_("Отредактировано"), null=True, blank=True)
    is_deleted = models.BooleanField(_("Удалено?"), default=False, db_index=True)
    reply_to = models.ForeignKey(
        'self',
        null=True, blank=True,
        on_delete=models.SET_NULL, # Сохраняем сообщение, даже если ответ удален
        related_name='replies',
        verbose_name=_("В ответ на")
    )
    # search_vector = SearchVectorField(null=True, blank=True, editable=False) # Для PostgreSQL FTS

    class Meta:
        ordering = ('date_added',) # Сообщения всегда в хронологическом порядке
        verbose_name = _("Сообщение чата")
        verbose_name_plural = _("Сообщения чата")
        indexes = [
            models.Index(fields=['room', 'date_added']),
            models.Index(fields=['room', 'is_deleted', 'date_added']),
            # GinIndex(fields=['search_vector']), # Если PostgreSQL FTS
        ]

    def __str__(self):
        prefix = f"[{_('Удалено')}] " if self.is_deleted else ""
        user_name = self.user.username if self.user else _("System")
        content_preview = f"'{self.content[:30]}...'" if self.content else (_("[Файл]") if self.file else "")
        if self.is_deleted: content_preview = ""
        return f"{prefix}{user_name} ({self.date_added:%d.%m %H:%M}): {content_preview}"

    def get_filename(self):
        if self.file and hasattr(self.file, 'name'):
            return os.path.basename(self.file.name)
        return None

    def save(self, *args, **kwargs):
        is_new = self._state.adding
        super().save(*args, **kwargs)
        if is_new and self.room: # При создании нового сообщения обновляем активность комнаты
            self.room.update_last_activity()


class MessageReadStatus(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(User, on_delete=models.CASCADE, verbose_name=_("Пользователь"))
    room = models.ForeignKey(Room, on_delete=models.CASCADE, verbose_name=_("Комната"))
    last_read_message = models.ForeignKey(
        Message,
        null=True, blank=True,
        on_delete=models.SET_NULL, # Если сообщение удалено, статус сохраняется, но указывает на null
        verbose_name=_("Последнее прочитанное")
    )
    # Обновляется при каждом сохранении, используем для отслеживания, когда пользователь последний раз "видел" комнату
    last_read_timestamp = models.DateTimeField(_("Время последнего прочтения"), auto_now=True)

    class Meta:
        unique_together = ('user', 'room') # У одного юзера один статус на комнату
        verbose_name = _("Статус прочтения")
        verbose_name_plural = _("Статусы прочтения")
        indexes = [
            models.Index(fields=['user', 'room', 'last_read_message']),
        ]

    def __str__(self):
        return f"{self.user.username} in {self.room.name} read up to {self.last_read_message_id or 'N/A'}"


class Reaction(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    message = models.ForeignKey(Message, related_name='reactions', on_delete=models.CASCADE, verbose_name=_("Сообщение"))
    user = models.ForeignKey(User, related_name='reactions', on_delete=models.CASCADE, verbose_name=_("Пользователь"))
    emoji = models.CharField(_("Эмодзи"), max_length=50) # Можно использовать CharField с выбором или более сложную валидацию
    created_at = models.DateTimeField(_("Создано"), auto_now_add=True)

    class Meta:
        unique_together = ('message', 'user', 'emoji') # Пользователь может поставить только одну такую реакцию на сообщение
        ordering = ('created_at',)
        verbose_name = _("Реакция")
        verbose_name_plural = _("Реакции")
        indexes = [
            models.Index(fields=['message', 'user', 'emoji']),
            models.Index(fields=['message', 'emoji']),
        ]

    def __str__(self):
        user_name = self.user.username if self.user else '??'
        return f"{user_name} : {self.emoji} on MsgID {self.message_id}"