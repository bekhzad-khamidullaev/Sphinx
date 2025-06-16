import logging
import uuid
from django.db import models
from django.conf import settings
from django.urls import reverse
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from django.core.exceptions import ValidationError
from taggit.managers import TaggableManager
from taggit.models import TagBase, GenericUUIDTaggedItemBase

try:
    # This try-except block allows the checklist app to function
    # even if the tasks app is not installed or configured.
    from tasks.models import Task, TaskCategory
except ImportError:
    Task = None
    TaskCategory = None
<<<<<<< HEAD
    logging.warning(
        "Could not import Task or TaskCategory from tasks.models. Checklist functionality might be limited."
    )

    class _DummyModel(models.Model):
        class Meta:
            abstract = True
            managed = False

        name = models.CharField(max_length=1)

        def __str__(self):
            return str(self.pk)

    if Task is None:

        class Task(_DummyModel):
            pass

    if TaskCategory is None:

        class TaskCategory(_DummyModel):
            pass
=======
    logging.warning("Could not import Task or TaskCategory from tasks.models. Checklist functionality might be limited.")
    # Define dummy models to prevent NameError if Task/TaskCategory are used in FKs
    class Task:
         pass
    class TaskCategory:
         pass
>>>>>>> servicedesk


User = settings.AUTH_USER_MODEL
logger = logging.getLogger(__name__)


class AnswerType(models.TextChoices):
<<<<<<< HEAD
    TEXT = "text", _("Текстовое поле")
    NUMBER = "number", _("Числовое поле")
    SCALE_1_4 = "scale_1_4", _("Оценка 1–4")
    SCALE_1_5 = "scale_1_5", _("Оценка 1–5")
    YES_NO = "yes_no", _("Да / Нет")
    YES_NO_MEH = "yes_no_meh", _("Да / Нет / Не очень")
    BOOLEAN = "boolean", _("Да/Нет (Boolean)")
    DATE = "date", _("Дата")
    DATETIME = "datetime", _("Дата и время")
    TIME = "time", _("Время")
    FILE = "file", _("Файл")
    URL = "url", _("Ссылка")


class ChecklistRunStatus(models.TextChoices):
    DRAFT = "draft", _("Черновик")
    IN_PROGRESS = "in_progress", _("В процессе")
    SUBMITTED = "submitted", _("Отправлено")
    APPROVED = "approved", _("Одобрено")
    REJECTED = "rejected", _("Отклонено")


class ChecklistItemStatus(models.TextChoices):
    PENDING = "pending", _("Ожидает ответа")
    OK = "ok", _("OK")
    NOT_OK = "not_ok", _("Не OK")
    NOT_APPLICABLE = "na", _("Неприменимо")


class LocationLevel(models.TextChoices):
    VENUE = "venue", _("Заведение/Ресторан")
    ROOM = "room", _("Комната/Помещение")
    AREA = "area", _("Зона/Уголок")
    POINT = "point", _("Точка/Объект")


class Location(models.Model):
    name = models.CharField(
        max_length=150, unique=True, verbose_name=_("Название Местоположения")
    )
    description = models.TextField(blank=True, verbose_name=_("Описание"))
    parent = models.ForeignKey(
        "self",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="child_locations",
        verbose_name=_("Родительское Местоположение"),
    )
    level = models.CharField(
        max_length=20,
        choices=LocationLevel.choices,
        default=LocationLevel.VENUE,
        db_index=True,
        verbose_name=_("Тип локации"),
    )
    logo_image = models.ImageField(
        upload_to="location_logos/%Y/%m/",
        null=True,
        blank=True,
        verbose_name=_("Логотип"),
    )
=======
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
>>>>>>> servicedesk
    created_at = models.DateTimeField(auto_now_add=True, verbose_name=_("Создан"))
    updated_at = models.DateTimeField(auto_now=True, verbose_name=_("Обновлен"))

    class Meta:
        verbose_name = _("Местоположение")
        verbose_name_plural = _("Местоположения")
        ordering = ["name"]

    LEVEL_ORDER = {
        LocationLevel.VENUE: 1,
        LocationLevel.ROOM: 2,
        LocationLevel.AREA: 3,
        LocationLevel.POINT: 4,
    }

    @property
    def full_name(self):
        if self.parent:
            return f"{self.parent.full_name} / {self.name}"
        return self.name

    def __str__(self):
        return self.full_name

