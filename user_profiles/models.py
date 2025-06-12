# user_profiles/models.py
import logging
from django.contrib.auth.models import AbstractUser, Permission
from django.db import models
from django.conf import settings
from django.utils.translation import gettext_lazy as _
from django.db.models import JSONField
from django.urls import reverse
from django.core.exceptions import ValidationError, PermissionDenied

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
        return reverse('user_profiles:department_update', kwargs={'pk': self.pk})

    def clean(self):
        super().clean()
        if self.parent and self.parent.pk == self.pk:
            raise ValidationError(_('Отдел не может быть сам себе родительским.'))
        p = self.parent
        while p:
            if p.pk == self.pk:
                raise ValidationError(_('Обнаружена циклическая зависимость в родительских отделах.'))
            p = p.parent

    def save(self, *args, **kwargs):
        is_new = self._state.adding
        self.full_clean()
        super().save(*args, **kwargs)
        try:
            channel_layer = get_channel_layer()
            if channel_layer:
                action = "create" if is_new else "update"
                async_to_sync(channel_layer.group_send)(
                    "departments_list",
                    {"type": "department_update", "message": {"action": action, "id": self.id, "name": self.name}}
                )
            else:
                logger.warning("Channel layer not configured, WebSocket notification for Department skipped.")
        except Exception as e:
            logger.error(f"Failed to send WebSocket for Department {self.id}: {e}")

    def delete(self, *args, **kwargs):
        dept_id = self.id
        dept_name = self.name
        super().delete(*args, **kwargs)
        try:
            channel_layer = get_channel_layer()
            if channel_layer:
                async_to_sync(channel_layer.group_send)(
                    "departments_list",
                    {"type": "department_update", "message": {"action": "delete", "id": dept_id, "name": dept_name}}
                )
            else:
                logger.warning("Channel layer not configured, WebSocket deletion notification for Department skipped.")
        except Exception as e:
            logger.error(f"Failed to send WebSocket deletion for Department {dept_id}: {e}")


class JobTitle(models.Model):
    name = models.CharField(max_length=150, unique=True, verbose_name=_("Название должности"))
    description = models.TextField(blank=True, verbose_name=_("Описание должности"))

    class Meta:
        verbose_name = _("Должность")
        verbose_name_plural = _("Должности")
        ordering = ["name"]

    def __str__(self):
        return self.name

class Role(models.Model):
    name = models.CharField(max_length=150, unique=True, verbose_name=_('Название роли'))
    permissions = models.ManyToManyField(Permission, blank=True, verbose_name=_('Права'))
    description = models.TextField(blank=True, verbose_name=_('Описание'))

    class Meta:
        verbose_name = _('Роль')
        verbose_name_plural = _('Роли')
        ordering = ['name']

    def __str__(self):
        return self.name

class TeamMembershipUser(models.Model):
    user = models.ForeignKey("User", on_delete=models.CASCADE, related_name="teammembership_user_set")
    team = models.ForeignKey("Team", on_delete=models.CASCADE, related_name="teammembership_team_set")
    date_joined = models.DateTimeField(auto_now_add=True, verbose_name=_("Дата присоединения"))

    class Meta:
        unique_together = ('user', 'team')
        verbose_name = _("Членство в команде (User-Team)")
        verbose_name_plural = _("Членства в командах (User-Team)")
        ordering = ['team__name', 'user__username']

    def __str__(self):
        return f"{self.user.username} in {self.team.name}"


