# user_profiles/models.py
import logging
from django.contrib.auth.models import AbstractUser
from django.db import models
from django.conf import settings # For AUTH_USER_MODEL
from django.utils.translation import gettext_lazy as _
from django.db.models import JSONField # For user settings
from django.urls import reverse

# For WebSocket notifications
from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer

logger = logging.getLogger(__name__)

class BaseModel(models.Model):
    created_at = models.DateTimeField(auto_now_add=True, verbose_name=_("Дата создания"))
    updated_at = models.DateTimeField(auto_now=True, verbose_name=_("Дата обновления"))

    class Meta:
        abstract = True
        ordering = ['-created_at']

class Department(BaseModel):
    name = models.CharField(max_length=150, unique=True, verbose_name=_("Название отдела"))
    parent = models.ForeignKey(
        'self', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='children', verbose_name=_("Вышестоящий отдел")
    )
    head = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='headed_departments', verbose_name=_("Руководитель отдела")
    )
    description = models.TextField(blank=True, verbose_name=_("Описание"))

    class Meta:
        verbose_name = _("Отдел")
        verbose_name_plural = _("Отделы")
        ordering = ['name']
        indexes = [models.Index(fields=["name"]), models.Index(fields=["parent"])]

    def __str__(self):
        return self.name

    def get_absolute_url(self):
        # Assuming you might have a detail view for departments
        return reverse('user_profiles:department_detail', kwargs={'pk': self.pk}) # Update URL name if needed

    def save(self, *args, **kwargs):
        is_new = self._state.adding
        super().save(*args, **kwargs)
        # WebSocket notification
        try:
            channel_layer = get_channel_layer()
            action = "create" if is_new else "update"
            async_to_sync(channel_layer.group_send)(
                "departments_list", # Generic group for department list updates
                {"type": "department_update", "message": {"action": action, "id": self.id, "name": self.name}}
            )
        except Exception as e:
            logger.error(f"Failed to send WebSocket for Department {self.id}: {e}")

    def delete(self, *args, **kwargs):
        dept_id = self.id
        dept_name = self.name
        super().delete(*args, **kwargs)
        try:
            channel_layer = get_channel_layer()
            async_to_sync(channel_layer.group_send)(
                "departments_list",
                {"type": "department_update", "message": {"action": "delete", "id": dept_id, "name": dept_name}}
            )
        except Exception as e:
            logger.error(f"Failed to send WebSocket deletion for Department {dept_id}: {e}")


class JobTitle(models.Model): # Not inheriting BaseModel for simplicity, can be added
    name = models.CharField(max_length=150, unique=True, verbose_name=_("Название должности"))
    description = models.TextField(blank=True, verbose_name=_("Описание должности"))

    class Meta:
        verbose_name = _("Должность")
        verbose_name_plural = _("Должности")
        ordering = ["name"]

    def __str__(self):
        return self.name


