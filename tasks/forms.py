# tasks/forms.py
# -*- coding: utf-8 -*-

import logging
import re
from datetime import timedelta
from django.utils import timezone
from django import forms
from django.urls import reverse_lazy
from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _
from django.db import transaction
from crispy_forms.helper import FormHelper
from crispy_forms.layout import Layout, Fieldset, Row, Field
from django_select2.forms import (
    Select2Widget, Select2MultipleWidget,
    ModelSelect2Widget, ModelSelect2MultipleWidget
)

from .models import Task, TaskPhoto, Project, TaskCategory, TaskSubcategory, TaskComment
from user_profiles.models import User, TaskUserRole # Assuming these are available

logger = logging.getLogger(__name__)

BASE_INPUT_CLASSES = "block w-full px-4 py-2 border border-gray-300 rounded-lg shadow-sm focus:ring focus:ring-blue-500 focus:border-blue-500 focus:outline-none dark:bg-dark-700 dark:border-dark-600 dark:text-gray-200 dark:placeholder-gray-500 transition duration-150 ease-in-out"
TEXT_INPUT_CLASSES = f"form-input {BASE_INPUT_CLASSES}"
TEXTAREA_CLASSES = f"form-textarea {BASE_INPUT_CLASSES}"
SELECT_CLASSES = f"form-select {BASE_INPUT_CLASSES}"
DATE_INPUT_CLASSES = f"form-input {BASE_INPUT_CLASSES} flatpickr-date" # Add a class for JS date picker
DATETIME_INPUT_CLASSES = f"form-input {BASE_INPUT_CLASSES} flatpickr-datetime" # Add a class for JS datetime picker
FILE_INPUT_CLASSES = "form-control block w-full text-sm text-gray-900 border border-gray-300 rounded-lg cursor-pointer bg-gray-50 dark:text-gray-400 focus:outline-none dark:bg-dark-600 dark:border-dark-500 dark:placeholder-gray-400 file:mr-4 file:py-2 file:px-4 file:rounded-lg file:border-0 file:text-sm file:font-semibold file:bg-blue-50 file:text-blue-700 hover:file:bg-blue-100 dark:file:bg-dark-500 dark:file:text-gray-300 dark:hover:file:bg-dark-400 transition duration-150 ease-in-out"
SELECT2_SINGLE_CLASS = "select2-single-widget"
SELECT2_MULTIPLE_CLASS = "select2-multiple-widget"
USER_AUTOCOMPLETE_URL_NAME = 'tasks:user_autocomplete'


class ProjectForm(forms.ModelForm):
    class Meta:
        model = Project
        fields = ["name", "description", "start_date", "end_date"]
        widgets = {
            "name": forms.TextInput(attrs={'class': TEXT_INPUT_CLASSES, 'placeholder': _('Введите название проекта')}),
            "description": forms.Textarea(attrs={'rows': 4, 'class': TEXTAREA_CLASSES, 'placeholder': _('Добавьте описание проекта')}),
            "start_date": forms.DateInput(format='%Y-%m-%d', attrs={"type": "date", 'class': DATE_INPUT_CLASSES, 'placeholder': _('ГГГГ-ММ-ДД')}),
            "end_date": forms.DateInput(format='%Y-%m-%d', attrs={"type": "date", 'class': DATE_INPUT_CLASSES, 'placeholder': _('ГГГГ-ММ-ДД')}),
        }
        labels = {"name": _("Название проекта"), "description": _("Описание"), "start_date": _("Дата начала"), "end_date": _("Дата завершения")}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.helper = FormHelper(self)
        self.helper.form_method = 'post'
        self.helper.form_tag = False
        self.helper.disable_csrf = True

    def clean(self):
        cleaned_data = super().clean()
        start_date = cleaned_data.get("start_date")
        end_date = cleaned_data.get("end_date")
        if not start_date: # Default start_date if not provided
             cleaned_data['start_date'] = timezone.now().date()
             start_date = cleaned_data['start_date']

        if start_date and end_date and end_date < start_date:
            self.add_error('end_date', ValidationError(_("Дата завершения не может быть раньше даты начала.")))
        return cleaned_data

