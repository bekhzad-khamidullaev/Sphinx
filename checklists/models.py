import logging
import uuid
from django.db import models
from django.conf import settings
from django.urls import reverse
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from django.core.exceptions import ValidationError
from taggit.managers import TaggableManager

try:
    # This try-except block allows the checklist app to function
    # even if the tasks app is not installed or configured.
    from tasks.models import Task, TaskCategory
except ImportError:
    Task = None
    TaskCategory = None
    logging.warning("Could not import Task or TaskCategory from tasks.models. Checklist functionality might be limited.")
    # Define dummy models to prevent NameError if Task/TaskCategory are used in FKs
    class Task:
         pass
    class TaskCategory:
         pass


User = settings.AUTH_USER_MODEL
logger = logging.getLogger(__name__)

class AnswerType(models.TextChoices):
    """
    Defines the expected type of answer for a ChecklistTemplateItem.
    Influences form rendering and data storage/validation.
    """
    TEXT = 'text', _('Текстовое поле') # Single or multi-line text
    NUMBER = 'number', _('Числовое поле') # Integer or float
    SCALE_1_4 = 'scale_1_4', _('Оценка 1–4') # Discrete scale
    SCALE_1_5 = 'scale_1_5', _('Оценка 1–5') # Discrete scale
    YES_NO = 'yes_no', _('Да / Нет') # Simple binary choice
    YES_NO_MEH = 'yes_no_meh', _('Да / Нет / Не очень') # Ternary choice
    BOOLEAN = 'boolean', _('Да/Нет (Boolean)') # True/False/None
    DATE = 'date', _('Дата')
    DATETIME = 'datetime', _('Дата и время')
    TIME = 'time', _('Время')
    FILE = 'file', _('Файл') # Allows uploading a file per result
    URL = 'url', _('Ссылка') # Allows entering a URL


class ChecklistRunStatus(models.TextChoices):
    """
    Overall status of a performed Checklist run.
    """
    DRAFT = 'draft', _('Черновик')
    IN_PROGRESS = 'in_progress', _('В процессе')
    SUBMITTED = 'submitted', _('Отправлено') # Completed by performer, awaiting review
    APPROVED = 'approved', _('Одобрено') # Reviewed and approved
    REJECTED = 'rejected', _('Отклонено') # Reviewed and rejected (may require correction)

class ChecklistItemStatus(models.TextChoices):
    """
    Status of a specific item within a completed checklist run result.
    Used for tracking, reporting, and identifying issues.
    """
    PENDING = 'pending', _('Ожидает ответа') # Initial status before response is recorded
    OK = 'ok', _('OK') # Item meets criteria
    NOT_OK = 'not_ok', _('Не OK') # Item does not meet criteria (an issue)
    NOT_APPLICABLE = 'na', _('Неприменимо') # Item is not relevant in this context


class Location(models.Model):
    """
    Represents a physical or logical location/area. Can be hierarchical.
    """
    name = models.CharField(max_length=150, unique=True, verbose_name=_("Название Местоположения"))
    description = models.TextField(blank=True, verbose_name=_("Описание"))
    parent = models.ForeignKey('self', null=True, blank=True, on_delete=models.SET_NULL, related_name='child_locations', verbose_name=_("Родительское Местоположение"))
    created_at = models.DateTimeField(auto_now_add=True, verbose_name=_("Создан"))
    updated_at = models.DateTimeField(auto_now=True, verbose_name=_("Обновлен"))

    class Meta:
        verbose_name = _("Местоположение")
        verbose_name_plural = _("Местоположения")
        ordering = ['name']

    def __str__(self):
        return self.name

