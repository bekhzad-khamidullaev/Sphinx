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
from crispy_forms.layout import Layout, Fieldset, Row, Column, Field, HTML, Submit
from django_select2.forms import (
    Select2Widget, Select2MultipleWidget,
    ModelSelect2Widget, ModelSelect2MultipleWidget
)

from .models import Task, TaskPhoto, Project, TaskCategory, TaskSubcategory, TaskComment, TaskAssignment
from django.contrib.auth import get_user_model
User = get_user_model()

logger = logging.getLogger(__name__)

BASE_INPUT_CLASSES = "block w-full px-3 py-2 border border-gray-300 rounded-md shadow-sm focus:ring-indigo-500 focus:border-indigo-500 sm:text-sm transition duration-150 ease-in-out dark:bg-dark-600 dark:border-dark-500 dark:text-gray-200 dark:focus:ring-indigo-400 dark:focus:border-indigo-400"
TEXT_INPUT_CLASSES = f"form-input {BASE_INPUT_CLASSES}"
TEXTAREA_CLASSES = f"form-textarea {BASE_INPUT_CLASSES}"
SELECT_CLASSES = f"form-select {BASE_INPUT_CLASSES}"
DATE_INPUT_CLASSES = f"form-input {BASE_INPUT_CLASSES} flatpickr-date"
DATETIME_INPUT_CLASSES = f"form-input {BASE_INPUT_CLASSES} flatpickr-datetime"
FILE_INPUT_CLASSES = "form-control block w-full text-sm text-gray-900 border border-gray-300 rounded-lg cursor-pointer bg-gray-50 focus:outline-none file:mr-4 file:py-2 file:px-4 file:rounded-lg file:border-0 file:text-sm file:font-semibold file:bg-blue-50 file:text-blue-700 hover:file:bg-blue-100 transition duration-150 ease-in-out dark:text-gray-300 dark:border-dark-500 dark:bg-dark-600 dark:file:bg-blue-800 dark:file:text-blue-300 dark:hover:file:bg-blue-700"
CHECKBOX_CLASSES = "form-checkbox h-5 w-5 text-indigo-600 rounded border-gray-300 focus:ring-indigo-500 dark:bg-dark-600 dark:border-dark-500 dark:checked:bg-indigo-500 dark:focus:ring-indigo-400"


USER_AUTOCOMPLETE_URL_NAME = 'tasks:user_autocomplete'

class CrispyFormMixin(forms.Form):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.helper = FormHelper(self)
        self.helper.form_method = 'post'
        self.helper.form_tag = False
        self.helper.disable_csrf = True

