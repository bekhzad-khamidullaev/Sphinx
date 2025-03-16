from django.db import models
from django.contrib.auth.models import AbstractUser
from django.conf import settings
from django.utils.translation import gettext_lazy as _

# ------------------------ Базовая Модель ------------------------

class BaseModel(models.Model):
    created_at = models.DateTimeField(auto_now_add=True, verbose_name=_("Дата создания"))
    updated_at = models.DateTimeField(auto_now=True, verbose_name=_("Дата обновления"))

    class Meta:
        abstract = True

# ------------------------ Модель пользователя ------------------------

class User(AbstractUser):
    # Убираем поле profile, так как оно может быть лишним, если вы используете UserProfile
    image = models.ImageField(default='profile_pics/user.svg', upload_to='profile_pics/')

class UserProfile(models.Model):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='user_profile')
    team = models.ForeignKey('user_profiles.Team', on_delete=models.SET_NULL, null=True, blank=True)

    def __str__(self):
        return self.user.username

# ------------------------ Команды ------------------------

class Team(BaseModel):
    name = models.CharField(max_length=100, verbose_name=_("Название команды"))
    team_leader = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="teams_managed")
    members = models.ManyToManyField(settings.AUTH_USER_MODEL, blank=True, related_name="teams_member")
    description = models.TextField(blank=True, verbose_name=_("Описание команды"))

    class Meta:
        verbose_name = _("Команда")
        verbose_name_plural = _("Команды")
        ordering = ["name"]

    def __str__(self):
        return self.name

# ------------------------ Роли ------------------------

class Role(models.Model):
    name = models.CharField(max_length=50, unique=True, verbose_name=_("Название роли"), db_index=True)

    class Meta:
        verbose_name = _("Роль")
        verbose_name_plural = _("Роли")
        ordering = ["name"]
        indexes = [models.Index(fields=["name"], name="role_name_idx")]

    def __str__(self):
        return self.name

# ------------------------ Роли пользователей в задачах ------------------------

class TaskUserRole(models.Model):
    class RoleChoices(models.TextChoices):
        EXECUTOR = "executor", _("Исполнитель")
        WATCHER = "watcher", _("Наблюдатель")
        RESPONSIBLE = "responsible", _("Ответственный")

    task = models.ForeignKey("crm_core.Task", on_delete=models.CASCADE, related_name="user_roles", db_index=True)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="task_roles", db_index=True)
    role = models.CharField(max_length=20, choices=RoleChoices.choices, default=RoleChoices.EXECUTOR, db_index=True)

    class Meta:
        verbose_name = _("Роль пользователя в задаче")
        verbose_name_plural = _("Роли пользователей в задачах")
        unique_together = ("task", "user", "role")
        indexes = [models.Index(fields=["task", "user", "role"], name="taskuserrole_unique_role_idx")]

    def __str__(self):
        return f"{self.user.username} - {self.get_role_display()} ({self.task.task_number})"

