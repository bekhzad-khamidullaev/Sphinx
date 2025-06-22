import logging
from datetime import timedelta, datetime, time as time_obj
from unidecode import unidecode
from django.utils import timezone
from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models, IntegrityError, transaction
from django.db.models import F, Q
from django.dispatch import receiver
from django.db.models.signals import post_save, post_delete
from django.urls import reverse
from django.utils.translation import gettext_lazy as _
from django.utils.crypto import get_random_string

from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer

try:
    from user_profiles.models import User as AuthUser, Team, Department
except ImportError:
    logger = logging.getLogger(__name__)
    logger.warning(
        "User, Team, or Department model not found in user_profiles. "
        "Tasks app functionality related to these models might be limited or broken. "
        "Using Django's default User model as a fallback for ForeignKey relations if AUTH_USER_MODEL is not set."
    )
    from django.contrib.auth.models import User as DjangoUser
    AuthUser = settings.AUTH_USER_MODEL if hasattr(settings, 'AUTH_USER_MODEL') else DjangoUser

    class DummyTeam(models.Model):
        name = models.CharField(max_length=100)
        class Meta: app_label = 'user_profiles_dummy_team'; abstract = True
        def __str__(self): return self.name
    Team = DummyTeam

    class DummyDepartment(models.Model):
        name = models.CharField(max_length=100)
        class Meta: app_label = 'user_profiles_dummy_dept'; abstract = True
        def __str__(self): return self.name
    Department = DummyDepartment

logger = logging.getLogger(__name__)

class BaseModel(models.Model):
    created_at = models.DateTimeField(auto_now_add=True, verbose_name=_("Дата создания"))
    updated_at = models.DateTimeField(auto_now=True, verbose_name=_("Дата обновления"))

    class Meta:
        abstract = True
        ordering = ['-created_at']

class Project(BaseModel):
    name = models.CharField(_("название проекта"), max_length=255, db_index=True, unique=True)
    description = models.TextField(_("описание проекта"), blank=True, null=True)
    start_date = models.DateField(_("дата начала"), null=True, blank=True)
    end_date = models.DateField(_("дата завершения"), null=True, blank=True)
    is_active = models.BooleanField(_("активен"), default=True)
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
                              related_name='owned_projects', verbose_name=_("владелец проекта"),
                              help_text=_("Пользователь, управляющий проектом и его настройками."))

    def clean(self):
        super().clean()
        if self.start_date and self.end_date and self.start_date > self.end_date:
            raise ValidationError({'end_date': _("Дата завершения не может быть раньше даты начала.")})
        if not self.start_date and not self.pk:
            self.start_date = timezone.now().date()

    def save(self, *args, **kwargs):
        is_new = self._state.adding
        self.full_clean()
        super().save(*args, **kwargs)
        try:
            channel_layer = get_channel_layer()
            action = "create" if is_new else "update"
            async_to_sync(channel_layer.group_send)(
                "projects_list",
                {"type": "project_update", "message": {
                    "action": action, "id": self.id, "name": self.name,
                    "start_date": self.start_date.isoformat() if self.start_date else None,
                    "end_date": self.end_date.isoformat() if self.end_date else None,
                }}
            )
        except Exception as e:
            logger.error(f"Failed to send WebSocket notification for Project {self.id}: {e}")

    def delete(self, *args, **kwargs):
        project_id = self.id
        project_name = self.name
        super().delete(*args, **kwargs)
        try:
            channel_layer = get_channel_layer()
            async_to_sync(channel_layer.group_send)(
                "projects_list",
                {"type": "project_update", "message": {"action": "delete", "id": project_id, "name": project_name}}
            )
        except Exception as e:
            logger.error(f"Failed to send WebSocket deletion notification for Project {project_id}: {e}")

    def get_absolute_url(self):
         return reverse('tasks:task_list') + f'?project={self.pk}'

    class Meta:
        verbose_name = _("Проект")
        verbose_name_plural = _("Проекты")
        ordering = ["name", "-created_at"]
        indexes = [models.Index(fields=["name"], name="project_name_idx")]

    def __str__(self):
        return self.name

