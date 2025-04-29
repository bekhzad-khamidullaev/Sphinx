# checklists/forms.py
import logging
from django import forms
from django.core.exceptions import ValidationError
from django.forms import inlineformset_factory, BaseInlineFormSet
from django.utils.translation import gettext_lazy as _

from .models import (
    ChecklistTemplate,
    ChecklistTemplateItem,
    Checklist,
    ChecklistResult,
    ChecklistItemStatus,
)

# Import TaskCategory safely
try:
    from tasks.models import TaskCategory
except ImportError:
    TaskCategory = None

# Setup logger for this module
logger = logging.getLogger(__name__)
# Optional: Set level for debugging during development if not set globally
# logger.setLevel(logging.DEBUG)

# --- Reusable Tailwind CSS Classes ---
BASE_INPUT_CLASSES = "block w-full px-3 py-2 border border-gray-300 rounded-md shadow-sm focus:ring-indigo-500 focus:border-indigo-500 sm:text-sm dark:bg-dark-700 dark:border-dark-600 dark:text-gray-200 dark:placeholder-gray-500"
TEXT_INPUT_CLASSES = f"form-input {BASE_INPUT_CLASSES}"
TEXTAREA_CLASSES = f"form-textarea {BASE_INPUT_CLASSES}"
SELECT_CLASSES = f"form-select {BASE_INPUT_CLASSES}"
CHECKBOX_CLASSES = "form-checkbox h-4 w-4 text-indigo-600 border-gray-300 rounded focus:ring-indigo-500 dark:bg-dark-600 dark:border-dark-500 dark:checked:bg-indigo-500 dark:focus:ring-offset-dark-800"
NUMBER_INPUT_CLASSES_SMALL = (
    f"form-input {BASE_INPUT_CLASSES} w-16 text-center text-sm py-1"
)
RADIO_LABEL_CLASSES = "inline-flex items-center mr-4 cursor-pointer text-sm"
RADIO_INPUT_CLASSES = "form-radio h-4 w-4 text-indigo-600 border-gray-300 focus:ring-indigo-500 dark:bg-dark-600 dark:border-dark-500 dark:checked:bg-indigo-500 dark:focus:ring-offset-dark-800"

if TaskCategory is None:
    logger.warning(
        "TaskCategory model not available for Checklist forms. Category field will be disabled."
    )


# ==================================
# Checklist Template Form
# ==================================
class ChecklistTemplateForm(forms.ModelForm):
    """Form for creating and editing Checklist Templates."""

    logger.debug("Defining ChecklistTemplateForm fields...")

    if TaskCategory:
        category = forms.ModelChoiceField(
            queryset=TaskCategory.objects.all().order_by("name"),
            required=False,
            label=_("Категория (из Задач)"),
            widget=forms.Select(attrs={"class": SELECT_CLASSES}),
            help_text=_("Группировка шаблонов."),
        )
    else:
        category = forms.CharField(
            label=_("Категория (из Задач)"),
            required=False,
            disabled=True,
            widget=forms.TextInput(
                attrs={
                    "class": TEXT_INPUT_CLASSES
                    + " bg-gray-100 dark:bg-dark-800 cursor-not-allowed"
                }
            ),
            help_text=_("Модуль 'tasks' не найден."),
        )

    class Meta:
        model = ChecklistTemplate
        fields = ["name", "category", "description", "is_active"]
        widgets = {
            "name": forms.TextInput(
                attrs={
                    "class": TEXT_INPUT_CLASSES,
                    "placeholder": _("Название шаблона..."),
                }
            ),
            "description": forms.Textarea(
                attrs={
                    "rows": 3,
                    "class": TEXTAREA_CLASSES,
                    "placeholder": _("Описание назначения..."),
                }
            ),
            "is_active": forms.CheckboxInput(
                attrs={"class": CHECKBOX_CLASSES + " ml-2"}
            ),
        }
        labels = {
            "name": _("Название"),
            "description": _("Описание"),
            "is_active": _("Активен"),
        }
        help_texts = {"is_active": _("Активные шаблоны доступны для выполнения.")}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        instance_pk = self.instance.pk if self.instance else "New"
        logger.debug(
            f"ChecklistTemplateForm initialized for instance PK: {instance_pk}"
        )

    def clean(self):
        cleaned_data = super().clean()
        instance_pk = self.instance.pk if self.instance else "New"
        logger.debug(
            f"Running clean() for ChecklistTemplateForm PK: {instance_pk}. Data: {cleaned_data}"
        )
        # Example Validation: Check for unique name (case-insensitive) if needed
        name = cleaned_data.get("name")
        if name:
            query = ChecklistTemplate.objects.filter(name__iexact=name)
            if self.instance and self.instance.pk:
                query = query.exclude(pk=self.instance.pk)
            if query.exists():
                logger.warning(
                    f"Validation Error: Template with name '{name}' already exists."
                )
                self.add_error(
                    "name",
                    ValidationError(
                        _("Шаблон с таким названием уже существует."),
                        code="duplicate_name",
                    ),
                )
        return cleaned_data


