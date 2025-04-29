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
    # Add more specific statuses if needed, e.g., YES/NO, PASS/FAIL

class ChecklistTemplate(models.Model):
    """ Defines the structure and standard items for a reusable checklist. """
    name = models.CharField(max_length=255, verbose_name=_("Название шаблона"))
    description = models.TextField(blank=True, verbose_name=_("Описание"))
    category = models.ForeignKey(
        TaskCategory,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='checklist_templates',
        verbose_name=_("Категория (из Задач)")
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

class ChecklistTemplateItem(models.Model):
    """ An individual item/question within a ChecklistTemplate. """
    template = models.ForeignKey(
        ChecklistTemplate,
        on_delete=models.CASCADE,
        related_name='items',
        verbose_name=_("Шаблон")
    )
    item_text = models.CharField(max_length=500, verbose_name=_("Текст пункта/вопроса"))
    order = models.PositiveIntegerField(default=0, verbose_name=_("Порядок"), help_text=_("Порядок отображения пункта в чеклисте."))
    # Optional: Define expected answer type if needed later
    # expected_status_type = models.CharField(max_length=20, choices=..., default=...)

    class Meta:
        verbose_name = _("Пункт шаблона чеклиста")
        verbose_name_plural = _("Пункты шаблонов чеклистов")
        ordering = ['template', 'order', 'id'] # Order by template, then custom order, then ID

    def __str__(self):
        return f"{self.template.name} - {self.item_text[:50]}"

class Checklist(models.Model):
    """ An instance of a checklist being performed. """
    template = models.ForeignKey(
        ChecklistTemplate,
        on_delete=models.PROTECT, # Don't delete history if template is deleted
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
    # Optional: Add location, general comments for the whole checklist run
    location = models.CharField(max_length=200, blank=True, verbose_name=_("Местоположение/Зона"))
    notes = models.TextField(blank=True, verbose_name=_("Общие примечания"))
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
        return f"{self.template.name} - {user_name} @ {self.performed_at.strftime('%Y-%m-%d %H:%M')}"

    def get_absolute_url(self):
        return reverse('checklists:checklist_detail', kwargs={'pk': self.pk})

    @property
    def has_issues(self):
        """ Check if any result in this checklist run is 'Not OK'. """
        return self.results.filter(status=ChecklistItemStatus.NOT_OK).exists()

    def mark_complete(self):
        """ Mark the checklist as complete and set completion time. """
        if not self.is_complete:
            self.is_complete = True
            self.completion_time = timezone.now()
            self.save(update_fields=['is_complete', 'completion_time'])
            logger.info(f"Checklist {self.id} marked as complete.")


class ChecklistResult(models.Model):
    """ The result for a specific item within a specific checklist run. """
    checklist_run = models.ForeignKey(
        Checklist,
        on_delete=models.CASCADE,
        related_name='results',
        verbose_name=_("Прогон чеклиста")
    )
    template_item = models.ForeignKey(
        ChecklistTemplateItem,
        on_delete=models.CASCADE, # If template item removed, result doesn't make sense
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
    recorded_at = models.DateTimeField(auto_now=True, verbose_name=_("Время записи результата")) # Time this specific item was saved

    class Meta:
        verbose_name = _("Результат пункта чеклиста")
        verbose_name_plural = _("Результаты пунктов чеклистов")
        ordering = ['checklist_run', 'template_item__order']
        # Ensure only one result per item per run
        constraints = [
            models.UniqueConstraint(fields=['checklist_run', 'template_item'], name='unique_result_per_item_run')
        ]
        indexes = [
            models.Index(fields=['checklist_run', 'template_item']),
            models.Index(fields=['status']),
        ]

    def __str__(self):
        return f"Result for '{self.template_item.item_text[:30]}' in run {self.checklist_run_id}: {self.get_status_display()}"