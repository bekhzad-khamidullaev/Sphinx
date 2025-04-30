# checklists/forms.py
import logging
from django import forms
from django.core.exceptions import ValidationError
from django.forms import inlineformset_factory, BaseInlineFormSet, models as model_forms # Use model_forms alias
from django.utils.translation import gettext_lazy as _
from django.contrib.auth import get_user_model
from django.db import models
from .models import (
    ChecklistTemplate, ChecklistTemplateItem, Checklist, ChecklistResult,
    ChecklistItemStatus, Location, ChecklistPoint
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


if TaskCategory is None:
    logger.warning("TaskCategory model not available for Checklist forms.")

# ==================================
# Checklist Template Form
# ==================================
class ChecklistTemplateForm(forms.ModelForm):
    if TaskCategory:
        category = forms.ModelChoiceField(
            queryset=TaskCategory.objects.all().order_by('name'), required=False,
            label=_("Категория (из Задач)"), widget=forms.Select(attrs={'class': SELECT_CLASSES}),
            help_text=_("Группировка шаблонов.")
        )
    else:
        category = forms.CharField(label=_("Категория"), required=False, disabled=True, help_text=_("Модуль 'tasks' не найден."))

    target_location = forms.ModelChoiceField(
        queryset=Location.objects.all().order_by('name'), required=False,
        label=_("Целевое Местоположение (Общее)"),
        widget=forms.Select(attrs={'class': SELECT_CLASSES, 'id': 'id_target_location'}), # ID for JS
        help_text=_("Опционально: Основное местоположение для этого шаблона.")
    )
    target_point = forms.ModelChoiceField(
        queryset=ChecklistPoint.objects.none(), required=False, # Populated by JS
        label=_("Целевая Точка/Комната (Общая)"),
        widget=forms.Select(attrs={'class': SELECT_CLASSES, 'id': 'id_target_point'}), # ID for JS
        help_text=_("Опционально: Конкретная точка (доступно после выбора местоположения).")
    )

    class Meta:
        model = ChecklistTemplate
        fields = ['name', 'category', 'target_location', 'target_point', 'description', 'is_active']
        widgets = {
            'name': forms.TextInput(attrs={'class': TEXT_INPUT_CLASSES, 'placeholder': _("Название шаблона...")}),
            'description': forms.Textarea(attrs={'rows': 3, 'class': TEXTAREA_CLASSES, 'placeholder': _("Описание назначения...")}),
            'is_active': forms.CheckboxInput(attrs={'class': CHECKBOX_CLASSES}),
        }
        labels = {'name': _("Название"), 'description': _("Описание"), 'is_active': _("Активен")}
        help_texts = {'is_active': _("Активные шаблоны доступны для выполнения.")}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        instance = self.instance # Get instance more reliably

        # Set initial queryset for target_point based on initial target_location
        if self.fields.get('target_point'):
            location_id = None
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
                self.fields['target_point'].queryset = ChecklistPoint.objects.none()

    def clean(self):
        cleaned_data = super().clean()
        point = cleaned_data.get('target_point')
        location = cleaned_data.get('target_location')

        if point and location and point.location != location:
            self.add_error('target_point', ValidationError(
                _('Выбранная точка не принадлежит указанному местоположению.'), code='point_location_mismatch'
            ))
        elif point and not location: cleaned_data['target_point'] = None # Auto-clear point
        return cleaned_data

# ==================================
# Checklist Template Item Form
# ==================================
class ChecklistTemplateItemForm(forms.ModelForm):
    target_point = forms.ModelChoiceField(
        queryset=ChecklistPoint.objects.none(), # Set dynamically
        required=False, label=_("Точка"),
        widget=forms.Select(attrs={'class': SELECT_CLASSES + ' text-xs py-1'}),
        help_text=_("Для конкр. точки")
    )

    class Meta:
        model = ChecklistTemplateItem
        fields = ['order', 'item_text', 'target_point']
        widgets = {
            'item_text': forms.Textarea(attrs={'class': f'{TEXTAREA_CLASSES} text-sm py-1', 'rows': 2, 'placeholder': _('Текст пункта/вопроса...')}),
            'order': forms.NumberInput(attrs={'class': NUMBER_INPUT_CLASSES_SMALL, 'min': '0'}),
        }
        labels = {'order': _("№"), 'item_text': _("Текст пункта")}

    def __init__(self, *args, **kwargs):
        # Get parent instance (template) passed from the formset view
        self.parent_instance = kwargs.pop('parent_instance', None)
        super().__init__(*args, **kwargs)

        # Set queryset for target_point based on parent template's location
        template_location = getattr(self.parent_instance, 'target_location', None)
        if template_location:
            self.fields['target_point'].queryset = ChecklistPoint.objects.filter(location=template_location).order_by('name')
        else:
            # Show all points if template has no specific location, grouped by location
            self.fields['target_point'].queryset = ChecklistPoint.objects.all().select_related('location').order_by('location__name', 'name')
            # Or disable if you require a template location first:
            # self.fields['target_point'].queryset = ChecklistPoint.objects.none()
            # self.fields['target_point'].widget.attrs['disabled'] = True
            # self.fields['target_point'].help_text = _("Выберите местоположение в шаблоне")

        # Item text is required if the form isn't marked for deletion
        self.fields['item_text'].required = True


    def clean_order(self):
        order = self.cleaned_data.get('order')
        if order is None: return 0
        if order < 0: raise ValidationError(_("Порядок не может быть отрицательным."), code='negative_order')
        return order

    def clean(self):
        cleaned_data = super().clean()
        point = cleaned_data.get('target_point')
        template_location = getattr(self.parent_instance, 'target_location', None)

        # Validate point belongs to template's location (if template has one)
        if point and template_location and point.location != template_location:
            self.add_error('target_point', ValidationError(
                _('Точка пункта не соответствует местоположению шаблона (%(loc)s).') % {'loc': template_location},
                code='item_point_location_mismatch'
            ))
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

ChecklistTemplateItemFormSet = inlineformset_factory(
    ChecklistTemplate, ChecklistTemplateItem,
    form=ChecklistTemplateItemForm,
    formset=BaseChecklistTemplateItemFormSet, # Use custom base formset
    fields=('order', 'item_text', 'target_point'),
    extra=1, min_num=0, validate_min=False,
    can_delete=True, can_order=False
)

# ==================================
# Checklist Result Form
# ==================================
class ChecklistResultForm(forms.ModelForm):
    template_item_display = forms.CharField(label=_("Пункт"), required=False, widget=forms.Textarea(attrs={'readonly': True, 'rows': 2, 'class': READONLY_TEXTAREA_CLASSES}))
    template_item_point_display = forms.CharField(label="", required=False, widget=forms.TextInput(attrs={'readonly': True, 'class': READONLY_INPUT_CLASSES}))

    class Meta:
        model = ChecklistResult
        fields = ['template_item_display', 'template_item_point_display', 'status', 'comments']
        widgets = {
            'status': forms.RadioSelect(attrs={'class': 'flex flex-wrap gap-x-4 gap-y-1'}), # Wrapper class
            'comments': forms.Textarea(attrs={'rows': 1, 'class': f'{TEXTAREA_CLASSES} text-sm py-1', 'placeholder': _('Комментарий (если Не OK)...')}),
        }
        labels = {'status': _("Результат"), 'comments': _("Комментарий")}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance and self.instance.pk and self.instance.template_item:
            self.fields['template_item_display'].initial = self.instance.template_item.item_text
            if self.instance.template_item.target_point:
                 self.fields['template_item_point_display'].initial = f"({_('Точка')}: {self.instance.template_item.target_point.name})"
        self.fields['status'].required = True
        self.fields['status'].empty_label = None
        # Order fields for display
        self.order_fields(['template_item_display', 'template_item_point_display', 'status', 'comments'])


    def clean(self):
        cleaned_data = super().clean()
        status = cleaned_data.get('status')
        comments = cleaned_data.get('comments', '').strip()
        if status == ChecklistItemStatus.NOT_OK and not comments:
            self.add_error('comments', ValidationError(
                _('Комментарий обязателен, если статус "%(status)s".') % {'status': ChecklistItemStatus.NOT_OK.label},
                code='comment_required_for_not_ok'
            ))
        return cleaned_data

# ==================================
# Checklist Result Formset
# ==================================
class BaseChecklistResultFormSet(BaseInlineFormSet):
    def add_fields(self, form, index):
        super().add_fields(form, index)
        # Display fields handled within ChecklistResultForm __init__ now

    def clean(self):
        super().clean()
        # Example validation: Ensure at least one item is answered (not pending)
        answered_count = 0
        for form in self.forms:
            # Skip empty forms or those marked for deletion
            if self.can_delete and self._should_delete_form(form):
                continue
            if form.cleaned_data and form.cleaned_data.get('status') != ChecklistItemStatus.PENDING:
                answered_count += 1

        # if answered_count == 0 and self.total_form_count() > 0:
        #     raise ValidationError(_("Необходимо ответить хотя бы на один пункт чеклиста."), code='no_answers')


ChecklistResultFormSet = inlineformset_factory(
    Checklist, ChecklistResult,
    form=ChecklistResultForm,
    formset=BaseChecklistResultFormSet,
    fields=('status', 'comments'),
    extra=0, can_delete=False
)