<<<<<<< HEAD
    def get_absolute_url(self):
        try:
            # Используем имя URL-паттерна 'location_detail' из qrfikr/urls.py
            return reverse("qrfikr:location_detail", kwargs={"pk": self.pk})
        except Exception:
            # Запасной URL, если что-то пойдет не так
            return reverse("tasks:task_list_default")  # Или другой подходящий URL

    def clean(self):
        super().clean()
        if self.parent:
            parent_order = self.LEVEL_ORDER.get(self.parent.level, 0)
            current_order = self.LEVEL_ORDER.get(self.level, 0)
            if parent_order >= current_order:
                raise ValidationError(
                    {
                        "parent": _(
                            "Уровень родительской локации должен быть выше текущего."
                        )
                    }
                )


class ChecklistPoint(models.Model):
    location = models.ForeignKey(
        Location,
        on_delete=models.CASCADE,
        related_name="points",
        verbose_name=_("Местоположение"),
    )
=======
class ChecklistPoint(models.Model):
    """
    Represents a specific point, room, or area within a Location.
    """
    location = models.ForeignKey(Location, on_delete=models.CASCADE, related_name='points', verbose_name=_("Местоположение"))
>>>>>>> servicedesk
    name = models.CharField(max_length=150, verbose_name=_("Название Точки/Комнаты"))
    description = models.TextField(blank=True, verbose_name=_("Описание"))
    created_at = models.DateTimeField(auto_now_add=True, verbose_name=_("Создан"))
    updated_at = models.DateTimeField(auto_now=True, verbose_name=_("Обновлен"))

    class Meta:
        verbose_name = _("Точка/Комната Чеклиста")
        verbose_name_plural = _("Точки/Комнаты Чеклистов")
        ordering = ["location__name", "name"]
        constraints = [
            models.UniqueConstraint(
                fields=["location", "name"], name="unique_point_per_location"
            )
        ]

    def __str__(self):
        return f"{self.location.name} / {self.name}"


class ChecklistTemplateTag(TagBase):
    class Meta:
        verbose_name = _("Тег шаблона чеклиста")
        verbose_name_plural = _("Теги шаблонов чеклиста")


class ChecklistTemplateTaggedItem(GenericUUIDTaggedItemBase):
    tag = models.ForeignKey(
        ChecklistTemplateTag,
        related_name="tagged_items",
        on_delete=models.CASCADE,
    )

    class Meta:
        verbose_name = _("Связь шаблона чеклиста и тега")
        verbose_name_plural = _("Связи шаблонов чеклиста и тегов")


