# tasks/models.py
import logging
from datetime import timedelta
from unidecode import unidecode

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models, IntegrityError, transaction
from django.db.models import F, Q
from django.dispatch import receiver
from django.db.models.signals import post_save
from django.urls import reverse
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from django.utils.crypto import get_random_string

from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer

from user_profiles.models import User, Team, TaskUserRole, Department

logger = logging.getLogger(__name__)

# ------------------------ Base Model ------------------------
class BaseModel(models.Model):
    created_at = models.DateTimeField(auto_now_add=True, verbose_name=_("Дата создания"))
    updated_at = models.DateTimeField(auto_now=True, verbose_name=_("Дата обновления"))

    class Meta:
        abstract = True
        ordering = ['-created_at']


# ------------------------ Projects ------------------------
class Project(BaseModel):
    name = models.CharField(max_length=200, verbose_name=_("Название проекта"), db_index=True)
    description = models.TextField(blank=True, verbose_name=_("Описание проекта"))
    start_date = models.DateField(null=True, blank=True, verbose_name=_("Дата начала"))
    end_date = models.DateField(null=True, blank=True, verbose_name=_("Дата завершения"))

    def clean(self):
        if self.start_date and self.end_date and self.start_date > self.end_date:
            raise ValidationError(_("Дата завершения не может быть раньше даты начала."))

    def save(self, *args, **kwargs):
        is_new = self._state.adding
        super().save(*args, **kwargs)
        try:
            channel_layer = get_channel_layer()
            action = "create" if is_new else "update"
            async_to_sync(channel_layer.group_send)(
                "projects_list",
                {"type": "project_update", "message": {"action": action, "id": self.id, "name": self.name}}
            )
        except Exception as e:
            logger.error(f"Failed to send WebSocket notification for Project {self.id}: {e}")


    def delete(self, *args, **kwargs):
        project_id = self.id
        super().delete(*args, **kwargs)
        try:
            channel_layer = get_channel_layer()
            async_to_sync(channel_layer.group_send)(
                "projects_list",
                {"type": "project_update", "message": {"action": "delete", "id": project_id}}
            )
        except Exception as e:
            logger.error(f"Failed to send WebSocket deletion notification for Project {project_id}: {e}")


    def get_absolute_url(self):
         return f"{reverse('tasks:task_list')}?project={self.pk}"


    class Meta:
        verbose_name = _("Проект")
        verbose_name_plural = _("Проекты")
        ordering = ["name", "-created_at"]
        indexes = [models.Index(fields=["name"], name="project_name_idx")]

    def __str__(self):
        return self.name


# ------------------------ Task Categories & Subcategories ------------------------
class TaskCategory(BaseModel):
    name = models.CharField(max_length=100, unique=True, verbose_name=_("Название категории"), db_index=True)
    description = models.TextField(blank=True, verbose_name=_("Описание категории"))

    def get_absolute_url(self):
        return f"{reverse('tasks:task_list')}?category={self.pk}"

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

    def get_absolute_url(self):
        return f"{reverse('tasks:task_list')}?subcategory={self.pk}"

    class Meta:
        verbose_name = _("Подкатегория задач")
        verbose_name_plural = _("Подкатегории задач")
        ordering = ["category__name", "name"]
        indexes = [ models.Index(fields=["name"], name="subcat_name_idx") ]
        constraints = [ models.UniqueConstraint(fields=["category", "name"], name="unique_subcategory_per_category") ]

    def __str__(self):
        cat_name = self.category.name if self.category else _("Без категории")
        return f"{cat_name} / {self.name}"


