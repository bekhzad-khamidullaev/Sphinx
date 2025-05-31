# checklists/forms.py
import logging
from django import forms
from django.core.exceptions import ValidationError
from django.forms import inlineformset_factory, BaseInlineFormSet, models as model_forms
from django.utils.translation import gettext_lazy as _
from django.contrib.auth import get_user_model
from django.db import models as django_db_models
from django.utils.safestring import mark_safe
from django.utils import timezone
from .models import (
    ChecklistTemplate, ChecklistTemplateItem, Checklist, ChecklistResult, ChecklistItemStatus, ChecklistSection,
    ChecklistItemStatus, Location, ChecklistPoint, AnswerType, ChecklistRunStatus
)
try:
    from tasks.models import TaskCategory
except ImportError:
    TaskCategory = None

User = get_user_model()
logger = logging.getLogger(__name__)

BASE_INPUT_CLASSES = "block w-full px-3 py-2 border border-gray-300 rounded-md shadow-sm focus:ring-indigo-500 focus:border-indigo-500 sm:text-sm disabled:bg-gray-100 disabled:cursor-not-allowed"
TEXT_INPUT_CLASSES = f"form-input {BASE_INPUT_CLASSES}"
TEXTAREA_CLASSES = f"form-textarea {BASE_INPUT_CLASSES}"
SELECT_CLASSES = f"form-select {BASE_INPUT_CLASSES}"
CHECKBOX_CLASSES = "form-checkbox h-4 w-4 text-indigo-600 border-gray-300 rounded focus:ring-indigo-500"
NUMBER_INPUT_CLASSES_SMALL = f"form-input {BASE_INPUT_CLASSES} w-16 text-center text-sm py-1"
FILE_INPUT_CLASSES = "form-input block w-full text-sm text-gray-900 border border-gray-300 rounded-lg cursor-pointer bg-gray-50 focus:outline-none file:mr-4 file:py-2 file:px-3 file:rounded-l-md file:border-0 file:text-sm file:font-semibold file:bg-indigo-50 file:text-indigo-700 hover:file:bg-indigo-100"


READONLY_TEXTAREA_CLASSES = 'block w-full text-sm p-2 rounded-md border-none bg-gray-100 focus:ring-0 pointer-events-none'
READONLY_INPUT_CLASSES = 'text-xs text-gray-500 border-none bg-transparent p-0 m-0 -mt-1 pointer-events-none'

STATUS_RADIO_WRAPPER_CLASSES = 'flex flex-wrap gap-x-1 gap-y-2'
STATUS_RADIO_LABEL_CLASSES = "inline-flex items-center mr-2 cursor-pointer px-3 py-1.5 border border-gray-300 rounded-md text-sm font-medium hover:bg-gray-50 transition-colors"
STATUS_RADIO_INPUT_CLASSES = "sr-only"

class ChecklistItemStatusRadioSelect(forms.RadioSelect):
    template_name = 'widgets/checklist_status_radio.html'


if TaskCategory is None:
    logger.warning("TaskCategory model not available for Checklist forms.")