class TaskCategory(BaseModel):
    name = models.CharField(max_length=100, unique=True, verbose_name=_("Название категории"), db_index=True)
    description = models.TextField(blank=True, verbose_name=_("Описание категории"))

    def save(self, *args, **kwargs):
        is_new = self._state.adding
        super().save(*args, **kwargs)
        try:
            channel_layer = get_channel_layer()
            action = "create" if is_new else "update"
            async_to_sync(channel_layer.group_send)(
                "categories_list",
                {"type": "category_update", "message": {"action": action, "id": self.id, "name": self.name}}
            )
        except Exception as e:
            logger.error(f"Failed to send WebSocket notification for TaskCategory {self.id}: {e}")

    def delete(self, *args, **kwargs):
        category_id = self.id
        category_name = self.name
        super().delete(*args, **kwargs)
        try:
            channel_layer = get_channel_layer()
            async_to_sync(channel_layer.group_send)(
                "categories_list",
                {"type": "category_update", "message": {"action": "delete", "id": category_id, "name": category_name}}
            )
        except Exception as e:
            logger.error(f"Failed to send WebSocket deletion notification for TaskCategory {category_id}: {e}")

    def get_absolute_url(self):
        return reverse('tasks:category_detail', kwargs={'pk': self.pk})

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

    def save(self, *args, **kwargs):
        is_new = self._state.adding
        super().save(*args, **kwargs)
        try:
            channel_layer = get_channel_layer()
            action = "create" if is_new else "update"
            async_to_sync(channel_layer.group_send)(
                "subcategories_list",
                {"type": "subcategory_update", "message": {
                    "action": action, "id": self.id, "name": self.name,
                    "category_id": self.category_id, "category_name": self.category.name
                }}
            )
        except Exception as e:
            logger.error(f"Failed to send WebSocket notification for TaskSubcategory {self.id}: {e}")

    def delete(self, *args, **kwargs):
        subcategory_id = self.id
        subcategory_name = self.name
        super().delete(*args, **kwargs)
        try:
            channel_layer = get_channel_layer()
            async_to_sync(channel_layer.group_send)(
                "subcategories_list",
                {"type": "subcategory_update", "message": {"action": "delete", "id": subcategory_id, "name": subcategory_name}}
            )
        except Exception as e:
            logger.error(f"Failed to send WebSocket deletion notification for TaskSubcategory {subcategory_id}: {e}")

    def get_absolute_url(self):
        return reverse('tasks:subcategory_detail', kwargs={'pk': self.pk})

    class Meta:
        verbose_name = _("Подкатегория задач")
        verbose_name_plural = _("Подкатегории задач")
        ordering = ["category__name", "name"]
        indexes = [ models.Index(fields=["name"], name="subcat_name_idx") ]
        constraints = [ models.UniqueConstraint(fields=["category", "name"], name="unique_subcategory_per_category") ]

    def __str__(self):
        return f"{self.category.name} / {self.name}"