# ------------------------ Tasks ------------------------
class Task(BaseModel):
    class TaskPriority(models.IntegerChoices):
        LOW = 5, _("Низкий")
        MEDIUM_LOW = 4, _("Ниже среднего")
        MEDIUM = 3, _("Средний")
        MEDIUM_HIGH = 2, _("Выше среднего")
        HIGH = 1, _("Высокий")

    class StatusChoices(models.TextChoices):
        NEW = "new", _("Новая")
        IN_PROGRESS = "in_progress", _("В работе")
        ON_HOLD = "on_hold", _("Отложена")
        COMPLETED = "completed", _("Выполнена")
        CANCELLED = "cancelled", _("Отменена")
        OVERDUE = "overdue", _("Просрочена")

    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name="tasks", verbose_name=_("Проект"), db_index=True)
    category = models.ForeignKey(TaskCategory, on_delete=models.SET_NULL, null=True, blank=True, related_name="tasks", verbose_name=_("Категория"), db_index=True)
    subcategory = models.ForeignKey(TaskSubcategory, on_delete=models.SET_NULL, null=True, blank=True, related_name="tasks", verbose_name=_("Подкатегория"), db_index=True)
    task_number = models.CharField(max_length=25, unique=True, blank=True, verbose_name=_("Номер задачи"), db_index=True)
    title = models.CharField(max_length=255, verbose_name=_("Название задачи"))
    description = models.TextField(verbose_name=_("Описание задачи"), blank=True)
    status = models.CharField(max_length=20, choices=StatusChoices.choices, default=StatusChoices.NEW, verbose_name=_("Статус"), db_index=True)
    priority = models.IntegerField(default=TaskPriority.MEDIUM, choices=TaskPriority.choices, verbose_name=_("Приоритет"), db_index=True)
    deadline = models.DateTimeField(null=True, blank=True, verbose_name=_("Срок выполнения"), db_index=True)
    start_date = models.DateTimeField(null=True, blank=True, verbose_name=_("Дата начала"))
    completion_date = models.DateTimeField(null=True, blank=True, verbose_name=_("Дата завершения"))
    estimated_time = models.DurationField(null=True, blank=True, verbose_name=_("Оценка времени"))
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="created_tasks", verbose_name=_("Создатель"), db_index=True)

    def clean(self):
        if self.deadline and self.start_date and self.deadline < self.start_date:
            raise ValidationError(_("Срок выполнения не может быть раньше даты начала."))
        if self.completion_date and self.start_date and self.completion_date < self.start_date:
             raise ValidationError(_("Дата завершения не может быть раньше даты начала."))

        if self.category and self.subcategory and self.category != self.subcategory.category:
            raise ValidationError(_("Подкатегория не принадлежит выбранной категории."))
        if not self.category and self.subcategory:
            self.category = self.subcategory.category

        is_being_completed = self.status == self.StatusChoices.COMPLETED
        original_status = None
        if not self._state.adding and self.pk:
            try:
                original_status = Task.objects.values('status').get(pk=self.pk)['status'] # Оптимизация
            except Task.DoesNotExist: pass

        if is_being_completed and not self.completion_date:
            self.completion_date = timezone.now()
            logger.debug(f"Task {self.pk or 'new'}: Setting completion_date due to status COMPLETED.")
        elif not is_being_completed and original_status == self.StatusChoices.COMPLETED:
            self.completion_date = None
            logger.debug(f"Task {self.pk}: Clearing completion_date because status changed from COMPLETED.")

        if self.is_overdue and self.status not in [self.StatusChoices.COMPLETED, self.StatusChoices.CANCELLED, self.StatusChoices.OVERDUE]:
            logger.debug(f"Task {self.pk or 'new'}: Setting status to OVERDUE because deadline passed.")
            self.status = self.StatusChoices.OVERDUE

    def save(self, *args, **kwargs):
        is_new = self._state.adding
        if is_new and not self.task_number:
            # Вызываем clean перед генерацией номера, чтобы self.project_id был доступен
            try:
                 self.clean() # Вызываем clean для установки category, если нужно
            except ValidationError:
                 # Если clean не прошел, номер не генерируем, save() вызовет ошибку позже
                 pass
            if not self.task_number: # Проверяем еще раз, т.к. clean мог упасть
                 self.task_number = self._generate_unique_task_number()

        # full_clean не вызываем здесь, полагаемся на вызов в ModelForm/Admin
        super().save(*args, **kwargs)


    def _generate_unique_task_number(self):
        # ... (код генерации номера без изменений) ...
        if not self.project_id:
             logger.warning("Attempting to generate task number without a project.")
             project_code = "TASK"
             last_task_qs = Task.objects.filter(project__isnull=True)
        else:
            try:
                project_name = Project.objects.get(id=self.project_id).name
                project_code = unidecode(project_name).upper()
                project_code = "".join(filter(str.isalnum, project_code))[:4] or "PROJ"
            except Project.DoesNotExist:
                 logger.error(f"Project with id {self.project_id} not found during task number generation.")
                 project_code = "UNKP"
            last_task_qs = Task.objects.filter(project_id=self.project_id)

        max_attempts = 10
        for attempt in range(max_attempts):
            try:
                with transaction.atomic():
                    last_task = last_task_qs.select_for_update().order_by('-id').values('task_number').first()
                    next_number = 1
                    if last_task and last_task['task_number']:
                        parts = last_task['task_number'].split('-')
                        potential_num = parts[-1]
                        if potential_num.isdigit():
                             try: next_number = int(potential_num) + 1
                             except ValueError: logger.warning(f"Could not parse number part '{potential_num}' from task number {last_task['task_number']}. Resetting sequence.")
                        else: logger.warning(f"Last part '{potential_num}' of task number {last_task['task_number']} is not a digit. Resetting sequence.")

                    new_task_number = f"{project_code}-{next_number:04d}"
                    if not Task.objects.filter(task_number=new_task_number).exists():
                        logger.info(f"Generated task number {new_task_number} for project {self.project_id or 'None'}")
                        return new_task_number
                    else: logger.warning(f"Generated task number {new_task_number} already exists (attempt {attempt+1}). Retrying.")
            except IntegrityError as e: logger.error(f"IntegrityError during task number generation (attempt {attempt+1}): {e}. Retrying.")
            except Exception as e: logger.exception(f"Unexpected error during task number generation (attempt {attempt+1}): {e}. Retrying.")

            if attempt < max_attempts - 1:
                 import time
                 time.sleep(0.1 * (attempt + 1))

        logger.error("Failed to generate unique task number after multiple attempts. Using fallback.")
        timestamp_part = timezone.now().strftime('%Y%m%d%H%M%S')
        random_part = get_random_string(4).upper()
        fallback_number = f"{project_code}-ERR-{timestamp_part}-{random_part}"
        if not Task.objects.filter(task_number=fallback_number).exists(): return fallback_number
        else: raise IntegrityError("Fatal: Could not generate a unique task number even with fallback.")


    def get_absolute_url(self):
        return reverse("tasks:task_detail", kwargs={"pk": self.pk})

    @property
    def status_display(self):
        return self.get_status_display()

    @property
    def priority_display(self):
        return self.get_priority_display()

    @property
    def is_overdue(self):
        return (
            self.deadline and self.deadline < timezone.now()
            and self.status not in [self.StatusChoices.COMPLETED, self.StatusChoices.CANCELLED]
        )

    def get_users_by_role(self, role):
        return User.objects.filter(task_roles__task=self, task_roles__role=role)

    def get_responsible_users(self):
        return self.get_users_by_role(TaskUserRole.RoleChoices.RESPONSIBLE)

    def get_executors(self):
        return self.get_users_by_role(TaskUserRole.RoleChoices.EXECUTOR)

    def get_watchers(self):
        return self.get_users_by_role(TaskUserRole.RoleChoices.WATCHER)


    def has_permission(self, user, permission_type='view'):
        # ... (код проверки прав без изменений) ...
        if not user or not user.is_authenticated:
            logger.debug(f"Permission check failed for task {self.id}: User not authenticated.")
            return False
        if user.is_superuser:
            logger.debug(f"Permission granted for task {self.id}: User {user.username} is superuser.")
            return True

        is_creator = self.created_by == user
        user_roles_set = set(TaskUserRole.objects.filter(task=self, user=user).values_list('role', flat=True))
        is_responsible = TaskUserRole.RoleChoices.RESPONSIBLE in user_roles_set
        is_executor = TaskUserRole.RoleChoices.EXECUTOR in user_roles_set
        is_watcher = TaskUserRole.RoleChoices.WATCHER in user_roles_set
        is_participant = bool(user_roles_set)

        if permission_type == 'view':
            has_perm = is_creator or is_participant
            if has_perm: logger.debug(f"Perm 'view' granted for task {self.id} to user {user.username} (creator={is_creator}, participant={is_participant}).")
            return has_perm
        if permission_type == 'change':
            has_perm = is_creator or is_responsible or is_executor
            if has_perm: logger.debug(f"Perm 'change' granted for task {self.id} to user {user.username} (creator={is_creator}, resp={is_responsible}, exec={is_executor}).")
            return has_perm
        if permission_type == 'delete':
            has_perm = is_creator or is_responsible
            if has_perm: logger.debug(f"Perm 'delete' granted for task {self.id} to user {user.username} (creator={is_creator}, resp={is_responsible}).")
            return has_perm
        if permission_type == 'change_status':
            has_perm = is_responsible or is_executor
            if has_perm: logger.debug(f"Perm 'change_status' granted for task {self.id} to user {user.username} (resp={is_responsible}, exec={is_executor}).")
            return has_perm
        if permission_type == 'assign_users':
            has_perm = is_creator or is_responsible
            if has_perm: logger.debug(f"Perm 'assign_users' granted for task {self.id} to user {user.username} (creator={is_creator}, resp={is_responsible}).")
            return has_perm
        if permission_type == 'add_comment':
            has_perm = is_creator or is_participant
            if has_perm: logger.debug(f"Perm 'add_comment' granted for task {self.id} to user {user.username}.")
            return has_perm

        logger.debug(f"Permission denied for user {user.username} on task {self.id} for action '{permission_type}'. Roles: {user_roles_set}, Creator: {is_creator}")
        return False


    class Meta:
        verbose_name = _("Задача")
        verbose_name_plural = _("Задачи")
        ordering = ["priority", "deadline", "-created_at"]
        indexes = [
            models.Index(fields=["task_number"], name="task_task_number_idx"),
            models.Index(fields=["status"], name="task_status_idx"),
            models.Index(fields=["priority"], name="task_priority_idx"),
            models.Index(fields=["deadline"], name="task_deadline_idx"),
            models.Index(fields=["project"], name="task_project_idx"),
            models.Index(fields=["created_by"], name="task_creator_idx"),
        ]

    def __str__(self):
        num = self.task_number or f"ID:{self.id}"
        return f"[{num}] {self.title[:60]}"