class ChecklistTemplateForm(forms.ModelForm):
    category_field_kwargs = {
        'required': False,
        'label': _("Категория (из Задач)"),
        'widget': forms.Select(attrs={'class': SELECT_CLASSES, 'data-placeholder': _("Выберите категорию...")}),
        'help_text': _("Группировка шаблонов.")
    }
    if TaskCategory and hasattr(TaskCategory, '_meta') and TaskCategory._meta.concrete_model:
        category = forms.ModelChoiceField(queryset=TaskCategory.objects.all().order_by('name'), **category_field_kwargs)
    else:
        category_field_kwargs['disabled'] = True
        category_field_kwargs['help_text'] = _("Модуль 'tasks' не найден или TaskCategory не является конкретной моделью.")
        category = forms.CharField(**category_field_kwargs)


    target_location = forms.ModelChoiceField(
        queryset=Location.objects.all().order_by('name'), required=False,
        label=_("Целевое Местоположение (Общее)"),
        widget=forms.Select(attrs={'class': SELECT_CLASSES, 'id': 'id_target_location', 'data-placeholder': _("Выберите местоположение...")}),
        help_text=_("Опционально: Основное местоположение для этого шаблона.")
    )
    target_point = forms.ModelChoiceField(
        queryset=ChecklistPoint.objects.none(), required=False,
        label=_("Целевая Точка/Комната (Общая)"),
        widget=forms.Select(attrs={'class': SELECT_CLASSES, 'id': 'id_target_point', 'data-placeholder': _("Выберите точку...")}),
        help_text=_("Опционально: Конкретная точка (доступно после выбора местоположения).")
    )

    class Meta:
        model = ChecklistTemplate
        fields = ['name', 'category', 'target_location', 'target_point', 'description', 'is_active', 'version', 'frequency', 'next_due_date', 'tags', 'is_archived']
        widgets = {
            'name': forms.TextInput(attrs={'class': TEXT_INPUT_CLASSES, 'placeholder': _("Название шаблона...")}),
            'description': forms.Textarea(attrs={'rows': 3, 'class': TEXTAREA_CLASSES, 'placeholder': _("Описание назначения...")}),
            'is_active': forms.CheckboxInput(attrs={'class': CHECKBOX_CLASSES + " ml-2"}),
            'version': forms.TextInput(attrs={'class': TEXT_INPUT_CLASSES + ' w-32', 'placeholder': '1.0'}),
            'frequency': forms.TextInput(attrs={'class': TEXT_INPUT_CLASSES, 'placeholder': _("ежедневно, еженедельно...")}),
            'next_due_date': forms.DateInput(attrs={'type': 'date', 'class': TEXT_INPUT_CLASSES + ' w-auto flatpickr-date'}),
             'is_archived': forms.CheckboxInput(attrs={'class': CHECKBOX_CLASSES + " ml-2"}),
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

        if self.fields.get('target_point'):
            location_id = None
            if instance and instance.pk and instance.target_location_id:
                location_id = instance.target_location_id
            elif self.initial.get('target_location'):
                loc_val = self.initial['target_location']
                location_id = loc_val.pk if isinstance(loc_val, django_db_models.Model) else loc_val
            elif 'target_location' in self.data and self.data['target_location']:
                try:
                    location_id = int(self.data['target_location'])
                except (ValueError, TypeError):
                    location_id = None


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
                _('Выбранная точка (%(point_name)s) не принадлежит указанному местоположению (%(location_name)s).') % {'point_name': point.name, 'location_name': location.name},
                code='point_location_mismatch'
            ))
        elif point and not location:
             logger.debug("Clearing target_point because target_location is not set or cleared.")
             cleaned_data['target_point'] = None
        return cleaned_data

