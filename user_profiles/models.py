# user_profiles/models.py
import logging
from django.contrib.auth.models import AbstractUser, Group, Permission # Import Group and Permission
from django.db import models
from django.conf import settings
from django.utils.translation import gettext_lazy as _
from django.db.models import JSONField

logger = logging.getLogger(__name__)

# --- Base Model ---
class BaseModel(models.Model):
    created_at = models.DateTimeField(auto_now_add=True, verbose_name=_("Дата создания"))
    updated_at = models.DateTimeField(auto_now=True, verbose_name=_("Дата обновления"))

    class Meta:
        abstract = True
        ordering = ['-created_at']

# --- Department ---
class Department(BaseModel):
    """Represents a department or unit within the company structure."""
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
        indexes = [ models.Index(fields=["name"]), models.Index(fields=["parent"]), ]

    def __str__(self):
        return self.name

# --- Job Title Model (New) ---
class JobTitle(models.Model):
    """Represents a descriptive job title within the organization."""
    name = models.CharField(max_length=150, unique=True, verbose_name=_("Название должности"))
    description = models.TextField(blank=True, verbose_name=_("Описание должности"))
    # Optional: Add level or category if needed

    class Meta:
        verbose_name = _("Должность")
        verbose_name_plural = _("Должности")
        ordering = ["name"]

    def __str__(self):
        return self.name

# --- Custom User Model ---
class User(AbstractUser):
    """Extended user model integrating with structure and job titles."""
    # Use email as the unique identifier? Set USERNAME_FIELD = 'email'
    # and add 'username' to REQUIRED_FIELDS if so.
    email = models.EmailField(_('email address'), unique=True) # Email should be unique
    phone_number = models.CharField(_("Номер телефона"), max_length=25, blank=True, null=True)
    # Removed the direct job_title CharField, using ForeignKey instead
    image = models.ImageField(_("Аватар"), default='profile_pics/user.svg', upload_to='profile_pics/', blank=True)
    department = models.ForeignKey(
        Department, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='employees', verbose_name=_("Отдел")
    )
    # Link to the new JobTitle model
    job_title = models.ForeignKey(
         JobTitle, on_delete=models.SET_NULL, null=True, blank=True,
         related_name="users", verbose_name=_("Должность")
    )
    # REMOVED: primary_role ForeignKey to the old Role model

    # Django's built-in 'groups' ManyToManyField (inherited from AbstractUser)
    # will be used for assigning permission roles (Django Groups).

    settings = JSONField(_("Настройки пользователя"), default=dict, blank=True)

    USERNAME_FIELD = 'username' # Or 'email'
    REQUIRED_FIELDS = ['email'] # Make email required during createsuperuser

    class Meta:
        verbose_name = _("Пользователь")
        verbose_name_plural = _("Пользователи")
        ordering = ['last_name', 'first_name', 'username']

    def __str__(self):
        return self.display_name

    @property
    def display_name(self):
         """Returns full name, falls back to username."""
         if self.first_name and self.last_name:
             return f"{self.first_name} {self.last_name}"
         return self.username

    def get_setting(self, key, default=None):
        if not isinstance(self.settings, dict): self.settings = {}
        return self.settings.get(key, default)

    def set_setting(self, key, value):
        if not isinstance(self.settings, dict): self.settings = {}
        self.settings[key] = value
        self.save(update_fields=['settings'])

# --- Teams ---
class Team(BaseModel):
    """Represents a working team."""
    name = models.CharField(max_length=100, verbose_name=_("Название команды"), unique=True)
    team_leader = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="led_teams", verbose_name=_("Лидер команды")
    )
    members = models.ManyToManyField(
        User, blank=True, related_name="teams",
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
        indexes = [ models.Index(fields=["name"]), models.Index(fields=["department"]), ]

    def __str__(self):
        return self.name

# --- Task-Specific User Roles ---
class TaskUserRole(BaseModel):
    """Defines a user's specific role within a particular task."""
    class RoleChoices(models.TextChoices):
        RESPONSIBLE = "responsible", _("Ответственный")
        EXECUTOR = "executor", _("Исполнитель")
        WATCHER = "watcher", _("Наблюдатель")

    task = models.ForeignKey(
        "tasks.Task", on_delete=models.CASCADE,
        related_name="user_roles", verbose_name=_("Задача"), db_index=True
    )
    user = models.ForeignKey(
        User, on_delete=models.CASCADE,
        related_name="task_roles", verbose_name=_("Пользователь"), db_index=True
    )
    role = models.CharField(
        max_length=20, choices=RoleChoices.choices,
        verbose_name=_("Роль в задаче"), db_index=True
    )

    class Meta:
        verbose_name = _("Роль пользователя в задаче")
        verbose_name_plural = _("Роли пользователей в задачах")
        # User can only have one role per task with this constraint
        unique_together = ("task", "user")
        ordering = ['task', 'user']
        indexes = [
            models.Index(fields=["task", "user"]),
            models.Index(fields=["task", "role"]),
            models.Index(fields=["user", "role"]),
        ]

    def __str__(self):
        task_display = getattr(self.task, 'task_number', f"Task {self.task_id}")
        user_display = getattr(self.user, 'display_name', f"User {self.user_id}")
        return f"{user_display} - {self.get_role_display()} в {task_display}"