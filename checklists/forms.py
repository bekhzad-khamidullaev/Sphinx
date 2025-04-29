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
    ChecklistItemStatus
)
# Assuming TaskCategory is needed for filtering or display if not using Select2
# Import it safely in case the tasks app isn't always present or configured
try:
    from tasks.models import TaskCategory
except ImportError:
    TaskCategory = None
    logger.warning("Could not import TaskCategory from tasks.models for Checklist forms.")


logger = logging.getLogger(__name__)

# --- Reusable Tailwind CSS Classes (Define locally for this module) ---
# Based on classes from tasks/forms.py for consistency
BASE_INPUT_CLASSES = "block w-full px-4 py-2 border border-gray-300 rounded-lg shadow-sm focus:ring focus:ring-blue-500 focus:border-blue-500 focus:outline-none dark:bg-dark-700 dark:border-dark-600 dark:text-gray-200 dark:placeholder-gray-500 transition duration-150 ease-in-out"
TEXT_INPUT_CLASSES = f"form-input {BASE_INPUT_CLASSES}"
TEXTAREA_CLASSES = f"form-textarea {BASE_INPUT_CLASSES}"
SELECT_CLASSES = f"form-select {BASE_INPUT_CLASSES}"
CHECKBOX_CLASSES = "form-checkbox h-5 w-5 rounded text-blue-600 border-gray-300 dark:border-dark-500 dark:bg-dark-600 dark:checked:bg-blue-500 focus:ring-blue-500 dark:focus:ring-blue-500 dark:focus:ring-offset-dark-800 transition duration-150 ease-in-out"
# Specific for small inputs like 'order'
NUMBER_INPUT_CLASSES_SMALL = f"form-input {BASE_INPUT_CLASSES} w-16 text-center text-sm"
# Classes for radio buttons (wrapper needs styling in template or custom widget)
RADIO_SELECT_CLASSES = "inline-flex items-center space-x-2" # JS/CSS in template handles individual radio look

# ==============================================================================
# Checklist Template Form
# ==============================================================================
class ChecklistTemplateForm(forms.ModelForm):
    """Form for creating and editing Checklist Templates."""

    # Make category optional if TaskCategory couldn't be imported
    if TaskCategory:
        category = forms.ModelChoiceField(
            queryset=TaskCategory.objects.all().order_by('name'),
            required=False, # Allow templates without a category
            label=_("Категория (из Задач)"),
            widget=forms.Select(attrs={'class': SELECT_CLASSES}),
            help_text=_("Выберите подходящую категорию для группировки.")
        )
    else:
         # Provide a disabled placeholder if TaskCategory is unavailable
        category = forms.CharField(
            label=_("Категория (из Задач)"),
            required=False,
            disabled=True,
            widget=forms.TextInput(attrs={'class': TEXT_INPUT_CLASSES + ' bg-gray-100 dark:bg-dark-800 cursor-not-allowed'}),
            help_text=_("Модуль 'tasks' с категориями не найден.")
        )


    class Meta:
        model = ChecklistTemplate
        fields = ['name', 'category', 'description', 'is_active']
        widgets = {
            'name': forms.TextInput(attrs={
                'class': TEXT_INPUT_CLASSES,
                'placeholder': _("Название шаблона, напр., 'Ежедневный обход склада'")
            }),
            # Category widget is handled by the explicit field definition above
            'description': forms.Textarea(attrs={
                'rows': 3,
                'class': TEXTAREA_CLASSES,
                'placeholder': _("Краткое описание назначения чеклиста (опционально)")
            }),
            'is_active': forms.CheckboxInput(attrs={'class': CHECKBOX_CLASSES}),
        }
        labels = {
            'name': _("Название шаблона"),
            # 'category' label is defined in the explicit field
            'description': _("Описание"),
            'is_active': _("Активен"),
        }
        help_texts = {
            'name': _("Дайте шаблону понятное имя."),
            # 'category' help_text is defined in the explicit field
            'is_active': _("Только активные шаблоны будут доступны для выполнения."),
        }

