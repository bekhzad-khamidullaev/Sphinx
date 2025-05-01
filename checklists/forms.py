import logging
from django import forms
from django.core.exceptions import ValidationError
from django.forms import inlineformset_factory, BaseInlineFormSet, models as model_forms # Use model_forms alias
from django.utils.translation import gettext_lazy as _
from django.contrib.auth import get_user_model
from django.db import models
from django.utils.safestring import mark_safe # For custom radio rendering
from django.utils import timezone # Added timezone import
from .models import (
    ChecklistTemplate, ChecklistTemplateItem, Checklist, ChecklistResult,
    ChecklistItemStatus, Location, ChecklistPoint, AnswerType, ChecklistRunStatus
)
try:
    from tasks.models import TaskCategory
except ImportError:
    TaskCategory = None

User = get_user_model()
logger = logging.getLogger(__name__)

# --- Tailwind CSS Classes ---
BASE_INPUT_CLASSES = "block w-full px-3 py-2 border border-gray-300 rounded-md shadow-sm focus:ring-indigo-500 focus:border-indigo-500 sm:text-sm dark:bg-dark-700 dark:border-dark-600 dark:text-gray-200 dark:placeholder-gray-500"
TEXT_INPUT_CLASSES = f"form-input {BASE_INPUT_CLASSES}"
TEXTAREA_CLASSES = f"form-textarea {BASE_INPUT_CLASSES}"
SELECT_CLASSES = f"form-select {BASE_INPUT_CLASSES}"
CHECKBOX_CLASSES = "form-checkbox h-4 w-4 text-indigo-600 border-gray-300 rounded focus:ring-indigo-500 dark:bg-dark-600 dark:border-dark-500 dark:checked:bg-indigo-500 dark:focus:ring-offset-dark-800"
NUMBER_INPUT_CLASSES_SMALL = f"form-input {BASE_INPUT_CLASSES} w-16 text-center text-sm py-1"
RADIO_LABEL_CLASSES = "inline-flex items-center mr-4 cursor-pointer text-sm"
RADIO_INPUT_CLASSES = "form-radio h-4 w-4 text-indigo-600 border-gray-300 focus:ring-indigo-500 dark:bg-dark-600 dark:border-dark-500 dark:checked:bg-indigo-500 dark:focus:ring-offset-dark-800"
READONLY_TEXTAREA_CLASSES = 'block w-full text-sm p-2 rounded-md border-none bg-gray-100 dark:bg-dark-900/50 dark:text-gray-300 focus:ring-0 pointer-events-none'
READONLY_INPUT_CLASSES = 'text-xs text-gray-500 dark:text-gray-400 border-none bg-transparent p-0 m-0 -mt-1 pointer-events-none'
STATUS_RADIO_CLASSES = 'flex flex-wrap gap-x-4 gap-y-1' # Wrapper class for status radios

# Custom Widget for ChecklistItemStatus Radio Select
class ChecklistItemStatusRadioSelect(forms.RadioSelect):
    # You could customize render here if needed, but CSS class on wrapper might be enough
    pass


if TaskCategory is None:
    logger.warning("TaskCategory model not available for Checklist forms.")