class ChecklistTemplate(models.Model):
    """
    Defines the structure and properties of a checklist.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    uuid = models.UUIDField(default=uuid.uuid4, editable=False, unique=True)
    name = models.CharField(max_length=255, verbose_name=_("Название шаблона"))
    description = models.TextField(blank=True, verbose_name=_("Описание"))
<<<<<<< HEAD
    category = models.ForeignKey(
        TaskCategory,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="checklist_templates",
        verbose_name=_("Категория (из Задач)"),
    )
    target_location = models.ForeignKey(
        Location,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="checklist_templates",
        verbose_name=_("Целевое Местоположение"),
    )
    target_point = models.ForeignKey(
        ChecklistPoint,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="checklist_templates",
        verbose_name=_("Целевая Точка/Комната"),
    )
    is_active = models.BooleanField(
        default=True,
        verbose_name=_("Активен"),
        help_text=_("Активные шаблоны доступны для создания новых чеклистов."),
    )
    version = models.CharField(
        max_length=20, blank=True, default="1.0", verbose_name=_("Версия")
    )
    is_archived = models.BooleanField(
        default=False,
        verbose_name=_("Архивирован"),
        help_text=_(
            "Архивированные шаблоны скрыты из основного списка и не могут быть использованы для новых чеклистов."
        ),
    )
    frequency = models.CharField(
        max_length=50,
        blank=True,
        verbose_name=_("Периодичность"),
        help_text=_(
            "Например: ежедневно, еженедельно по понедельникам, раз в месяц 15 числа."
        ),
    )
    next_due_date = models.DateField(
        null=True,
        blank=True,
        verbose_name=_("След. дата выполнения"),
        help_text=_("Для автоматического планирования (если реализовано)."),
    )
    tags = TaggableManager(
        through=ChecklistTemplateTaggedItem,
        blank=True,
        verbose_name=_("Теги"),
        help_text=_("Разделяйте теги запятыми."),
    )
=======
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
>>>>>>> servicedesk
    created_at = models.DateTimeField(auto_now_add=True, verbose_name=_("Создан"))
    updated_at = models.DateTimeField(auto_now=True, verbose_name=_("Обновлен"))

    class Meta:
        verbose_name = _("Шаблон чеклиста")
        verbose_name_plural = _("Шаблоны чеклистов")
<<<<<<< HEAD
        ordering = [
            (
                "category__name"
                if TaskCategory
                and hasattr(TaskCategory, "_meta")
                and TaskCategory._meta.concrete_model
                else "name"
            ),
            "name",
        ]
=======
        ordering = ['category__name' if TaskCategory else 'name', 'name'] # Adjust ordering if category is dummy
>>>>>>> servicedesk

    def __str__(self):
        return self.name

    def get_absolute_url(self):
        return reverse("checklists:template_detail", kwargs={"pk": self.pk})

    def clean(self):
<<<<<<< HEAD
        super().clean()
        if (
            self.target_point
            and self.target_location
            and self.target_point.location != self.target_location
        ):
            raise ValidationError(
                {
                    "target_point": _(
                        "Выбранная точка (%(point_name)s) не принадлежит указанному местоположению (%(location_name)s)."
                    )
                    % {
                        "point_name": self.target_point.name,
                        "location_name": self.target_location.name,
                    }
                }
            )
=======
        # Ensure target_point belongs to target_location if both are set
        if self.target_point and self.target_location and self.target_point.location != self.target_location:
            raise ValidationError({'target_point': _('Выбранная точка не принадлежит указанному местоположению.')})
        # Clear target_point if target_location is cleared
>>>>>>> servicedesk
        if not self.target_location and self.target_point:
            self.target_point = None


class ChecklistSection(models.Model):
<<<<<<< HEAD
    template = models.ForeignKey(
        ChecklistTemplate,
        on_delete=models.CASCADE,
        related_name="sections",
        verbose_name=_("Шаблон"),
    )
    title = models.CharField(max_length=255, verbose_name=_("Название секции"))
    order = models.PositiveIntegerField(
        default=0, verbose_name=_("Порядок отображения")
    )
=======
    """
    Represents a section within a Checklist Template to group items.
    """
    template = models.ForeignKey(ChecklistTemplate, on_delete=models.CASCADE, related_name='sections')
    title = models.CharField(max_length=255, verbose_name=_('Название секции'))
    order = models.PositiveIntegerField(default=0)
>>>>>>> servicedesk

    class Meta:
        verbose_name = _("Секция шаблона")
        verbose_name_plural = _("Секции шаблона")
<<<<<<< HEAD
        ordering = ["template", "order", "title"]
        unique_together = ("template", "order")
=======
        ordering = ['order', 'title']
        unique_together = ('template', 'order') # Ensure order is unique within a template section list
>>>>>>> servicedesk

    def __str__(self):
        return self.title


class ChecklistTemplateItem(models.Model):
<<<<<<< HEAD
    template = models.ForeignKey(
        ChecklistTemplate,
        on_delete=models.CASCADE,
        related_name="items",
        verbose_name=_("Шаблон"),
    )
    section = models.ForeignKey(
        ChecklistSection,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="items",
        verbose_name=_("Секция"),
    )
    item_text = models.TextField(verbose_name=_("Текст пункта/вопроса"))
    order = models.PositiveIntegerField(default=0, verbose_name=_("Порядок в секции"))
    target_point = models.ForeignKey(
        ChecklistPoint,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="template_items",
        verbose_name=_("Конкретная Точка (если отличается от общей)"),
    )
    answer_type = models.CharField(
        max_length=20,
        choices=AnswerType.choices,
        default=AnswerType.TEXT,
        verbose_name=_("Тип ответа"),
    )
    help_text = models.CharField(
        max_length=255,
        blank=True,
        verbose_name=_("Подсказка"),
        help_text=_("Дополнительная информация или инструкции для пункта."),
    )
    default_value = models.CharField(
        max_length=255,
        blank=True,
        verbose_name=_("Значение по умолчанию"),
        help_text=_(
            "Будет подставлено при создании чеклиста. Формат зависит от типа ответа."
        ),
    )
    parent_item = models.ForeignKey(
        "self",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="sub_items",
        verbose_name=_("Родительский пункт"),
        help_text=_("Для создания вложенных (зависимых) пунктов."),
    )
=======
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
>>>>>>> servicedesk

    class Meta:
        verbose_name = _("Пункт шаблона чеклиста")
        verbose_name_plural = _("Пункты шаблонов чеклистов")
<<<<<<< HEAD
        ordering = ["template", "section__order", "section__title", "order", "id"]
        unique_together = ("template", "section", "order")

    def __str__(self):
        section_prefix = (
            f"{self.section.title} ({self.section.order}) / "
            if self.section
            else _("Без секции / ")
        )
        return f"{section_prefix}{self.order}. {self.item_text[:50]}{'...' if len(self.item_text) > 50 else ''}"

    def clean(self):
        super().clean()
        if (
            self.target_point
            and self.template.target_location
            and self.target_point.location != self.template.target_location
        ):
            raise ValidationError(
                {
                    "target_point": _(
                        "Конкретная точка пункта (%(point_name)s) не соответствует общему местоположению шаблона (%(template_loc_name)s)."
                    )
                    % {
                        "point_name": self.target_point.name,
                        "template_loc_name": self.template.target_location.name,
                    }
                }
            )
        if self.section and self.section.template != self.template:
            raise ValidationError(
                {
                    "section": _(
                        "Выбранная секция (%(section_title)s) не принадлежит текущему шаблону (%(template_name)s)."
                    )
                    % {
                        "section_title": self.section.title,
                        "template_name": self.template.name,
                    }
                }
            )
        if self.parent_item:
            if self.parent_item == self:
                raise ValidationError(
                    {"parent_item": _("Пункт не может быть родительским сам для себя.")}
                )
            if self.parent_item.template != self.template:
                raise ValidationError(
                    {
                        "parent_item": _(
                            "Родительский пункт должен принадлежать тому же шаблону."
                        )
                    }
                )
            if self.parent_item.parent_item == self:
                raise ValidationError(
                    {
                        "parent_item": _(
                            "Обнаружена циклическая зависимость с родительским пунктом (A->B, B->A)."
                        )
                    }
                )

=======
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
>>>>>>> servicedesk

class Checklist(models.Model):
    """
    Represents a single instance of a ChecklistTemplate being performed.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
