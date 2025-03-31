from django.conf import settings
from django.core.exceptions import ValidationError  # Correct import
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

    def __str__(self):
        return f"{self.id} - {self.created_at}"


# ------------------------ Кампании ------------------------

class Project(BaseModel):
    name = models.CharField(max_length=200, verbose_name=_("Название кампании"), db_index=True)
    description = models.TextField(blank=True, verbose_name=_("Описание кампании"))
    start_date = models.DateField(null=True, blank=True, verbose_name=_("Дата начала"))
    end_date = models.DateField(null=True, blank=True, verbose_name=_("Дата завершения"))
    channel_layer = get_channel_layer()

    def clean(self):
        """Проверяет, что дата завершения не раньше даты начала."""
        if self.start_date and self.end_date and self.start_date > self.end_date:
            raise ValidationError(_("Дата завершения не может быть раньше даты начала."))

    def save(self, *args, **kwargs):
        """Отправка уведомления по WebSocket при создании/обновлении кампании."""
        self.clean()
        is_new = self._state.adding
        super().save(*args, **kwargs)

        action = "create" if is_new else "update"
        async_to_sync(self.channel_layer.group_send)(
            "projects", {"type": "updateProjects", "message": {"action": action, "id": self.id, "name": self.name}}
        )

    def delete(self, *args, **kwargs):
        """Отправка уведомления по WebSocket при удалении кампании."""
        async_to_sync(self.channel_layer.group_send)(
            "projects", {"type": "updateProjects", "message": {"action": "delete", "id": self.id}}
        )
        super().delete(*args, **kwargs)

    def get_absolute_url(self):
        """Возвращает URL для просмотра кампании."""
        from django.urls import reverse
        return reverse("tasks:project_detail", kwargs={"pk": self.pk})

    class Meta:
        verbose_name = _("Кампания")
        verbose_name_plural = _("Кампании")
        ordering = ["name", "-created_at"]
        indexes = [models.Index(fields=["name"], name="project_name_idx")]

    def __str__(self):
        return self.name


# ------------------------ Категории и Подкатегории ------------------------