# ==================================
# Checklist Template Form
# ==================================
class ChecklistTemplateForm(forms.ModelForm):
    # Redefine category field if TaskCategory is available
    if TaskCategory:
        category = forms.ModelChoiceField(
            queryset=TaskCategory.objects.all().order_by('name'), required=False,
            label=_("Категория (из Задач)"), widget=forms.Select(attrs={'class': SELECT_CLASSES}),
            help_text=_("Группировка шаблонов.")
        )
    else:
        # Provide a dummy field if TaskCategory is not available
        category = forms.CharField(label=_("Категория"), required=False, disabled=True, help_text=_("Модуль 'tasks' не найден."))

    target_location = forms.ModelChoiceField(
        queryset=Location.objects.all().order_by('name'), required=False,
        label=_("Целевое Местоположение (Общее)"),
        widget=forms.Select(attrs={'class': SELECT_CLASSES, 'id': 'id_target_location'}), # ID for JS
        help_text=_("Опционально: Основное местоположение для этого шаблона.")
    )
    target_point = forms.ModelChoiceField(
        queryset=ChecklistPoint.objects.none(), required=False, # Populated by JS or __init__
        label=_("Целевая Точка/Комната (Общая)"),
        widget=forms.Select(attrs={'class': SELECT_CLASSES, 'id': 'id_target_point'}), # ID for JS
        help_text=_("Опционально: Конкретная точка (доступно после выбора местоположения).")
    )
    # Assuming tags field is handled by TaggableManager and django-taggit forms

    class Meta:
        model = ChecklistTemplate
        # Include all relevant fields for creation/editing
        fields = ['name', 'category', 'target_location', 'target_point', 'description', 'is_active', 'version', 'frequency', 'next_due_date', 'tags', 'is_archived']
        widgets = {
            'name': forms.TextInput(attrs={'class': TEXT_INPUT_CLASSES, 'placeholder': _("Название шаблона...")}),
            'description': forms.Textarea(attrs={'rows': 3, 'class': TEXTAREA_CLASSES, 'placeholder': _("Описание назначения...")}),
            'is_active': forms.CheckboxInput(attrs={'class': CHECKBOX_CLASSES}),
            'version': forms.TextInput(attrs={'class': TEXT_INPUT_CLASSES + ' w-32', 'placeholder': '1.0'}),
            'frequency': forms.TextInput(attrs={'class': TEXT_INPUT_CLASSES, 'placeholder': _("ежедневно, еженедельно...")}),
            'next_due_date': forms.DateInput(attrs={'type': 'date', 'class': TEXT_INPUT_CLASSES + ' w-40 flatpickr-date'}), # Add flatpickr class
             'is_archived': forms.CheckboxInput(attrs={'class': CHECKBOX_CLASSES}),
             # tags widget is usually handled by django-taggit widget,
             # but you can customize it:
             'tags': forms.TextInput(attrs={'class': TEXT_INPUT_CLASSES, 'placeholder': _("тег1, тег2...")}),
        }
        labels = {
            'name': _("Название"),
            'description': _("Описание"),
            'is_active': _("Активен"),
            'version': _("Версия"),
            'frequency': _("Периодичность"),
            'next_due_date': _("След. дата выполнения"),
            'tags': _("Теги"),
            'is_archived': _("Архивирован"),
        }
        help_texts = {
            'is_active': _("Активные шаблоны доступны для выполнения."),
            'is_archived': _("Архивированные шаблоны скрываются из основного списка."),
            'tags': _("Разделяйте теги запятыми."),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        instance = self.instance

        # Set initial queryset for target_point based on instance or initial data
        if self.fields.get('target_point'): # Check if field exists (in case TaskCategory was missing)
            location_id = None
            # Prioritize instance data, then initial data
            if instance and instance.pk and instance.target_location_id:
                location_id = instance.target_location_id
            elif self.initial.get('target_location'):
                loc_val = self.initial['target_location']
                location_id = loc_val.pk if isinstance(loc_val, models.Model) else loc_val

            if location_id:
                try:
                    self.fields['target_point'].queryset = ChecklistPoint.objects.filter(location_id=location_id).order_by('name')
                except Exception as e:
                    logger.error(f"Error initializing target_point queryset: {e}")
                    self.fields['target_point'].queryset = ChecklistPoint.objects.none()
            else:
                # If no location is set, the point dropdown should be empty or show all points
                 self.fields['target_point'].queryset = ChecklistPoint.objects.none() # Or .all() if you want all points globally


    def clean(self):
        cleaned_data = super().clean()
        point = cleaned_data.get('target_point')
        location = cleaned_data.get('target_location')

        # Re-validate point/location consistency
        if point and location and point.location != location:
            self.add_error('target_point', ValidationError(
                _('Выбранная точка не принадлежит указанному местоположению.'), code='point_location_mismatch'
            ))
        # Auto-clear point if location is removed
        elif point and not location:
             logger.debug("Clearing target_point because target_location is not set.")
             cleaned_data['target_point'] = None
             # Do not add an error here, just clear the value


        return cleaned_data

# ==================================
# Checklist Template Item Form (for Template Item Formset)
# ==================================
class ChecklistTemplateItemForm(forms.ModelForm):
    # Re-declare fields to apply CSS classes and filter querysets
    order = forms.IntegerField(
        widget=forms.NumberInput(attrs={'class': NUMBER_INPUT_CLASSES_SMALL, 'min': '0'}),
        label=_("№"), initial=0
    )
    item_text = forms.CharField(
        widget=forms.Textarea(attrs={'class': f'{TEXTAREA_CLASSES} text-sm py-1', 'rows': 2, 'placeholder': _('Текст пункта/вопроса...')}),
        label=_("Текст пункта")
    )
    answer_type = forms.ChoiceField(
        choices=AnswerType.choices,
        widget=forms.Select(attrs={'class': SELECT_CLASSES + ' text-xs py-1'}),
        label=_("Тип ответа")
    )
    target_point = forms.ModelChoiceField(
        queryset=ChecklistPoint.objects.none(), # Set dynamically in __init__
        required=False, label=_("Точка"),
        widget=forms.Select(attrs={'class': SELECT_CLASSES + ' text-xs py-1'}),
        help_text=_("Для конкр. точки")
    )
    help_text = forms.CharField(
         required=False, label=_("Подсказка"),
         widget=forms.TextInput(attrs={'class': TEXT_INPUT_CLASSES + ' text-xs py-1', 'placeholder': _("Доп. информация...")}),
         help_text=_("Отображается при выполнении.")
    )
    default_value = forms.CharField(
         required=False, label=_("Значение по умолчанию"),
         widget=forms.TextInput(attrs={'class': TEXT_INPUT_CLASSES + ' text-xs py-1', 'placeholder': _("Напр. 'Да', 'OK', '5'...")}),
         help_text=_("Заполнится автоматически при создании чеклиста.")
    )
    parent_item = forms.ModelChoiceField(
         queryset=ChecklistTemplateItem.objects.none(), # Set dynamically in __init__
         required=False, label=_("Родительский пункт"),
         widget=forms.Select(attrs={'class': SELECT_CLASSES + ' text-xs py-1'}),
         help_text=_("Для создания вложенности.")
    )


    class Meta:
        model = ChecklistTemplateItem
        # Include all fields in the form
        fields = ['order', 'item_text', 'answer_type', 'target_point', 'help_text', 'default_value', 'parent_item', 'section'] # section needed for formset order/grouping
        widgets = {
            'section': forms.HiddenInput(), # Managed by formset/view logic
        }

    def __init__(self, *args, **kwargs):
        # Get parent instance (template) passed from the formset view
        self.parent_instance = kwargs.pop('parent_instance', None)
        super().__init__(*args, **kwargs)

        # Set queryset for target_point based on parent template's location
        template_location = None
        if self.parent_instance:
            template_location = getattr(self.parent_instance, 'target_location', None) # Use getattr for safety

        if template_location:
            self.fields['target_point'].queryset = ChecklistPoint.objects.filter(location=template_location).order_by('name')
        else:
             # If template has no specific location, maybe show all points grouped?
             # Or, restrict point selection in item if template has no location.
             # Restricting seems safer for data consistency.
             self.fields['target_point'].queryset = ChecklistPoint.objects.none()
             self.fields['target_point'].widget.attrs['disabled'] = True
             self.fields['target_point'].help_text = _("Выберите местоположение в шаблоне для выбора точки пункта")

        # Set queryset for parent_item to items *within the same template*
        # **FIX**: Only query items if the parent_instance is saved (has a pk)
        if self.parent_instance and self.parent_instance.pk:
            # Exclude the current item itself from the parent choices if it's an existing item
            qs = ChecklistTemplateItem.objects.filter(template=self.parent_instance)
            if self.instance and self.instance.pk:
                 qs = qs.exclude(pk=self.instance.pk)
                 # Also exclude descendants to prevent simple circular dependencies
                 # This requires a recursive query or similar, let's keep it simple for now
                 # A basic check is done in the model's clean method.
            self.fields['parent_item'].queryset = qs.select_related('section').order_by('section__order', 'order')
        else:
            # If parent_instance is not saved or doesn't exist, no items can be parents yet.
            self.fields['parent_item'].queryset = ChecklistTemplateItem.objects.none()
            self.fields['parent_item'].widget.attrs['disabled'] = True # Cannot select parent without saved template

        # Item text is required if the form isn't marked for deletion
        self.fields['item_text'].required = True


    def clean_order(self):
        order = self.cleaned_data.get('order')
        if order is None: return 0 # Default order
        if order < 0: raise ValidationError(_("Порядок не может быть отрицательным."), code='negative_order')
        return order

    def clean(self):
        cleaned_data = super().clean()
        point = cleaned_data.get('target_point')
        template = self.parent_instance # Get template instance from formset passing
        # Check if template is None before accessing attributes
        if not template:
             return cleaned_data # Cannot validate further without template

        template_location = getattr(template, 'target_location', None)

        # Re-validate point belongs to template's location (if template has one)
        if point and template_location and point.location != template_location:
            self.add_error('target_point', ValidationError(
                _('Точка пункта не соответствует местоположению шаблона (%(loc)s).') % {'loc': template_location.name},
                code='item_point_location_mismatch'
            ))
        # Auto-clear point if template has no location or it was cleared
        elif point and not template_location:
             cleaned_data['target_point'] = None # Point cannot exist without a template location

        # Validate parent_item is in the same template (handled by queryset, but extra check doesn't hurt)
        parent = cleaned_data.get('parent_item')
        if parent and parent.template != template:
             self.add_error('parent_item', ValidationError(
                 _('Родительский пункт должен быть из того же шаблона.'), code='parent_template_mismatch'
             ))
        # Model clean() handles self-referencing and simple cycles.

        # Validate default_value format based on answer_type? E.g., default for number is numeric.
        # This adds complexity. Maybe handle this client-side or leave as text for flexibility.
        # For now, default_value is just a CharField.

        return cleaned_data


# ==================================
# Checklist Template Item Formset
# ==================================
class BaseChecklistTemplateItemFormSet(BaseInlineFormSet):
    # Pass the parent instance to each form
    def get_form_kwargs(self, index):
        kwargs = super().get_form_kwargs(index)
        kwargs['parent_instance'] = self.instance # Pass the ChecklistTemplate instance
        return kwargs

    # Optional: Add validation for unique order within section/template here
    def clean(self):
        super().clean()
        if any(self.errors):
            return # Don't bother with unique checks if other errors exist

        orders = {} # Store orders per section (or None for unsectioned)
        for i, form in enumerate(self.forms):
            if not form.is_valid() or not form.cleaned_data or self._should_delete_form(form):
                continue # Skip invalid or deleted forms

            order = form.cleaned_data.get('order')
            section = form.cleaned_data.get('section') # Section FK is now in the form
            section_id = section.id if section else None # Use section ID or None as key

            if order is None: continue # Skip if order is missing

            order_key = (section_id, order)
            if order_key in orders:
                 # Duplicate order found within the same section
                 form.add_error('order', ValidationError(
                     _("Порядок '%(order)s' уже используется для другого пункта %(section_info)s в этом шаблоне.") % {
                         'order': order,
                         'section_info': f"в секции '{section.title}'" if section else _("без секции")
                     },
                     code='duplicate_order_in_section'
                 ))
                 # Also add error to the first form that had this order
                 first_form_index = orders[order_key]
                 self.forms[first_form_index].add_error('order', ValidationError(
                     _("Этот порядок дублируется другим пунктом."),
                     code='duplicate_order_in_section'
                 ))

            else:
                 orders[order_key] = i


ChecklistTemplateItemFormSet = inlineformset_factory(
    ChecklistTemplate, ChecklistTemplateItem,
    form=ChecklistTemplateItemForm,
    formset=BaseChecklistTemplateItemFormSet, # Use custom base formset
    # Fields list needs to match the form's Meta fields
    fields=('order', 'item_text', 'answer_type', 'target_point', 'help_text', 'default_value', 'parent_item', 'section'),
    extra=1, min_num=0, validate_min=False,
    can_delete=True, can_order=False # Use 'order' field for explicit ordering
)


# ==================================
# Checklist Result Form (for Perform Checklist View)
# ==================================
class ChecklistResultForm(forms.ModelForm):
    # Hidden fields for model values - only one will be used based on answer_type
    # These are declared in Meta fields now.

    # Read-only display fields for context
    template_item_display = forms.CharField(label=_("Пункт"), required=False, widget=forms.Textarea(attrs={'readonly': True, 'rows': 2, 'class': READONLY_TEXTAREA_CLASSES}))
    template_item_point_display = forms.CharField(label="", required=False, widget=forms.TextInput(attrs={'readonly': True, 'class': READONLY_INPUT_CLASSES}))
    help_text_display = forms.CharField(label="", required=False, widget=forms.Textarea(attrs={'readonly': True, 'rows': 1, 'class': f'{READONLY_TEXTAREA_CLASSES} text-gray-500 italic text-xs p-0 -mb-2 mt-1'}))

    class Meta:
        model = ChecklistResult
        # Include ALL potential model fields used by the dynamic form AND status/comments/corrected
        # Exclude FKs (template_item, checklist_run) and the PK (id) as they are handled by formset/model
        fields = ['status', 'comments', 'is_corrected',
                  'value', 'numeric_value', 'boolean_value', 'date_value', 'datetime_value', 'time_value',
                  'file_attachment', 'media_url']
        widgets = {
            # Use HiddenInput for value fields initially, override in __init__
            'value': forms.HiddenInput(),
            'numeric_value': forms.HiddenInput(),
            'boolean_value': forms.HiddenInput(),
            'date_value': forms.HiddenInput(),
            'datetime_value': forms.HiddenInput(),
            'time_value': forms.HiddenInput(),
            'file_attachment': forms.HiddenInput(),
            'media_url': forms.HiddenInput(),
            # Visible fields
            'status': ChecklistItemStatusRadioSelect(attrs={'class': STATUS_RADIO_CLASSES}), # Apply wrapper class
            'comments': forms.Textarea(attrs={'rows': 1, 'class': f'{TEXTAREA_CLASSES} text-sm py-1 mt-2', 'placeholder': _('Комментарий (если Не OK)...')}),
            'is_corrected': forms.CheckboxInput(attrs={'class': CHECKBOX_CLASSES + ' ms-2'}), # Simple styling for checkbox
        }
        labels = {
             'status': _("Результат"),
             'comments': _("Комментарий"),
             'is_corrected': _("Исправлено"),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        instance = self.instance # The ChecklistResult instance

        # Populate read-only display fields
        if instance and instance.template_item: # Use .template_item directly from instance
            item = instance.template_item
            self.fields['template_item_display'].initial = item.item_text
            if item.target_point:
                 self.fields['template_item_point_display'].initial = f"({_('Точка')}: {item.target_point.name})"
            if item.help_text:
                 self.fields['help_text_display'].initial = item.help_text

            # ===========================================================
            # Dynamically configure the primary input field
            # ===========================================================
            answer_type = item.answer_type
            field_name_to_use = None
            widget_to_use = None
            label_text = _("Ответ")
            is_file_field = False # Flag for file handling

            # Map AnswerType to the model field and appropriate widget/label
            if answer_type == AnswerType.TEXT:
                field_name_to_use = 'value' # Uses TextField in model
                widget_to_use = forms.Textarea(attrs={'rows': 2, 'class': f'{TEXTAREA_CLASSES} text-sm'})
            elif answer_type in [AnswerType.SCALE_1_4, AnswerType.SCALE_1_5]:
                field_name_to_use = 'numeric_value' # Uses FloatField in model
                choices = [(i, str(i)) for i in range(1, 5 if answer_type == AnswerType.SCALE_1_4 else 6)]
                widget_to_use = forms.RadioSelect(choices=choices, attrs={'class': 'flex flex-wrap gap-x-4'})
                label_text = _("Оценка")
            elif answer_type in [AnswerType.YES_NO, AnswerType.YES_NO_MEH]:
                 field_name_to_use = 'value' # Uses TextField in model (stores 'yes', 'no', 'yes_no_meh')
                 choices = []
                 if answer_type == AnswerType.YES_NO:
                      choices = [('yes', _('Да')), ('no', _('Нет'))]
                 elif answer_type == AnswerType.YES_NO_MEH:
                      choices = [('yes', _('Да')), ('yes_no_meh', _('Не очень')), ('no', _('Нет'))] # Order by common sense
                 widget_to_use = forms.RadioSelect(choices=choices, attrs={'class': 'flex flex-wrap gap-x-4'})
                 label_text = _("Ответ")
            elif answer_type == AnswerType.NUMBER:
                field_name_to_use = 'numeric_value' # Uses FloatField in model
                widget_to_use = forms.NumberInput(attrs={'class': f'{TEXT_INPUT_CLASSES} w-32'})
                label_text = _("Число")
            elif answer_type == AnswerType.DATE:
                field_name_to_use = 'date_value' # Uses DateField in model
                widget_to_use = forms.DateInput(attrs={'type': 'date', 'class': f'{TEXT_INPUT_CLASSES} w-40 flatpickr-date'})
                label_text = _("Дата")
            elif answer_type == AnswerType.DATETIME:
                field_name_to_use = 'datetime_value' # Uses DateTimeField in model
                widget_to_use = forms.DateTimeInput(attrs={'type': 'datetime-local', 'class': f'{TEXT_INPUT_CLASSES} w-56 flatpickr-datetime'})
                label_text = _("Дата и время")
            elif answer_type == AnswerType.TIME:
                field_name_to_use = 'time_value' # Uses TimeField in model
                widget_to_use = forms.TimeInput(attrs={'type': 'time', 'class': f'{TEXT_INPUT_CLASSES} w-32 flatpickr-time'})
                label_text = _("Время")
            elif answer_type == AnswerType.BOOLEAN:
                 field_name_to_use = 'boolean_value' # Uses BooleanField in model
                 # Use RadioSelect for more intuitive Yes/No
                 widget_to_use = forms.RadioSelect(choices=[('true', _('Да')), ('false', _('Нет'))], attrs={'class': 'flex flex-wrap gap-x-4'})
                 # widget_to_use = forms.NullBooleanSelect(attrs={'class': SELECT_CLASSES + ' w-32'}) # Alternative
                 label_text = _("Ответ")
            elif answer_type == AnswerType.FILE:
                 field_name_to_use = 'file_attachment' # Uses FileField in model
                 # Use ClearableFileInput for existing files
                 widget_to_use = forms.ClearableFileInput(attrs={'class': f'{BASE_INPUT_CLASSES} file-input'})
                 label_text = _("Файл")
                 is_file_field = True # Flag for enctype
            elif answer_type == AnswerType.URL:
                 field_name_to_use = 'media_url' # Uses URLField in model
                 widget_to_use = forms.URLInput(attrs={'class': TEXT_INPUT_CLASSES, 'placeholder': 'https://...'})
                 label_text = _("Ссылка")

            # Configure the actual input field if a mapping was found
            if field_name_to_use and field_name_to_use in self.fields:
                 # Make the field visible and assign the correct widget/label
                 self.fields[field_name_to_use].widget = widget_to_use
                 self.fields[field_name_to_use].label = label_text
                 self.fields[field_name_to_use].required = False # Items are not required by default, validation handles 'pending' status

                 # Set initial value from the correct model field
                 # Handle boolean rendering for RadioSelect
                 if field_name_to_use == 'boolean_value' and isinstance(widget_to_use, forms.RadioSelect):
                      initial_bool = getattr(instance, field_name_to_use, None) # Use getattr with default None
                      if initial_bool is True:
                           self.fields[field_name_to_use].initial = 'true'
                      elif initial_bool is False:
                           self.fields[field_name_to_use].initial = 'false'
                      else:
                           self.fields[field_name_to_use].initial = None
                 else:
                      self.fields[field_name_to_use].initial = getattr(instance, field_name_to_use, None) # Use getattr with default None


            # Ensure status field is required and has no empty label
            self.fields['status'].required = True
            self.fields['status'].empty_label = None # Force selection unless allow blank is needed

            # Order fields for display in the template - place the dynamic input field strategically
            ordered_fields = [
                 'template_item_display', 'template_item_point_display', 'help_text_display',
                 'status', # Status comes after item info
                 # The dynamic input field goes here
                 'comments', 'is_corrected', # Comments and corrected flag come after the answer
             ]
            # Insert the specific value field into the ordered list
            if field_name_to_use:
                 ordered_fields.insert(ordered_fields.index('comments'), field_name_to_use) # Place before comments

            self.order_fields(ordered_fields)

        else:
             # This case should ideally not happen if formset is created with a queryset of results
             logger.error("ChecklistResultForm initialized without an instance or template_item.")


    def clean(self):
        """
        Custom clean method to handle value based on answer type and validate status/comments.
        """
        cleaned_data = super().clean()
        instance = self.instance # The ChecklistResult instance being cleaned
        if not instance or not instance.template_item:
             # Cannot perform validation without the instance/template item
             return cleaned_data

        item = instance.template_item # The associated ChecklistTemplateItem

        status = cleaned_data.get('status')
        comments = cleaned_data.get('comments', '').strip()

        # --- 1. Handle Status and Comments Validation ---
        if status == ChecklistItemStatus.NOT_OK and not comments:
             self.add_error('comments', ValidationError(
                 _('Комментарий обязателен, если статус "%(status)s".') % {'status': ChecklistItemStatus.NOT_OK.label},
                 code='comment_required_for_not_ok'
             ))

        # --- 2. Process Value based on Answer Type and Clear Irrelevant Fields ---
        correct_value_field = item.primary_value_field_name # Use model property

        # Handle boolean specifically as RadioSelect returns 'true'/'false' strings
        if correct_value_field == 'boolean_value' and isinstance(self.fields['boolean_value'].widget, forms.RadioSelect):
            submitted_str_value = cleaned_data.get('boolean_value')
            if submitted_str_value == 'true':
                cleaned_data['boolean_value'] = True
            elif submitted_str_value == 'false':
                cleaned_data['boolean_value'] = False
            else:
                cleaned_data['boolean_value'] = None

        # Clear all other value fields in cleaned_data to ensure only the correct one is saved
        all_value_fields = ['value', 'numeric_value', 'boolean_value', 'date_value', 'datetime_value', 'time_value', 'file_attachment', 'media_url']
        for field in all_value_fields:
            if field != correct_value_field:
                # FileField needs special handling for clearing
                if field == 'file_attachment':
                     # Check if the clear checkbox was checked (Django handles this in form.cleaned_data)
                     if cleaned_data.get(f"{field}-clear"):
                          cleaned_data[field] = False # Mark for clearing
                     else:
                          # If not explicitly cleared, remove from cleaned_data to avoid overwriting existing file with None
                          if field in cleaned_data:
                              del cleaned_data[field]
                else:
                    # For other fields, set to None only if they are actually present in cleaned_data
                    # This prevents overwriting existing db values with None if the field wasn't submitted
                    if field in cleaned_data:
                         cleaned_data[field] = None
            # The correct_value_field is already processed above

        # --- 3. Validate value presence if status is not PENDING or NA ---
        if status in [ChecklistItemStatus.OK, ChecklistItemStatus.NOT_OK]:
            value_provided = False
            if correct_value_field:
                submitted_value = cleaned_data.get(correct_value_field)

                # Special check for FileField: False means "clear existing file", None means no change
                if correct_value_field == 'file_attachment':
                    # A new file upload counts as value_provided
                    if submitted_value and submitted_value is not False:
                        value_provided = True
                    # Clearing an existing file counts as an action
                    elif submitted_value is False and instance and instance.file_attachment:
                        value_provided = True
                    # Keeping an existing file (submitted_value is None, instance has file) counts
                    elif submitted_value is None and instance and instance.file_attachment:
                        value_provided = True
                elif isinstance(submitted_value, str):
                     value_provided = bool(submitted_value.strip()) # Check for non-empty string
                elif submitted_value is not None: # Includes numbers, dates, booleans (True/False)
                     value_provided = True


            value_types_requiring_input = [
                AnswerType.TEXT, AnswerType.SCALE_1_4, AnswerType.SCALE_1_5,
                AnswerType.YES_NO, AnswerType.YES_NO_MEH, AnswerType.NUMBER,
                AnswerType.DATE, AnswerType.DATETIME, AnswerType.TIME,
                AnswerType.BOOLEAN, AnswerType.FILE, AnswerType.URL
            ]
            # Add required check from template item if you implement it: and item.is_required
            if item.answer_type in value_types_requiring_input and not value_provided:
                  if correct_value_field and correct_value_field in self.fields:
                      self.add_error(correct_value_field, ValidationError(
                           _('Пожалуйста, предоставьте ответ для этого пункта.'), code='value_required_for_status'
                      ))
                  else:
                       self.add_error(None, ValidationError(
                            _('Пункт "%(item)s" требует ответа.') % {'item': item.item_text}, code='value_required_general'
                       ))

        # --- 4. Handle numeric_value mapping for text/bool choices ---
        if item.answer_type in [AnswerType.YES_NO, AnswerType.YES_NO_MEH]:
             text_value = cleaned_data.get('value')
             if text_value == 'yes': cleaned_data['numeric_value'] = 1.0
             elif text_value == 'no': cleaned_data['numeric_value'] = 0.0
             elif text_value == 'yes_no_meh': cleaned_data['numeric_value'] = 0.5
             else: cleaned_data['numeric_value'] = None
        elif item.answer_type == AnswerType.BOOLEAN:
             bool_value = cleaned_data.get('boolean_value')
             if bool_value is True: cleaned_data['numeric_value'] = 1.0
             elif bool_value is False: cleaned_data['numeric_value'] = 0.0
             else: cleaned_data['numeric_value'] = None

        # --- 5. Set created/updated by user ---
        # This is better handled in the view during formset processing
        # to access the request user reliably.

        return cleaned_data


# ==================================
# Checklist Result Inline Formset (for Perform Checklist View)
# ==================================
class BasePerformChecklistResultFormSet(BaseInlineFormSet):
    """
    Custom formset for the 'Perform Checklist' view.
    Uses the dynamic ChecklistResultForm.
    """
    def get_form_kwargs(self, index):
        """Pass request user to the form for created_by/updated_by (optional)."""
        kwargs = super().get_form_kwargs(index)
        # Access request user if available (e.g., passed from the view)
        # kwargs['user'] = self.request.user # Need request access
        return kwargs

    def clean(self):
        """
        Perform any formset-level validation if needed.
        Item-level validation is mostly in ChecklistResultForm.clean().
        """
        super().clean()
        if any(self.errors):
             return # Skip further checks if form-level errors exist


PerformChecklistResultFormSet = inlineformset_factory(
    Checklist, ChecklistResult,
    form=ChecklistResultForm,
    formset=BasePerformChecklistResultFormSet,
    # The fields list must include ALL potential model fields used by the dynamic form
    # EXCLUDE id, template_item, checklist_run
    fields=['status', 'comments', 'is_corrected', 'value', 'numeric_value', 'boolean_value', 'date_value', 'datetime_value', 'time_value', 'file_attachment', 'media_url'],
    extra=0, # No extra empty forms
    can_delete=False, # Results are created when the run is created, not deleted here
)

# ==================================
# Checklist Run Status Update Form
# ==================================
class ChecklistStatusUpdateForm(forms.ModelForm):
     class Meta:
         model = Checklist
         # Allow changing status, approved_by, approved_at, and notes
         fields = ['status', 'approved_by', 'approved_at', 'notes']
         widgets = {
             'status': forms.Select(attrs={'class': SELECT_CLASSES}),
             'approved_by': forms.Select(attrs={'class': SELECT_CLASSES}),
             # Using DateTimeInput allows manual entry, or you could hide/make readonly
             'approved_at': forms.DateTimeInput(attrs={'type': 'datetime-local', 'class': TEXT_INPUT_CLASSES + ' w-fit flatpickr-datetime'}), # Add flatpickr class
             'notes': forms.Textarea(attrs={'rows': 3, 'class': TEXTAREA_CLASSES}),
         }
         labels = {
              'status': _("Статус"),
              'approved_by': _("Одобрено кем"),
              'approved_at': _("Время одобрения"),
              'notes': _("Дополнительные примечания к статусу"),
         }

     def __init__(self, *args, **kwargs):
         super().__init__(*args, **kwargs)
         # Limit approved_by queryset if needed (e.g., only staff users)
         self.fields['approved_by'].queryset = User.objects.filter(is_staff=True).order_by('username')
         self.fields['approved_by'].required = False # Not always required

         # Store initial status to check for changes in save()
         if self.instance.pk:
              self.instance._original_status = self.instance.status


     def clean(self):
         cleaned_data = super().clean()
         status = cleaned_data.get('status')
         approved_by = cleaned_data.get('approved_by')
         approved_at = cleaned_data.get('approved_at')
         notes = cleaned_data.get('notes', '').strip()

         # Validation for APPROVED status
         if status == ChecklistRunStatus.APPROVED:
             if not approved_by:
                 self.add_error('approved_by', ValidationError(_("При статусе 'Одобрено' необходимо указать, кем одобрено."), code='approved_by_required'))
             # approved_at will be set in save() if not provided, so no validation here

         # Validation for REJECTED status
         if status == ChecklistRunStatus.REJECTED and not notes:
             self.add_error('notes', ValidationError(_("При статусе 'Отклонено' необходимо указать причину в примечаниях."), code='notes_required_for_rejected'))

         return cleaned_data

     def save(self, commit=True):
         instance = super().save(commit=False)
         # Automatically set approved_at if status changes to APPROVED and it's not set
         original_status = getattr(instance, '_original_status', None)

         if instance.status == ChecklistRunStatus.APPROVED and original_status != ChecklistRunStatus.APPROVED and not instance.approved_at:
              instance.approved_at = timezone.now()
              logger.debug(f"Auto-setting approved_at for checklist {instance.id}")

         # Clear approval fields if status changes away from APPROVED
         if instance.status != ChecklistRunStatus.APPROVED and original_status == ChecklistRunStatus.APPROVED:
              instance.approved_by = None
              instance.approved_at = None
              logger.debug(f"Clearing approval fields for checklist {instance.id}")

         # Ensure is_complete is True if status is SUBMITTED, APPROVED or REJECTED
         if instance.status in [ChecklistRunStatus.SUBMITTED, ChecklistRunStatus.APPROVED, ChecklistRunStatus.REJECTED]:
             if not instance.is_complete: # Only update if not already complete
                  instance.is_complete = True
                  logger.debug(f"Setting is_complete=True for checklist {instance.id} due to status change.")
             if instance.completion_time is None:
                  instance.completion_time = timezone.now() # Ensure completion_time is set
                  logger.debug(f"Setting completion_time for checklist {instance.id} due to status change.")

         if commit:
             instance.save()
             # Save many-to-many data if needed (not applicable here)
             # self.save_m2m()
         return instance