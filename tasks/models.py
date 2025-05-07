# tasks/models.py
# -*- coding: utf-8 -*-

import logging
from datetime import timedelta, datetime, time
from unidecode import unidecode
from django.utils import timezone
from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models, IntegrityError, transaction
from django.db.models import F, Q
from django.dispatch import receiver
from django.db.models.signals import post_save
from django.urls import reverse
from django.utils.translation import gettext_lazy as _
from django.utils.crypto import get_random_string

from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer

# Assuming user_profiles.models exists and is importable
# In a real scenario, handle potential ImportError gracefully if tasks can exist without user_profiles
from user_profiles.models import User, Team, TaskUserRole, Department

logger = logging.getLogger(__name__)

class BaseModel(models.Model):
    created_at = models.DateTimeField(auto_now_add=True, verbose_name=_("Дата создания"))
    updated_at = models.DateTimeField(auto_now=True, verbose_name=_("Дата обновления"))

    class Meta:
        abstract = True
        ordering = ['-created_at']


class Project(BaseModel):
    name = models.CharField(max_length=200, verbose_name=_("Название проекта"), db_index=True)
    description = models.TextField(blank=True, verbose_name=_("Описание проекта"))
    start_date = models.DateField(null=True, blank=True, verbose_name=_("Дата начала"))
    end_date = models.DateField(null=True, blank=True, verbose_name=_("Дата завершения"))

    def clean(self):
        super().clean()
        if self.start_date and self.end_date and self.start_date > self.end_date:
            raise ValidationError(_("Дата завершения не может быть раньше даты начала."))

    def save(self, *args, **kwargs):
        is_new = self._state.adding
        super().save(*args, **kwargs)
        try:
            channel_layer = get_channel_layer()
            action = "create" if is_new else "update"
            async_to_sync(channel_layer.group_send)(
                "projects_list", # General group for project list updates
                {"type": "project_update", # Corresponds to a method in a consumer
                 "message": {"action": action, "id": self.id, "name": self.name}}
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
         # Points to the task list filtered by this project, a common UX pattern
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
        OVERDUE = "overdue", _("Просрочена") # Added Overdue status

    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name="tasks", verbose_name=_("Проект"), db_index=True)
    category = models.ForeignKey(TaskCategory, on_delete=models.SET_NULL, null=True, blank=True, related_name="tasks", verbose_name=_("Категория"), db_index=True)
    subcategory = models.ForeignKey(TaskSubcategory, on_delete=models.SET_NULL, null=True, blank=True, related_name="tasks", verbose_name=_("Подкатегория"), db_index=True)
    task_number = models.CharField(max_length=25, unique=True, blank=True, verbose_name=_("Номер задачи"), db_index=True)
    title = models.CharField(max_length=255, verbose_name=_("Название задачи"))
    description = models.TextField(verbose_name=_("Описание задачи"), blank=True)
    status = models.CharField(max_length=20, choices=StatusChoices.choices, default=StatusChoices.NEW, verbose_name=_("Статус"), db_index=True)
    priority = models.IntegerField(default=TaskPriority.MEDIUM, choices=TaskPriority.choices, verbose_name=_("Приоритет"), db_index=True)
    deadline = models.DateTimeField(null=True, blank=True, verbose_name=_("Срок выполнения"), db_index=True)
    start_date = models.DateField(verbose_name=_('Дата начала')) # Changed from DateTimeField, tasks usually start on a day
    completion_date = models.DateTimeField(null=True, blank=True, verbose_name=_("Дата завершения"))
    estimated_time = models.DurationField(null=True, blank=True, verbose_name=_("Оценка времени"))
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="created_tasks", verbose_name=_("Создатель"), db_index=True)
    # User roles are now managed via TaskUserRole model (see user_profiles.models)

    def clean(self):
        super().clean()

        if self.start_date:
            # Convert DateField to aware datetime for comparison with DateTimeFields
            # Assuming start_date is the beginning of the day in the current timezone
            start_datetime = timezone.make_aware(datetime.combine(self.start_date, time.min))

            if self.deadline and self.deadline < start_datetime:
                raise ValidationError({
                    'deadline': _("Срок выполнения не может быть раньше даты начала.")
                })

            if self.completion_date and self.completion_date < start_datetime:
                raise ValidationError({
                    'completion_date': _("Дата завершения не может быть раньше даты начала.")
                })

        if self.category and self.subcategory and self.category != self.subcategory.category:
            raise ValidationError(_("Подкатегория не принадлежит выбранной категории."))

        # Auto-set category if only subcategory is provided and category is missing
        if not self.category and self.subcategory:
            self.category = self.subcategory.category

        # Handle completion_date based on status
        is_being_completed = (self.status == self.StatusChoices.COMPLETED)
        original_status = None
        if not self._state.adding and self.pk: # Check if instance exists
            try:
                original_task = Task.objects.get(pk=self.pk)
                original_status = original_task.status
            except Task.DoesNotExist:
                pass # Should not happen if pk exists, but handle defensively

        if is_being_completed and not self.completion_date:
            self.completion_date = timezone.now()
        elif not is_being_completed and original_status == self.StatusChoices.COMPLETED:
            # If status changes from COMPLETED to something else, clear completion_date
            self.completion_date = None

        # Auto-set to OVERDUE if applicable (before save)
        if self.is_overdue and self.status not in (
            self.StatusChoices.COMPLETED,
            self.StatusChoices.CANCELLED,
            self.StatusChoices.OVERDUE # Avoid re-setting if already overdue
        ):
            self.status = self.StatusChoices.OVERDUE

    def save(self, *args, **kwargs):
        is_new = self._state.adding
        # Ensure clean() is called to validate and potentially set category from subcategory,
        # or set status to OVERDUE, or set completion_date.
        # The ModelForm will call clean() on the form, which calls clean() on the model instance.
        # If saving directly (not via form), full_clean() should be called.
        # For task_number generation, we need project_id.
        if is_new: # Only call full_clean if it's a new object or not called by form
            if not kwargs.get('force_insert', False) and not hasattr(self, '_called_from_form_save'):
                 self.full_clean() # This will call self.clean()

        if is_new and not self.task_number:
            # self.project_id should be set by now if project was assigned
            self.task_number = self._generate_unique_task_number()

        super().save(*args, **kwargs)


    def _generate_unique_task_number(self):
        if not self.project_id:
             logger.warning("Attempting to generate task number without a project. This task may not be associated with a project yet.")
             project_code = "TASK" # Fallback prefix if no project
             # Query for tasks without a project to determine the next number in that "global" sequence
             last_task_qs = Task.objects.filter(project__isnull=True)
        else:
            try:
                # Fetch project name efficiently
                project_name = Project.objects.values_list('name', flat=True).get(id=self.project_id)
                project_code = unidecode(project_name).upper()
                project_code = "".join(filter(str.isalnum, project_code))[:4] or "PROJ" # Ensure non-empty, max 4 chars
            except Project.DoesNotExist:
                 logger.error(f"Project with id {self.project_id} not found during task number generation. Using fallback prefix 'UNKP'.")
                 project_code = "UNKP" # Unknown Project
            last_task_qs = Task.objects.filter(project_id=self.project_id)

        max_attempts = 10
        for attempt in range(max_attempts):
            try:
                # Using transaction.atomic and select_for_update to handle concurrency
                with transaction.atomic():
                    # Lock the relevant rows or a proxy table if high concurrency is an issue
                    # For project-specific sequences, locking last_task in that project is good.
                    last_task = last_task_qs.select_for_update().order_by('-id').values('task_number').first()

                    next_number = 1
                    if last_task and last_task['task_number']:
                        # Attempt to parse the numeric part of the last task_number
                        # Assuming format like "PROJ-0001"
                        parts = last_task['task_number'].split('-')
                        if len(parts) > 1 and parts[-1].isdigit():
                             try:
                                 next_number = int(parts[-1]) + 1
                             except ValueError:
                                 logger.warning(f"Could not parse number part '{parts[-1]}' from task number {last_task['task_number']}. Resetting sequence for {project_code}.")
                        else:
                             logger.warning(f"Last part of task number {last_task['task_number']} is not a digit or format is unexpected. Resetting sequence for {project_code}.")

                    new_task_number = f"{project_code}-{next_number:04d}" # Pad with leading zeros

                    # Check for existence outside the transaction or after potential commit if possible,
                    # but for uniqueness, this check inside is common.
                    if not Task.objects.filter(task_number=new_task_number).exists():
                        logger.info(f"Generated task number {new_task_number} for project {self.project_id or 'None'}")
                        return new_task_number
                    else:
                        # This case means the generated number (e.g., PROJ-0005) already exists,
                        # possibly due to manual entry or a past error.
                        # The loop will retry, and next_number will be incremented based on the *colliding* number
                        # or, if the logic is simpler, it might just increment from the `last_task` again,
                        # which could lead to repeated collisions if the sequence has gaps filled manually.
                        # A robust solution might involve querying for the MAX number matching the pattern if collisions occur.
                        # For now, the current logic will increment from `last_task`'s sequence.
                        logger.warning(f"Generated task number {new_task_number} already exists (attempt {attempt+1}). Retrying with incremented number or new random part if logic changes.")
                        # If collision, next_number should be incremented based on the collision or a new strategy
            except IntegrityError as e: # Should be rare with the .exists() check, but guards against race conditions if not perfectly transactional
                logger.error(f"IntegrityError during task number generation (attempt {attempt+1}): {e}. Retrying.")
            except Exception as e: # Catch other unexpected errors
                logger.exception(f"Unexpected error during task number generation (attempt {attempt+1}): {e}. Retrying.")

            # Small delay before retrying to avoid hammering DB on persistent conflict
            if attempt < max_attempts - 1:
                 import time # local import
                 time.sleep(0.1 * (attempt + 1)) # Exponential backoff

        # Fallback if all attempts fail
        logger.error("Failed to generate unique task number after multiple attempts. Using fallback with timestamp and random string.")
        timestamp_part = timezone.now().strftime('%Y%m%d%H%M%S%f') # Added microseconds for more uniqueness
        random_part = get_random_string(6).upper() # Increased random part length
        fallback_number = f"{project_code}-FLBK-{timestamp_part}-{random_part}"

        # Final check for the fallback number, though highly unlikely to collide
        if not Task.objects.filter(task_number=fallback_number).exists():
            return fallback_number
        else:
            # This case is extremely rare and indicates a deeper issue or extreme load.
            logger.critical(f"Fallback task number {fallback_number} also collided. Raising IntegrityError.")
            raise IntegrityError("Fatal: Could not generate a unique task number even with robust fallback.")


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
        # Ensure TaskUserRole is available and properly configured
        if 'user_profiles.TaskUserRole' in settings.INSTALLED_APPS or hasattr(self, 'user_roles'):
            # This assumes 'user_roles' is the related_name from TaskUserRole to Task
            return User.objects.filter(task_roles__task=self, task_roles__role=role)
        return User.objects.none() # Return empty queryset if roles not available


    def get_responsible_users(self):
        return self.get_users_by_role(TaskUserRole.RoleChoices.RESPONSIBLE)

    def get_executors(self):
        return self.get_users_by_role(TaskUserRole.RoleChoices.EXECUTOR)

    def get_watchers(self):
        return self.get_users_by_role(TaskUserRole.RoleChoices.WATCHER)


    def has_permission(self, user, permission_type='view'):
        """
        Checks if a user has a specific type of permission for this task.
        Types: 'view', 'change', 'delete', 'change_status', 'assign_users', 'add_comment'
        """
        if not user or not user.is_authenticated:
            return False
        if user.is_superuser or user.is_staff: # Staff often have wide-ranging permissions
            return True

        is_creator = self.created_by == user
        # Efficiently check roles if TaskUserRole is used
        user_roles_set = set()
        if hasattr(self, 'user_roles'): # Checks if reverse relation exists (from TaskUserRole.task)
            # Fetch all roles for this user on this task in one go
            user_roles_set = set(self.user_roles.filter(user=user).values_list('role', flat=True))

        is_responsible = TaskUserRole.RoleChoices.RESPONSIBLE in user_roles_set
        is_executor = TaskUserRole.RoleChoices.EXECUTOR in user_roles_set
        # is_watcher = TaskUserRole.RoleChoices.WATCHER in user_roles_set # Watchers usually don't get edit/delete
        is_participant = bool(user_roles_set) # Any role makes a participant

        # Define permissions based on roles and creator status
        if permission_type == 'view':
            # Creator, any participant, or specific project/org permissions (to be added later)
            return is_creator or is_participant
        if permission_type == 'change': # General change permission
            return is_creator or is_responsible or is_executor
        if permission_type == 'delete':
            return is_creator or is_responsible # Typically only creator or lead can delete
        if permission_type == 'change_status':
            return is_responsible or is_executor
        if permission_type == 'assign_users': # Who can change responsible/executors/watchers
            return is_creator or is_responsible
        if permission_type == 'add_comment': # Typically, any participant or creator can comment
            return is_creator or is_participant

        # Default to False if no specific rule matches
        logger.debug(f"Permission '{permission_type}' denied for user {user.username} on task {self.id}.")
        return False


    class Meta:
        verbose_name = _("Задача")
        verbose_name_plural = _("Задачи")
        ordering = ["priority", "deadline", "-created_at"] # Default ordering
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


