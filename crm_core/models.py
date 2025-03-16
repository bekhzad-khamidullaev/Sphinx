from django.db import models
from django.conf import settings
from django.utils.translation import gettext_lazy as _
from django.utils import timezone
from django.dispatch import receiver
from django.db.models.signals import pre_save, post_save
from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
import logging

logger = logging.getLogger(__name__)

# ------------------------ Базовая Модель ------------------------

class BaseModel(models.Model):
    created_at = models.DateTimeField(auto_now_add=True, verbose_name=_("Дата создания"))
    updated_at = models.DateTimeField(auto_now=True, verbose_name=_("Дата обновления"))

    class Meta:
        abstract = True

# ------------------------ Кампании ------------------------

class Campaign(BaseModel):
    name = models.CharField(max_length=200, verbose_name=_("Название кампании"), db_index=True)
    description = models.TextField(blank=True, verbose_name=_("Описание кампании"))
    start_date = models.DateField(null=True, blank=True, verbose_name=_("Дата начала"))
    end_date = models.DateField(null=True, blank=True, verbose_name=_("Дата завершения"))

    class Meta:
        verbose_name = _("Кампания")
        verbose_name_plural = _("Кампании")
        ordering = ["name", "-created_at"]
        indexes = [models.Index(fields=["name"], name="campaign_name_idx")]

    def __str__(self):
        return self.name

# ------------------------ Команды ------------------------

class Team(BaseModel):
    name = models.CharField(max_length=100, verbose_name=_("Название команды"), db_index=True)
    team_leader = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="teams_managed")
    members = models.ManyToManyField(settings.AUTH_USER_MODEL, blank=True, related_name="teams_member")
    description = models.TextField(blank=True, verbose_name=_("Описание команды"))
    task_categories = models.ManyToManyField("crm_core.TaskCategory", blank=True, related_name="teams")

    class Meta:
        verbose_name = _("Команда")
        verbose_name_plural = _("Команды")
        ordering = ["name"]
        indexes = [models.Index(fields=["name"], name="team_name_idx")]

    def __str__(self):
        return self.name

# ------------------------ Категории и Подкатегории ------------------------

class TaskCategory(BaseModel):
    name = models.CharField(max_length=100, unique=True, verbose_name=_("Название категории"), db_index=True)
    description = models.TextField(blank=True, verbose_name=_("Описание категории"))
    last_assigned_team = models.ForeignKey("crm_core.Team", on_delete=models.SET_NULL, null=True, blank=True, related_name="last_category_tasks")

    class Meta:
        verbose_name = _("Категория задач")
        verbose_name_plural = _("Категории задач")
        ordering = ["name"]
        indexes = [models.Index(fields=["name"], name="taskcategory_name_idx")]

    def __str__(self):
        return self.name

class TaskSubcategory(BaseModel):
    category = models.ForeignKey(TaskCategory, on_delete=models.CASCADE, related_name="subcategories", verbose_name=_("Категория"), db_index=True)
    name = models.CharField(max_length=100, verbose_name=_("Название подкатегории"), db_index=True)
    description = models.TextField(blank=True, verbose_name=_("Описание подкатегории"))

    class Meta:
        verbose_name = _("Подкатегория задач")
        verbose_name_plural = _("Подкатегории задач")
        ordering = ["category", "name"]
        indexes = [
            models.Index(fields=["category", "name"], name="subcat_catname_idx"),
            models.Index(fields=["name"], name="tasksubcategory_name_idx"),
        ]

    def __str__(self):
        return f"{self.category.name} - {self.name}"

# ------------------------ Задачи ------------------------

class Task(BaseModel):
    class TaskPriority(models.IntegerChoices):
        HIGH = 1, _("Высокий")
        MEDIUM_HIGH = 2, _("Выше среднего")
        MEDIUM = 3, _("Средний")
        MEDIUM_LOW = 4, _("Ниже среднего")
        LOW = 5, _("Низкий")

    TASK_STATUS_CHOICES = [
        ("new", _("Новая")),
        ("in_progress", _("В работе")),
        ("on_hold", _("Отложена")),
        ("completed", _("Выполнена")),
        ("cancelled", _("Отменена")),
        ("overdue", _("Просрочена")),
    ]

    campaign = models.ForeignKey("crm_core.Campaign", on_delete=models.CASCADE, related_name="tasks", db_index=True)
    category = models.ForeignKey("crm_core.TaskCategory", on_delete=models.SET_NULL, null=True, blank=True, related_name="tasks", db_index=True)
    subcategory = models.ForeignKey("crm_core.TaskSubcategory", on_delete=models.SET_NULL, null=True, blank=True, related_name="tasks", db_index=True)
    task_number = models.CharField(max_length=20, unique=True, blank=True, verbose_name=_("Номер задачи"), db_index=True)
    description = models.TextField(verbose_name=_("Описание задачи"))
    assignee = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="assigned_tasks", db_index=True)
    team = models.ForeignKey("crm_core.Team", on_delete=models.SET_NULL, null=True, blank=True, related_name="tasks", db_index=True)
    status = models.CharField(max_length=20, choices=TASK_STATUS_CHOICES, default="new", db_index=True)
    priority = models.IntegerField(default=TaskPriority.MEDIUM, choices=TaskPriority.choices, db_index=True)
    deadline = models.DateTimeField(null=True, blank=True, db_index=True)
    start_date = models.DateTimeField(null=True, blank=True)
    completion_date = models.DateTimeField(null=True, blank=True)
    estimated_time = models.DurationField(null=True, blank=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="tasks_created", db_index=True)

    class Meta:
        verbose_name = _("Задача")
        verbose_name_plural = _("Задачи")
        ordering = ["priority", "deadline", "-created_at"]
        indexes = [
            models.Index(fields=["task_number"], name="task_task_number_idx"),
            models.Index(fields=["status"], name="task_status_idx"),
            models.Index(fields=["priority"], name="task_priority_idx"),
        ]

    def __str__(self):
        return f"{self.task_number} - {self.campaign.name} - {self.description[:50]}"

# ------------------------ Фотографии ------------------------

class TaskPhoto(BaseModel):
    task = models.ForeignKey(Task, on_delete=models.CASCADE, related_name="task_photos", db_index=True)
    photo = models.ImageField(upload_to="task_photos/")
    uploaded_at = models.DateTimeField(auto_now_add=True)
    description = models.CharField(
        max_length=255,
        blank=True,
        verbose_name=_("Описание фотографии"),
        help_text=_("Добавьте описание к фотографии (необязательно)."),
    )
    class Meta:
        verbose_name = _("Фотография к задаче")
        verbose_name_plural = _("Фотографии к задачам")
        ordering = ["-uploaded_at"]
        indexes = [models.Index(fields=["task"], name="taskphoto_task_idx")]

    def __str__(self):
        return f"Фото {self.task.task_number}"

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

    task = models.ForeignKey(Task, on_delete=models.CASCADE, related_name="user_roles", db_index=True)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="task_roles", db_index=True)
    role = models.CharField(max_length=20, choices=RoleChoices.choices, default=RoleChoices.EXECUTOR, db_index=True)

    class Meta:
        verbose_name = _("Роль пользователя в задаче")
        verbose_name_plural = _("Роли пользователей в задачах")
        unique_together = ("task", "user", "role")
        indexes = [models.Index(fields=["task", "user", "role"], name="taskuserrole_unique_role_idx")]

    def __str__(self):
        return f"{self.user.username} - {self.get_role_display()} ({self.task.task_number})"