# checklists/models.py
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
    from tasks.models import Task, TaskCategory
except ImportError:
    Task = None
    TaskCategory = None
    logging.warning("Could not import Task or TaskCategory from tasks.models. Checklist functionality might be limited.")

    class _DummyModel(models.Model):
        class Meta:
            abstract = True
            managed = False

        name = models.CharField(max_length=1)
        def __str__(self): return str(self.pk)

    if Task is None:
        class Task(_DummyModel): pass
    if TaskCategory is None:
        class TaskCategory(_DummyModel): pass


User = settings.AUTH_USER_MODEL
logger = logging.getLogger(__name__)

class AnswerType(models.TextChoices):
    TEXT = 'text', _('Текстовое поле')
    NUMBER = 'number', _('Числовое поле')
    SCALE_1_4 = 'scale_1_4', _('Оценка 1–4')
    SCALE_1_5 = 'scale_1_5', _('Оценка 1–5')
    YES_NO = 'yes_no', _('Да / Нет')
    YES_NO_MEH = 'yes_no_meh', _('Да / Нет / Не очень')
    BOOLEAN = 'boolean', _('Да/Нет (Boolean)')
    DATE = 'date', _('Дата')
    DATETIME = 'datetime', _('Дата и время')
    TIME = 'time', _('Время')
    FILE = 'file', _('Файл')
    URL = 'url', _('Ссылка')


class ChecklistRunStatus(models.TextChoices):
    DRAFT = 'draft', _('Черновик')
    IN_PROGRESS = 'in_progress', _('В процессе')
    SUBMITTED = 'submitted', _('Отправлено')
    APPROVED = 'approved', _('Одобрено')
    REJECTED = 'rejected', _('Отклонено')

class ChecklistItemStatus(models.TextChoices):
    PENDING = 'pending', _('Ожидает ответа')
    OK = 'ok', _('OK')
    NOT_OK = 'not_ok', _('Не OK')
    NOT_APPLICABLE = 'na', _('Неприменимо')


class Location(models.Model):
    name = models.CharField(max_length=150, unique=True, verbose_name=_("Название Местоположения"))
    description = models.TextField(blank=True, verbose_name=_("Описание"))
    parent = models.ForeignKey(
        'self',
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='child_locations',
        verbose_name=_("Родительское Местоположение")
    )
    logo_image = models.ImageField(upload_to='location_logos/%Y/%m/', null=True, blank=True, verbose_name=_("Логотип"))
    created_at = models.DateTimeField(auto_now_add=True, verbose_name=_("Создан"))
    updated_at = models.DateTimeField(auto_now=True, verbose_name=_("Обновлен"))

    class Meta:
        verbose_name = _("Местоположение")
        verbose_name_plural = _("Местоположения")
        ordering = ['name']

    def __str__(self):
        return self.name

    def get_absolute_url(self):
        try:
            # Используем имя URL-паттерна 'location_detail' из qrfikr/urls.py
            return reverse('qrfikr:location_detail', kwargs={'pk': self.pk})
        except Exception:
            # Запасной URL, если что-то пойдет не так
            return reverse('tasks:task_list_default') # Или другой подходящий URL

class ChecklistPoint(models.Model):
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
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    uuid = models.UUIDField(default=uuid.uuid4, editable=False, unique=True)
    name = models.CharField(max_length=255, verbose_name=_("Название шаблона"))
    description = models.TextField(blank=True, verbose_name=_("Описание"))
    category = models.ForeignKey(
        TaskCategory,
        on_delete=models.SET_NULL, null=True, blank=True,
        related_name='checklist_templates', verbose_name=_("Категория (из Задач)")
    )
    target_location = models.ForeignKey(Location, on_delete=models.SET_NULL, null=True, blank=True, related_name='checklist_templates', verbose_name=_("Целевое Местоположение"))
    target_point = models.ForeignKey(ChecklistPoint, on_delete=models.SET_NULL, null=True, blank=True, related_name='checklist_templates', verbose_name=_("Целевая Точка/Комната"))
    is_active = models.BooleanField(default=True, verbose_name=_("Активен"), help_text=_("Активные шаблоны доступны для создания новых чеклистов."))
    version = models.CharField(max_length=20, blank=True, default="1.0", verbose_name=_("Версия"))
    is_archived = models.BooleanField(default=False, verbose_name=_("Архивирован"), help_text=_("Архивированные шаблоны скрыты из основного списка и не могут быть использованы для новых чеклистов."))
    frequency = models.CharField(max_length=50, blank=True, verbose_name=_("Периодичность"), help_text=_("Например: ежедневно, еженедельно по понедельникам, раз в месяц 15 числа."))
    next_due_date = models.DateField(null=True, blank=True, verbose_name=_("След. дата выполнения"), help_text=_("Для автоматического планирования (если реализовано)."))
    tags = TaggableManager(blank=True, verbose_name=_("Теги"), help_text=_("Разделяйте теги запятыми."))
    created_at = models.DateTimeField(auto_now_add=True, verbose_name=_("Создан"))
    updated_at = models.DateTimeField(auto_now=True, verbose_name=_("Обновлен"))

    class Meta:
        verbose_name = _("Шаблон чеклиста")
        verbose_name_plural = _("Шаблоны чеклистов")
        ordering = ['category__name' if TaskCategory and hasattr(TaskCategory, '_meta') and TaskCategory._meta.concrete_model else 'name', 'name']        

    def __str__(self):
        return self.name

    def get_absolute_url(self):
        return reverse('checklists:template_detail', kwargs={'pk': self.pk})

    def clean(self):
        super().clean()
        if self.target_point and self.target_location and self.target_point.location != self.target_location:
            raise ValidationError({'target_point': _('Выбранная точка (%(point_name)s) не принадлежит указанному местоположению (%(location_name)s).') % {'point_name': self.target_point.name, 'location_name': self.target_location.name}})    
        if not self.target_location and self.target_point:
            self.target_point = None