class TaskCategoryForm(forms.ModelForm):
    class Meta:
        model = TaskCategory
        fields = ["name", "description"]
        widgets = {
            "name": forms.TextInput(attrs={'class': TEXT_INPUT_CLASSES, 'placeholder': _('Название категории')}),
            "description": forms.Textarea(attrs={"rows": 3, 'class': TEXTAREA_CLASSES, 'placeholder': _('Описание категории')}),
        }
        labels = {"name": _("Название категории"), "description": _("Описание")}

class TaskSubcategoryForm(forms.ModelForm):
    category = forms.ModelChoiceField(
        queryset=TaskCategory.objects.all().order_by("name"), label=_("Родительская категория"),
        widget=Select2Widget(attrs={'data-placeholder': _("Выберите категорию..."), 'class': f'{SELECT_CLASSES} {SELECT2_SINGLE_CLASS}'})
    )
    class Meta:
        model = TaskSubcategory
        fields = ["category", "name", "description"]
        widgets = {
            "name": forms.TextInput(attrs={'class': TEXT_INPUT_CLASSES, 'placeholder': _('Название подкатегории')}),
            "description": forms.Textarea(attrs={"rows": 3, 'class': TEXTAREA_CLASSES, 'placeholder': _('Описание подкатегории')}),
        }
        labels = {"name": _("Название подкатегории"), "description": _("Описание")}

    def clean(self):
        cleaned_data = super().clean()
        category = cleaned_data.get('category')
        name = cleaned_data.get('name')
        instance_pk = self.instance.pk if self.instance else None

        if category and name:
            query = TaskSubcategory.objects.filter(category=category, name__iexact=name)
            if instance_pk:
                query = query.exclude(pk=instance_pk)
            if query.exists():
                self.add_error('name', ValidationError(_("Подкатегория с таким названием уже существует в выбранной категории.")))
        return cleaned_data