class TaskCategory(BaseModel):
    name = models.CharField(max_length=100, unique=True, verbose_name=_("Название категории"), db_index=True)
    description = models.TextField(blank=True, verbose_name=_("Описание категории"))
    last_assigned_team = models.ForeignKey("user_profiles.Team", on_delete=models.SET_NULL, null=True, blank=True, related_name="last_category_tasks")
    channel_layer = get_channel_layer()

    def clean(self):
        """Проверяет, что название категории уникально."""
        if TaskCategory.objects.filter(name=self.name).exclude(id=self.id).exists():
            raise ValidationError(_("Категория с таким названием уже существует."))

    def save(self, *args, **kwargs):
        """Отправка уведомления по WebSocket при создании/обновлении категории."""
        self.clean()
        is_new = self._state.adding
        super().save(*args, **kwargs)

        action = "create" if is_new else "update"
        async_to_sync(self.channel_layer.group_send)(
            "categories", {"type": "updateData", "message": {"action": action, "id": self.id, "name": self.name}}
        )

    def delete(self, *args, **kwargs):
        """Отправка уведомления по WebSocket при удалении категории."""
        async_to_sync(self.channel_layer.group_send)(
            "categories", {"type": "updateData", "message": {"action": "delete", "id": self.id}}
        )
        super().delete(*args, **kwargs)

    def get_absolute_url(self):
        """Возвращает URL для просмотра категории."""
        from django.urls import reverse
        return reverse("tasks:category_detail", kwargs={"pk": self.pk})

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
    last_assigned_team = models.ForeignKey("user_profiles.Team", on_delete=models.SET_NULL, null=True, blank=True, related_name="last_subcategory_tasks")
    channel_layer = get_channel_layer()

    def clean(self):
        """Проверяет, что подкатегория уникальна в рамках категории."""
        if TaskSubcategory.objects.filter(category=self.category, name=self.name).exclude(id=self.id).exists():
            raise ValidationError(_("Подкатегория с таким названием уже существует в этой категории."))

    def save(self, *args, **kwargs):
        """Отправка уведомления по WebSocket при создании/обновлении подкатегории."""
        self.clean()
        is_new = self._state.adding
        super().save(*args, **kwargs)

        action = "create" if is_new else "update"
        async_to_sync(self.channel_layer.group_send)(
            "subcategories", {"type": "updateData", "message": {"action": action, "id": self.id, "name": self.name}}
        )

    def delete(self, *args, **kwargs):
        """Отправка уведомления по WebSocket при удалении подкатегории."""
        async_to_sync(self.channel_layer.group_send)(
            "subcategories", {"type": "updateData", "message": {"action": "delete", "id": self.id}}
        )
        super().delete(*args, **kwargs)

    def get_absolute_url(self):
        """Возвращает URL для просмотра подкатегории."""
        from django.urls import reverse
        return reverse("tasks:subcategory_detail", kwargs={"pk": self.pk})

    class Meta:
        verbose_name = _("Подкатегория задач")
        verbose_name_plural = _("Подкатегории задач")
        ordering = ["category", "name"]
        indexes = [
            models.Index(fields=["category", "name"], name="subcat_catname_idx"),
            models.Index(fields=["name"], name="tasksubcategory_name_idx"),
        ]
        constraints = [
            models.UniqueConstraint(fields=["category", "name"], name="unique_subcategory_name")
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

    project = models.ForeignKey("tasks.Project", on_delete=models.CASCADE, related_name="tasks", db_index=True)
    category = models.ForeignKey("tasks.TaskCategory", on_delete=models.SET_NULL, null=True, blank=True, related_name="tasks", db_index=True)
    subcategory = models.ForeignKey("tasks.TaskSubcategory", on_delete=models.SET_NULL, null=True, blank=True, related_name="tasks", db_index=True)
    task_number = models.CharField(max_length=20, unique=True, blank=True, verbose_name=_("Номер задачи"), db_index=True)
    description = models.TextField(verbose_name=_("Описание задачи"))
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

    def clean(self):
        """Проверяет корректность данных задачи."""
        if self.deadline and self.completion_date and self.deadline < self.completion_date:
            raise ValidationError(_("Дата завершения не может быть раньше дедлайна."))

        if self.assignee and self.team:
            raise ValidationError(_("Задача не может быть назначена одновременно на пользователя и команду."))

        if self.category and self.subcategory and self.category != self.subcategory.category:
             raise ValidationError(_("Подкатегория не принадлежит выбранной категории."))

        if self.status == "completed" and not self.completion_date:
            self.completion_date = timezone.now()  # Автоматическое заполнение completion_date
        elif self.status != "completed" and self.completion_date:
            self.completion_date = None

        if self.is_overdue and self.status not in ["completed", "cancelled", "overdue"]:
            self.status = "overdue"  # Автоматическая смена статуса на "overdue"


    def save(self, *args, **kwargs):
        """Генерирует уникальный task_number и назначает роли при сохранении задачи."""
        self.clean()  # Вызываем clean() перед сохранением
        if not self.task_number:
            self.task_number = self.generate_unique_task_number()

        super().save(*args, **kwargs)

        # Назначение ролей при сохранении задачи
        if self.team:
            self.assign_team_roles()

        # Автоматическое назначение команды, если задача назначена на пользователя
        if self.assignee and not self.team:
            self.team = self.assignee.user_profile.team
            super().save(*args, **kwargs)  # Call super().save() again to save the team change

    def assign_team_roles(self):
        """Назначает роли для команды и её участников."""
        if not self.team:
            return

        leader = self.team.team_leader
        if leader:
            TaskUserRole.objects.get_or_create(task=self, user=leader, role=TaskUserRole.RoleChoices.EXECUTOR)

        for member in self.team.members.exclude(id=leader.id):
            TaskUserRole.objects.get_or_create(task=self, user=member, role=TaskUserRole.RoleChoices.WATCHER)

    def generate_unique_task_number(self):
        """Генерирует уникальный номер задачи."""
        if not self.project:
            raise ValueError("Нельзя создать задачу без кампании!")

        project_code = unidecode(self.project.name).upper().replace(" ", "")[:4] or "TASK"

        for attempt in range(10):
            with transaction.atomic():
                last_task = Task.objects.select_for_update().filter(project=self.project).order_by("-id").first()
                next_number = 1

                if last_task and last_task.task_number:
                    try:
                        last_number = int(last_task.task_number.split("-")[-1])
                        next_number = last_number + 1
                    except ValueError:
                        pass  # Игнорируем ошибки

                task_number = f"{project_code}-{next_number:04d}"

                if not Task.objects.filter(task_number=task_number).exists():
                    return task_number

        logger.error("Не удалось сгенерировать уникальный номер задачи после 10 попыток!")
        raise IntegrityError("Не удалось сгенерировать уникальный номер задачи после 10 попыток!")

    def get_absolute_url(self):
        """Возвращает URL для просмотра задачи."""
        from django.urls import reverse
        return reverse("tasks:task_detail", kwargs={"pk": self.pk})

    def get_status_display(self):
        """Возвращает строковое представление статуса задачи."""
        return dict(self.TASK_STATUS_CHOICES).get(self.status, self.status)

    def get_priority_display(self):
        """Возвращает строковое представление приоритета задачи."""
        return self.TaskPriority(self.priority).label

    @property
    def is_overdue(self):
        """Проверяет, просрочена ли задача."""
        return self.deadline and self.deadline < timezone.now() and self.status not in ["completed", "cancelled", "overdue"]

    def has_permission_to_change(self, user):
        """
        Проверяет, имеет ли пользователь право изменять (статус, и т.д.) этой задачи.
        АДАПТИРУЙТЕ ЭТУ ЛОГИКУ ПОД ВАШИ ПРАВИЛА!
        """
        if not user or not user.is_authenticated:
            logger.debug(f"Permission check failed for task {self.id}: User not authenticated.")
            return False

        # Суперпользователь может всё
        if user.is_superuser:
            logger.debug(f"Permission granted for task {self.id}: User {user.username} is superuser.")
            return True

        # Создатель задачи может её изменять
        if self.created_by_id == user.id:
            logger.debug(f"Permission granted for task {self.id}: User {user.username} is creator.")
            return True

        # Назначенный исполнитель может изменять
        if self.assignee_id == user.id:
            logger.debug(f"Permission granted for task {self.id}: User {user.username} is assignee.")
            return True # TODO: Add logic here if assignee can only change certain statuses?

        # Лидер команды, которой назначена задача, может изменять
        # Check if team exists and has a leader before accessing team_leader.id
        if self.team and self.team.team_leader_id and self.team.team_leader_id == user.id:
             logger.debug(f"Permission granted for task {self.id}: User {user.username} is leader of assigned team {self.team.name}.")
             return True

        # Проверка через роли TaskUserRole (Пример - раскомментируйте и настройте, если используете)
        required_roles = [TaskUserRole.RoleChoices.EXECUTOR, TaskUserRole.RoleChoices.RESPONSIBLE]
        if TaskUserRole.objects.filter(
            task_id=self.id,
            user_id=user.id,
            role__in=required_roles
        ).exists():
            logger.debug(f"Permission granted for task {self.id}: User {user.username} has role in {required_roles}.")
            return True

        # Если ни одно из условий не выполнено
        logger.debug(f"User {user.username} has NO permission to change task {self.id} based on current rules (creator: {self.created_by_id}, assignee: {self.assignee_id}, team_leader: {self.team.team_leader_id if self.team else 'N/A'}).")
        return False

    class Meta:
        verbose_name = _("Задача")
        verbose_name_plural = _("Задачи")
        ordering = ["priority", "deadline", "-created_at"]
        indexes = [
            models.Index(fields=["task_number"], name="task_task_number_idx"),
            models.Index(fields=["status"], name="task_status_idx"),
            models.Index(fields=["priority"], name="task_priority_idx"),
        ]
        constraints = [
            models.UniqueConstraint(fields=["task_number"], name="unique_task_number")
        ]

    def __str__(self):
        return f"{self.task_number} - {self.project.name} - {self.description[:50]}"


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