<<<<<<< HEAD
    template = models.ForeignKey(
        ChecklistTemplate,
        on_delete=models.PROTECT,
        related_name="runs",
        verbose_name=_("Шаблон"),
    )
    performed_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="performed_checklists",
        verbose_name=_("Кем выполнен"),
        db_index=True,
    )
    performed_at = models.DateTimeField(
        default=timezone.now, verbose_name=_("Дата/Время начала"), db_index=True
    )
    related_task = models.ForeignKey(
        Task,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="checklists",
        verbose_name=_("Связанная задача"),
    )
    location = models.ForeignKey(
        Location,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="checklist_runs",
        verbose_name=_("Местоположение выполнения"),
    )
    point = models.ForeignKey(
        ChecklistPoint,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="checklist_runs",
        verbose_name=_("Точка выполнения"),
    )
    notes = models.TextField(blank=True, verbose_name=_("Общие примечания к чеклисту"))
    is_complete = models.BooleanField(
        default=False,
        verbose_name=_("Завершен"),
        db_index=True,
        help_text=_("Отмечается, когда все пункты заполнены и чеклист отправлен."),
    )
    completion_time = models.DateTimeField(
        null=True, blank=True, verbose_name=_("Время завершения")
    )
    status = models.CharField(
        max_length=20,
        choices=ChecklistRunStatus.choices,
        default=ChecklistRunStatus.DRAFT,
        verbose_name=_("Статус"),
        db_index=True,
    )
    approved_by = models.ForeignKey(
        User,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="approved_checklists",
        verbose_name=_("Одобрено/Отклонено кем"),
    )
    approved_at = models.DateTimeField(
        null=True, blank=True, verbose_name=_("Время одобрения/отклонения")
    )
    score = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name=_("Оценка (%)"),
        help_text=_("Процент выполнения или другая метрика."),
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name=_("Создан"))
    updated_at = models.DateTimeField(auto_now=True, verbose_name=_("Обновлен"))
    external_reference = models.CharField(
        max_length=255,
        blank=True,
        null=True,
        verbose_name=_("Внешняя ссылка/ID"),
        help_text=_("ID из внешней системы, если применимо."),
    )

    class Meta:
        verbose_name = _("Выполненный чеклист (Прогон)")
        verbose_name_plural = _("Выполненные чеклисты (Прогоны)")
        ordering = ["-performed_at", "-created_at"]
        permissions = [
            (
                "confirm_checklist",
                _("Может подтверждать чеклист"),
            )
        ]