class ChecklistTemplateItemForm(forms.ModelForm):
    order = forms.IntegerField(
        widget=forms.NumberInput(attrs={'class': NUMBER_INPUT_CLASSES_SMALL, 'min': '0'}),
        label=_("№"), initial=0
    )
    item_text = forms.CharField(
        widget=forms.Textarea(attrs={'class': TEXTAREA_CLASSES + ' text-sm py-1', 'rows': 2, 'placeholder': _('Текст пункта/вопроса...')}),
        label=_("Текст пункта")
    )
    answer_type = forms.ChoiceField(
        choices=AnswerType.choices,
        widget=forms.Select(attrs={'class': SELECT_CLASSES + ' text-sm py-1'}),
        label=_("Тип ответа")
    )
    target_point = forms.ModelChoiceField(
        queryset=ChecklistPoint.objects.all(),
        required=False, label=_("Точка"),
        widget=forms.Select(attrs={'class': SELECT_CLASSES + ' text-sm py-1 select2-basic', 'data-placeholder': _("Для конкретной точки...")}),
        help_text=_("Опционально, для этого пункта.")
    )
    help_text = forms.CharField(
         required=False, label=_("Подсказка"),
         widget=forms.TextInput(attrs={'class': TEXT_INPUT_CLASSES + ' text-sm py-1', 'placeholder': _("Доп. информация...")}),
         help_text=_("Отображается при выполнении.")
    )
    default_value = forms.CharField(
         required=False, label=_("Значение по умолчанию"),
         widget=forms.TextInput(attrs={'class': TEXT_INPUT_CLASSES + ' text-sm py-1', 'placeholder': _("Напр. 'Да', 'OK', '5'...")}),
         help_text=_("Заполнится автоматически при создании чеклиста.")
    )
    parent_item = forms.ModelChoiceField(
         queryset=ChecklistTemplateItem.objects.none(),
         required=False, label=_("Родительский пункт"),
         widget=forms.Select(attrs={'class': SELECT_CLASSES + ' text-sm py-1 select2-basic', 'data-placeholder': _("Выберите родителя...")}),
         help_text=_("Для создания вложенности.")
    )
    section = forms.ModelChoiceField(
        queryset=ChecklistSection.objects.none(),
        required=False, label=_("Секция"),
        widget=forms.Select(attrs={'class': SELECT_CLASSES + ' text-sm py-1 select2-basic', 'data-placeholder': _("Выберите секцию...")})
    )


    class Meta:
        model = ChecklistTemplateItem
        fields = ['section', 'order', 'item_text', 'answer_type', 'target_point', 'help_text', 'default_value', 'parent_item']


    def __init__(self, *args, **kwargs):
        self.parent_template_instance = kwargs.pop('parent_instance', None)
        super().__init__(*args, **kwargs)

        template_location = None
        if self.parent_template_instance:
            template_location = getattr(self.parent_template_instance, 'target_location', None)

        if template_location:
            self.fields['target_point'].queryset = ChecklistPoint.objects.filter(location=template_location).order_by('name')
        else:
             self.fields['target_point'].queryset = ChecklistPoint.objects.none()
             self.fields['target_point'].widget.attrs['disabled'] = True
             self.fields['target_point'].help_text = _("Сначала выберите местоположение в шаблоне.")

        if self.parent_template_instance and self.parent_template_instance.pk:
            parent_items_qs = ChecklistTemplateItem.objects.filter(template=self.parent_template_instance)
            if self.instance and self.instance.pk:
                 parent_items_qs = parent_items_qs.exclude(pk=self.instance.pk)
            self.fields['parent_item'].queryset = parent_items_qs.select_related('section').order_by('section__order', 'order', 'item_text')
            self.fields['section'].queryset = ChecklistSection.objects.filter(template=self.parent_template_instance).order_by('order', 'title')
        else:
            self.fields['parent_item'].queryset = ChecklistTemplateItem.objects.none()
            self.fields['parent_item'].widget.attrs['disabled'] = True
            self.fields['section'].queryset = ChecklistSection.objects.none()
            self.fields['section'].widget.attrs['disabled'] = True


        self.fields['item_text'].required = True

    def clean_order(self):
        order = self.cleaned_data.get('order')
        if order is None: return 0
        if order < 0: raise ValidationError(_("Порядок не может быть отрицательным."), code='negative_order')
        return order

    def clean(self):
        cleaned_data = super().clean()
        point = cleaned_data.get('target_point')
        template = self.parent_template_instance
        if not template:
             return cleaned_data

        template_location = getattr(template, 'target_location', None)

        if point and template_location and point.location != template_location:
            self.add_error('target_point', ValidationError(
                _('Точка пункта (%(point_name)s) не соответствует местоположению шаблона (%(loc_name)s).') % {'point_name': point.name, 'loc_name': template_location.name},
                code='item_point_location_mismatch'
            ))
        elif point and not template_location:
             cleaned_data['target_point'] = None

        parent = cleaned_data.get('parent_item')
        if parent and parent.template != template:
             self.add_error('parent_item', ValidationError(
                 _('Родительский пункт должен быть из того же шаблона.'), code='parent_template_mismatch'
             ))
        
        section = cleaned_data.get('section')
        if section and section.template != template:
            self.add_error('section', ValidationError(
                 _('Секция должна принадлежать тому же шаблону.'), code='section_template_mismatch'
            ))
        return cleaned_data