class ChecklistSection(models.Model):
    template = models.ForeignKey(ChecklistTemplate, on_delete=models.CASCADE, related_name='sections', verbose_name=_("Шаблон"))
    title = models.CharField(max_length=255, verbose_name=_('Название секции'))
    order = models.PositiveIntegerField(default=0, verbose_name=_("Порядок отображения"))

    class Meta:
        verbose_name = _("Секция шаблона")
        verbose_name_plural = _("Секции шаблона")
        ordering = ['template', 'order', 'title']
        unique_together = ('template', 'order')

    def __str__(self):
        return f"{self.order}. {self.title} (Шаблон: {self.template.name})"


class ChecklistTemplateItem(models.Model):
    template = models.ForeignKey(ChecklistTemplate, on_delete=models.CASCADE, related_name='items', verbose_name=_("Шаблон"))
    section = models.ForeignKey(ChecklistSection, on_delete=models.SET_NULL, null=True, blank=True, related_name='items', verbose_name=_("Секция"))
    item_text = models.TextField(verbose_name=_("Текст пункта/вопроса"))
    order = models.PositiveIntegerField(default=0, verbose_name=_("Порядок в секции"))
    target_point = models.ForeignKey(ChecklistPoint, on_delete=models.SET_NULL, null=True, blank=True, related_name='template_items', verbose_name=_("Конкретная Точка (если отличается от общей)"))
    answer_type = models.CharField(max_length=20, choices=AnswerType.choices, default=AnswerType.TEXT, verbose_name=_("Тип ответа"))
    help_text = models.CharField(max_length=255, blank=True, verbose_name=_("Подсказка"), help_text=_("Дополнительная информация или инструкции для пункта."))
    default_value = models.CharField(max_length=255, blank=True, verbose_name=_("Значение по умолчанию"), help_text=_("Будет подставлено при создании чеклиста. Формат зависит от типа ответа."))
    parent_item = models.ForeignKey('self', null=True, blank=True, on_delete=models.SET_NULL, related_name='sub_items', verbose_name=_("Родительский пункт"), help_text=_("Для создания вложенных (зависимых) пунктов."))

    class Meta:
        verbose_name = _("Пункт шаблона чеклиста")
        verbose_name_plural = _("Пункты шаблонов чеклистов")
        ordering = ['template', 'section__order', 'section__title', 'order', 'id']
        unique_together = ('template', 'section', 'order')

    def __str__(self):
        section_prefix = f"{self.section.title} ({self.section.order}) / " if self.section else _("Без секции / ")
        return f"{section_prefix}{self.order}. {self.item_text[:50]}{'...' if len(self.item_text) > 50 else ''}"

    def clean(self):
        super().clean()
        if self.target_point and self.template.target_location and self.target_point.location != self.template.target_location:
            raise ValidationError({'target_point': _('Конкретная точка пункта (%(point_name)s) не соответствует общему местоположению шаблона (%(template_loc_name)s).') % {'point_name': self.target_point.name, 'template_loc_name': self.template.target_location.name}})
        if self.section and self.section.template != self.template:
             raise ValidationError({'section': _('Выбранная секция (%(section_title)s) не принадлежит текущему шаблону (%(template_name)s).') % {'section_title': self.section.title, 'template_name': self.template.name}})
        if self.parent_item:
            if self.parent_item == self:
                raise ValidationError({'parent_item': _('Пункт не может быть родительским сам для себя.')})
            if self.parent_item.template != self.template:
                raise ValidationError({'parent_item': _('Родительский пункт должен принадлежать тому же шаблону.')})
            if self.parent_item.parent_item == self:
                raise ValidationError({'parent_item': _('Обнаружена циклическая зависимость с родительским пунктом (A->B, B->A).')})

