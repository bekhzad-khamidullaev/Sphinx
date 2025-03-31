from django.db import models
from django.contrib.auth.models import AbstractUser
from django.conf import settings
from django.utils.translation import gettext_lazy as _
from django.utils.timezone import now

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
    # Consider moving RoleChoices here if Role model is removed
    class RoleChoices(models.TextChoices):
        EXECUTOR = "executor", _("Исполнитель")
        WATCHER = "watcher", _("Наблюдатель")
        RESPONSIBLE = "responsible", _("Ответственный")
        # Add other roles as needed, e.g., REVIEWER, REPORTER

    # Use CASCADE carefully, maybe SET_NULL or PROTECT is better depending on requirements
    task = models.ForeignKey(
        "tasks.Task", # Use string notation to avoid import issues
        on_delete=models.CASCADE,
        related_name="user_roles",
        db_index=True,
        verbose_name=_("Задача")
        )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="task_roles",
        db_index=True,
        verbose_name=_("Пользователь")
        )
    role = models.CharField(
        max_length=20,
        choices=RoleChoices.choices,
        # default=RoleChoices.WATCHER, # Default might be WATCHER instead of EXECUTOR
        db_index=True,
        verbose_name=_("Роль")
        )

    # Add created_at/updated_at if needed, inheriting BaseModel is an option
    created_at = models.DateTimeField(auto_now_add=True, verbose_name=_("Дата назначения"))


    class Meta:
        verbose_name = _("Роль пользователя в задаче")
        verbose_name_plural = _("Роли пользователей в задачах")
        # Ensure a user can only have one role per task
        unique_together = ("task", "user") # Removed 'role' if user has only one role per task
        # If user can have multiple roles (e.g., watcher AND executor), keep role in unique_together
        # unique_together = ("task", "user", "role")

        indexes = [
             # Index for the unique constraint if role is included
             # models.Index(fields=["task", "user", "role"], name="taskuserrole_unique_role_idx"),
             # Index for the unique constraint if role is NOT included
              models.Index(fields=["task", "user"], name="taskuserrole_task_user_idx"),
             # Separate indexes for common lookups
             models.Index(fields=["task"], name="taskuserrole_task_idx"),
             models.Index(fields=["user"], name="taskuserrole_user_idx"),
        ]
        ordering = ['task', 'user'] # Default ordering

    def __str__(self):
         # Access related fields safely
        user_name = self.user.username if self.user else _("Unknown User")
        task_num = self.task.task_number if self.task else _("Unknown Task")
        return f"{user_name} - {self.get_role_display()} ({task_num})"