class Task(BaseModel):
    class TaskPriority(models.IntegerChoices):
        LOW = 5, _("Низкий")
        MEDIUM_LOW = 4, _("Ниже среднего")
        MEDIUM = 3, _("Средний")
        MEDIUM_HIGH = 2, _("Выше среднего")
        HIGH = 1, _("Высокий")

    class StatusChoices(models.TextChoices):
        BACKLOG = "backlog", _("Бэклог")
        NEW = "new", _("Новая") # "TODO" might be better than "NEW"
        IN_PROGRESS = "in_progress", _("В работе")
        ON_HOLD = "on_hold", _("Отложена")
        # IN_REVIEW = "in_review", _("На проверке") # Consider adding this if workflow needs it
        COMPLETED = "completed", _("Выполнена") # "DONE" might be better
        CANCELLED = "cancelled", _("Отменена")
        OVERDUE = "overdue", _("Просрочена")
        # CLOSED = "closed", _("Закрыта") # After completed, for archival

    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name="tasks", verbose_name=_("Проект"), db_index=True)
    category = models.ForeignKey(TaskCategory, on_delete=models.SET_NULL, null=True, blank=True, related_name="tasks", verbose_name=_("Категория"), db_index=True)
    subcategory = models.ForeignKey(TaskSubcategory, on_delete=models.SET_NULL, null=True, blank=True, related_name="tasks", verbose_name=_("Подкатегория"), db_index=True)

    task_number = models.CharField(max_length=40, unique=True, blank=True, verbose_name=_("Номер задачи"), db_index=True)
    title = models.CharField(max_length=255, verbose_name=_("Название задачи"))
    description = models.TextField(verbose_name=_("Описание задачи"), blank=True)
    status = models.CharField(max_length=20, choices=StatusChoices.choices, default=StatusChoices.NEW, verbose_name=_("Статус"), db_index=True)
    priority = models.IntegerField(choices=TaskPriority.choices, default=TaskPriority.MEDIUM, verbose_name=_("Приоритет"), db_index=True)
    start_date = models.DateField(verbose_name=_('Дата начала'), default=timezone.now)
    due_date = models.DateField(_("срок выполнения"), null=True, blank=True, db_index=True, help_text=_("Планируемая дата завершения задачи."))
    completion_date = models.DateTimeField(null=True, blank=True, verbose_name=_("Дата завершения"))
    estimated_time = models.DurationField(null=True, blank=True, verbose_name=_("Оценка времени (план)"))

    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="created_tasks", verbose_name=_("Инициатор"), db_index=True)

    team = models.ForeignKey(Team, on_delete=models.SET_NULL, null=True, blank=True, related_name='tasks', verbose_name=_("Команда"))
    department = models.ForeignKey(Department, on_delete=models.SET_NULL, null=True, blank=True, related_name='tasks', verbose_name=_("Отдел"))

    def clean(self):
        super().clean()
        if self.start_date and self.due_date and self.due_date < self.start_date:
            raise ValidationError({'due_date': _("Срок выполнения не может быть раньше даты начала.")})
        if self.completion_date and self.start_date and self.completion_date.date() < self.start_date:
            raise ValidationError({'completion_date': _("Дата завершения не может быть раньше даты начала.")})

        if self.subcategory and not self.category:
            self.category = self.subcategory.category
        elif self.category and self.subcategory and self.category != self.subcategory.category:
            raise ValidationError({'subcategory': _("Подкатегория не принадлежит выбранной категории.")})

        original_status = None
        if self.pk:
            try: original_task = Task.objects.get(pk=self.pk); original_status = original_task.status
            except Task.DoesNotExist: pass

        if self.status == self.StatusChoices.COMPLETED:
            if not self.completion_date: self.completion_date = timezone.now()
        elif original_status == self.StatusChoices.COMPLETED and self.status != self.StatusChoices.COMPLETED:
             self.completion_date = None

        if self.due_date and self.due_date < timezone.now().date() and \
           self.status not in [self.StatusChoices.COMPLETED, self.StatusChoices.CANCELLED, self.StatusChoices.OVERDUE]:
            self.status = self.StatusChoices.OVERDUE

        if self._state.adding and not self.due_date:
            start = self.start_date or timezone.now().date()
            try:
                days = PriorityDeadline.get_days(self.priority)
                delta = timedelta(days=days)
            except Exception as e:  # pragma: no cover
                logger.error(f"Priority deadline lookup failed: {e}")
                delta = timedelta(days=7)
            self.due_date = start + delta

    def save(self, *args, **kwargs):
        is_new = self._state.adding
        if not kwargs.pop('skip_clean', False): self.full_clean()
        if is_new and not self.task_number: self.task_number = self._generate_unique_task_number()
        super().save(*args, **kwargs)

    def _generate_unique_task_number(self):
        project_code_str = "TASK"
        if self.project_id:
            try:
                project = Project.objects.get(id=self.project_id)
                project_code_str = unidecode(project.name).upper()
                project_code_str = "".join(filter(str.isalnum, project_code_str))[:4] or "PROJ"
            except Project.DoesNotExist:
                logger.warning(f"Project {self.project_id} not found for task number generation. Using fallback.")
                project_code_str = "UNKP"

        last_task_qs = Task.objects.filter(task_number__startswith=f"{project_code_str}-")
        new_task_number = None
        for attempt in range(10):
            try:
                with transaction.atomic():
                    last_task = last_task_qs.select_for_update().order_by('-id').values_list('task_number', flat=True).first()
                    next_num = 1
                    if last_task:
                        try:
                            num_part = last_task.split('-')[-1]
                            if num_part.isdigit(): next_num = int(num_part) + 1
                            else: logger.warning(f"Cannot parse numeric part of last task number {last_task} for {project_code_str}. Resetting.")
                        except (IndexError, ValueError): logger.warning(f"Could not parse last task number {last_task} for {project_code_str}. Resetting.")
                    new_task_number = f"{project_code_str}-{next_num:04d}"
                    if not Task.objects.filter(task_number=new_task_number).exists(): return new_task_number
                    logger.info(f"Task number collision for {new_task_number} (attempt {attempt+1}). Will retry.")
            except IntegrityError:
                logger.warning(f"IntegrityError during task number generation (attempt {attempt+1}).")
            except Exception as e: logger.error(f"Error generating task number (attempt {attempt+1}): {e}")
        logger.error(f"Failed to generate unique task number for {project_code_str} after multiple attempts. Using timestamp fallback.")
        timestamp_part = timezone.now().strftime('%Y%m%d%H%M%S%f')[:17]
        random_part = get_random_string(3).upper()
        fallback_number = f"{project_code_str[:4]}-FLBK-{timestamp_part}-{random_part}"
        if not Task.objects.filter(task_number=fallback_number).exists(): return fallback_number
        fallback_number_safer = f"{project_code_str[:4]}-FLBK-{timestamp_part}-{get_random_string(6).upper()}"
        if not Task.objects.filter(task_number=fallback_number_safer).exists(): return fallback_number_safer
        raise IntegrityError(f"CRITICAL: Fallback task number {fallback_number_safer} also collided. System error.")

    @property
    def status_display(self): return self.get_status_display()
    @property
    def priority_display(self): return self.get_priority_display()
    @property
    def is_overdue(self):
        return self.due_date and self.due_date < timezone.now().date() and \
               self.status not in [self.StatusChoices.COMPLETED, self.StatusChoices.CANCELLED]
    @property
    def is_resolved(self):
        return self.status in [self.StatusChoices.COMPLETED, self.StatusChoices.CANCELLED] # Add self.StatusChoices.CLOSED if used

    def get_users_by_role(self, role):
        return AuthUser.objects.filter(task_assignments__task=self, task_assignments__role=role)
    def get_responsible_users(self): return self.get_users_by_role(TaskAssignment.RoleChoices.RESPONSIBLE)
    def get_executors(self): return self.get_users_by_role(TaskAssignment.RoleChoices.EXECUTOR)
    def get_watchers(self): return self.get_users_by_role(TaskAssignment.RoleChoices.WATCHER)
    def get_all_participants(self): return AuthUser.objects.filter(task_assignments__task=self).distinct()

    def can_view(self, user):
        if not user or not user.is_authenticated: return False
        if user.is_superuser or user.is_staff: return True
        return self.created_by == user or self.assignments.filter(user=user).exists()

    def can_change_properties(self, user):
        if not self.can_view(user): return False
        if user.is_superuser or user.is_staff: return True
        return self.created_by == user or self.assignments.filter(user=user, role=TaskAssignment.RoleChoices.RESPONSIBLE).exists()

    def can_delete(self, user):
        if not self.can_view(user): return False
        if user.is_superuser or user.is_staff: return True
        return self.created_by == user or self.assignments.filter(user=user, role=TaskAssignment.RoleChoices.RESPONSIBLE).exists()

    def can_change_status(self, user, new_status=None):
        if not self.can_view(user): return False
        if user.is_superuser or user.is_staff: return True
        return self.created_by == user or self.assignments.filter(user=user, role__in=[TaskAssignment.RoleChoices.RESPONSIBLE, TaskAssignment.RoleChoices.EXECUTOR]).exists()

    def can_manage_assignments(self, user):
        if not self.can_view(user): return False
        if user.is_superuser or user.is_staff: return True
        return self.created_by == user or self.assignments.filter(user=user, role=TaskAssignment.RoleChoices.RESPONSIBLE).exists()

    def can_add_comment(self, user):
        return self.can_view(user)

    def get_absolute_url(self):
        return reverse("tasks:task_detail", kwargs={"pk": self.pk})

    def get_chat_room(self):
        from room.models import Room
        slug = f"task-{self.pk}"
        defaults = {"name": f"Task #{self.pk}", "creator": self.created_by}
        room, _ = Room.objects.get_or_create(slug=slug, defaults=defaults)
        if self.created_by and self.created_by not in room.participants.all():
            room.participants.add(self.created_by)
        return room

    def get_chat_room_url(self):
        return self.get_chat_room().get_absolute_url()

    class Meta:
        verbose_name = _("Задача")
        verbose_name_plural = _("Задачи")
        ordering = ["priority", "due_date", "-created_at"]
        indexes = [
            models.Index(fields=["task_number"], name="task_task_number_idx"),
            models.Index(fields=["status"], name="task_status_idx"),
            models.Index(fields=["priority"], name="task_priority_idx"),
            models.Index(fields=["due_date"], name="task_due_date_idx"),
            models.Index(fields=["project"], name="task_project_idx"),
            models.Index(fields=["created_by"], name="task_creator_idx"),
            models.Index(fields=["team"], name="task_team_idx"),
            models.Index(fields=["department"], name="task_department_idx"),
        ]
    def __str__(self):
        return f"[{self.task_number or self.pk}] {self.title[:60]}"