# ==============================================================================
# Task Comments Model
# ==============================================================================
class TaskComment(BaseModel):
    """Комментарий к задаче."""
    task = models.ForeignKey(
        Task,
        on_delete=models.CASCADE,
        related_name='comments', # Имя для доступа task.comments.all()
        verbose_name=_("Задача"),
        db_index=True
    )
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL, # Сохраняем коммент, даже если юзер удален
        related_name='task_comments',
        verbose_name=_("Автор"),
        null=True, # Автор может быть null, если пользователь удален
        blank=False, # Но при создании автор должен быть
        db_index=True
    )
    text = models.TextField(
        verbose_name=_("Текст комментария"),
        blank=False # Комментарий не может быть пустым
    )
    # created_at, updated_at наследуются от BaseModel

    class Meta:
        verbose_name = _("Комментарий к задаче")
        verbose_name_plural = _("Комментарии к задачам")
        ordering = ['created_at'] # По умолчанию сначала старые
        indexes = [
            models.Index(fields=['task']),
            models.Index(fields=['author']),
            models.Index(fields=['created_at']),
        ]

    def __str__(self):
        author_name = self.author.display_name if self.author else _("Удаленный пользователь")
        task_display = self.task.task_number or f"ID:{self.task_id}"
        return f"Комментарий от {author_name} к {task_display} ({self.created_at:%d.%m.%y %H:%M})"