class TaskForm(forms.ModelForm):
    title = forms.CharField(label=_('Название задачи'), max_length=255, widget=forms.TextInput(attrs={'class': TEXT_INPUT_CLASSES, 'placeholder': _('Название задачи')}))
    description = forms.CharField(label=_('Описание задачи'), required=False, widget=forms.Textarea(attrs={'class': TEXTAREA_CLASSES, 'rows': 5, 'placeholder': _('Описание задачи')}))
    deadline = forms.DateTimeField(label=_('Срок выполнения'), required=False, widget=forms.DateTimeInput(format='%Y-%m-%dT%H:%M', attrs={'type': 'datetime-local', 'class': DATETIME_INPUT_CLASSES}))
    estimated_time = forms.CharField(label=_('Планируемое время'), required=False, help_text=_("Формат: 'Xd Yh Zm'. Пример: 1d 2h 30m"), widget=forms.TextInput(attrs={'class': TEXT_INPUT_CLASSES, 'placeholder': _('Напр., 2h 30m')}))
    priority = forms.ChoiceField(label=_('Приоритет'), choices=[], widget=forms.Select(attrs={'class': SELECT_CLASSES}))
    project = forms.ModelChoiceField(label=_('Проект'), queryset=Project.objects.all().order_by("name"), required=True, widget=Select2Widget(attrs={'data-placeholder': _('Выберите проект...'), 'class': f'{SELECT_CLASSES} {SELECT2_SINGLE_CLASS}'}))
    category = forms.ModelChoiceField(label=_('Категория'), queryset=TaskCategory.objects.all().order_by("name"), required=False, widget=Select2Widget(attrs={'id': 'id_category', 'data-placeholder': _('Выберите категорию...'), 'class': f'{SELECT_CLASSES} {SELECT2_SINGLE_CLASS}'}))
    subcategory = forms.ModelChoiceField(label=_('Подкатегория'), queryset=TaskSubcategory.objects.none(), required=False, widget=Select2Widget(attrs={'id': 'id_subcategory', 'disabled': True, 'data-placeholder': _('Сначала выберите категорию...'), 'class': f'{SELECT_CLASSES} {SELECT2_SINGLE_CLASS}'}))
    start_date = forms.DateField(label=_('Дата начала'), required=True, widget=forms.DateInput(format='%Y-%m-%d', attrs={'type': 'date', 'class': DATE_INPUT_CLASSES}))

    if User and TaskUserRole: # Ensure models are available
        user_select_widget_attrs = {
            'data-ajax--url': reverse_lazy(USER_AUTOCOMPLETE_URL_NAME),
            'data-ajax--cache': 'true', 'data-ajax--delay': 250,
            'data-minimum-input-length': 1,
            'class': f'{SELECT_CLASSES} model-select2-widget', # Base class for all model select2
            'data-theme': 'bootstrap-5' # Example theme
        }
        responsible_user = forms.ModelChoiceField(
            label=_('Ответственный'), queryset=User.objects.filter(is_active=True), required=True,
            widget=ModelSelect2Widget(model=User, search_fields=['username__icontains', 'first_name__icontains', 'last_name__icontains', 'email__icontains'],
                                     attrs={**user_select_widget_attrs, 'data-placeholder': _('Выберите ответственного...'), 'data-project-field': 'id_project'})
        )
        executors = forms.ModelMultipleChoiceField(
            label=_('Исполнители'), queryset=User.objects.filter(is_active=True), required=False,
            widget=ModelSelect2MultipleWidget(model=User, search_fields=['username__icontains', 'first_name__icontains', 'last_name__icontains', 'email__icontains'],
                                              attrs={**user_select_widget_attrs, 'data-placeholder': _('Выберите исполнителей...'), 'data-project-field': 'id_project'})
        )
        watchers = forms.ModelMultipleChoiceField(
            label=_('Наблюдатели'), queryset=User.objects.filter(is_active=True), required=False,
            widget=ModelSelect2MultipleWidget(model=User, search_fields=['username__icontains', 'first_name__icontains', 'last_name__icontains', 'email__icontains'],
                                             attrs={**user_select_widget_attrs, 'data-placeholder': _('Выберите наблюдателей...'), 'data-project-field': 'id_project'})
        )
    else: # Fallback if User/TaskUserRole not available
        responsible_user = forms.CharField(label=_('Ответственный'), required=True, disabled=True, help_text=_("Модуль пользователей недоступен."))
        executors = forms.CharField(label=_('Исполнители'), required=False, disabled=True, help_text=_("Модуль пользователей недоступен."))
        watchers = forms.CharField(label=_('Наблюдатели'), required=False, disabled=True, help_text=_("Модуль пользователей недоступен."))


    class Meta:
        model = Task
        fields = ["title", "description", "priority", "project", "category", "subcategory", "start_date", "deadline", "estimated_time"]
        # Status is typically managed via actions or workflow, not direct form input unless specified.
        # created_by is set in save method.

    def __init__(self, *args, **kwargs):
        self.request_user = kwargs.pop('user', None)
        instance = kwargs.get("instance")
        initial_data = kwargs.get("initial", {})

        if instance and instance.pk and User and TaskUserRole:
            roles_data = TaskUserRole.objects.filter(task=instance).values_list("user_id", "role")
            initial_data.setdefault("responsible_user", next((uid for uid, r in roles_data if r == TaskUserRole.RoleChoices.RESPONSIBLE), None))
            initial_data.setdefault("executors", [uid for uid, r in roles_data if r == TaskUserRole.RoleChoices.EXECUTOR])
            initial_data.setdefault("watchers", [uid for uid, r in roles_data if r == TaskUserRole.RoleChoices.WATCHER])
        kwargs["initial"] = initial_data
        super().__init__(*args, **kwargs)

        if hasattr(Task, 'TaskPriority'):
            self.fields['priority'].choices = Task.TaskPriority.choices
            if not self.initial.get('priority') and not (instance and instance.priority):
                self.fields['priority'].initial = Task.TaskPriority.MEDIUM
        
        if not self.initial.get('start_date') and not (instance and instance.start_date):
            self.fields['start_date'].initial = timezone.now().date()


        category_id = self.initial.get('category') or (instance and instance.category_id)
        if category_id:
            self.fields['subcategory'].queryset = TaskSubcategory.objects.filter(category_id=category_id).order_by('name')
            self.fields['subcategory'].widget.attrs.pop('disabled', None)
        else:
            self.fields['subcategory'].queryset = TaskSubcategory.objects.none()
            self.fields['subcategory'].widget.attrs['disabled'] = True

        self.helper = FormHelper(self)
        self.helper.form_method = 'post'
        self.helper.form_tag = False
        self.helper.disable_csrf = True
        self.helper.layout = Layout(
            Fieldset('', Field('title', css_class='mb-4'), Field('description', css_class='mb-4'), css_class='border-b border-gray-200 dark:border-dark-600 pb-6 mb-6'),
            Fieldset(_('Детали и классификация'),
                Row(Field('priority', wrapper_class='w-full md:w-1/2 px-2 mb-4'), Field('project', wrapper_class='w-full md:w-1/2 px-2 mb-4'), css_class='flex flex-wrap -mx-2'),
                Row(Field('category', wrapper_class='w-full md:w-1/2 px-2 mb-4'), Field('subcategory', wrapper_class='w-full md:w-1/2 px-2 mb-4'), css_class='flex flex-wrap -mx-2'),
                css_class='border-b border-gray-200 dark:border-dark-600 pb-6 mb-6'
            ),
            Fieldset(_('Сроки и оценка'),
                Row(Field('start_date', wrapper_class='w-full md:w-1/3 px-2 mb-4'), Field('deadline', wrapper_class='w-full md:w-1/3 px-2 mb-4'), Field('estimated_time', wrapper_class='w-full md:w-1/3 px-2 mb-4'), css_class='flex flex-wrap -mx-2'),
                css_class='border-b border-gray-200 dark:border-dark-600 pb-6 mb-6'
            ),
            Fieldset(_('Участники'), Field('responsible_user', css_class='mb-4'), Field('executors', css_class='mb-4'), Field('watchers', css_class='mb-4'))
        )

    def clean_estimated_time(self):
        duration_string = self.cleaned_data.get("estimated_time")
        if not duration_string: return None
        normalized_duration = duration_string.lower().replace(' ', '')
        pattern = re.compile(r"^(?:(?P<days>\d+)(?:d|д))?(?:(?P<hours>\d+)(?:h|ч))?(?:(?P<minutes>\d+)(?:m|м))?$")
        match = pattern.match(normalized_duration)
        if match and match.group(0):
            time_parameters = {k: int(v) for k, v in match.groupdict().items() if v is not None}
            if time_parameters: return timedelta(**time_parameters)
        raise ValidationError(_("Неверный формат времени. Используйте 'Xd Yh Zm'. Пример: '1d 2h 30m'."), code='invalid_timedelta')

    def clean(self):
        cleaned_data = super().clean()
        category = cleaned_data.get("category")
        subcategory = cleaned_data.get("subcategory")
        start_date = cleaned_data.get("start_date")
        deadline_dt = cleaned_data.get("deadline")

        if subcategory and not category: self.add_error('subcategory', _("Нельзя выбрать подкатегорию без категории."))
        elif subcategory and category and subcategory.category != category: self.add_error('subcategory', _("Подкатегория не принадлежит категории."))
        
        if start_date and deadline_dt and deadline_dt.date() < start_date:
            self.add_error('deadline', _("Срок выполнения не может быть раньше даты начала."))

        if User and TaskUserRole: # Check if models are available
            responsible = cleaned_data.get("responsible_user")
            executors = cleaned_data.get("executors") or User.objects.none()
            watchers = cleaned_data.get("watchers") or User.objects.none()
            if responsible:
                if hasattr(executors, '__iter__') and responsible in executors: self.add_error('executors', _("Ответственный не может быть исполнителем."))
                if hasattr(watchers, '__iter__') and responsible in watchers: self.add_error('watchers', _("Ответственный не может быть наблюдателем."))
        return cleaned_data

    @transaction.atomic
    def save(self, commit=True):
        task_instance = super().save(commit=False)
        if not task_instance.pk and self.request_user and hasattr(task_instance, 'created_by') and not task_instance.created_by_id:
            task_instance.created_by = self.request_user
        
        # Set _called_from_form_save to True before calling model's save if model's save checks this flag
        # This helps avoid double full_clean if model's save also calls it.
        # setattr(task_instance, '_called_from_form_save', True)

        if commit:
            task_instance.save() # This will call model's full_clean() if not flagged
            self.save_m2m() # For any direct M2M fields on the form, though roles are manual here

            if User and TaskUserRole: # Ensure models are available
                responsible = self.cleaned_data.get('responsible_user')
                executors = self.cleaned_data.get('executors') or User.objects.none()
                watchers = self.cleaned_data.get('watchers') or User.objects.none()
                
                current_roles = {role.user_id: role for role in TaskUserRole.objects.filter(task=task_instance)}
                target_roles_map = {} # user_id: role_type

                if responsible: target_roles_map[responsible.id] = TaskUserRole.RoleChoices.RESPONSIBLE
                for ex in executors:
                    if ex.id != (responsible.id if responsible else None): # Executor cannot be responsible
                        target_roles_map[ex.id] = TaskUserRole.RoleChoices.EXECUTOR
                for wa in watchers:
                    if wa.id != (responsible.id if responsible else None) and wa.id not in [ex.id for ex in executors]: # Watcher cannot be resp or exec
                         target_roles_map[wa.id] = TaskUserRole.RoleChoices.WATCHER
                
                roles_to_create = []
                roles_to_update = []
                roles_to_delete_pks = []

                for user_id, role_type in target_roles_map.items():
                    if user_id in current_roles:
                        if current_roles[user_id].role != role_type:
                            role_instance = current_roles[user_id]
                            role_instance.role = role_type
                            roles_to_update.append(role_instance)
                        del current_roles[user_id] # Remove from current_roles as it's handled
                    else:
                        roles_to_create.append(TaskUserRole(task=task_instance, user_id=user_id, role=role_type))
                
                roles_to_delete_pks = [role.pk for role in current_roles.values()]

                if roles_to_create: TaskUserRole.objects.bulk_create(roles_to_create, ignore_conflicts=False) # allow fail on conflict
                if roles_to_update: TaskUserRole.objects.bulk_update(roles_to_update, ['role'])
                if roles_to_delete_pks: TaskUserRole.objects.filter(pk__in=roles_to_delete_pks).delete()
            
        # if hasattr(task_instance, '_called_from_form_save'):
        #    delattr(task_instance, '_called_from_form_save')
        return task_instance

class TaskPhotoForm(forms.ModelForm):
    class Meta:
        model = TaskPhoto
        fields = ["photo", "description"]
        widgets = {
            "photo": forms.ClearableFileInput(attrs={"class": FILE_INPUT_CLASSES, 'accept': 'image/*'}),
            "description": forms.Textarea(attrs={"rows": 2, 'class': TEXTAREA_CLASSES, 'placeholder': _('Описание фото')}),
        }
        labels = {"photo": _("Файл фото"), "description": _("Описание фото")}

class TaskCommentForm(forms.ModelForm):
    class Meta:
        model = TaskComment
        fields = ["text"]
        widgets = {"text": forms.Textarea(attrs={"rows": 3, "placeholder": _("Ваш комментарий..."), "class": TEXTAREA_CLASSES})}
        labels = {"text": ""}