=======
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
>>>>>>> servicedesk

    def __str__(self):
        loc_info = f" @ {self.location.name}" if self.location else ""
        point_info = f" / {self.point.name}" if self.point else ""
<<<<<<< HEAD
        performer = (
            f" ({self.performed_by.username})"
            if self.performed_by
            else _(" (не назначен)")
        )
        return f"Чеклист: {self.template.name}{loc_info}{point_info} - {self.performed_at.strftime('%d.%m.%Y %H:%M')}{performer} [{self.get_status_display()}]"

    def get_absolute_url(self):
        return reverse("checklists:checklist_detail", kwargs={"pk": self.pk})
=======
        performer = f" ({self.performed_by.username})" if self.performed_by else ""
        return f"{self.template.name}{loc_info}{point_info} - {self.performed_at.strftime('%d.%m.%Y %H:%M')}{performer}"

    def get_absolute_url(self):
        # Use the history_list detail view name
        return reverse('checklists:checklist_detail', kwargs={'pk': self.pk})
>>>>>>> servicedesk

    def has_issues(self):
        """Checks if any result has a 'Not OK' status."""
        return self.results.filter(status=ChecklistItemStatus.NOT_OK).exists()

    def mark_complete(self):
        """Marks the checklist run as complete and sets status to SUBMITTED."""
        if not self.is_complete and self.status in [ChecklistRunStatus.DRAFT, ChecklistRunStatus.IN_PROGRESS]:
            self.is_complete = True
            self.completion_time = timezone.now()
            self.status = ChecklistRunStatus.SUBMITTED
<<<<<<< HEAD
            self.save(update_fields=["is_complete", "completion_time", "status"])
            logger.info(
                f"Checklist run {self.id} marked complete and status set to SUBMITTED."
            )
        else:
            logger.warning(
                f"Attempted to mark_complete on already finalized checklist {self.id} (status: {self.status})."
            )
=======
            self.save(update_fields=['is_complete', 'completion_time', 'status'])
            logger.info(f"Checklist run {self.id} marked complete and status set to SUBMITTED.")
>>>>>>> servicedesk

    def clean(self):
        # Ensure point belongs to location if both are set
        if self.point and self.location and self.point.location != self.location:
<<<<<<< HEAD
            raise ValidationError(
                {
                    "point": _(
                        "Точка выполнения (%(point_name)s) не принадлежит указанному местоположению выполнения (%(location_name)s)."
                    )
                    % {
                        "point_name": self.point.name,
                        "location_name": self.location.name,
                    }
                }
            )
=======
            raise ValidationError({'point': _('Точка не принадлежит выбранному местоположению.')})
        # Clear point if location is cleared
>>>>>>> servicedesk
        if not self.location and self.point:
            self.point = None