# ------------------------ Task Photos ------------------------
class TaskPhoto(BaseModel):
    task = models.ForeignKey(Task, on_delete=models.CASCADE, related_name="photos", verbose_name=_("Задача"), db_index=True)
    uploaded_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="uploaded_photos", verbose_name=_("Загрузил"))
    photo = models.ImageField(upload_to="task_photos/", verbose_name=_("Фотография"))
    description = models.CharField(max_length=255, blank=True, verbose_name=_("Описание фотографии"))

    class Meta:
        verbose_name = _("Фотография к задаче")
        verbose_name_plural = _("Фотографии к задачам")
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["task"], name="taskphoto_task_idx")]

    def __str__(self):
        task_display = self.task.task_number or f"Task {self.task_id}"
        uploader = self.uploaded_by.username if self.uploaded_by else _("неизвестно")
        return f"Фото ({self.id}) к {task_display} от {uploader}"


# ------------------------ Signals ------------------------

@receiver(post_save, sender=Task)
def task_post_save_handler(sender, instance: Task, created: bool, update_fields=None, **kwargs):
    """
    Обработчик после сохранения задачи. Отправляет WebSocket уведомления при изменении статуса.
    Объединяет логику уведомлений о завершении с общим обновлением статуса.
    """
    status_changed = update_fields is None or 'status' in update_fields

    if status_changed:
        # Определяем, завершена ли задача в этом сохранении
        is_completed_now = instance.status == Task.StatusChoices.COMPLETED

        # Собираем базовые данные для сообщения
        task_data_for_detail = {
            "event": "status_update",
            "task_id": instance.id,
            "status": instance.status,
            "status_display": instance.status_display,
            "completion_date": instance.completion_date.isoformat() if instance.completion_date else None,
            "is_completed": is_completed_now, # Добавляем флаг завершения
            # Можно добавить, кто изменил (если эта информация доступна)
            # "updated_by": getattr(instance, '_updated_by_user', None) # Пример, если передавать пользователя
        }
        task_data_for_list = {
            "event": "task_updated",
            "task_id": instance.id,
            "status": instance.status,
            "priority": instance.priority,
            "title": instance.title,
            "is_completed": is_completed_now, # Также полезно для списка
        }

        # Отправляем WebSocket уведомления
        try:
            channel_layer = get_channel_layer()
            # Уведомление для страницы деталей задачи
            async_to_sync(channel_layer.group_send)(
                f"task_{instance.id}", # Группа для конкретной задачи
                {"type": "task_update", "message": task_data_for_detail}
            )
            # Уведомление для общего списка задач
            async_to_sync(channel_layer.group_send)(
                "tasks_list", # Группа для списков задач
                {"type": "list_update", "message": task_data_for_list}
            )
            logger.debug(f"Sent WebSocket update for Task {instance.id} (Status: {instance.status}, Completed: {is_completed_now})")

            # Если нужно отправить email или другие уведомления ИМЕННО при завершении:
            if is_completed_now:
                 # Проверяем, что статус *только что* изменился на COMPLETED,
                 # чтобы избежать повторной отправки при каждом сохранении уже завершенной задачи.
                 was_just_completed = False
                 if created: # Создана сразу завершенной
                      was_just_completed = True
                 else:
                      # Проверяем предыдущее состояние (если возможно)
                      try:
                           # Запрашиваем только старый статус для оптимизации
                           old_status = Task.objects.values('status').get(pk=instance.pk)['status']
                           if old_status != Task.StatusChoices.COMPLETED:
                                was_just_completed = True
                      except Task.DoesNotExist:
                           was_just_completed = True # Если старой нет - значит, только что создана/завершена
                      except Exception as e:
                           logger.error(f"Could not reliably determine previous status for task {instance.id}: {e}")
                           # В этом случае можем отправить уведомление на всякий случай, или пропустить
                           # was_just_completed = True # Отправить на всякий случай

                 if was_just_completed:
                      logger.info(f"Task {instance.task_number} was just completed. Triggering specific completion actions (e.g., email).")
                      # Здесь можно вызвать функцию отправки email и т.д.
                    #   from .notifications import send_task_completion_email
                    #   send_task_completion_email(instance)


        except Exception as e:
            logger.error(f"Failed during WebSocket/completion notification for Task {instance.id}: {e}")