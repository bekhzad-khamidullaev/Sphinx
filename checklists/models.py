# checklists/models.py
import logging
import uuid
from django.db import models
from django.conf import settings
from django.urls import reverse
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from django.core.exceptions import ValidationError

# Safely import Task and TaskCategory from the tasks app
try:
    from tasks.models import Task, TaskCategory
except ImportError:
    Task = None
    TaskCategory = None
    logging.warning("Could not import Task or TaskCategory from tasks.models. Checklist functionality might be limited.")

# Use AUTH_USER_MODEL from settings for flexibility
User = settings.AUTH_USER_MODEL
logger = logging.getLogger(__name__)

# ==================================
# Location and Point Models
# ==================================
class Location(models.Model):
    """ Represents a physical location (e.g., Building, Floor, Area). """
    name = models.CharField(max_length=150, unique=True, verbose_name=_("Название Местоположения"))
    description = models.TextField(blank=True, verbose_name=_("Описание"))
    parent = models.ForeignKey(
        'self', null=True, blank=True, on_delete=models.SET_NULL,
        related_name='child_locations', verbose_name=_("Родительское Местоположение")
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = _("Местоположение")
        verbose_name_plural = _("Местоположения")
        ordering = ['name']

    def __str__(self):
        return self.name

class ChecklistPoint(models.Model):
    """ Represents a specific point or room within a Location. """
    location = models.ForeignKey(
        Location, on_delete=models.CASCADE, related_name='points',
        verbose_name=_("Местоположение")
    )
    name = models.CharField(max_length=150, verbose_name=_("Название Точки/Комнаты"))
    description = models.TextField(blank=True, verbose_name=_("Описание"))
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = _("Точка/Комната Чеклиста")
        verbose_name_plural = _("Точки/Комнаты Чеклистов")
        ordering = ['location__name', 'name']
        constraints = [
            models.UniqueConstraint(fields=['location', 'name'], name='unique_point_per_location')
        ]

    def __str__(self):
        return f"{self.location.name} / {self.name}"


# ==================================
# Checklist Template Models
# ==================================
class ChecklistTemplate(models.Model):
    """ Defines the structure and standard items for a reusable checklist. """
    name = models.CharField(max_length=255, verbose_name=_("Название шаблона"))
    description = models.TextField(blank=True, verbose_name=_("Описание"))
    category = models.ForeignKey(
        TaskCategory, # Will be None if tasks app not found
        on_delete=models.SET_NULL, null=True, blank=True,
        related_name='checklist_templates', verbose_name=_("Категория (из Задач)")
    )
    target_location = models.ForeignKey(
        Location, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='checklist_templates_loc', # Changed related_name to avoid clash
        verbose_name=_("Целевое Местоположение (Общее)")
    )
    target_point = models.ForeignKey(
        ChecklistPoint, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='checklist_templates_point', # Changed related_name
        verbose_name=_("Целевая Точка/Комната (Общая)")
    )
    is_active = models.BooleanField(default=True, verbose_name=_("Активен"), help_text=_("Активные шаблоны доступны для выполнения."))
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = _("Шаблон чеклиста")
        verbose_name_plural = _("Шаблоны чеклистов")
        ordering = ['category__name', 'name']

    def __str__(self):
        return self.name

    def get_absolute_url(self):
        return reverse('checklists:template_detail', kwargs={'pk': self.pk})

    def clean(self):
        # Ensure target_point belongs to target_location if both are set
        if self.target_point and self.target_location:
            if self.target_point.location != self.target_location:
                raise ValidationError({
                    'target_point': ValidationError(
                        _('Выбранная точка не принадлежит указанному местоположению.'),
                        code='point_location_mismatch'
                    )
                })
        # Ensure point is cleared if location is cleared
        if not self.target_location and self.target_point:
             self.target_point = None # Clear point if location is removed


class ChecklistTemplateItem(models.Model):
    """ An individual item/question within a ChecklistTemplate. """
    template = models.ForeignKey(
        ChecklistTemplate, on_delete=models.CASCADE,
        related_name='items', verbose_name=_("Шаблон")
    )
    item_text = models.TextField(verbose_name=_("Текст пункта/вопроса")) # Use TextField
    order = models.PositiveIntegerField(default=0, verbose_name=_("Порядок"), help_text=_("Порядок отображения пункта в чеклисте."))
    target_point = models.ForeignKey(
        ChecklistPoint, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='template_items', verbose_name=_("Целевая Точка/Комната для Пункта"),
        help_text=_("Опционально: привязать этот пункт к конкретной точке/комнате.")
    )

    class Meta:
        verbose_name = _("Пункт шаблона чеклиста")
        verbose_name_plural = _("Пункты шаблонов чеклистов")
        ordering = ['template', 'order', 'id']

    def __str__(self):
        return f"{self.template.name} - {self.item_text[:50]}"

    def clean(self):
        # Ensure item's target_point belongs to template's target_location if both are set
        if self.target_point and self.template.target_location:
            if self.target_point.location != self.template.target_location:
                 raise ValidationError({
                    'target_point': ValidationError(
                        _('Точка этого пункта не принадлежит общему местоположению шаблона (%(tmpl_loc)s).') % {'tmpl_loc': self.template.target_location},
                        code='item_point_location_mismatch'
                    )
                })

# ==================================
# Checklist Run Models
# ==================================
# Choices for Item Results/Status
class ChecklistItemStatus(models.TextChoices):
    PENDING = 'pending', _('Ожидает')
    OK = 'ok', _('OK')
    NOT_OK = 'not_ok', _('Не OK')
    NOT_APPLICABLE = 'na', _('Неприменимо')

class Checklist(models.Model):
    """ An instance of a checklist being performed. """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False) # Use UUID for runs
    template = models.ForeignKey(
        ChecklistTemplate, on_delete=models.PROTECT, # Keep history even if template is deleted
        related_name='runs', verbose_name=_("Шаблон")
    )
    performed_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True,
        related_name='performed_checklists', verbose_name=_("Кем выполнен")
    )
    performed_at = models.DateTimeField(default=timezone.now, verbose_name=_("Дата/Время начала"), db_index=True)
    related_task = models.ForeignKey(
        Task, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='checklists', verbose_name=_("Связанная задача")
    )
    # Specific Location/Point for THIS run
    location = models.ForeignKey(
        Location, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='checklist_runs_loc', verbose_name=_("Местоположение Прогона") # Changed related_name
    )
    point = models.ForeignKey(
        ChecklistPoint, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='checklist_runs_point', verbose_name=_("Точка/Комната Прогона") # Changed related_name
    )
    notes = models.TextField(blank=True, verbose_name=_("Общие примечания к Прогону"))
    is_complete = models.BooleanField(default=False, verbose_name=_("Завершен"), db_index=True)
    completion_time = models.DateTimeField(null=True, blank=True, verbose_name=_("Время завершения"))

    class Meta:
        verbose_name = _("Выполненный чеклист (прогон)")
        verbose_name_plural = _("Выполненные чеклисты (прогоны)")
        ordering = ['-performed_at']
        indexes = [
            models.Index(fields=['performed_at']),
            models.Index(fields=['template']),
            models.Index(fields=['performed_by']),
            models.Index(fields=['is_complete']),
            models.Index(fields=['location']),
            models.Index(fields=['point']),
        ]

    def __str__(self):
        user_name = self.performed_by.username if self.performed_by else 'N/A'
        loc_point = f"{self.location}{' / '+self.point.name if self.point else ''}" if self.location else _("Место не указано")
        return f"{self.template.name} [{loc_point}] @ {self.performed_at.strftime('%d.%m.%y %H:%M')} ({user_name})"

    def get_absolute_url(self):
        return reverse('checklists:checklist_detail', kwargs={'pk': self.pk})

    @property
    def has_issues(self):
        return self.results.filter(status=ChecklistItemStatus.NOT_OK).exists()

    def mark_complete(self):
        if not self.is_complete:
            self.is_complete = True
            self.completion_time = timezone.now()
            self.save(update_fields=['is_complete', 'completion_time'])
            logger.info(f"Checklist run {self.id} marked as complete.")

    def clean(self):
        # Ensure point belongs to location if both are set
        if self.point and self.location:
            if self.point.location != self.location:
                 raise ValidationError({
                    'point': ValidationError(
                        _('Выбранная точка не принадлежит указанному местоположению прогона.'),
                        code='run_point_location_mismatch'
                    )
                })
        if not self.location and self.point:
            self.point = None # Clear point if location removed

