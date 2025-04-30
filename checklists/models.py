# checklists/models.py
import logging
from django.db import models
from django.conf import settings
from django.urls import reverse
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from tasks.models import Task, TaskCategory # Use categories from tasks app

logger = logging.getLogger(__name__)

# Choices for Item Results/Status
class ChecklistItemStatus(models.TextChoices):
    PENDING = 'pending', _('Ожидает')
    OK = 'ok', _('OK')
    NOT_OK = 'not_ok', _('Не OK')
    NOT_APPLICABLE = 'na', _('Неприменимо')

# ==================================
# Location and Point Models
# ==================================
class Location(models.Model):
    """ Represents a physical location (e.g., Building, Floor, Area). """
    name = models.CharField(max_length=150, unique=True, verbose_name=_("Название Местоположения"))
    description = models.TextField(blank=True, verbose_name=_("Описание"))
    # Optional hierarchy
    parent = models.ForeignKey('self', null=True, blank=True, on_delete=models.SET_NULL, related_name='child_locations', verbose_name=_("Родительское Местоположение"))
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
    location = models.ForeignKey(Location, on_delete=models.CASCADE, related_name='points', verbose_name=_("Местоположение"))
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


class ChecklistTemplate(models.Model):
    name = models.CharField(max_length=255, verbose_name=_("Название шаблона"))
    description = models.TextField(blank=True, verbose_name=_("Описание"))
    category = models.ForeignKey(
        TaskCategory,
        on_delete=models.SET_NULL, null=True, blank=True,
        related_name='checklist_templates', verbose_name=_("Категория (из Задач)")
    )
    # Optional: Link template to a default location/point
    target_location = models.ForeignKey(
        Location, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='checklist_templates', verbose_name=_("Целевое Местоположение")
    )
    target_point = models.ForeignKey(
        ChecklistPoint, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='checklist_templates', verbose_name=_("Целевая Точка/Комната")
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
        # URL to view the template details
        return reverse('checklists:template_detail', kwargs={'pk': self.pk})

class ChecklistTemplateItem(models.Model):
    template = models.ForeignKey(
        ChecklistTemplate,
        on_delete=models.CASCADE,
        related_name='items',
        verbose_name=_("Шаблон")
    )
    # Use TextField for potentially longer items
    item_text = models.TextField(verbose_name=_("Текст пункта/вопроса"))
    order = models.PositiveIntegerField(default=0, verbose_name=_("Порядок"), help_text=_("Порядок отображения пункта в чеклисте."))
    # Optional: Link specific item to a point
    target_point = models.ForeignKey(
        ChecklistPoint, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='template_items', verbose_name=_("Целевая Точка/Комната для Пункта")
    )

    class Meta:
        verbose_name = _("Пункт шаблона чеклиста")
        verbose_name_plural = _("Пункты шаблонов чеклистов")
        ordering = ['template', 'order', 'id'] # Order by template, then custom order

    def __str__(self):
        return f"{self.template.name} - {self.item_text[:50]}"

class Checklist(models.Model):
    template = models.ForeignKey(
        ChecklistTemplate,
        on_delete=models.PROTECT, # Keep history even if template is deleted
        related_name='runs',
        verbose_name=_("Шаблон")
    )
    performed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name='performed_checklists',
        verbose_name=_("Кем выполнен")
    )
    performed_at = models.DateTimeField(default=timezone.now, verbose_name=_("Дата/Время выполнения"), db_index=True)
    related_task = models.ForeignKey(
        Task,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='checklists',
        verbose_name=_("Связанная задача")
    )
    location = models.ForeignKey(
        Location, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='checklist_runs', verbose_name=_("Местоположение Прогона")
    )
    point = models.ForeignKey(
        ChecklistPoint, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='checklist_runs', verbose_name=_("Точка/Комната Прогона")
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
        ]

    def __str__(self):
        user_name = self.performed_by.username if self.performed_by else 'N/A'
        return f"{self.template.name} @ {self.performed_at.strftime('%d.%m.%y %H:%M')} ({user_name})"

    def get_absolute_url(self):
        # URL to view the results of this specific run
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

class ChecklistResult(models.Model):
    checklist_run = models.ForeignKey(
        Checklist,
        on_delete=models.CASCADE,
        related_name='results',
        verbose_name=_("Прогон чеклиста")
    )
    template_item = models.ForeignKey(
        ChecklistTemplateItem,
        on_delete=models.CASCADE, # Result meaningless without the item
        related_name='results',
        verbose_name=_("Пункт шаблона")
    )
    status = models.CharField(
        max_length=20,
        choices=ChecklistItemStatus.choices,
        default=ChecklistItemStatus.PENDING,
        verbose_name=_("Статус/Результат")
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
        return f"Result for '{self.template_item.item_text[:30]}' in run {self.checklist_run_id}: {self.get_status_display()}"