class User(AbstractUser):
    email = models.EmailField(_('email address'), unique=True) # Enforce unique email
    phone_number = models.CharField(_("Номер телефона"), max_length=25, blank=True, null=True)
    image = models.ImageField(_("Аватар"), default='profile_pics/user.svg', upload_to='profile_pics/', blank=True, null=True) # Allow null
    department = models.ForeignKey(
        Department, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='employees', verbose_name=_("Отдел")
    )
    job_title = models.ForeignKey(
         JobTitle, on_delete=models.SET_NULL, null=True, blank=True,
         related_name="users", verbose_name=_("Должность")
    )
    settings = JSONField(_("Настройки пользователя"), default=dict, blank=True)

    class Meta:
        verbose_name = _("Пользователь")
        verbose_name_plural = _("Пользователи")
        ordering = ['last_name', 'first_name', 'username']
        # db_table = 'auth_user' # If you want to keep the default table name, though not recommended for major changes

    def __str__(self):
        return self.display_name

    @property
    def display_name(self):
         if self.first_name and self.last_name:
             return f"{self.first_name} {self.last_name}"
         return self.username

    def get_absolute_url(self):
        # Assuming you have a user detail/update view in user_profiles
        return reverse('user_profiles:user_update', kwargs={'pk': self.pk}) # Or a public profile view

    def get_setting(self, key, default=None):
        if not isinstance(self.settings, dict): self.settings = {}
        return self.settings.get(key, default)

    def set_setting(self, key, value, save_now=True):
        if not isinstance(self.settings, dict): self.settings = {}
        if self.settings.get(key) != value:
            self.settings[key] = value
            if save_now:
                self.save(update_fields=['settings'])
            return True # Indicates a change was made
        return False # No change

    def save(self, *args, **kwargs):
        is_new = self._state.adding
        super().save(*args, **kwargs)
        try:
            channel_layer = get_channel_layer()
            action = "create" if is_new else "update"
            async_to_sync(channel_layer.group_send)(
                "users_list", # General group for user list updates
                {"type": "user_update", "message": {
                    "action": action, "id": self.id, "username": self.username,
                    "display_name": self.display_name, "is_active": self.is_active
                    # Add other relevant fields for list view updates
                }}
            )
            # For specific user updates (e.g., profile page)
            async_to_sync(channel_layer.group_send)(
                 f"user_{self.id}",
                 {"type": "user_profile_update", "message": { # More detailed message
                     "action": action, "id": self.id, "username": self.username,
                     "display_name": self.display_name, "email": self.email,
                     "job_title": self.job_title.name if self.job_title else None,
                     "department": self.department.name if self.department else None,
                     "image_url": self.image.url if self.image else None,
                 }}
            )
        except Exception as e:
            logger.error(f"Failed to send WebSocket for User {self.id}: {e}")

    def delete(self, *args, **kwargs):
        user_id = self.id
        username = self.username
        super().delete(*args, **kwargs)
        try:
            channel_layer = get_channel_layer()
            async_to_sync(channel_layer.group_send)(
                "users_list",
                {"type": "user_update", "message": {"action": "delete", "id": user_id, "username": username}}
            )
            async_to_sync(channel_layer.group_send)(
                 f"user_{user_id}", # Notify specific user channel if they are being deleted
                 {"type": "user_profile_update", "message": {"action": "delete", "id": user_id}}
            )
        except Exception as e:
            logger.error(f"Failed to send WebSocket deletion for User {user_id}: {e}")


class Team(BaseModel):
    name = models.CharField(max_length=100, verbose_name=_("Название команды"), unique=True)
    team_leader = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="led_teams", verbose_name=_("Лидер команды")
    )
    members = models.ManyToManyField(
        settings.AUTH_USER_MODEL, blank=True, related_name="teams",
        verbose_name=_("Участники")
    )
    department = models.ForeignKey(
        Department, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='teams', verbose_name=_("Отдел")
    )
    description = models.TextField(blank=True, verbose_name=_("Описание команды"))

    class Meta:
        verbose_name = _("Команда")
        verbose_name_plural = _("Команды")
        ordering = ["name"]
        indexes = [models.Index(fields=["name"]), models.Index(fields=["department"])]

    def __str__(self):
        return self.name

    def get_absolute_url(self):
        return reverse('user_profiles:team_detail', kwargs={'pk': self.pk}) # Update URL name if needed

    def save(self, *args, **kwargs):
        is_new = self._state.adding
        super().save(*args, **kwargs)
        try:
            channel_layer = get_channel_layer()
            action = "create" if is_new else "update"
            async_to_sync(channel_layer.group_send)(
                "teams_list",
                {"type": "team_update", "message": {"action": action, "id": self.id, "name": self.name}}
            )
        except Exception as e:
            logger.error(f"Failed to send WebSocket for Team {self.id}: {e}")

    def delete(self, *args, **kwargs):
        team_id = self.id
        team_name = self.name
        super().delete(*args, **kwargs)
        try:
            channel_layer = get_channel_layer()
            async_to_sync(channel_layer.group_send)(
                "teams_list",
                {"type": "team_update", "message": {"action": "delete", "id": team_id, "name": team_name}}
            )
        except Exception as e:
            logger.error(f"Failed to send WebSocket deletion for Team {team_id}: {e}")