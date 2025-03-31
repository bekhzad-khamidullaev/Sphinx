# tasks/forms.py
import logging
import re
from datetime import timedelta

from crispy_forms.helper import FormHelper
from crispy_forms.layout import Layout, Fieldset, Row, Field, Submit, HTML
from crispy_forms.bootstrap import FormActions
from django import forms
from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _
from django.forms import modelformset_factory, inlineformset_factory
from django.utils import timezone

# Импорты моделей из текущего приложения tasks
from .models import (
    Task, TaskPhoto, Project, TaskCategory,
    TaskSubcategory, TaskComment
)
# Импорты моделей из приложения user_profiles (только то, что нужно для TaskForm)
from user_profiles.models import User, TaskUserRole # Убрали Team, Department

logger = logging.getLogger(__name__)

# --- Utility function --- (Можно вынести в отдельный utils.py, если используется в нескольких местах)
def add_common_attrs(field, placeholder=None, input_class="form-control"):
    attrs = field.widget.attrs
    current_classes = attrs.get('class', '')
    if input_class not in current_classes.split():
        attrs['class'] = f'{current_classes} {input_class}'.strip()
    if placeholder and 'placeholder' not in attrs:
        attrs["placeholder"] = placeholder
    field.widget.attrs.update(attrs)

# ==============================================================================
# Form for Project
# ==============================================================================
class ProjectForm(forms.ModelForm):
    class Meta:
        model = Project
        fields = ["name", "description", "start_date", "end_date"]
        widgets = {
            "name": forms.TextInput(attrs={'placeholder': _("Название проекта")}),
            "description": forms.Textarea(attrs={'rows': 4, 'placeholder': _("Детальное описание проекта")}),
            "start_date": forms.DateInput(attrs={"type": "date", 'class': 'form-control'}),
            "end_date": forms.DateInput(attrs={"type": "date", 'class': 'form-control'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.helper = FormHelper(self)
        self.helper.form_method = 'post'
        self.helper.form_tag = False
        self.helper.disable_csrf = True
        self.helper.layout = Layout(
            Field("name", css_class="mb-3"),
            Field("description", css_class="mb-3"),
            Row(
                 Field("start_date", wrapper_class="col-md-6"),
                 Field("end_date", wrapper_class="col-md-6"),
                 css_class="mb-3"
            ),
            # Кнопки добавляются в шаблоне
        )

# ==============================================================================
# Form for Task Category
# ==============================================================================
class TaskCategoryForm(forms.ModelForm):
    class Meta:
        model = TaskCategory
        fields = ["name", "description"]
        widgets = {
            'name': forms.TextInput(attrs={'placeholder': _("Название категории")}),
            'description': forms.Textarea(attrs={'rows': 3, 'placeholder': _("Описание (опционально)")}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.helper = FormHelper(self)
        self.helper.form_method = 'post'; self.helper.form_tag = False; self.helper.disable_csrf = True
        self.helper.layout = Layout( Field("name", css_class="mb-3"), Field("description", css_class="mb-3"), )

# ==============================================================================
# Form for Task Subcategory
# ==============================================================================
class TaskSubcategoryForm(forms.ModelForm):
    category = forms.ModelChoiceField(
        queryset=TaskCategory.objects.all().order_by('name'),
        label=_('Категория'),
        widget=forms.Select(attrs={'class': 'form-select select2-single', 'data-placeholder': _("Выберите категорию...")})
    )
    class Meta:
        model = TaskSubcategory
        fields = ["category", "name", "description"]
        widgets = {
            'name': forms.TextInput(attrs={'placeholder': _("Название подкатегории")}),
            'description': forms.Textarea(attrs={'rows': 3, 'placeholder': _("Описание (опционально)")}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.helper = FormHelper(self)
        self.helper.form_method = 'post'; self.helper.form_tag = False; self.helper.disable_csrf = True
        self.helper.layout = Layout( Field("category", css_class="mb-3"), Field("name", css_class="mb-3"), Field("description", css_class="mb-3"),)

# ==============================================================================
# Form for Task
# ==============================================================================
class TaskForm(forms.ModelForm):
    project = forms.ModelChoiceField(
         queryset=Project.objects.all().order_by('name'), label=_("Проект"),
         widget=forms.Select(attrs={'class': 'form-select select2-single', 'data-placeholder': _("Выберите проект...")}))
    category = forms.ModelChoiceField(
        queryset=TaskCategory.objects.all().order_by('name'), required=False, label=_("Категория"),
        widget=forms.Select(attrs={'class': 'form-select select2-single', 'data-placeholder': _("Выберите категорию (опционально)..."), 'id': 'id_task_category'}))
    subcategory = forms.ModelChoiceField(
        queryset=TaskSubcategory.objects.none(), required=False, label=_("Подкатегория"),
        widget=forms.Select(attrs={'class': 'form-select select2-single', 'data-placeholder': _("Сначала выберите категорию..."), 'id': 'id_task_subcategory'}))
    priority = forms.ChoiceField(
         choices=Task.TaskPriority.choices, label=_("Приоритет"), initial=Task.TaskPriority.MEDIUM,
         widget=forms.Select(attrs={'class': 'form-select'}))
    responsible_user = forms.ModelChoiceField(
        queryset=User.objects.filter(is_active=True).order_by('username'), required=False, label=_("Ответственный"),
        widget=forms.Select(attrs={'class': 'form-select select2-single', 'data-placeholder': _("Выберите ответственного...")}))
    executors = forms.ModelMultipleChoiceField(
        queryset=User.objects.filter(is_active=True).order_by('username'), required=False, label=_("Исполнители"),
        widget=forms.SelectMultiple(attrs={'class': 'select2-multiple', 'data-placeholder': _("Выберите исполнителей...")}))
    watchers = forms.ModelMultipleChoiceField(
        queryset=User.objects.filter(is_active=True).order_by('username'), required=False, label=_("Наблюдатели"),
        widget=forms.SelectMultiple(attrs={'class': 'select2-multiple', 'data-placeholder': _("Выберите наблюдателей...")}))

    class Meta:
        model = Task
        fields = [ "title", "description", "deadline", "start_date", "estimated_time", ]
        widgets = {
            "title": forms.TextInput(attrs={'placeholder': _("Краткое и понятное название задачи")}),
            "description": forms.Textarea(attrs={'rows': 5, 'placeholder': _("Подробное описание, шаги выполнения, ожидаемый результат...")}),
            "deadline": forms.DateTimeInput(attrs={"type": "datetime-local", 'class': 'form-control'}),
            "start_date": forms.DateTimeInput(attrs={"type": "datetime-local", 'class': 'form-control'}),
            "estimated_time": forms.TextInput(attrs={'placeholder': _('Напр., 1d 2h 30m или 45m'), 'class': 'form-control'}),
        }
        labels = { 'title': _('Название задачи'), 'description': _('Описание задачи'), 'deadline': _('Крайний срок'), 'start_date': _('Дата начала'), 'estimated_time': _('Планируемое время'), }

    def __init__(self, *args, **kwargs):
        instance = kwargs.get('instance'); initial_data = kwargs.get('initial', {})
        if instance and instance.pk:
            try:
                 roles_data = TaskUserRole.objects.filter(task=instance).values('user_id', 'role')
                 resp_id = next((r['user_id'] for r in roles_data if r['role'] == TaskUserRole.RoleChoices.RESPONSIBLE), None)
                 initial_data['responsible_user'] = resp_id; initial_data['executors'] = [r['user_id'] for r in roles_data if r['role'] == TaskUserRole.RoleChoices.EXECUTOR]; initial_data['watchers'] = [r['user_id'] for r in roles_data if r['role'] == TaskUserRole.RoleChoices.WATCHER]
                 kwargs['initial'] = initial_data
                 logger.debug(f"TaskForm Init: Initial roles set for task {instance.pk}: {initial_data}")
            except Exception as e: logger.error(f"Error fetching initial roles for task {instance.pk}: {e}")
        super().__init__(*args, **kwargs)
        self.helper = FormHelper(self); self.helper.form_method = 'post'; self.helper.form_tag = False; self.helper.disable_csrf = True
        self.helper.layout = Layout(
            Fieldset( _('Основная информация'), Field('project'), Field('title'), Field('description'), Row( Field('category', wrapper_class='col-md-6'), Field('subcategory', wrapper_class='col-md-6'), css_class='mb-3'), css_class='border-b border-gray-200 dark:border-dark-600 pb-4 mb-4' ),
            Fieldset( _('Участники'), Field('responsible_user', css_class='mb-3'), Field('executors', css_class='mb-3'), Field('watchers', css_class='mb-3'), css_class='border-b border-gray-200 dark:border-dark-600 pb-4 mb-4' ),
            Fieldset( _('Сроки и планирование'), Row( Field('priority', wrapper_class='col-md-4'), Field('start_date', wrapper_class='col-md-4'), Field('deadline', wrapper_class='col-md-4'), css_class='mb-3'), Row( Field('estimated_time', wrapper_class='col-md-4'), HTML('<div class="col-md-8"></div>'), css_class='mb-3')))
        category_id = None
        if 'category' in self.data: category_id = self.data.get('category')
        elif instance and instance.category_id: category_id = instance.category_id
        if category_id:
             try: self.fields['subcategory'].queryset = TaskSubcategory.objects.filter(category_id=category_id).order_by('name'); self.fields['subcategory'].widget.attrs.pop('disabled', None)
             except (ValueError, TypeError): self.fields['subcategory'].queryset = TaskSubcategory.objects.none(); self.fields['subcategory'].widget.attrs['disabled'] = True
        else: self.fields['subcategory'].queryset = TaskSubcategory.objects.none(); self.fields['subcategory'].widget.attrs['disabled'] = True

    def clean_estimated_time(self):
        duration_str = self.cleaned_data.get('estimated_time');
        if isinstance(duration_str, timedelta): return duration_str
        if not duration_str: return None
        pattern = re.compile(r'((?P<days>\d+)\s*d)?\s*((?P<hours>\d+)\s*h)?\s*((?P<minutes>\d+)\s*m)?'); match = pattern.match(duration_str.lower().strip())
        if not match or not match.group(0):
             if duration_str.isdigit():
                 minutes = int(duration_str)
                 if minutes > 0: return timedelta(minutes=minutes)
             raise ValidationError(_("Неверный формат оценки времени. Используйте, например, '1d 2h 30m', '2h', '45m' или просто число минут."))
        parts = match.groupdict(); time_params = {}
        if parts.get('days'): time_params['days'] = int(parts['days'])
        if parts.get('hours'): time_params['hours'] = int(parts['hours'])
        if parts.get('minutes'): time_params['minutes'] = int(parts['minutes'])
        if not time_params: raise ValidationError(_("Укажите хотя бы одно значение времени (d, h, m)."))
        try: duration = timedelta(**time_params); assert duration.total_seconds() > 0 or ValidationError(_("Оценка времени должна быть положительной.")); return duration
        except ValueError: raise ValidationError(_("Некорректные значения времени."))

    def save(self, commit=True):
        task = super().save(commit=False);
        if commit: task.save(); self._save_roles(task)
        return task

    def _save_roles(self, task):
        TaskUserRole.objects.filter( task=task, role__in=[TaskUserRole.RoleChoices.RESPONSIBLE, TaskUserRole.RoleChoices.EXECUTOR, TaskUserRole.RoleChoices.WATCHER] ).delete()
        roles_to_create = []; responsible = self.cleaned_data.get('responsible_user'); executors = self.cleaned_data.get('executors', User.objects.none()); watchers = self.cleaned_data.get('watchers', User.objects.none()); primary_users = set()
        if responsible: roles_to_create.append(TaskUserRole(task=task, user=responsible, role=TaskUserRole.RoleChoices.RESPONSIBLE)); primary_users.add(responsible)
        for user in executors:
             if user not in primary_users: roles_to_create.append(TaskUserRole(task=task, user=user, role=TaskUserRole.RoleChoices.EXECUTOR)); primary_users.add(user)
        for user in watchers:
            if user not in primary_users:
                 if not any(r.user == user and r.role == TaskUserRole.RoleChoices.WATCHER for r in roles_to_create): roles_to_create.append(TaskUserRole(task=task, user=user, role=TaskUserRole.RoleChoices.WATCHER))
        if roles_to_create:
            try: TaskUserRole.objects.bulk_create(roles_to_create, ignore_conflicts=True); logger.info(f"Saved roles for task {task.id}. Count: {len(roles_to_create)}")
            except Exception as e: logger.error(f"Error saving roles for task {task.id}: {e}")

# ==============================================================================
# Form for Task Photo
# ==============================================================================
class TaskPhotoForm(forms.ModelForm):
    class Meta:
        model = TaskPhoto
        fields = ["photo", "description"]
        widgets = {
             'description': forms.Textarea(attrs={'rows': 2, 'placeholder': _("Краткое описание фото (опционально)")}),
             'photo': forms.ClearableFileInput(attrs={'class': 'form-control'}),
        }
        labels = { 'photo': _('Файл фото'), 'description': _('Описание фото'), }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

# ==============================================================================
# Form for Task Comment
# ==============================================================================
class TaskCommentForm(forms.ModelForm):
    class Meta:
        model = TaskComment
        fields = ['text']
        widgets = {
            'text': forms.Textarea(

                attrs={
                    'rows': 3,
                    'placeholder': _("Введите ваш комментарий..."),
                    'class': 'form-textarea mt-1 block w-full rounded-md border-gray-300 shadow-sm focus:border-blue-500 focus:ring-blue-500 dark:bg-dark-600 dark:border-dark-500 dark:text-gray-200 sm:text-sm',
                    'aria-label': _("Текст комментария") # Добавляем aria-label СЮДА
                }
                # --- КОНЕЦ ИСПРАВЛЕНИЯ ---
            )
        }
        labels = {
            'text': '', # Скрываем стандартный label
        }