class TaskAssignment(BaseModel):
    class RoleChoices(models.TextChoices):
        RESPONSIBLE = 'responsible', _('Ответственный')
        EXECUTOR = 'executor', _('Исполнитель')
        WATCHER = 'watcher', _('Наблюдатель')
        REPORTER = 'reporter', _('Автор/Заявитель')

    task = models.ForeignKey(Task, on_delete=models.CASCADE, related_name="assignments", verbose_name=_("Задача"))
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="task_assignments", verbose_name=_("Пользователь"))
    role = models.CharField(max_length=20, choices=RoleChoices.choices, verbose_name=_("Роль"))
    assigned_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='given_task_assignments', verbose_name=_("Кем назначено"))

    class Meta:
        verbose_name = _("Назначение задачи")
        verbose_name_plural = _("Назначения задач")
        constraints = [ models.UniqueConstraint(fields=['task', 'user'], name='unique_user_assignment_per_task') ]
        ordering = ['task', 'role', 'user__username']
        indexes = [ models.Index(fields=['task', 'user']), models.Index(fields=['task', 'role']), ]
    def __str__(self):
        return f"{self.user.get_username()} - {self.get_role_display()} в {self.task.task_number or self.task.title[:20]}"

class TaskComment(BaseModel):
    task = models.ForeignKey(Task, on_delete=models.CASCADE, related_name='comments', verbose_name=_("Задача"), db_index=True)
    author = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name='task_comments', verbose_name=_("Автор"), db_index=True)
    text = models.TextField(verbose_name=_("Текст комментария"))
    class Meta:
        verbose_name = _("Комментарий к задаче")
        verbose_name_plural = _("Комментарии к задачам")
        ordering = ['created_at']
        indexes = [ models.Index(fields=['task', 'created_at']), ]
    def __str__(self):
        author_name = self.author.get_username() if self.author else _("Аноним")
        return f"Комментарий от {author_name} к задаче '{self.task.task_number or self.task.id}'"