class User(AbstractUser):
    email = models.EmailField(_('email address'), unique=True)
    phone_number = models.CharField(_("Номер телефона"), max_length=25, blank=True, null=True)
    image = models.ImageField(_("Аватар"), default='profile_pics/user.svg', upload_to='profile_pics/', blank=True, null=True)
    department = models.ForeignKey(
        Department, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='employees', verbose_name=_("Отдел")
    )
    job_title = models.ForeignKey(
        JobTitle, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="users", verbose_name=_("Должность")
    )
    settings = JSONField(_("Настройки пользователя"), default=dict, blank=True)
    teams = models.ManyToManyField(
        'Team',
        through=TeamMembershipUser,
        through_fields=('user', 'team'),
        verbose_name=_("Состоит в командах"),
        blank=True,
        related_name="team_members_reverse"
    )
    roles = models.ManyToManyField(
        Role,
        verbose_name=_('Роли'),
        blank=True,
        related_name='users'
    )

    class Meta:
        verbose_name = _("Пользователь")
        verbose_name_plural = _("Пользователи")
        ordering = ['last_name', 'first_name', 'username']

    def __str__(self):
        return self.display_name

    @property
    def display_name(self):
        if self.first_name and self.last_name:
            return f"{self.first_name} {self.last_name}"
        return self.username

    def get_absolute_url(self):
        return reverse('user_profiles:user_update', kwargs={'pk': self.pk})

    def get_setting(self, key, default=None):
        if not isinstance(self.settings, dict):
            self.settings = {}
        return self.settings.get(key, default)

    def set_setting(self, key, value, save_now=True):
        if not isinstance(self.settings, dict):
            self.settings = {}
        current_value = self.settings.get(key)
        setting_changed = False
        if current_value != value:
            self.settings[key] = value
            setting_changed = True
        elif key not in self.settings and value is not None:
            self.settings[key] = value
            setting_changed = True

        if setting_changed and save_now:
            self.save(update_fields=['settings'])
        return setting_changed


    def save(self, *args, **kwargs):
        is_new = self._state.adding
        if self.email:
            self.email = self.email.lower()
        
        if not is_new and self.pk:
            try:
                old_instance = User.objects.get(pk=self.pk)
                if old_instance.is_superuser and not self.is_superuser:
                    if User.objects.filter(is_superuser=True).exclude(pk=self.pk).count() == 0:
                        logger.warning(f"Attempt to remove superuser status from the last superuser {self.username} via model save. Reverting.")
                        self.is_superuser = True
            except User.DoesNotExist:
                pass
        
        super().save(*args, **kwargs)
        
        try:
            channel_layer = get_channel_layer()
            if channel_layer:
                action = "create" if is_new else "update"
                async_to_sync(channel_layer.group_send)(
                    "users_list",
                    {"type": "user_update", "message": {
                        "action": action, "id": self.id, "username": self.username,
                        "display_name": self.display_name, "is_active": self.is_active
                    }}
                )
                async_to_sync(channel_layer.group_send)(
                    f"user_{self.id}",
                    {"type": "user_profile_update", "message": {
                        "action": action, "id": self.id, "username": self.username,
                        "display_name": self.display_name, "email": self.email,
                        "job_title": self.job_title.name if self.job_title else None,
                        "department": self.department.name if self.department else None,
                        "image_url": self.image.url if self.image else None,
                    }}
                )
            else:
                logger.warning("Channel layer not configured, WebSocket notification for User skipped.")
        except Exception as e:
            logger.error(f"Failed to send WebSocket for User {self.id}: {e}")

    def delete(self, *args, **kwargs):
        user_id = self.id
        username = self.username
        is_last_superuser = False
        if self.is_superuser:
            if User.objects.filter(is_superuser=True).exclude(pk=self.pk).count() == 0:
                is_last_superuser = True
        
        if is_last_superuser:
            logger.error(f"Attempt to delete the last superuser: {username}. Operation aborted.")
            raise PermissionDenied(_("Нельзя удалить единственного суперпользователя в системе."))

        super().delete(*args, **kwargs)
        try:
            channel_layer = get_channel_layer()
            if channel_layer:
                async_to_sync(channel_layer.group_send)(
                    "users_list",
                    {"type": "user_update", "message": {"action": "delete", "id": user_id, "username": username}}
                )
                async_to_sync(channel_layer.group_send)(
                    f"user_{user_id}",
                    {"type": "user_profile_update", "message": {"action": "delete", "id": user_id}}
                )
            else:
                logger.warning("Channel layer not configured, WebSocket deletion notification for User skipped.")
        except Exception as e:
            logger.error(f"Failed to send WebSocket deletion for User {user_id}: {e}")


class Team(BaseModel):
    name = models.CharField(max_length=100, verbose_name=_("Название команды"), unique=True)
    team_leader = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="led_teams", verbose_name=_("Лидер команды")
    )
    members = models.ManyToManyField(
        settings.AUTH_USER_MODEL,
        through=TeamMembershipUser,
        through_fields=('team', 'user'),
        blank=True,
        verbose_name=_("Участники"),
        related_name="teams_where_user_is_member"
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
        return reverse('user_profiles:team_update', kwargs={'pk': self.pk})

    def save(self, *args, **kwargs):
        is_new = self._state.adding
        super().save(*args, **kwargs)
        try:
            channel_layer = get_channel_layer()
            if channel_layer:
                action = "create" if is_new else "update"
                async_to_sync(channel_layer.group_send)(
                    "teams_list",
                    {"type": "team_update", "message": {"action": action, "id": self.id, "name": self.name}}
                )
            else:
                logger.warning("Channel layer not configured, WebSocket notification for Team skipped.")
        except Exception as e:
            logger.error(f"Failed to send WebSocket for Team {self.id}: {e}")

    def delete(self, *args, **kwargs):
        team_id = self.id
        team_name = self.name
        super().delete(*args, **kwargs)
        try:
            channel_layer = get_channel_layer()
            if channel_layer:
                async_to_sync(channel_layer.group_send)(
                    "teams_list",
                    {"type": "team_update", "message": {"action": "delete", "id": team_id, "name": team_name}}
                )
            else:
                logger.warning("Channel layer not configured, WebSocket deletion notification for Team skipped.")
        except Exception as e:
            logger.error(f"Failed to send WebSocket deletion for Team {team_id}: {e}")
    def clean(self):
        super().clean()
        if self.team_leader and not self.members.filter(pk=self.team_leader.pk).exists():
            raise ValidationError(_("Лидер команды должен быть участником команды."))
        if self.department and self.department.head and self.department.head != self.team_leader:
            raise ValidationError(_("Лидер команды должен быть руководителем отдела, если указан отдел."))
        if self.members.count() == 0:
            raise ValidationError(_("Команда должна иметь хотя бы одного участника."))