class ChecklistResult(models.Model):
    """
    Stores the result for a specific ChecklistTemplateItem within a Checklist run.
    Uses generic fields to store different data types based on the item's answer_type.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
<<<<<<< HEAD
    checklist_run = models.ForeignKey(
        Checklist,
        on_delete=models.CASCADE,
        related_name="results",
        verbose_name=_("Прогон чеклиста"),
    )
    template_item = models.ForeignKey(
        ChecklistTemplateItem,
        on_delete=models.CASCADE,
        related_name="results",
        verbose_name=_("Пункт шаблона"),
    )
=======
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
>>>>>>> servicedesk

    value = models.TextField(
        blank=True, null=True, verbose_name=_("Ответ (текст/выбор)")
    )
    numeric_value = models.FloatField(
        null=True, blank=True, verbose_name=_("Числовое значение ответа")
    )
    boolean_value = models.BooleanField(
        null=True, blank=True, verbose_name=_("Булево значение ответа")
    )
    date_value = models.DateField(
        null=True, blank=True, verbose_name=_("Значение типа Дата")
    )
    datetime_value = models.DateTimeField(
        null=True, blank=True, verbose_name=_("Значение типа Дата и время")
    )
    time_value = models.TimeField(
        null=True, blank=True, verbose_name=_("Значение типа Время")
    )
    file_attachment = models.FileField(
        upload_to="checklist_attachments/%Y/%m/%d/",
        blank=True,
        null=True,
        verbose_name=_("Прикрепленный файл"),
    )
    media_url = models.URLField(
        max_length=500, blank=True, null=True, verbose_name=_("Ссылка на медиа (URL)")
    )

<<<<<<< HEAD
    comments = models.TextField(blank=True, verbose_name=_("Комментарий к пункту"))
    status = models.CharField(
        max_length=20,
        choices=ChecklistItemStatus.choices,
        default=ChecklistItemStatus.PENDING,
        verbose_name=_("Статус пункта"),
        db_index=True,
    )
    is_corrected = models.BooleanField(
        default=False,
        verbose_name=_("Проблема исправлена"),
        help_text=_(
            "Отметьте, если проблема, указанная в этом пункте, была устранена."
        ),
    )

    recorded_at = models.DateTimeField(
        auto_now=True, verbose_name=_("Время последней записи/обновления")
    )
    created_by = models.ForeignKey(
        User,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="created_checklist_results",
        verbose_name=_("Создано кем"),
    )
    updated_by = models.ForeignKey(
        User,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="updated_checklist_results",
        verbose_name=_("Обновлено кем"),
    )

    class Meta:
        verbose_name = _("Результат пункта чеклиста")
        verbose_name_plural = _("Результаты пунктов чеклиста")
        ordering = [
            "checklist_run",
            "template_item__section__order",
            "template_item__order",
            "template_item_id",
        ]
        unique_together = ("checklist_run", "template_item")

    def __str__(self):
        item_text_short = self.template_item.item_text[:30] + (
            "..." if len(self.template_item.item_text) > 30 else ""
        )
        return f"[{self.get_status_display()}] {self.checklist_run.id.hex[:8]} / {item_text_short} -> {self.display_value or '-'}"

    @property
    def display_value(self):
        if hasattr(self, "_display_value_cache"):
            return self._display_value_cache

        val = "-"
        if not self.template_item:  # Добавлена проверка
            self._display_value_cache = val
            return val

        item_type = self.template_item.answer_type
        if item_type == AnswerType.TEXT:
            val = self.value
        elif item_type in [
            AnswerType.SCALE_1_4,
            AnswerType.SCALE_1_5,
            AnswerType.NUMBER,
        ]:
            val = self.numeric_value if self.numeric_value is not None else self.value
        elif item_type in [AnswerType.YES_NO, AnswerType.YES_NO_MEH]:
            if self.value == "yes":
                val = _("Да")
            elif self.value == "no":
                val = _("Нет")
            elif self.value == "yes_no_meh":
                val = _("Не очень")
            else:
                val = self.value
        elif item_type == AnswerType.BOOLEAN:
            if self.boolean_value is True:
                val = _("Да")
            elif self.boolean_value is False:
                val = _("Нет")
        elif item_type == AnswerType.DATE:
            val = self.date_value
        elif item_type == AnswerType.DATETIME:
            val = self.datetime_value
        elif item_type == AnswerType.TIME:
            val = self.time_value
        elif item_type == AnswerType.FILE:
            val = (
                self.file_attachment.url
                if self.file_attachment
                else (_("Нет файла") if self.pk else "-")
            )
        elif item_type == AnswerType.URL:
            val = self.media_url

        self._display_value_cache = val if val is not None else "-"
        return self._display_value_cache

    @property
    def primary_value_field_name(self):
        if not self.template_item:
            return "value"  # Защита, если template_item отсутствует
        item_type = self.template_item.answer_type
        if item_type == AnswerType.TEXT:
            return "value"
        if item_type in [AnswerType.SCALE_1_4, AnswerType.SCALE_1_5, AnswerType.NUMBER]:
            return "numeric_value"
        if item_type in [AnswerType.YES_NO, AnswerType.YES_NO_MEH]:
            return "value"
        if item_type == AnswerType.BOOLEAN:
            return "boolean_value"
        if item_type == AnswerType.DATE:
            return "date_value"
        if item_type == AnswerType.DATETIME:
            return "datetime_value"
        if item_type == AnswerType.TIME:
            return "time_value"
        if item_type == AnswerType.FILE:
            return "file_attachment"
        if item_type == AnswerType.URL:
            return "media_url"
        return "value"

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
=======
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
>>>>>>> servicedesk