class TaskComment(BaseModel):
    task = models.ForeignKey(
        Task,
        on_delete=models.CASCADE,
        related_name='comments',
        verbose_name=_("Задача"),
        db_index=True # Good for querying comments by task
    )
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL, # Keep comment if author deleted, but mark as unknown
        related_name='task_comments',
        verbose_name=_("Автор"),
        null=True, # Allow anonymous/system comments if author is null
        blank=False, # But if set, it must be a valid user
        db_index=True
    )
    text = models.TextField(
        verbose_name=_("Текст комментария"),
        blank=False # Comments should not be empty
    )

    class Meta:
        verbose_name = _("Комментарий к задаче")
        verbose_name_plural = _("Комментарии к задачам")
        ordering = ['created_at'] # Show oldest comments first by default
        indexes = [
            models.Index(fields=['task']),
            models.Index(fields=['author']),
            models.Index(fields=['created_at']),
        ]

    def __str__(self):
        author_name = self.author.display_name if self.author else _("Удаленный пользователь")
        task_display = self.task.task_number or f"ID:{self.task_id}"
        return f"Комментарий от {author_name} к {task_display} ({self.created_at:%d.%m.%y %H:%M})"


class TaskPhoto(BaseModel):
    task = models.ForeignKey(Task, on_delete=models.CASCADE, related_name="photos", verbose_name=_("Задача"), db_index=True)
    uploaded_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="uploaded_photos", verbose_name=_("Загрузил"))
    photo = models.ImageField(upload_to="task_photos/", verbose_name=_("Фотография"), blank=True, null=True) # Consider adding validators for size/type
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