# ==============================================================================
# Checklist Template Item Form and Formset
# ==============================================================================
class ChecklistTemplateItemForm(forms.ModelForm):
    """Form for a single item within the ChecklistTemplateItemFormSet."""
    class Meta:
        model = ChecklistTemplateItem
        # 'template' is set automatically by the formset
        # 'id' is needed implicitly by the formset for updates/deletes
        fields = ['order', 'item_text']
        widgets = {
            'item_text': forms.TextInput(attrs={
                'class': f'{TEXT_INPUT_CLASSES} text-sm', # Use text-sm for items
                'placeholder': _('Текст пункта/вопроса, напр., "Проверить пожарные выходы"')
            }),
            'order': forms.NumberInput(attrs={
                'class': NUMBER_INPUT_CLASSES_SMALL,
                'min': '0',
                'placeholder': _("№")
            }),
        }
        labels = {
            'order': _("Пор."), # Shorter label
            'item_text': _("Текст пункта"),
        }

    def clean(self):
        """
        Ensure item text is provided if the form is not marked for deletion,
        and order is non-negative.
        """
        cleaned_data = super().clean()
        is_deleted = cleaned_data.get('DELETE', False)
        item_text = cleaned_data.get('item_text', '').strip()
        order = cleaned_data.get('order')

        # Require item_text only if the form is not being deleted AND it's not an empty extra form
        # This is hard to determine reliably here. Model's blank=False is the primary validation.
        # We can add a check: if not item_text and not is_deleted and self.instance and self.instance.pk:
        #     self.add_error('item_text', ValidationError(_("Этот пункт не может быть пустым."), code='required'))

        if order is not None and order < 0:
            self.add_error('order', ValidationError(_("Порядок не может быть отрицательным."), code='negative_order'))

        return cleaned_data


ChecklistTemplateItemFormSet = inlineformset_factory(
    ChecklistTemplate,                  # Parent Model
    ChecklistTemplateItem,              # Child Model
    form=ChecklistTemplateItemForm,     # Use the custom form above
    fields=('order', 'item_text'),      # Fields to include from the model/form
    extra=1,                            # Start with 1 empty extra form
    min_num=0,                          # Allow zero items (template can be saved empty)
    validate_min=False,                 # Don't force validation on min_num=0
    can_delete=True,                    # Allow deleting existing items
    can_order=False                     # We use our own 'order' field, not built-in ordering
    # Widgets are now defined in ChecklistTemplateItemForm
)


# ==============================================================================
# Checklist Results FormSet (for Performing Checklist)
# ==============================================================================
class BaseChecklistResultFormSet(BaseInlineFormSet):
    """
    Base formset to add the read-only item text display
    when performing a checklist.
    """
    def add_fields(self, form, index):
        super().add_fields(form, index)
        # Display the corresponding template item's text read-only
        # Ensure 'instance' and 'template_item' are available
        template_item_text = ''
        # Check if form has an instance and the related template_item exists
        if form.instance and hasattr(form.instance, 'template_item') and form.instance.template_item:
             template_item_text = form.instance.template_item.item_text
        # If it's a new form (no instance yet), try getting from initial data if provided
        elif form.initial and form.initial.get('template_item'):
            try:
                item = ChecklistTemplateItem.objects.get(pk=form.initial['template_item'])
                template_item_text = item.item_text
            except ChecklistTemplateItem.DoesNotExist:
                logger.warning(f"Template item with pk {form.initial['template_item']} not found for initial data in formset.")

        form.fields['template_item_display'] = forms.CharField(
            label=_("Пункт для проверки"),
            initial=template_item_text,
            required=False,
            widget=forms.Textarea(attrs={ # Use Textarea for potentially long item text
                'readonly': True,
                'rows': 2, # Allow slightly more space
                'class': 'block w-full text-sm p-2 rounded-md border-none bg-gray-100 dark:bg-dark-900/50 dark:text-gray-300 pointer-events-none focus:ring-0' # Readonly styling
            })
        )
        # Order fields for better layout in the template
        # Make sure all expected fields are present before ordering
        field_order = ['template_item_display', 'status', 'comments']
        existing_fields = list(form.fields.keys())
        form.order_fields([f for f in field_order if f in existing_fields])


ChecklistResultFormSet = inlineformset_factory(
    Checklist,                          # Parent Model (the specific run)
    ChecklistResult,                    # Child Model (the results)
    formset=BaseChecklistResultFormSet, # Use the custom base formset
    fields=('status', 'comments'),      # Fields to edit for each item
    extra=0,                            # Do not show extra empty forms (created dynamically in view if needed)
    can_delete=False,                   # Cannot delete results while performing
    widgets={
        # Use RadioSelect for status - more user-friendly for predefined choices
        'status': forms.RadioSelect(
            # Note: 'class' here applies to the wrapper, not individual radios.
            # Styling individual radios often requires template customization or a custom widget.
             attrs={'class': RADIO_SELECT_CLASSES}
        ),
        'comments': forms.Textarea(attrs={
            'rows': 1, # Start small, can grow
            'class': f'{TEXTAREA_CLASSES} text-sm py-1', # Apply consistent styling, slightly smaller padding
            'placeholder': _('Комментарий (если статус "Не OK" или по необходимости)...')
        }),
    }
)