class ChecklistResult(models.Model):
    """ The result for a specific item within a specific checklist run. """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False) # UUID for results too
    checklist_run = models.ForeignKey(
        Checklist, on_delete=models.CASCADE,
        related_name='results', verbose_name=_("Прогон чеклиста")
    )
    template_item = models.ForeignKey(
        ChecklistTemplateItem, on_delete=models.CASCADE, # Result meaningless without the item
        related_name='results', verbose_name=_("Пункт шаблона")
    )
    status = models.CharField(
        max_length=20, choices=ChecklistItemStatus.choices,
        default=ChecklistItemStatus.PENDING, verbose_name=_("Статус/Результат")
    )
    comments = models.TextField(blank=True, verbose_name=_("Комментарий к пункту"))
    recorded_at = models.DateTimeField(auto_now=True, verbose_name=_("Время записи результата"))

    class Meta:
        verbose_name = _("Результат пункта чеклиста")
        verbose_name_plural = _("Результаты пунктов чеклистов")
        ordering = ['checklist_run', 'template_item__order']
        constraints = [
            models.UniqueConstraint(fields=['checklist_run', 'template_item'], name='unique_result_per_item_run')
        ]
        indexes = [
            models.Index(fields=['checklist_run', 'template_item']),
            models.Index(fields=['status']),
        ]

    def __str__(self):
        status_display = self.get_status_display()
        item_text = self.template_item.item_text[:30] if self.template_item else '???'
        return f"Run {self.checklist_run_id}: '{item_text}...' -> {status_display}"