class ProjectForm(CrispyFormMixin, forms.ModelForm):
    class Meta:
        model = Project
        fields = ["name", "description", "owner", "start_date", "end_date", "is_active"]
        widgets = {
            "name": forms.TextInput(attrs={'class': TEXT_INPUT_CLASSES, 'placeholder': _('Введите название проекта')}),
            "description": forms.Textarea(attrs={'rows': 4, 'class': TEXTAREA_CLASSES, 'placeholder': _('Добавьте описание проекта')}),
            "owner": Select2Widget(attrs={'data-placeholder': _("Выберите владельца (необязательно)")}),
            "start_date": forms.DateInput(format='%Y-%m-%d', attrs={"type": "date", 'class': DATE_INPUT_CLASSES}),
            "end_date": forms.DateInput(format='%Y-%m-%d', attrs={"type": "date", 'class': DATE_INPUT_CLASSES}),
            "is_active": forms.CheckboxInput(attrs={'class': CHECKBOX_CLASSES}),
        }
        labels = {
            "name": _("Название проекта"), "description": _("Описание"),
            "start_date": _("Дата начала"), "end_date": _("Дата завершения"),
            "is_active": _("Проект активен"), "owner": _("Владелец проекта")
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.helper.layout = Layout(
            Fieldset(_("Основная информация"),'name', 'description', 'owner', 'is_active', css_class="mb-4 p-4 border rounded-lg border-gray-200 dark:border-dark-600"),
            Fieldset(_("Сроки проекта"), Row(Column('start_date', css_class='md:w-1/2'), Column('end_date', css_class='md:w-1/2')), css_class="mb-4 p-4 border rounded-lg border-gray-200 dark:border-dark-600"),
        )

    def clean(self):
        cleaned_data = super().clean()
        start_date = cleaned_data.get("start_date")
        end_date = cleaned_data.get("end_date")

        if not start_date and not (self.instance and self.instance.pk):
            cleaned_data['start_date'] = timezone.now().date()
            start_date = cleaned_data['start_date']

        if start_date and end_date and end_date < start_date:
            self.add_error('end_date', ValidationError(_("Дата завершения не может быть раньше даты начала.")))
        return cleaned_data

class TaskCategoryForm(CrispyFormMixin, forms.ModelForm):
    class Meta: model = TaskCategory; fields = ["name", "description"]
    widgets = {"name": forms.TextInput(attrs={'class': TEXT_INPUT_CLASSES}), "description": forms.Textarea(attrs={'rows': 2, 'class': TEXTAREA_CLASSES})}
    def __init__(self, *args, **kwargs): super().__init__(*args, **kwargs); self.helper.layout = Layout('name', 'description')

class TaskSubcategoryForm(CrispyFormMixin, forms.ModelForm):
    category = forms.ModelChoiceField(queryset=TaskCategory.objects.all().order_by("name"), label=_("Родительская категория"), widget=Select2Widget(attrs={'data-placeholder': _("Выберите категорию...")}))
    class Meta: model = TaskSubcategory; fields = ["category", "name", "description"]
    widgets = {"name": forms.TextInput(attrs={'class': TEXT_INPUT_CLASSES}), "description": forms.Textarea(attrs={'rows': 2, 'class': TEXTAREA_CLASSES})}
    def __init__(self, *args, **kwargs): super().__init__(*args, **kwargs); self.helper.layout = Layout('category', 'name', 'description')
    def clean(self):
        cleaned_data = super().clean(); category = cleaned_data.get('category'); name = cleaned_data.get('name')
        if category and name:
            query = TaskSubcategory.objects.filter(category=category, name__iexact=name)
            if self.instance and self.instance.pk: query = query.exclude(pk=self.instance.pk)
            if query.exists(): self.add_error('name', ValidationError(_("Подкатегория с таким названием уже существует в этой категории.")))
        return cleaned_data


class TaskForm(CrispyFormMixin, forms.ModelForm):
    project = forms.ModelChoiceField(label=_('Проект'), queryset=Project.objects.filter(is_active=True).order_by("name"), required=True, widget=Select2Widget(attrs={'data-placeholder': _('Выберите проект...')}))
    category = forms.ModelChoiceField(label=_('Категория'), queryset=TaskCategory.objects.all().order_by("name"), required=False, widget=Select2Widget(attrs={'id': 'id_category', 'data-placeholder': _('Выберите категорию (необязательно)')}))
    subcategory = forms.ModelChoiceField(label=_('Подкатегория'), queryset=TaskSubcategory.objects.none(), required=False, widget=Select2Widget(attrs={'id': 'id_subcategory', 'disabled': True, 'data-placeholder': _('Сначала выберите категорию')}))
    estimated_time = forms.CharField(label=_('Оценка времени'), required=False, help_text=_("Формат: 1d 2h 30m (d-дни, h-часы, m-минуты)"), widget=forms.TextInput(attrs={'class': TEXT_INPUT_CLASSES, 'placeholder': _('Напр., 1d 4h')}))

    _user_select_widget_common_attrs = {
        'data-ajax--url': reverse_lazy(USER_AUTOCOMPLETE_URL_NAME),
        'data-ajax--cache': 'true', 'data-ajax--delay': 250,
        'data-minimum-input-length': 1,
    }
    responsible_user = forms.ModelChoiceField(label=_('Ответственный'), queryset=User.objects.filter(is_active=True), required=False, widget=ModelSelect2Widget(model=User, search_fields=['username__icontains', 'first_name__icontains', 'last_name__icontains', 'email__icontains'], attrs={**_user_select_widget_common_attrs, 'id': 'id_responsible_user', 'data-placeholder': _('Выберите ответственного...')}))
    executors = forms.ModelMultipleChoiceField(label=_('Исполнители'), queryset=User.objects.filter(is_active=True), required=False, widget=ModelSelect2MultipleWidget(model=User, search_fields=['username__icontains', 'first_name__icontains', 'last_name__icontains', 'email__icontains'], attrs={**_user_select_widget_common_attrs, 'id': 'id_executors', 'data-placeholder': _('Добавьте исполнителей...')}))
    watchers = forms.ModelMultipleChoiceField(label=_('Наблюдатели'), queryset=User.objects.filter(is_active=True), required=False, widget=ModelSelect2MultipleWidget(model=User, search_fields=['username__icontains', 'first_name__icontains', 'last_name__icontains', 'email__icontains'], attrs={**_user_select_widget_common_attrs, 'id': 'id_watchers', 'data-placeholder': _('Добавьте наблюдателей...')}))

    class Meta:
        model = Task
        fields = ["project", "title", "description", "category", "subcategory", "status", "priority", "start_date", "due_date", "estimated_time"]
        widgets = {
            "title": forms.TextInput(attrs={'class': TEXT_INPUT_CLASSES, 'placeholder': _('Краткое и информативное название задачи')}),
            "description": forms.Textarea(attrs={'rows': 5, 'class': TEXTAREA_CLASSES, 'placeholder': _('Подробное описание...')}),
            "status": forms.Select(attrs={'class': SELECT_CLASSES}),
            "priority": forms.Select(attrs={'class': SELECT_CLASSES}),
            "start_date": forms.DateInput(format='%Y-%m-%d', attrs={'type': 'date', 'class': DATE_INPUT_CLASSES}),
            "due_date": forms.DateInput(format='%Y-%m-%d', attrs={'type': 'date', 'class': DATE_INPUT_CLASSES}),
        }

    def __init__(self, *args, **kwargs):
        self.request_user = kwargs.pop('user', None)
        instance = kwargs.get("instance")
        initial_data = kwargs.get("initial", {})
        if instance and instance.pk:
            assignments = TaskAssignment.objects.filter(task=instance).select_related('user')
            initial_data.setdefault("responsible_user", next((a.user for a in assignments if a.role == TaskAssignment.RoleChoices.RESPONSIBLE), None))
            initial_data.setdefault("executors", [a.user.pk for a in assignments if a.role == TaskAssignment.RoleChoices.EXECUTOR])
            initial_data.setdefault("watchers", [a.user.pk for a in assignments if a.role == TaskAssignment.RoleChoices.WATCHER])
        kwargs["initial"] = initial_data
        super().__init__(*args, **kwargs)
        if not self.initial.get('priority') and not (instance and instance.priority): self.fields['priority'].initial = Task.TaskPriority.MEDIUM
        if not self.initial.get('start_date') and not (instance and instance.start_date) and not (instance and instance.pk): self.fields['start_date'].initial = timezone.now().date()
        if not self.initial.get('status') and not (instance and instance.status) and not (instance and instance.pk): self.fields['status'].initial = Task.StatusChoices.BACKLOG

        category_id_from_data = self.data.get(self.add_prefix('category')) if self.is_bound else None
        category_id_from_initial = self.initial.get('category'); category_id_from_instance = instance.category_id if instance else None
        final_category_id = category_id_from_data or (category_id_from_initial.id if hasattr(category_id_from_initial, 'id') else category_id_from_initial) or category_id_from_instance
        if final_category_id:
            try: self.fields['subcategory'].queryset = TaskSubcategory.objects.filter(category_id=final_category_id).order_by('name'); self.fields['subcategory'].widget.attrs.pop('disabled', None)
            except (ValueError, TypeError): self.fields['subcategory'].queryset = TaskSubcategory.objects.none(); self.fields['subcategory'].widget.attrs['disabled'] = True
        else: self.fields['subcategory'].queryset = TaskSubcategory.objects.none(); self.fields['subcategory'].widget.attrs['disabled'] = True

        self.helper.layout = Layout(
            Fieldset(_('Основная информация'), Field('project'), Field('title'), Field('description'), css_class="mb-4 p-4 border rounded-lg border-gray-200 dark:border-dark-600"),
            Fieldset(_('Классификация и Детализация'), Row(Column(Field('category', wrapper_class="flex-grow"), css_class='md:w-1/2 pr-2'), Column(Field('subcategory', wrapper_class="flex-grow"), css_class='md:w-1/2 pl-2'), css_class="flex mb-4"), Row(Column(Field('status', wrapper_class="flex-grow"), css_class='md:w-1/2 pr-2'), Column(Field('priority', wrapper_class="flex-grow"), css_class='md:w-1/2 pl-2'), css_class="flex mb-4"), css_class="mb-4 p-4 border rounded-lg border-gray-200 dark:border-dark-600"),
            Fieldset(_('Сроки и Оценка'), Row(Column(Field('start_date', wrapper_class="flex-grow"), css_class='md:w-1/3 pr-2'), Column(Field('due_date', wrapper_class="flex-grow"), css_class='md:w-1/3 px-1'), Column(Field('estimated_time', wrapper_class="flex-grow"), css_class='md:w-1/3 pl-2'), css_class="flex mb-4"), css_class="mb-4 p-4 border rounded-lg border-gray-200 dark:border-dark-600"),
            Fieldset(_('Участники'), Field('responsible_user', css_class="mb-4"), Field('executors', css_class="mb-4"), Field('watchers', css_class="mb-4"), css_class="p-4 border rounded-lg border-gray-200 dark:border-dark-600")
        )

    def clean_estimated_time(self):
        duration_string = self.cleaned_data.get("estimated_time", "")
        if not duration_string.strip(): return None
        normalized_duration = duration_string.lower().replace(' ', '')
        days, hours, minutes = 0,0,0
        days_match = re.search(r"(\d+)d", normalized_duration); hours_match = re.search(r"(\d+)h", normalized_duration); minutes_match = re.search(r"(\d+)m", normalized_duration)
        if days_match: days = int(days_match.group(1)); normalized_duration = normalized_duration.replace(days_match.group(0), "")
        if hours_match: hours = int(hours_match.group(1)); normalized_duration = normalized_duration.replace(hours_match.group(0), "")
        if minutes_match: minutes = int(minutes_match.group(1)); normalized_duration = normalized_duration.replace(minutes_match.group(0), "")
        if normalized_duration: raise ValidationError(_("Неверный формат времени. Используйте 'Xd Yh Zm', например: 1d 2h 30m."), code='invalid_timedelta_format')
        if days == 0 and hours == 0 and minutes == 0:
            if duration_string.strip() and not (days_match or hours_match or minutes_match): raise ValidationError(_("Неверный формат времени. Укажите d, h, или m."), code='invalid_timedelta_units')
            return None
        return timedelta(days=days, hours=hours, minutes=minutes)

    def clean(self):
        cleaned_data = super().clean()
        category = cleaned_data.get("category"); subcategory = cleaned_data.get("subcategory")
        start_date = cleaned_data.get("start_date"); due_date = cleaned_data.get("due_date")
        if subcategory and not category: self.add_error('category', _("Необходимо выбрать категорию, если указана подкатегория."))
        elif subcategory and category and subcategory.category != category: self.add_error('subcategory', _("Выбранная подкатегория не принадлежит указанной категории."))
        if start_date and due_date and due_date < start_date: self.add_error('due_date', _("Срок выполнения не может быть раньше даты начала."))
        responsible = cleaned_data.get("responsible_user"); executors = cleaned_data.get("executors") or User.objects.none(); watchers = cleaned_data.get("watchers") or User.objects.none()
        if responsible and hasattr(executors, '__iter__') and responsible in executors: self.add_error('executors', _("Ответственный пользователь не может быть одновременно исполнителем."))
        if responsible and hasattr(watchers, '__iter__') and responsible in watchers: self.add_error('watchers', _("Ответственный пользователь не может быть одновременно наблюдателем."))
        if hasattr(executors, '__iter__') and hasattr(watchers, '__iter__'):
            common_users = set(executors) & set(watchers)
            if common_users: self.add_error(None, ValidationError(_("Пользователи %(users)s не могут быть одновременно исполнителями и наблюдателями.") % {'users': ", ".join(u.get_username() for u in common_users)}))
        return cleaned_data

    @transaction.atomic
    def save(self, commit=True):
        task_instance = super().save(commit=False)
        if not task_instance.pk and self.request_user and self.request_user.is_authenticated and not task_instance.created_by_id: task_instance.created_by = self.request_user
        setattr(task_instance, '_initiator_user_id', self.request_user.id if self.request_user and self.request_user.is_authenticated else None)
        setattr(task_instance, '_called_from_form_save', True)
        if commit:
            task_instance.save(); self.save_m2m()
            responsible_user = self.cleaned_data.get('responsible_user'); executor_users = self.cleaned_data.get('executors', User.objects.none()); watcher_users = self.cleaned_data.get('watchers', User.objects.none())
            current_assignments = TaskAssignment.objects.filter(task=task_instance); target_assignment_data = {}
            if responsible_user: target_assignment_data[(responsible_user.id, TaskAssignment.RoleChoices.RESPONSIBLE)] = True
            for user in executor_users:
                if user != responsible_user: target_assignment_data[(user.id, TaskAssignment.RoleChoices.EXECUTOR)] = True
            for user in watcher_users:
                if user != responsible_user and user not in executor_users: target_assignment_data[(user.id, TaskAssignment.RoleChoices.WATCHER)] = True
            if self.request_user and self.request_user.is_authenticated:
                creator_is_primary_assigned = (responsible_user == self.request_user) or (self.request_user in executor_users)
                if not creator_is_primary_assigned: target_assignment_data[(self.request_user.id, TaskAssignment.RoleChoices.REPORTER)] = True
            current_set_db = set((ca.user_id, ca.role) for ca in current_assignments); target_set_form = set(target_assignment_data.keys())
            to_delete_pks = [ca.pk for ca in current_assignments if (ca.user_id, ca.role) not in target_set_form]
            to_create_assignments = [ TaskAssignment(task=task_instance, user_id=user_id, role=role, assigned_by=(self.request_user if self.request_user.is_authenticated else None)) for user_id, role in target_set_form if (user_id, role) not in current_set_db ]
            if to_delete_pks: TaskAssignment.objects.filter(pk__in=to_delete_pks).delete()
            if to_create_assignments: TaskAssignment.objects.bulk_create(to_create_assignments, ignore_conflicts=True)
        if hasattr(task_instance, '_initiator_user_id'): delattr(task_instance, '_initiator_user_id')
        if hasattr(task_instance, '_called_from_form_save'): delattr(task_instance, '_called_from_form_save')
        return task_instance

class TaskPhotoForm(CrispyFormMixin, forms.ModelForm):
    class Meta: model = TaskPhoto; fields = ["photo", "description"]
    widgets = {"photo": forms.ClearableFileInput(attrs={"class": FILE_INPUT_CLASSES, 'accept': 'image/*'}), "description": forms.Textarea(attrs={"rows": 2, 'class': TEXTAREA_CLASSES, 'placeholder': _('Описание фото (необязательно)')})}
    def __init__(self, *args, **kwargs): super().__init__(*args, **kwargs); self.helper.form_tag = False

class TaskCommentForm(CrispyFormMixin, forms.ModelForm):
    class Meta: model = TaskComment; fields = ["text"]
    widgets = {"text": forms.Textarea(attrs={"rows": 3, "placeholder": _("Напишите комментарий..."), "class": TEXTAREA_CLASSES})}
    def __init__(self, *args, **kwargs): super().__init__(*args, **kwargs); self.helper.form_show_labels = False; self.helper.layout = Layout('text')