class TaskPhoto(BaseModel):
    task = models.ForeignKey(Task, on_delete=models.CASCADE, related_name="photos", verbose_name=_("Задача"), db_index=True)
    uploaded_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="uploaded_task_photos", verbose_name=_("Загрузил"))
    photo = models.ImageField(upload_to="task_photos/", verbose_name=_("Фотография"))
    description = models.CharField(max_length=255, blank=True, verbose_name=_("Описание фотографии"))
    class Meta:
        verbose_name = _("Фотография к задаче")
        verbose_name_plural = _("Фотографии к задачам")
        ordering = ["created_at"]
        indexes = [models.Index(fields=["task"], name="taskphoto_task_idx")]
    def __str__(self):
        return f"Фото к задаче '{self.task.task_number or self.task.id}' ({self.id})"


class PriorityDeadline(models.Model):
    priority = models.IntegerField(choices=Task.TaskPriority.choices, unique=True, verbose_name=_('Приоритет'))
    days = models.PositiveIntegerField(default=7, verbose_name=_('Срок (дней)'))

    class Meta:
        verbose_name = _('Срок по приоритету')
        verbose_name_plural = _('Сроки по приоритетам')
        ordering = ['priority']

    def __str__(self):
        return f"{self.get_priority_display()}: {self.days}d"

    @classmethod
    def get_days(cls, priority):
        try:
            return cls.objects.get(priority=priority).days
        except cls.DoesNotExist:
            default_map = {
                Task.TaskPriority.HIGH: 1,
                Task.TaskPriority.MEDIUM_HIGH: 3,
                Task.TaskPriority.MEDIUM: 7,
                Task.TaskPriority.MEDIUM_LOW: 14,
                Task.TaskPriority.LOW: 30,
            }
            return default_map.get(priority, 7)