class ChecklistPoint(models.Model):
    """
    Represents a specific point, room, or area within a Location.
    """
    location = models.ForeignKey(Location, on_delete=models.CASCADE, related_name='points', verbose_name=_("Местоположение"))
    name = models.CharField(max_length=150, verbose_name=_("Название Точки/Комнаты"))
    description = models.TextField(blank=True, verbose_name=_("Описание"))
    created_at = models.DateTimeField(auto_now_add=True, verbose_name=_("Создан"))
    updated_at = models.DateTimeField(auto_now=True, verbose_name=_("Обновлен"))

    class Meta:
        verbose_name = _("Точка/Комната Чеклиста")
        verbose_name_plural = _("Точки/Комнаты Чеклистов")
        ordering = ['location__name', 'name']
        constraints = [models.UniqueConstraint(fields=['location', 'name'], name='unique_point_per_location')]

    def __str__(self):
        return f"{self.location.name} / {self.name}"

class ChecklistTemplate(models.Model):
    """
    Defines the structure and properties of a checklist.
    """
    uuid = models.UUIDField(default=uuid.uuid4, editable=False, unique=True)
    name = models.CharField(max_length=255, verbose_name=_("Название шаблона"))
    description = models.TextField(blank=True, verbose_name=_("Описание"))
    # Use dummy TaskCategory if the app is not available
    category = models.ForeignKey(TaskCategory if TaskCategory else 'self', on_delete=models.SET_NULL, null=True, blank=True, related_name='checklist_templates', verbose_name=_("Категория (из Задач)"))
    target_location = models.ForeignKey(Location, on_delete=models.SET_NULL, null=True, blank=True, related_name='checklist_templates', verbose_name=_("Целевое Местоположение"))
    target_point = models.ForeignKey(ChecklistPoint, on_delete=models.SET_NULL, null=True, blank=True, related_name='checklist_templates', verbose_name=_("Целевая Точка/Комната"))
    is_active = models.BooleanField(default=True, verbose_name=_("Активен"))
    version = models.CharField(max_length=20, blank=True, default="1.0", verbose_name=_("Версия"))
    is_archived = models.BooleanField(default=False, verbose_name=_("Архивирован"))
    frequency = models.CharField(max_length=50, blank=True, verbose_name=_("Периодичность"))
    next_due_date = models.DateField(null=True, blank=True, verbose_name=_("След. дата выполнения"))
    tags = TaggableManager(blank=True, verbose_name=_("Теги"))
    created_at = models.DateTimeField(auto_now_add=True, verbose_name=_("Создан"))
    updated_at = models.DateTimeField(auto_now=True, verbose_name=_("Обновлен"))

    class Meta:
        verbose_name = _("Шаблон чеклиста")
        verbose_name_plural = _("Шаблоны чеклистов")
        ordering = ['category__name' if TaskCategory else 'name', 'name'] # Adjust ordering if category is dummy

    def __str__(self):
        return self.name

    def get_absolute_url(self):
        return reverse('checklists:template_detail', kwargs={'pk': self.pk})

    def clean(self):
        # Ensure target_point belongs to target_location if both are set
        if self.target_point and self.target_location and self.target_point.location != self.target_location:
            raise ValidationError({'target_point': _('Выбранная точка не принадлежит указанному местоположению.')})
        # Clear target_point if target_location is cleared
        if not self.target_location and self.target_point:
            self.target_point = None


class ChecklistSection(models.Model):
    """
    Represents a section within a Checklist Template to group items.
    """
    template = models.ForeignKey(ChecklistTemplate, on_delete=models.CASCADE, related_name='sections')
    title = models.CharField(max_length=255, verbose_name=_('Название секции'))
    order = models.PositiveIntegerField(default=0)

    class Meta:
        verbose_name = _("Секция шаблона")
        verbose_name_plural = _("Секции шаблона")
        ordering = ['order', 'title']
        unique_together = ('template', 'order') # Ensure order is unique within a template section list

    def __str__(self):
        return self.title