# ==================================
# Checklist Template Item Form
# ==================================
class ChecklistTemplateItemForm(forms.ModelForm):
    """Form for a single item within the ChecklistTemplateItemFormSet."""

    class Meta:
        model = ChecklistTemplateItem
        fields = ["order", "item_text"]
        widgets = {
            "item_text": forms.Textarea(
                attrs={
                    "class": f"{TEXTAREA_CLASSES} text-sm py-1",
                    "rows": 2,
                    "placeholder": _("Текст пункта/вопроса..."),
                }
            ),
            "order": forms.NumberInput(
                attrs={"class": NUMBER_INPUT_CLASSES_SMALL, "min": "0"}
            ),
        }
        labels = {"order": _("№"), "item_text": _("Текст пункта")}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Make item_text required visually and for validation unless form is deleted
        if not (self.prefix and self.data.get(f"{self.prefix}-DELETE")):
            self.fields["item_text"].required = True

    def clean_order(self):
        order = self.cleaned_data.get("order")
        if order is None:  # Handle case where order might not be provided for new forms
            return 0  # Default to 0 if empty
        if order < 0:
            raise ValidationError(
                _("Порядок не может быть отрицательным."), code="negative_order"
            )
        return order

    def clean(self):
        cleaned_data = super().clean()
        is_deleted = cleaned_data.get("DELETE", False)
        item_text = cleaned_data.get("item_text", "").strip()
        instance_pk = self.instance.pk if self.instance else "New"
        logger.debug(
            f"Running clean() for ChecklistTemplateItemForm PK: {instance_pk}. Deleted: {is_deleted}, Text: '{item_text[:30]}...', Order: {cleaned_data.get('order')}"
        )

        # Check requiredness only if not marked for deletion
        # (Relying on blank=False in model and required=True set in __init__)
        # if not is_deleted and not item_text:
        #    self.add_error('item_text', ValidationError(_("Текст пункта обязателен."), code='required'))

        return cleaned_data


# ==================================
# Checklist Template Item Formset
# ==================================
ChecklistTemplateItemFormSet = inlineformset_factory(
    ChecklistTemplate,
    ChecklistTemplateItem,
    form=ChecklistTemplateItemForm,
    fields=("order", "item_text"),
    extra=1,
    min_num=0,
    validate_min=False,  # Allow saving with 0 items initially
    can_delete=True,
    can_order=False,
)


# ==================================
# Checklist Result Form
# ==================================
class ChecklistResultForm(forms.ModelForm):
    """Form for a single result item within the ChecklistResultFormSet."""

    template_item_display = forms.CharField(
        label=_("Пункт"),
        required=False,
        widget=forms.Textarea(
            attrs={
                "readonly": True,
                "rows": 2,
                "class": "block w-full text-sm p-2 rounded-md border-none bg-gray-100 dark:bg-dark-900/50 dark:text-gray-300 focus:ring-0",
            }
        ),
    )

    class Meta:
        model = ChecklistResult
        fields = ["template_item_display", "status", "comments"]
        widgets = {
            "status": forms.RadioSelect(
                attrs={"class": "flex flex-wrap gap-x-4 gap-y-1"}
            ),
            "comments": forms.Textarea(
                attrs={
                    "rows": 1,
                    "class": f"{TEXTAREA_CLASSES} text-sm py-1",
                    "placeholder": _("Комментарий (если Не OK)..."),
                }
            ),
        }
        labels = {"status": _("Результат"), "comments": _("Комментарий")}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        instance_pk = self.instance.pk if self.instance else "New"
        logger.debug(f"ChecklistResultForm initialized for instance PK: {instance_pk}")
        if self.instance and self.instance.pk and self.instance.template_item:
            self.fields["template_item_display"].initial = (
                self.instance.template_item.item_text
            )
        self.fields["status"].required = True
        self.fields["status"].empty_label = None

    def clean(self):
        cleaned_data = super().clean()
        status = cleaned_data.get("status")
        comments = cleaned_data.get("comments", "").strip()
        instance_pk = self.instance.pk if self.instance else "New"
        logger.debug(
            f"Running clean() for ChecklistResultForm PK: {instance_pk}. Status: {status}, Comments: '{comments[:30]}...'"
        )

        if status == ChecklistItemStatus.NOT_OK and not comments:
            logger.warning(
                f"Validation Error: Comment required for result {instance_pk} because status is NOT_OK."
            )
            self.add_error(
                "comments",
                ValidationError(
                    _('Комментарий обязателен, если статус "%(status)s".')
                    % {"status": ChecklistItemStatus.NOT_OK.label},
                    code="comment_required_for_not_ok",
                ),
            )
        return cleaned_data


# ==================================
# Checklist Result Formset
# ==================================
class BaseChecklistResultFormSet(BaseInlineFormSet):
    """Base formset for checklist results."""

    def add_fields(self, form, index):
        super().add_fields(form, index)
        # The custom form 'ChecklistResultForm' now handles adding 'template_item_display'

    def clean(self):
        super().clean()
        logger.debug(
            f"Running clean() for BaseChecklistResultFormSet (Prefix: {self.prefix})"
        )
        # Any cross-form validation for the entire result set can go here


ChecklistResultFormSet = inlineformset_factory(
    Checklist,
    ChecklistResult,
    form=ChecklistResultForm,  # Use the custom form
    formset=BaseChecklistResultFormSet,  # Use the custom base formset
    fields=("status", "comments"),  # Editable fields
    extra=0,
    can_delete=False,
)