class BaseChecklistTemplateItemFormSet(BaseInlineFormSet):
    def get_form_kwargs(self, index):
        kwargs = super().get_form_kwargs(index)
        kwargs['parent_instance'] = self.instance
        return kwargs

    def clean(self):
        super().clean()
        if any(self.errors):
            return

        orders_in_sections = {}
        for i, form in enumerate(self.forms):
            if not form.is_valid() or not form.cleaned_data or self._should_delete_form(form):
                continue

            order = form.cleaned_data.get('order')
            section = form.cleaned_data.get('section')
            section_id = section.id if section else None

            if order is None: continue

            order_key = (section_id, order)
            if order_key in orders_in_sections:
                 error_msg = _("Порядок '%(order)s' уже используется для другого пункта %(section_info)s в этом шаблоне.") % {
                         'order': order,
                         'section_info': f"в секции '{section.title}'" if section else _("без секции")
                     }
                 form.add_error('order', ValidationError(error_msg, code='duplicate_order_in_section'))
            else:
                 orders_in_sections[order_key] = i


ChecklistTemplateItemFormSet = inlineformset_factory(
    ChecklistTemplate, ChecklistTemplateItem,
    form=ChecklistTemplateItemForm,
    formset=BaseChecklistTemplateItemFormSet,
    fields=('section', 'order', 'item_text', 'answer_type', 'target_point', 'help_text', 'default_value', 'parent_item'),
    extra=1, min_num=0, validate_min=False,
    can_delete=True, can_order=False
)