class ChecklistTemplateItem(models.Model):
    """
    Represents a single point/question within a Checklist Template.
    """
    template = models.ForeignKey(ChecklistTemplate, on_delete=models.CASCADE, related_name='items', verbose_name=_("Шаблон"))
    section = models.ForeignKey(ChecklistSection, on_delete=models.SET_NULL, null=True, blank=True, related_name='items', verbose_name=_("Секция"))
    item_text = models.TextField(verbose_name=_("Текст пункта/вопроса"))
    order = models.PositiveIntegerField(default=0, verbose_name=_("Порядок"))
    target_point = models.ForeignKey(ChecklistPoint, on_delete=models.SET_NULL, null=True, blank=True, related_name='template_items', verbose_name=_("Целевая Точка"))
    answer_type = models.CharField(max_length=20, choices=AnswerType.choices, default=AnswerType.TEXT, verbose_name=_("Тип ответа"))
    help_text = models.CharField(max_length=255, blank=True, verbose_name=_("Подсказка"))
    default_value = models.CharField(max_length=255, blank=True, verbose_name=_("Значение по умолчанию")) # Stored as text, needs parsing based on answer_type
    parent_item = models.ForeignKey('self', null=True, blank=True, on_delete=models.SET_NULL, related_name='sub_items', verbose_name=_("Родительский пункт"))
    # is_required = models.BooleanField(default=True, verbose_name=_("Обязательный")) # Consider adding required flag

    class Meta:
        verbose_name = _("Пункт шаблона чеклиста")
        verbose_name_plural = _("Пункты шаблонов чеклистов")
        # Order by template, section order (if section exists), then item order
        ordering = ['template', 'section__order', 'order', 'id']
        # Ensure order is unique within a section for a template
        unique_together = ('template', 'section', 'order')

    def __str__(self):
        section_prefix = f"{self.section.order}. " if self.section else ""
        return f"{section_prefix}{self.order}. {self.item_text[:50]}{'...' if len(self.item_text) > 50 else ''}"

    def clean(self):
        # Ensure target_point belongs to template's location if both are set
        if self.target_point and self.template.target_location and self.target_point.location != self.template.target_location:
            raise ValidationError({'target_point': _('Точка пункта не соответствует местоположению шаблона.')})
        # If section is set, ensure it belongs to the template
        if self.section and self.section.template != self.template:
             raise ValidationError({'section': _('Секция должна принадлежать тому же шаблону, что и пункт.')})
        # Disallow parent_item creating circular dependency or being itself
        if self.parent_item and self.parent_item == self:
             raise ValidationError({'parent_item': _('Пункт не может быть родительским сам для себя.')})
        # Basic check for simple circular dependency (doesn't cover complex chains)
        if self.parent_item and self.parent_item.parent_item == self:
             raise ValidationError({'parent_item': _('Обнаружена простая циклическая зависимость с родительским пунктом.')})