class Checklist(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    template = models.ForeignKey(ChecklistTemplate, on_delete=models.PROTECT, related_name='runs', verbose_name=_("Шаблон"))
    performed_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='performed_checklists', verbose_name=_("Кем выполнен"), db_index=True)
    performed_at = models.DateTimeField(default=timezone.now, verbose_name=_("Дата/Время начала"), db_index=True)
    related_task = models.ForeignKey(
        Task,
        on_delete=models.SET_NULL, null=True, blank=True,
        related_name='checklists', verbose_name=_("Связанная задача")
    )
    location = models.ForeignKey(Location, on_delete=models.SET_NULL, null=True, blank=True, related_name='checklist_runs', verbose_name=_("Местоположение выполнения"))
    point = models.ForeignKey(ChecklistPoint, on_delete=models.SET_NULL, null=True, blank=True, related_name='checklist_runs', verbose_name=_("Точка выполнения"))
    notes = models.TextField(blank=True, verbose_name=_("Общие примечания к чеклисту"))
    is_complete = models.BooleanField(default=False, verbose_name=_("Завершен"), db_index=True, help_text=_("Отмечается, когда все пункты заполнены и чеклист отправлен."))
    completion_time = models.DateTimeField(null=True, blank=True, verbose_name=_("Время завершения"))
    status = models.CharField(max_length=20, choices=ChecklistRunStatus.choices, default=ChecklistRunStatus.DRAFT, verbose_name=_("Статус"), db_index=True)
    approved_by = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL, related_name='approved_checklists', verbose_name=_("Одобрено/Отклонено кем"))
    approved_at = models.DateTimeField(null=True, blank=True, verbose_name=_("Время одобрения/отклонения"))
    score = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True, verbose_name=_("Оценка (%)"), help_text=_("Процент выполнения или другая метрика."))       
    created_at = models.DateTimeField(auto_now_add=True, verbose_name=_("Создан"))
    updated_at = models.DateTimeField(auto_now=True, verbose_name=_("Обновлен"))
    external_reference = models.CharField(max_length=255, blank=True, null=True, verbose_name=_("Внешняя ссылка/ID"), help_text=_("ID из внешней системы, если применимо."))

    class Meta:
        verbose_name = _("Выполненный чеклист (Прогон)")
        verbose_name_plural = _("Выполненные чеклисты (Прогоны)")
        ordering = ['-performed_at', '-created_at']

    def __str__(self):
        loc_info = f" @ {self.location.name}" if self.location else ""
        point_info = f" / {self.point.name}" if self.point else ""
        performer = f" ({self.performed_by.username})" if self.performed_by else _(" (не назначен)")
        return f"Чеклист: {self.template.name}{loc_info}{point_info} - {self.performed_at.strftime('%d.%m.%Y %H:%M')}{performer} [{self.get_status_display()}]"

    def get_absolute_url(self):
        return reverse('checklists:checklist_detail', kwargs={'pk': self.pk})

    def has_issues(self):
        return self.results.filter(status=ChecklistItemStatus.NOT_OK).exists()

    def mark_complete(self):
        if self.status in [ChecklistRunStatus.DRAFT, ChecklistRunStatus.IN_PROGRESS]:
            self.is_complete = True
            if not self.completion_time:
                self.completion_time = timezone.now()
            self.status = ChecklistRunStatus.SUBMITTED
            self.save(update_fields=['is_complete', 'completion_time', 'status'])
            logger.info(f"Checklist run {self.id} marked complete and status set to SUBMITTED.")
        else:
            logger.warning(f"Attempted to mark_complete on already finalized checklist {self.id} (status: {self.status}).")


    def clean(self):
        super().clean()
        if self.point and self.location and self.point.location != self.location:
            raise ValidationError({'point': _('Точка выполнения (%(point_name)s) не принадлежит указанному местоположению выполнения (%(location_name)s).') % {'point_name': self.point.name, 'location_name': self.location.name}})
        if not self.location and self.point:
            self.point = None