class ChecklistResultForm(forms.ModelForm):
    template_item_display = forms.CharField(label=_("Пункт"), required=False, widget=forms.Textarea(attrs={'readonly': True, 'rows': 2, 'class': READONLY_TEXTAREA_CLASSES}))
    template_item_point_display = forms.CharField(label="", required=False, widget=forms.TextInput(attrs={'readonly': True, 'class': READONLY_INPUT_CLASSES}))
    help_text_display = forms.CharField(label="", required=False, widget=forms.Textarea(attrs={'readonly': True, 'rows': 1, 'class': f'{READONLY_TEXTAREA_CLASSES} text-gray-500 italic text-xs p-0 mb-1 mt-0.5'}))

    class Meta:
        model = ChecklistResult
        fields = ['status', 'comments', 'is_corrected',
                  'value', 'numeric_value', 'boolean_value', 'date_value', 'datetime_value', 'time_value',
                  'file_attachment', 'media_url']
        widgets = {
            'value': forms.HiddenInput(),
            'numeric_value': forms.HiddenInput(),
            'boolean_value': forms.HiddenInput(),
            'date_value': forms.HiddenInput(),
            'datetime_value': forms.HiddenInput(),
            'time_value': forms.HiddenInput(),
            'file_attachment': forms.HiddenInput(),
            'media_url': forms.HiddenInput(),
            'status': ChecklistItemStatusRadioSelect(attrs={'class': STATUS_RADIO_WRAPPER_CLASSES}),
            'comments': forms.Textarea(attrs={'rows': 1, 'class': TEXTAREA_CLASSES + ' text-sm py-1 mt-1', 'placeholder': _('Комментарий (если Не OK)...')}),
            'is_corrected': forms.CheckboxInput(attrs={'class': CHECKBOX_CLASSES + ' ml-2'}),
        }
        labels = {
             'status': _("Результат"),
             'comments': _("Комментарий"),
             'is_corrected': _("Исправлено"),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        instance = self.instance

        if instance and instance.template_item:
            item = instance.template_item
            self.fields['template_item_display'].initial = item.item_text
            if item.target_point:
                 self.fields['template_item_point_display'].initial = f"({_('Точка')}: {item.target_point.name})"      
            if item.help_text:
                 self.fields['help_text_display'].initial = item.help_text

            answer_type = item.answer_type
            field_name_to_use = None
            widget_to_use = None
            label_text = item.item_text
            input_attrs = {'class': TEXT_INPUT_CLASSES + ' text-sm'}

            if answer_type == AnswerType.TEXT:
                field_name_to_use = 'value'
                widget_to_use = forms.Textarea(attrs={**input_attrs, 'rows': 2, 'placeholder': _('Введите текст...')})
            elif answer_type in [AnswerType.SCALE_1_4, AnswerType.SCALE_1_5]:
                field_name_to_use = 'numeric_value'
                choices = [(str(i), str(i)) for i in range(1, 5 if answer_type == AnswerType.SCALE_1_4 else 6)]
                widget_to_use = forms.RadioSelect(choices=choices, attrs={'class': STATUS_RADIO_WRAPPER_CLASSES})
                label_text = _("Оценка")
            elif answer_type in [AnswerType.YES_NO, AnswerType.YES_NO_MEH]:
                 field_name_to_use = 'value'
                 choices = [('yes', _('Да')), ('no', _('Нет'))]
                 if answer_type == AnswerType.YES_NO_MEH:
                      choices.insert(1, ('yes_no_meh', _('Не очень')))
                 widget_to_use = forms.RadioSelect(choices=choices, attrs={'class': STATUS_RADIO_WRAPPER_CLASSES})
                 label_text = _("Ответ")
            elif answer_type == AnswerType.NUMBER:
                field_name_to_use = 'numeric_value'
                widget_to_use = forms.NumberInput(attrs={**input_attrs, 'class': input_attrs['class'] + ' w-32', 'placeholder': _('Число')})
                label_text = _("Числовое значение")
            elif answer_type == AnswerType.DATE:
                field_name_to_use = 'date_value'
                widget_to_use = forms.DateInput(attrs={**input_attrs, 'type': 'date', 'class': input_attrs['class'] + ' w-auto flatpickr-perform-date'})
                label_text = _("Дата")
            elif answer_type == AnswerType.DATETIME:
                field_name_to_use = 'datetime_value'
                widget_to_use = forms.DateTimeInput(attrs={**input_attrs, 'type': 'datetime-local', 'class': input_attrs['class'] + ' w-auto flatpickr-perform-datetime'})
                label_text = _("Дата и время")
            elif answer_type == AnswerType.TIME:
                field_name_to_use = 'time_value'
                widget_to_use = forms.TimeInput(attrs={**input_attrs, 'type': 'time', 'class': input_attrs['class'] + ' w-auto flatpickr-perform-time'})
                label_text = _("Время")
            elif answer_type == AnswerType.BOOLEAN:
                 field_name_to_use = 'boolean_value'
                 widget_to_use = forms.RadioSelect(choices=[(True, _('Да')), (False, _('Нет'))], attrs={'class': STATUS_RADIO_WRAPPER_CLASSES})
                 label_text = _("Да/Нет")
            elif answer_type == AnswerType.FILE:
                 field_name_to_use = 'file_attachment'
                 widget_to_use = forms.ClearableFileInput(attrs={'class': FILE_INPUT_CLASSES})
                 label_text = _("Файл")
            elif answer_type == AnswerType.URL:
                 field_name_to_use = 'media_url'
                 widget_to_use = forms.URLInput(attrs={**input_attrs, 'placeholder': 'https://example.com'})
                 label_text = _("Ссылка (URL)")

            if field_name_to_use and field_name_to_use in self.fields:
                 self.fields[field_name_to_use].widget = widget_to_use
                 self.fields[field_name_to_use].label = label_text
                 self.fields[field_name_to_use].required = False
                 field_initial_value = getattr(instance, field_name_to_use, None)
                 if field_name_to_use == 'boolean_value' and isinstance(widget_to_use, forms.RadioSelect):
                     if field_initial_value is True: self.fields[field_name_to_use].initial = 'True'
                     elif field_initial_value is False: self.fields[field_name_to_use].initial = 'False'
                     else: self.fields[field_name_to_use].initial = None
                 else:
                    self.fields[field_name_to_use].initial = field_initial_value


            self.fields['status'].required = True
            self.fields['status'].empty_label = None

            ordered_fields = [
                 'template_item_display', 'template_item_point_display', 'help_text_display',
                 'status',
                 'comments', 'is_corrected',
             ]
            if field_name_to_use:
                 ordered_fields.insert(ordered_fields.index('comments'), field_name_to_use)

            self.order_fields(ordered_fields)
        else:
             logger.error("ChecklistResultForm initialized without a valid instance or template_item.")


    def clean(self):
        cleaned_data = super().clean()
        instance = self.instance
        if not instance or not instance.template_item:
             return cleaned_data

        item = instance.template_item
        status = cleaned_data.get('status')
        comments = cleaned_data.get('comments', '').strip()

        if status == ChecklistItemStatus.NOT_OK and not comments:
             self.add_error('comments', ValidationError(
                 _('Комментарий обязателен, если статус "%(status_name)s".') % {'status_name': ChecklistItemStatus.NOT_OK.label},
                 code='comment_required_for_not_ok'
             ))

        correct_value_field = instance.primary_value_field_name

        if correct_value_field == 'boolean_value' and isinstance(self.fields.get('boolean_value', {}).widget, forms.RadioSelect):
             submitted_str_value = cleaned_data.get('boolean_value')
             if submitted_str_value == 'True': cleaned_data['boolean_value'] = True
             elif submitted_str_value == 'False': cleaned_data['boolean_value'] = False
             else: cleaned_data['boolean_value'] = None


        all_value_fields = ['value', 'numeric_value', 'boolean_value', 'date_value', 'datetime_value', 'time_value', 'file_attachment', 'media_url']
        for field_key_loop in all_value_fields:
            if field_key_loop != correct_value_field:
                if field_key_loop == 'file_attachment':
                     if cleaned_data.get(f"{field_key_loop}-clear"):
                          cleaned_data[field_key_loop] = False
                     elif field_key_loop in cleaned_data and cleaned_data[field_key_loop] is None:
                          pass
                     elif field_key_loop in cleaned_data:
                          del cleaned_data[field_key_loop]
                elif field_key_loop in cleaned_data:
                    cleaned_data[field_key_loop] = None


        if status in [ChecklistItemStatus.OK, ChecklistItemStatus.NOT_OK]:
            value_provided = False
            if correct_value_field:
                submitted_value = cleaned_data.get(correct_value_field)

                if correct_value_field == 'file_attachment':
                    if submitted_value and submitted_value is not False: value_provided = True
                    elif submitted_value is False and instance and instance.file_attachment: value_provided = True
                    elif submitted_value is None and instance and instance.file_attachment: value_provided = True
                elif isinstance(submitted_value, str): value_provided = bool(submitted_value.strip())
                elif submitted_value is not None: value_provided = True

            value_types_requiring_input = AnswerType.values
            if item.answer_type in value_types_requiring_input and not value_provided:
                  primary_field_name_for_error = instance.primary_value_field_name
                  if primary_field_name_for_error and primary_field_name_for_error in self.fields:
                      self.add_error(primary_field_name_for_error, ValidationError(
                           _('Пожалуйста, предоставьте ответ для этого пункта.'), code='value_required_for_status'     
                      ))
                  else:
                       self.add_error(None, ValidationError(
                            _('Пункт "%(item_text)s" требует ответа.') % {'item_text': item.item_text}, code='value_required_general'
                       ))

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
        elif item.answer_type == AnswerType.NUMBER or item.answer_type in [AnswerType.SCALE_1_4, AnswerType.SCALE_1_5]:
            pass
        else:
            cleaned_data['numeric_value'] = None

        return cleaned_data


class BasePerformChecklistResultFormSet(BaseInlineFormSet):
    def get_form_kwargs(self, index):
        kwargs = super().get_form_kwargs(index)
        return kwargs

    def clean(self):
        super().clean()
        if any(self.errors):
             return


PerformChecklistResultFormSet = inlineformset_factory(
    Checklist, ChecklistResult,
    form=ChecklistResultForm,
    formset=BasePerformChecklistResultFormSet,
    fields=['status', 'comments', 'is_corrected', 'value', 'numeric_value', 'boolean_value', 'date_value', 'datetime_value', 'time_value', 'file_attachment', 'media_url'],
    extra=0,
    can_delete=False,
)

class ChecklistStatusUpdateForm(forms.ModelForm):
     class Meta:
         model = Checklist
         fields = ['status', 'approved_by', 'approved_at', 'notes']
         widgets = {
             'status': forms.Select(attrs={'class': SELECT_CLASSES, 'data-placeholder': _("Выберите статус...")}),
             'approved_by': forms.Select(attrs={'class': SELECT_CLASSES, 'data-placeholder': _("Выберите пользователя...")}),
             'approved_at': forms.DateTimeInput(attrs={'type': 'datetime-local', 'class': TEXT_INPUT_CLASSES + ' w-auto flatpickr-datetime'}),
             'notes': forms.Textarea(attrs={'rows': 3, 'class': TEXTAREA_CLASSES, 'placeholder': _("Причина изменения статуса или комментарий...")}),
         }
         labels = {
              'status': _("Новый статус"),
              'approved_by': _("Одобрено/Отклонено кем"),
              'approved_at': _("Время решения"),
              'notes': _("Примечание к решению"),
         }

     def __init__(self, *args, **kwargs):
         super().__init__(*args, **kwargs)
         self.fields['approved_by'].queryset = User.objects.filter(is_staff=True).order_by('username')
         self.fields['approved_by'].required = False
         self.fields['approved_at'].required = False

         if self.instance and self.instance.pk:
              self.instance._original_status = self.instance.status


     def clean(self):
         cleaned_data = super().clean()
         status = cleaned_data.get('status')
         approved_by = cleaned_data.get('approved_by')
         notes = cleaned_data.get('notes', '').strip()

         if status == ChecklistRunStatus.APPROVED:
             if not approved_by:
                 self.add_error('approved_by', ValidationError(_("При статусе 'Одобрено' необходимо указать, кем одобрено."), code='approved_by_required'))
         elif status == ChecklistRunStatus.REJECTED:
             if not approved_by:
                 self.add_error('approved_by', ValidationError(_("При статусе 'Отклонено' необходимо указать, кем принято решение."), code='rejected_by_required'))
             if not notes:
                 self.add_error('notes', ValidationError(_("При статусе 'Отклонено' необходимо указать причину в примечаниях."), code='notes_required_for_rejected'))

         return cleaned_data

     def save(self, commit=True):
         instance = super().save(commit=False)
         original_status = getattr(instance, '_original_status', None)

         if instance.status == ChecklistRunStatus.APPROVED and original_status != ChecklistRunStatus.APPROVED:
              if not instance.approved_at:
                  instance.approved_at = timezone.now()
              logger.debug(f"Checklist {instance.id} APPROVED at {instance.approved_at} by {instance.approved_by}")

         elif instance.status == ChecklistRunStatus.REJECTED and original_status != ChecklistRunStatus.REJECTED:
             if not instance.approved_at:
                  instance.approved_at = timezone.now()
             logger.debug(f"Checklist {instance.id} REJECTED at {instance.approved_at} by {instance.approved_by}")
         
         elif original_status in [ChecklistRunStatus.APPROVED, ChecklistRunStatus.REJECTED] and \
              instance.status not in [ChecklistRunStatus.APPROVED, ChecklistRunStatus.REJECTED]:
              instance.approved_by = None
              instance.approved_at = None
              logger.debug(f"Cleared approval fields for checklist {instance.id} as status changed from approved/rejected.")


         if instance.status in [ChecklistRunStatus.SUBMITTED, ChecklistRunStatus.APPROVED, ChecklistRunStatus.REJECTED]:
             if not instance.is_complete:
                  instance.is_complete = True
                  logger.info(f"Setting is_complete=True for checklist {instance.id} due to status update to final.")
             if instance.completion_time is None and instance.status == ChecklistRunStatus.SUBMITTED:
                  instance.completion_time = timezone.now()
                  logger.info(f"Setting completion_time for checklist {instance.id} on first submit.")


         if commit:
             instance.save()
         return instance