@receiver(post_save, sender=Task)
def task_post_save_ws_handler(sender, instance: Task, created: bool, update_fields=None, **kwargs):
    change_type = "create" if created else "update"
    list_message_data = {
        "action": change_type, "id": instance.id, "task_number": instance.task_number,
        "title": instance.title, "status": instance.status, "status_display": instance.status_display,
        "priority": instance.priority, "priority_display": instance.priority_display,
        "due_date": instance.due_date.isoformat() if instance.due_date else None,
        "project_id": instance.project_id,
    }
    detail_message_data = {
        **list_message_data, "description": instance.description,
        "start_date": instance.start_date.isoformat() if instance.start_date else None,
        "completion_date": instance.completion_date.isoformat() if instance.completion_date else None,
        "estimated_time": str(instance.estimated_time) if instance.estimated_time else None,
        "created_by_id": instance.created_by_id, "team_id": instance.team_id, "department_id": instance.department_id,
        "category_id": instance.category_id, "subcategory_id": instance.subcategory_id,
        "assignments": [
            {"user_id": assign.user_id, "username": assign.user.get_username(), "role": assign.role, "role_display": assign.get_role_display()}
            for assign in instance.assignments.select_related('user').all()
        ]
    }
    try:
        channel_layer = get_channel_layer()
        async_to_sync(channel_layer.group_send)("tasks_list", {"type": "list_update", "message": list_message_data})
        async_to_sync(channel_layer.group_send)(f"task_{instance.id}", {"type": "task_update", "message": detail_message_data})
        logger.debug(f"Sent WebSocket update for Task {instance.id} (Action: {change_type}, Status: {instance.status})")
    except Exception as e: logger.error(f"Failed during WebSocket notification for Task {instance.id}: {e}")