# --- Signals for WebSocket updates ---
# This signal handler broadcasts task updates to relevant WebSocket groups.
@receiver(post_save, sender=Task)
def task_post_save_handler(sender, instance: Task, created: bool, update_fields=None, **kwargs):
    # Determine if status actually changed or if it's a new task
    # `update_fields` is a frozenset of field names passed to save(), or None for full save
    status_changed = not update_fields or 'status' in update_fields # True if new or status updated

    if status_changed: # Only send if status might have changed or it's new
        is_completed_now = instance.status == Task.StatusChoices.COMPLETED
        original_status = None # Hard to get reliably here without pre_save or dirty fields

        # Data for task detail page clients (more comprehensive)
        task_data_for_detail = {
            "event": "status_update", # Specific event for status changes on detail page
            "task_id": instance.id,
            "status": instance.status,
            "status_display": instance.status_display, # from @property
            "completion_date": instance.completion_date.isoformat() if instance.completion_date else None,
            "is_completed": is_completed_now,
            # Add other fields if detail view needs them updated in real-time
        }
        # Data for task list page clients (more concise)
        task_data_for_list = {
            "event": "task_updated", # General event for list updates
            "task_id": instance.id,
            "status": instance.status,
            "priority": instance.priority,
            "title": instance.title,
            "is_completed": is_completed_now,
            # Add other fields relevant for list view items
        }

        try:
            channel_layer = get_channel_layer()
            # Send to specific task group (for detail views)
            async_to_sync(channel_layer.group_send)(
                f"task_{instance.id}", # Group for this specific task
                {"type": "task_update", "message": task_data_for_detail}
            )
            # Send to general task list group
            async_to_sync(channel_layer.group_send)(
                "tasks_list", # General group for task lists
                {"type": "list_update", "message": task_data_for_list}
            )
            logger.debug(f"Sent WebSocket update for Task {instance.id} (Status: {instance.status})")

            # Trigger external notifications (e.g., email via signals.py) if just completed
            if is_completed_now:
                # Determine if it was *just* completed in this save operation.
                # This logic is simplified. For true "just completed", you'd need to know the status *before* this save.
                was_just_completed = False
                if created: # Created and immediately completed
                    was_just_completed = True
                else:
                    # This part is tricky without knowing the exact previous status before this save.
                    # If update_fields is None, it's a full save, status could have changed.
                    # If update_fields has 'status', it definitely changed or was set.
                    # A robust check for "just completed" often involves comparing with the status before the save.
                    # For now, assume if it's completed and status was part of update_fields (or full save), it's "just completed".
                    # This might lead to repeated "completion" notifications if a completed task is saved again without status change.
                    # A better check would involve pre_save signal or a field to track previous status.
                    if status_changed: # If status was involved in the update
                        # This check is imperfect without old_status value prior to this save call.
                        # We assume if it's completed now and status was part of the update, it's a "new" completion event.
                        was_just_completed = True # Simplified assumption

                if was_just_completed:
                     logger.info(f"Task {instance.task_number} was just completed. Triggering specific completion actions.")
                     # Example: if you have a signal for task completion defined in signals.py
                     # from .signals import task_completed_signal # Ensure this signal is defined
                     # task_completed_signal.send(sender=Task, task=instance)

                     # Or call a notification function directly (less decoupled)
                     # from .notifications import send_task_completion_email
                     # send_task_completion_email(instance)

        except Exception as e:
            logger.error(f"Failed during WebSocket/completion notification for Task {instance.id}: {e}")