class ChecklistResult(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    checklist_run = models.ForeignKey(Checklist, on_delete=models.CASCADE, related_name='results', verbose_name=_("Прогон чеклиста"))
    template_item = models.ForeignKey(ChecklistTemplateItem, on_delete=models.CASCADE, related_name='results', verbose_name=_("Пункт шаблона"))

    value = models.TextField(blank=True, null=True, verbose_name=_("Ответ (текст/выбор)"))
    numeric_value = models.FloatField(null=True, blank=True, verbose_name=_("Числовое значение ответа"))
    boolean_value = models.BooleanField(null=True, blank=True, verbose_name=_("Булево значение ответа"))  
    date_value = models.DateField(null=True, blank=True, verbose_name=_("Значение типа Дата"))
    datetime_value = models.DateTimeField(null=True, blank=True, verbose_name=_("Значение типа Дата и время"))  
    time_value = models.TimeField(null=True, blank=True, verbose_name=_("Значение типа Время"))
    file_attachment = models.FileField(upload_to='checklist_attachments/%Y/%m/%d/', blank=True, null=True, verbose_name=_("Прикрепленный файл"))    
    media_url = models.URLField(max_length=500, blank=True, null=True, verbose_name=_("Ссылка на медиа (URL)"))


    comments = models.TextField(blank=True, verbose_name=_("Комментарий к пункту"))
    status = models.CharField(max_length=20, choices=ChecklistItemStatus.choices, default=ChecklistItemStatus.PENDING, verbose_name=_("Статус пункта"), db_index=True)
    is_corrected = models.BooleanField(default=False, verbose_name=_("Проблема исправлена"), help_text=_("Отметьте, если проблема, указанная в этом пункте, была устранена."))

    recorded_at = models.DateTimeField(auto_now=True, verbose_name=_("Время последней записи/обновления"))
    created_by = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL, related_name='created_checklist_results', verbose_name=_("Создано кем"))
    updated_by = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL, related_name='updated_checklist_results', verbose_name=_("Обновлено кем"))

    class Meta:
        verbose_name = _("Результат пункта чеклиста")
        verbose_name_plural = _("Результаты пунктов чеклиста")
        ordering = ['checklist_run', 'template_item__section__order', 'template_item__order', 'template_item_id']
        unique_together = ('checklist_run', 'template_item')

    def __str__(self):
        item_text_short = self.template_item.item_text[:30] + ('...' if len(self.template_item.item_text) > 30 else '')      
        return f"[{self.get_status_display()}] {self.checklist_run.id.hex[:8]} / {item_text_short} -> {self.display_value or '-'}"

    @property
    def display_value(self):
        if hasattr(self, '_display_value_cache'):
            return self._display_value_cache
        
        val = "-"
        if not self.template_item: # Добавлена проверка
            self._display_value_cache = val
            return val

        item_type = self.template_item.answer_type
        if item_type == AnswerType.TEXT: val = self.value
        elif item_type in [AnswerType.SCALE_1_4, AnswerType.SCALE_1_5, AnswerType.NUMBER]:
             val = self.numeric_value if self.numeric_value is not None else self.value
        elif item_type in [AnswerType.YES_NO, AnswerType.YES_NO_MEH]:
             if self.value == 'yes': val = _('Да')
             elif self.value == 'no': val = _('Нет')
             elif self.value == 'yes_no_meh': val = _('Не очень')
             else: val = self.value
        elif item_type == AnswerType.BOOLEAN:
             if self.boolean_value is True: val = _('Да')
             elif self.boolean_value is False: val = _('Нет')
        elif item_type == AnswerType.DATE: val = self.date_value
        elif item_type == AnswerType.DATETIME: val = self.datetime_value
        elif item_type == AnswerType.TIME: val = self.time_value
        elif item_type == AnswerType.FILE:
             val = self.file_attachment.url if self.file_attachment else (_("Нет файла") if self.pk else "-")
        elif item_type == AnswerType.URL:
             val = self.media_url
        
        self._display_value_cache = val if val is not None else "-"
        return self._display_value_cache


    @property
    def primary_value_field_name(self):
         if not self.template_item: return 'value' # Защита, если template_item отсутствует
         item_type = self.template_item.answer_type
         if item_type == AnswerType.TEXT: return 'value'
         if item_type in [AnswerType.SCALE_1_4, AnswerType.SCALE_1_5, AnswerType.NUMBER]: return 'numeric_value'       
         if item_type in [AnswerType.YES_NO, AnswerType.YES_NO_MEH]: return 'value'
         if item_type == AnswerType.BOOLEAN: return 'boolean_value'
         if item_type == AnswerType.DATE: return 'date_value'
         if item_type == AnswerType.DATETIME: return 'datetime_value'
         if item_type == AnswerType.TIME: return 'time_value'
         if item_type == AnswerType.FILE: return 'file_attachment'
         if item_type == AnswerType.URL: return 'media_url'
         return 'value'

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        try:
            from .utils import calculate_checklist_score
            if self.checklist_run_id:
                score = calculate_checklist_score(self.checklist_run)
                if self.checklist_run.score != score:
                    self.checklist_run.score = score
                    self.checklist_run.save(update_fields=["score"])
        except Exception as exc:
            logger.exception(
                "Failed to update checklist score for result %s: %s",
                self.pk,
                exc,
            )