@receiver(post_delete, sender=Task)
def task_post_delete_ws_handler(sender, instance: Task, **kwargs):
    message_data = {"action": "delete", "id": instance.id, "task_number": instance.task_number}
    try:
        channel_layer = get_channel_layer(); async_to_sync(channel_layer.group_send)("tasks_list", {"type": "list_update", "message": message_data})
        async_to_sync(channel_layer.group_send)(f"task_{instance.id}", {"type": "task_update", "message": message_data})
        logger.debug(f"Sent WebSocket deletion for Task {instance.id}")
    except Exception as e: logger.error(f"Failed during WebSocket deletion notification for Task {instance.id}: {e}")

@receiver([post_save, post_delete], sender=TaskAssignment)
def task_assignment_ws_handler(sender, instance: TaskAssignment, created=None, **kwargs):
    task_instance = instance.task
    if task_instance:
        logger.info(f"TaskAssignment changed for Task {task_instance.id}. Triggering task update notification.")
        list_message_data = {
            "action": "update", "id": task_instance.id, "task_number": task_instance.task_number, "title": task_instance.title,
            "status": task_instance.status, "priority": task_instance.priority,
            "assignments_summary": ", ".join([a.user.get_username() for a in task_instance.assignments.select_related('user').all()[:3]]) + ("..." if task_instance.assignments.count() > 3 else "")
        }
        detail_message_data = {
            "action": "update", "id": task_instance.id, "task_number": task_instance.task_number,
            "title": task_instance.title, "status": task_instance.status, "status_display": task_instance.status_display,
            "priority": task_instance.priority, "priority_display": task_instance.priority_display,
            "due_date": task_instance.due_date.isoformat() if task_instance.due_date else None,
            "project_id": task_instance.project_id, "description": task_instance.description,
            "start_date": task_instance.start_date.isoformat() if task_instance.start_date else None,
            "completion_date": task_instance.completion_date.isoformat() if task_instance.completion_date else None,
            "estimated_time": str(task_instance.estimated_time) if task_instance.estimated_time else None,
            "created_by_id": task_instance.created_by_id, "team_id": task_instance.team_id, "department_id": task_instance.department_id,
            "category_id": task_instance.category_id, "subcategory_id": task_instance.subcategory_id,
            "assignments": [
                {"user_id": assign.user_id, "username": assign.user.get_username(), "role": assign.role, "role_display": assign.get_role_display()}
                for assign in task_instance.assignments.select_related('user').all()
            ]
        }
        try:
            channel_layer = get_channel_layer()
            async_to_sync(channel_layer.group_send)("tasks_list", {"type": "list_update", "message": list_message_data})
            async_to_sync(channel_layer.group_send)(f"task_{task_instance.id}", {"type": "task_update", "message": detail_message_data})
        except Exception as e: logger.error(f"Error sending WS notification for TaskAssignment change on Task {task_instance.id}: {e}")

@receiver(post_save, sender=TaskComment)
def task_comment_post_save_ws_handler(sender, instance: TaskComment, created: bool, **kwargs):
    if created:
        channel_layer = get_channel_layer(); group_name = f'task_comments_{instance.task_id}'
        author = instance.author
        author_name = author.display_name if author and hasattr(author, 'display_name') else (author.username if author else _("Аноним"))
        author_avatar_url = author.image.url if author and hasattr(author, 'image') and author.image else None
        comment_data = {
            'id': instance.id, 'text': instance.text, 'created_at_iso': instance.created_at.isoformat(),
            'created_at_display': instance.created_at.strftime('%d.%m.%Y %H:%M'),
            'author': {'id': author.id if author else None, 'name': author_name, 'avatar_url': author_avatar_url},
            'task_id': instance.task_id,
        }
        try:
            async_to_sync(channel_layer.group_send)(group_name, {'type': 'comment_message', 'message': comment_data})
            logger.debug(f"Sent WebSocket notification for new TaskComment {instance.id} on Task {instance.task_id}")
        except Exception as e: logger.error(f"Error sending new comment {instance.id} to WebSocket group {group_name}: {e}")