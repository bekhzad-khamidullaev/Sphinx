from django.conf import settings
from django.utils.translation import gettext_lazy as _
from django.utils import timezone
from django.dispatch import receiver
from django.db.models.signals import pre_save, post_save
from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from django.utils.crypto import get_random_string
from django.db import models, IntegrityError, transaction
from django.db.models import F
from unidecode import unidecode
import time
import logging
from user_profiles.models import TaskUserRole

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

# ------------------------ Категории и Подкатегории ------------------------

class TaskCategory(BaseModel):
    name = models.CharField(max_length=100, unique=True, verbose_name=_("Название категории"), db_index=True)
    description = models.TextField(blank=True, verbose_name=_("Описание категории"))
    last_assigned_team = models.ForeignKey("user_profiles.Team", on_delete=models.SET_NULL, null=True, blank=True, related_name="last_category_tasks")

    class Meta:
        verbose_name = _("Категория задач")
        verbose_name_plural = _("Категории задач")
        ordering = ["name"]
        indexes = [models.Index(fields=["name"], name="taskcategory_name_idx")]

    def __str__(self):
        return self.name

class TaskSubcategory(BaseModel):
    category = models.ForeignKey("tasks.TaskCategory", on_delete=models.CASCADE, related_name="subcategories", verbose_name=_("Категория"), db_index=True)
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

    campaign = models.ForeignKey("tasks.Campaign", on_delete=models.CASCADE, related_name="tasks", db_index=True)
    category = models.ForeignKey("tasks.TaskCategory", on_delete=models.SET_NULL, null=True, blank=True, related_name="tasks", db_index=True)
    subcategory = models.ForeignKey("tasks.TaskSubcategory", on_delete=models.SET_NULL, null=True, blank=True, related_name="tasks", db_index=True)
    task_number = models.CharField(max_length=20, unique=True, blank=True, verbose_name=_("Номер задачи"), db_index=True)
    description = models.TextField(verbose_name=_("Описание задачи"))
    # assignee = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="assigned_tasks", db_index=True)
    assignee = models.ForeignKey("user_profiles.User", on_delete=models.SET_NULL, null=True, blank=True, related_name="assigned_tasks", db_index=True)
    team = models.ForeignKey("user_profiles.Team", on_delete=models.SET_NULL, null=True, blank=True, related_name="tasks")
    photos = models.ManyToManyField("tasks.TaskPhoto", blank=True, related_name="tasks")
    status = models.CharField(max_length=20, choices=TASK_STATUS_CHOICES, default="new", db_index=True)
    priority = models.IntegerField(default=TaskPriority.MEDIUM, choices=TaskPriority.choices, db_index=True)
    deadline = models.DateTimeField(null=True, blank=True, db_index=True)
    start_date = models.DateTimeField(null=True, blank=True)
    completion_date = models.DateTimeField(null=True, blank=True)
    estimated_time = models.DurationField(null=True, blank=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="tasks_created", db_index=True)

    def save(self, *args, **kwargs):
        """Генерирует уникальный task_number перед сохранением"""
        if not self.task_number:
            attempt = 0
            while attempt < 10:
                self.task_number = self.generate_unique_task_number()
                if not Task.objects.filter(task_number=self.task_number).exists():
                    break
                attempt += 1

            if attempt >= 10:
                raise IntegrityError("Не удалось сгенерировать уникальный номер задачи после 10 попыток!")
            
        super().save(*args, **kwargs)

        # If task is assigned to a team, assign the team leader as the executor
        if self.team:
            leader = self.team.team_leader
            if leader:
                TaskUserRole.objects.get_or_create(task=self, user=leader, role=TaskUserRole.RoleChoices.EXECUTOR)

            # Assign all team members as watchers
            for member in self.team.members.exclude(id=leader.id):
                TaskUserRole.objects.get_or_create(task=self, user=member, role=TaskUserRole.RoleChoices.WATCHER)

        # If task is assigned, automatically assign the team based on the assignee's profile
        if self.assignee and not self.team:
            self.team = self.assignee.user_profile.team



    def generate_unique_task_number(self):
        """Generates the next unique task number with better guarantees."""
        if not self.campaign:
            raise ValueError("Cannot create task without a campaign!")

        campaign_code = unidecode(self.campaign.name).upper().replace(" ", "")[:4]
        if not campaign_code:
            campaign_code = "TASK"

        with transaction.atomic():
            last_task = Task.objects.filter(campaign=self.campaign).order_by("-id").first()
            next_number = 1

            if last_task and last_task.task_number:
                try:
                    last_number = int(last_task.task_number.split("-")[-1])
                    next_number = last_number + 1
                except ValueError:
                    pass

            task_number = f"{campaign_code}-{next_number:04d}"

            # Ensure the generated task number is unique before assigning it
            if Task.objects.filter(task_number=task_number).exists():
                raise IntegrityError("Failed to generate a unique task number after 10 attempts!")

            return task_number


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
    task = models.ForeignKey("tasks.Task", on_delete=models.CASCADE, related_name="task_photos", db_index=True)
    photo = models.ImageField(upload_to="task_photos/")
    uploaded_at = models.DateTimeField(auto_now_add=True)
    description = models.CharField(max_length=255, blank=True, verbose_name=_("Описание фотографии"))

    class Meta:
        verbose_name = _("Фотография к задаче")
        verbose_name_plural = _("Фотографии к задачам")
        ordering = ["-uploaded_at"]
        indexes = [models.Index(fields=["task"], name="taskphoto_task_idx")]

    def __str__(self):
        return f"Фото {self.task.task_number}"