class Checklist(models.Model):
    """
    Represents a single instance of a ChecklistTemplate being performed.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    template = models.ForeignKey(ChecklistTemplate, on_delete=models.PROTECT, related_name='runs', verbose_name=_("Шаблон"))
    performed_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='performed_checklists', verbose_name=_("Кем выполнен"), db_index=True)
    performed_at = models.DateTimeField(default=timezone.now, verbose_name=_("Дата/Время начала"), db_index=True)
    # Use dummy Task if the app is not available
    related_task = models.ForeignKey(Task if Task else 'self', on_delete=models.SET_NULL, null=True, blank=True, related_name='checklists', verbose_name=_("Связанная задача"))
    location = models.ForeignKey(Location, on_delete=models.SET_NULL, null=True, blank=True, related_name='checklist_runs', verbose_name=_("Местоположение"))
    point = models.ForeignKey(ChecklistPoint, on_delete=models.SET_NULL, null=True, blank=True, related_name='checklist_runs', verbose_name=_("Точка"))
    notes = models.TextField(blank=True, verbose_name=_("Примечания"))
    is_complete = models.BooleanField(default=False, verbose_name=_("Завершен"), db_index=True) # Kept for compatibility/ease, but status is primary
    completion_time = models.DateTimeField(null=True, blank=True, verbose_name=_("Время завершения"))
    status = models.CharField(max_length=20, choices=ChecklistRunStatus.choices, default=ChecklistRunStatus.IN_PROGRESS, verbose_name=_("Статус"), db_index=True)
    approved_by = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL, related_name='approved_checklists', verbose_name=_("Одобрено кем"))
    approved_at = models.DateTimeField(null=True, blank=True, verbose_name=_("Время одобрения"))
    score = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True, verbose_name=_("Оценка")) # Overall score (e.g., 1-5 or percentage)
    created_at = models.DateTimeField(auto_now_add=True, verbose_name=_("Создан"))
    updated_at = models.DateTimeField(auto_now=True, verbose_name=_("Обновлен"))
    external_reference = models.CharField(max_length=255, blank=True, null=True, verbose_name=_("Внешняя ссылка")) # For integrations (BI, CRM, etc.)

    class Meta:
        verbose_name = _("Выполненный чеклист")
        verbose_name_plural = _("Выполненные чеклисты")
        ordering = ['-performed_at', '-created_at'] # Order by performed time descending, then creation time

    def __str__(self):
        loc_info = f" @ {self.location.name}" if self.location else ""
        point_info = f" / {self.point.name}" if self.point else ""
        performer = f" ({self.performed_by.username})" if self.performed_by else ""
        return f"{self.template.name}{loc_info}{point_info} - {self.performed_at.strftime('%d.%m.%Y %H:%M')}{performer}"

    def get_absolute_url(self):
        # Use the history_list detail view name
        return reverse('checklists:checklist_detail', kwargs={'pk': self.pk})

    def has_issues(self):
        """Checks if any result has a 'Not OK' status."""
        return self.results.filter(status=ChecklistItemStatus.NOT_OK).exists()

    def mark_complete(self):
        """Marks the checklist run as complete and sets status to SUBMITTED."""
        if not self.is_complete and self.status in [ChecklistRunStatus.DRAFT, ChecklistRunStatus.IN_PROGRESS]:
            self.is_complete = True
            self.completion_time = timezone.now()
            self.status = ChecklistRunStatus.SUBMITTED
            self.save(update_fields=['is_complete', 'completion_time', 'status'])
            logger.info(f"Checklist run {self.id} marked complete and status set to SUBMITTED.")

    def clean(self):
        # Ensure point belongs to location if both are set
        if self.point and self.location and self.point.location != self.location:
            raise ValidationError({'point': _('Точка не принадлежит выбранному местоположению.')})
        # Clear point if location is cleared
        if not self.location and self.point:
            self.point = None


class ChecklistResult(models.Model):
    """
    Stores the result for a specific ChecklistTemplateItem within a Checklist run.
    Uses generic fields to store different data types based on the item's answer_type.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    checklist_run = models.ForeignKey(Checklist, on_delete=models.CASCADE, related_name='results', verbose_name=_("Прогон"))
    template_item = models.ForeignKey(ChecklistTemplateItem, on_delete=models.CASCADE, related_name='results', verbose_name=_("Пункт"))

    # Fields to store the actual answer value based on item's answer_type
    # Use TextField for generic text, scales, yes/no/meh choices
    value = models.TextField(blank=True, null=True, verbose_name=_("Ответ (текст/выбор)")) # Changed to TextField, allow null
    numeric_value = models.FloatField(null=True, blank=True, verbose_name=_("Числовое значение")) # For NUMBER or SCALE types
    boolean_value = models.BooleanField(null=True, blank=True, verbose_name=_("Булево значение")) # For BOOLEAN types
    date_value = models.DateField(null=True, blank=True, verbose_name=_("Дата")) # For DATE types
    datetime_value = models.DateTimeField(null=True, blank=True, verbose_name=_("Дата и время")) # For DATETIME types
    time_value = models.TimeField(null=True, blank=True, verbose_name=_("Время")) # For TIME types
    file_attachment = models.FileField(upload_to='checklist_files/', blank=True, null=True, verbose_name=_("Файл")) # For FILE type
    media_url = models.URLField(max_length=500, blank=True, null=True, verbose_name=_("Ссылка на медиа")) # For URL type or other media (increased max_length)


    comments = models.TextField(blank=True, verbose_name=_("Комментарий"))
    status = models.CharField(max_length=20, choices=ChecklistItemStatus.choices, default=ChecklistItemStatus.PENDING, verbose_name=_("Статус пункта"), db_index=True)

    # is_flagged = models.BooleanField(default=False) # Removed, rely on status=NOT_OK
    is_corrected = models.BooleanField(default=False, verbose_name=_("Исправлено")) # Flag if issue (status=NOT_OK) was corrected later

    recorded_at = models.DateTimeField(auto_now=True, verbose_name=_("Записано")) # Auto update time on save
    created_by = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL, related_name='created_checklist_results', verbose_name=_("Создано кем"))
    updated_by = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL, related_name='updated_checklist_results', verbose_name=_("Обновлено кем"))

    class Meta:
        verbose_name = _("Результат пункта")
        verbose_name_plural = _("Результаты пунктов")
        # Order by the template item's order within the checklist run
        ordering = ['checklist_run', 'template_item__section__order', 'template_item__order']
        unique_together = ('checklist_run', 'template_item') # Ensure only one result per item per run

    def __str__(self):
        item_text = self.template_item.item_text[:30] + ('...' if len(self.template_item.item_text) > 30 else '')
        return f"[{self.get_status_display()}] {item_text} -> {self.display_value or '-'}"

    # No clean method here, validation happens in the form.

    @property
    def display_value(self):
        """
        Returns the most appropriate value for display based on the associated
        ChecklistTemplateItem's answer_type.
        """
        item_type = self.template_item.answer_type
        if item_type == AnswerType.TEXT:
             return self.value
        elif item_type in [AnswerType.SCALE_1_4, AnswerType.SCALE_1_5, AnswerType.NUMBER]:
             # Use numeric_value primarily, fallback to generic value
             return self.numeric_value if self.numeric_value is not None else self.value
        elif item_type in [AnswerType.YES_NO, AnswerType.YES_NO_MEH]:
             # Map stored string value to translated label
             if self.value == 'yes': return _('Да')
             if self.value == 'no': return _('Нет')
             if self.value == 'yes_no_meh': return _('Не очень')
             return self.value # Return raw value if not one of the choices
        elif item_type == AnswerType.BOOLEAN:
             # Map boolean value to translated Yes/No/None
             if self.boolean_value is True: return _('Да')
             if self.boolean_value is False: return _('Нет')
             # If NullBooleanField is None, return '-'
             return "-" if self.boolean_value is None else str(self.boolean_value) # Should not happen if mapped to Yes/No

        elif item_type == AnswerType.DATE:
             # Use date_value primarily
             return self.date_value # Django template filters will format dates
        elif item_type == AnswerType.DATETIME:
             # Use datetime_value primarily
             return self.datetime_value
        elif item_type == AnswerType.TIME:
             # Use time_value primarily
             return self.time_value

        elif item_type == AnswerType.FILE:
             # Return URL if file exists
             return self.file_attachment.url if self.file_attachment else (_("Нет файла") if self.pk else "-")
        elif item_type == AnswerType.URL:
             # Return URL string
             return self.media_url

        # Fallback for any unhandled type or if no specific value field is set
        return self.value or "-" # Return generic value or hyphen if empty


    # Property to determine which model field holds the primary value based on item type
    @property
    def primary_value_field_name(self):
         """Returns the name of the model field used to store the primary value."""
         item_type = self.template_item.answer_type
         if item_type == AnswerType.TEXT: return 'value'
         if item_type in [AnswerType.SCALE_1_4, AnswerType.SCALE_1_5, AnswerType.NUMBER]: return 'numeric_value'
         if item_type in [AnswerType.YES_NO, AnswerType.YES_NO_MEH]: return 'value' # Still store string choices here
         if item_type == AnswerType.BOOLEAN: return 'boolean_value'
         if item_type == AnswerType.DATE: return 'date_value'
         if item_type == AnswerType.DATETIME: return 'datetime_value'
         if item_type == AnswerType.TIME: return 'time_value'
         if item_type == AnswerType.FILE: return 'file_attachment'
         if item_type == AnswerType.URL: return 'media_url'
         return 'value' # Default


# Consider abstracting common fields/logic if you add many more models
# or have complex timestamps/user tracking.