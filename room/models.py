# room/models.py
import uuid
import os
from django.db import models
from django.conf import settings
from django.urls import reverse
from django.utils.translation import gettext_lazy as _
from django.utils import timezone

User = settings.AUTH_USER_MODEL # Используем settings.AUTH_USER_MODEL

class Room(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(_("Название комнаты"), max_length=100) # Рассмотрите unique=True, если имена комнат должны быть уникальны
    slug = models.SlugField(_("Slug (URL)"), unique=True, max_length=110, db_index=True, help_text=_("Автоматически генерируется из названия, если не указано. Используется в URL."))
    private = models.BooleanField(_("Приватная?"), default=False, db_index=True)
    participants = models.ManyToManyField(
        User,
        related_name='chat_rooms',
        blank=True, # Разрешаем пустой список участников (например, для публичных комнат или если создатель - единственный участник)
        verbose_name=_("Участники")
    )
    creator = models.ForeignKey(
        User,
        related_name='created_chat_rooms',
        on_delete=models.SET_NULL,
        null=True, blank=False, # Создатель должен быть, но может быть удален из системы (SET_NULL)
        verbose_name=_("Создатель")
    )
    created_at = models.DateTimeField(_("Создана"), auto_now_add=True)
    updated_at = models.DateTimeField(_("Обновлена"), auto_now=True)
    last_activity_at = models.DateTimeField(_("Последняя активность"), default=timezone.now, db_index=True)
    is_archived = models.BooleanField(_("В архиве?"), default=False, db_index=True)

    class Meta:
        ordering = ('-last_activity_at',)
        verbose_name = _("Чат-комната")
        verbose_name_plural = _("Чат-комнаты")
        indexes = [
            models.Index(fields=['is_archived', 'private', '-last_activity_at']),
            models.Index(fields=['name']), # Индекс по имени для поиска/сортировки
        ]

    def __str__(self):
        return self.name

    def get_absolute_url(self):
        return reverse('room:room', kwargs={'slug': self.slug})

    def update_last_activity(self, timestamp=None):
        self.last_activity_at = timestamp or timezone.now()
        # Используем update вместо save для производительности и избежания рекурсии сигналов, если есть
        Room.objects.filter(pk=self.pk).update(last_activity_at=self.last_activity_at)


class Message(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    room = models.ForeignKey(Room, related_name='messages', on_delete=models.CASCADE, verbose_name=_("Комната"))
    user = models.ForeignKey(User, related_name='messages', on_delete=models.CASCADE, verbose_name=_("Пользователь")) # Если пользователь удален, его сообщения тоже
    content = models.TextField(_("Содержание"), blank=True) # Сообщение может быть только файлом
    file = models.FileField(_("Файл"), upload_to='chat_files/%Y/%m/%d/', null=True, blank=True, max_length=255) # max_length для длинных имен файлов
    date_added = models.DateTimeField(_("Добавлено"), default=timezone.now, db_index=True)
    edited_at = models.DateTimeField(_("Отредактировано"), null=True, blank=True)
    is_deleted = models.BooleanField(_("Удалено?"), default=False, db_index=True)
    reply_to = models.ForeignKey(
        'self',
        null=True, blank=True,
        on_delete=models.SET_NULL,
        related_name='replies',
        verbose_name=_("В ответ на")
    )

    class Meta:
        ordering = ('date_added',)
        verbose_name = _("Сообщение чата")
        verbose_name_plural = _("Сообщения чата")
        indexes = [
            models.Index(fields=['room', 'date_added']),
            models.Index(fields=['room', 'is_deleted', 'date_added']),
        ]

    def __str__(self):
        prefix = f"[{_('Удалено')}] " if self.is_deleted else ""
        user_name = self.user.username if self.user else _("System")
        content_preview = ""
        if self.file and not self.content:
            content_preview = f"[{_('Файл')}: {self.get_filename()}]"
        elif self.content:
            content_preview = f"'{self.content[:30]}...'" if len(self.content) > 30 else self.content
        
        if self.is_deleted: content_preview = "" # Если удалено, не показываем контент
        
        return f"{prefix}{user_name} ({self.date_added:%d.%m %H:%M}): {content_preview}"

    def get_filename(self):
        if self.file and hasattr(self.file, 'name'):
            return os.path.basename(self.file.name)
        return None

    def save(self, *args, **kwargs):
        is_new = self._state.adding
        super().save(*args, **kwargs)
        if is_new and self.room:
            self.room.update_last_activity(timestamp=self.date_added) # Обновляем активность временем сообщения


class MessageReadStatus(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(User, on_delete=models.CASCADE, verbose_name=_("Пользователь"))
    room = models.ForeignKey(Room, on_delete=models.CASCADE, verbose_name=_("Комната"))
    last_read_message = models.ForeignKey(
        Message,
        null=True, blank=True,
        on_delete=models.SET_NULL,
        verbose_name=_("Последнее прочитанное")
    )
    last_read_timestamp = models.DateTimeField(_("Время последнего прочтения"), auto_now=True)

    class Meta:
        unique_together = ('user', 'room')
        verbose_name = _("Статус прочтения")
        verbose_name_plural = _("Статусы прочтения")
        indexes = [
            models.Index(fields=['user', 'room', 'last_read_message']),
            models.Index(fields=['user', 'room', 'last_read_timestamp']), # Индекс по времени для быстрого поиска
        ]

    def __str__(self):
        msg_id_str = str(self.last_read_message_id)[:8] + "..." if self.last_read_message_id else 'N/A'
        return f"{self.user.username} in {self.room.name} read up to {msg_id_str}"


class Reaction(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    message = models.ForeignKey(Message, related_name='reactions', on_delete=models.CASCADE, verbose_name=_("Сообщение"))
    user = models.ForeignKey(User, related_name='reactions', on_delete=models.CASCADE, verbose_name=_("Пользователь"))
    emoji = models.CharField(_("Эмодзи"), max_length=50) # Unicode эмодзи могут быть длиннее 1 символа
    created_at = models.DateTimeField(_("Создано"), auto_now_add=True, db_index=True) # Индекс для сортировки

    class Meta:
        unique_together = ('message', 'user', 'emoji')
        ordering = ('created_at',)
        verbose_name = _("Реакция")
        verbose_name_plural = _("Реакции")
        indexes = [
            # models.Index(fields=['message', 'user', 'emoji']), # Уже покрывается unique_together
            models.Index(fields=['message', 'emoji', 'created_at']), # Для подсчета и сортировки по времени
        ]

    def __str__(self):
        user_name = self.user.username if self.user else '??'
        return f"{user_name} : {self.emoji} on MsgID {str(self.message_id)[:8]}..."