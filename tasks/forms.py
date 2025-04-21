# tasks/forms.py

import logging
import re
from datetime import timedelta

from django import forms
from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _
from django.utils import timezone
from django.db import transaction
from crispy_forms.helper import FormHelper
from crispy_forms.layout import Layout, Fieldset, Row, Field, HTML
from django_select2.forms import Select2Widget, Select2MultipleWidget


logger = logging.getLogger(__name__)
# Импортируем модели из текущего приложения .models
# Важно: импортируем только сами модели, без обращения к их атрибутам на уровне класса
from .models import Task, TaskPhoto, Project, TaskCategory, TaskSubcategory, TaskComment
# Импортируем User и TaskUserRole из user_profiles
try:
    from user_profiles.models import User, TaskUserRole
except ImportError:
    logger.error("Could not import User or TaskUserRole from user_profiles.models")
    User = None
    TaskUserRole = None


# --- Общие классы для стилизации ---
TEXT_INPUT_CLASSES = "form-input block w-full px-4 py-2 border border-gray-300 rounded-lg shadow-sm focus:ring focus:ring-blue-500 focus:border-blue-500 focus:outline-none dark:bg-dark-700 dark:border-dark-600 dark:text-gray-200 dark:placeholder-gray-500"
TEXTAREA_CLASSES = "form-textarea block w-full px-4 py-2 border border-gray-300 rounded-lg shadow-sm focus:ring focus:ring-blue-500 focus:border-blue-500 focus:outline-none dark:bg-dark-700 dark:border-dark-600 dark:text-gray-200 dark:placeholder-gray-500"
SELECT_CLASSES = "form-select block w-full px-4 py-2 border border-gray-300 rounded-lg shadow-sm focus:ring focus:ring-blue-500 focus:border-blue-500 focus:outline-none dark:bg-dark-700 dark:border-dark-600 dark:text-gray-200"
DATE_INPUT_CLASSES = "form-input block w-full px-4 py-2 border border-gray-300 rounded-lg shadow-sm focus:ring focus:ring-blue-500 focus:border-blue-500 focus:outline-none dark:bg-dark-700 dark:border-dark-600 dark:text-gray-200 dark:placeholder-gray-500 flatpickr"
DATETIME_INPUT_CLASSES = DATE_INPUT_CLASSES
FILE_INPUT_CLASSES = "form-control block w-full text-sm text-gray-900 border border-gray-300 rounded-lg cursor-pointer bg-gray-50 dark:text-gray-400 focus:outline-none dark:bg-dark-600 dark:border-dark-500 dark:placeholder-gray-400 file:mr-4 file:py-2 file:px-4 file:rounded-lg file:border-0 file:text-sm file:font-semibold file:bg-blue-50 file:text-blue-700 hover:file:bg-blue-100 dark:file:bg-dark-500 dark:file:text-gray-300 dark:hover:file:bg-dark-400"


# ============================================================================== #
# Project Form
# ============================================================================== #
class ProjectForm(forms.ModelForm):
    class Meta:
        model = Project
        fields = ["name", "description", "start_date", "end_date"]
        widgets = {
            "name": forms.TextInput(attrs={'class': TEXT_INPUT_CLASSES, 'placeholder': _('Название проекта')}),
            "description": forms.Textarea(attrs={'rows': 4, 'class': TEXTAREA_CLASSES, 'placeholder': _('Описание проекта')}),
            "start_date": forms.DateInput(attrs={"type": "date", 'class': DATE_INPUT_CLASSES}),
            "end_date": forms.DateInput(attrs={"type": "date", 'class': DATE_INPUT_CLASSES}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.helper = FormHelper(self)
        self.helper.form_method = 'post'
        self.helper.form_tag = False
        self.helper.disable_csrf = True


# ============================================================================== #
# Task Category Form
# ============================================================================== #
class TaskCategoryForm(forms.ModelForm):
    class Meta:
        model = TaskCategory
        fields = ["name", "description"]
        widgets = {
            "name": forms.TextInput(attrs={'class': TEXT_INPUT_CLASSES, 'placeholder': _('Название категории')}),
            "description": forms.Textarea(attrs={"rows": 3, 'class': TEXTAREA_CLASSES, 'placeholder': _('Описание категории')}),
        }


# ============================================================================== #
# Task Subcategory Form
# ============================================================================== #
class TaskSubcategoryForm(forms.ModelForm):
    category = forms.ModelChoiceField(
        queryset=TaskCategory.objects.all().order_by("name"),
        widget=Select2Widget(attrs={
            'data-placeholder': _("Выберите категорию..."),
            'class': SELECT_CLASSES
            })
    )

    class Meta:
        model = TaskSubcategory
        fields = ["category", "name", "description"]
        widgets = {
            "name": forms.TextInput(attrs={'class': TEXT_INPUT_CLASSES, 'placeholder': _('Название подкатегории')}),
            "description": forms.Textarea(attrs={"rows": 3, 'class': TEXTAREA_CLASSES, 'placeholder': _('Описание подкатегории')}),
        }


# ============================================================================== #
# Task Form
# ============================================================================== #
class TaskForm(forms.ModelForm):
    # Определяем поля без choices на уровне класса
    title = forms.CharField(
        label=_('Название'),
        widget=forms.TextInput(attrs={'class': TEXT_INPUT_CLASSES, 'placeholder': _('Введите название задачи')})
    )
    description = forms.CharField(
        label=_('Описание'),
        required=False,
        widget=forms.Textarea(attrs={'class': TEXTAREA_CLASSES, 'rows': 5, 'placeholder': _('Введите подробное описание задачи')})
    )
    # start_date = forms.DateField(
    #     label=_('Дата начала'),
    #     required=False,
    #     widget=forms.DateInput(format='%Y-%m-%d', attrs={'type': 'date', 'class': DATE_INPUT_CLASSES})
    # )
    deadline = forms.DateTimeField(
        label=_('Срок выполнения'),
        required=False,
        widget=forms.DateTimeInput(format='%Y-%m-%dT%H:%M', attrs={'type': 'datetime-local', 'class': DATETIME_INPUT_CLASSES})
    )
    estimated_time = forms.CharField(
        label=_('Планируемое время'),
        required=False,
        widget=forms.TextInput(attrs={'class': TEXT_INPUT_CLASSES, 'placeholder': _('Напр., 1d 2h 30m или 45m')})
    )
    project = forms.ModelChoiceField(
        label=_('Проект'),
        queryset=Project.objects.all().order_by("name"),
        required=False,
        widget=Select2Widget(attrs={'data-placeholder': _('Выберите проект...')})
    )
    category = forms.ModelChoiceField(
        label=_('Категория'),
        queryset=TaskCategory.objects.all().order_by("name"),
        required=False,
        widget=Select2Widget(attrs={'id': 'id_category', 'data-placeholder': _('Выберите категорию...')})
    )
    subcategory = forms.ModelChoiceField(
        label=_('Подкатегория'),
        queryset=TaskSubcategory.objects.none(),
        required=False,
        widget=Select2Widget(attrs={'id': 'id_subcategory', 'disabled': True, 'data-placeholder': _('Сначала выберите категорию...')})
    )
    # Определяем поле priority без choices
    priority = forms.ChoiceField(
        label=_('Приоритет'),
        # choices будут установлены в __init__
        widget=forms.Select(attrs={'class': SELECT_CLASSES})
    )

    responsible_user_queryset = User.objects.filter(is_active=True) if User else User.objects.none()
    responsible_user = forms.ModelChoiceField(
        label=_('Ответственный'),
        queryset=responsible_user_queryset,
        widget=Select2Widget(attrs={'data-placeholder': _('Выберите ответственного...')})
    )
    executors = forms.ModelMultipleChoiceField(
        label=_('Исполнители'),
        queryset=responsible_user_queryset,
        required=False,
        widget=Select2MultipleWidget(attrs={'data-placeholder': _('Выберите исполнителей...')})
    )
    watchers = forms.ModelMultipleChoiceField(
        label=_('Наблюдатели'),
        queryset=responsible_user_queryset,
        required=False,
        widget=Select2MultipleWidget(attrs={'data-placeholder': _('Выберите наблюдателей...')})
    )

    class Meta:
        model = Task
        fields = [
            "title", "description", "priority", "category", "subcategory",
            "project", "deadline", "estimated_time",
        ]

    def __init__(self, *args, **kwargs):
        self.request_user = kwargs.pop('user', None)
        instance = kwargs.get("instance")
        initial_data = kwargs.get("initial", {})

        if instance and instance.pk and TaskUserRole:
            roles_data = TaskUserRole.objects.filter(task=instance).values_list("user_id", "role")
            executors_ids = [uid for uid, role in roles_data if role == TaskUserRole.RoleChoices.EXECUTOR]
            watchers_ids = [uid for uid, role in roles_data if role == TaskUserRole.RoleChoices.WATCHER]
            responsible_id = next((uid for uid, role in roles_data if role == TaskUserRole.RoleChoices.RESPONSIBLE), None)
            initial_data.setdefault("responsible_user", responsible_id)
            initial_data.setdefault("executors", executors_ids)
            initial_data.setdefault("watchers", watchers_ids)

        kwargs["initial"] = initial_data
        super().__init__(*args, **kwargs) # Вызываем super().__init__

        try:
            # Проверяем наличие TaskPriority перед использованием
            if hasattr(Task, 'TaskPriority'):
                self.fields['priority'].choices = Task.TaskPriority.choices
                # Устанавливаем initial, если он не был передан
                if 'priority' not in initial_data and not (instance and instance.priority):
                     self.fields['priority'].initial = Task.TaskPriority.MEDIUM
            else:
                logger.error("Model Task has no attribute 'TaskPriority'. Priority field will be empty.")
                self.fields['priority'].choices = [('', '-------')] # Пустые choices, если нет TaskPriority
                self.fields['priority'].widget.attrs['disabled'] = True # Блокируем поле
        except Exception as e:
             logger.exception(f"Error setting choices for priority field: {e}")
             self.fields['priority'].choices = [('', '-------')]
             self.fields['priority'].widget.attrs['disabled'] = True
        # -------------------------------------------------------

        # Предзаполнение подкатегории, если есть категория
        category_id = self.initial.get('category') or (instance and instance.category_id)
        if category_id:
             try:
                 self.fields['subcategory'].queryset = TaskSubcategory.objects.filter(category_id=category_id).order_by('name')
                 self.fields['subcategory'].widget.attrs.pop('disabled', None)
             except TaskSubcategory.DoesNotExist:
                 self.fields['subcategory'].queryset = TaskSubcategory.objects.none()
             except Exception as e:
                  logger.error(f"Error setting subcategory queryset: {e}")
                  self.fields['subcategory'].queryset = TaskSubcategory.objects.none()
        else:
             self.fields['subcategory'].queryset = TaskSubcategory.objects.none()
             self.fields['subcategory'].widget.attrs['disabled'] = True


        # --- Настройка Crispy Forms ---
        self.helper = FormHelper(self)
        self.helper.form_method = 'post'
        self.helper.form_tag = False
        self.helper.disable_csrf = True
        self.helper.layout = Layout(
            Fieldset(
                _('Основная информация'),
                'title',
                'description',
                Row( Field('priority', wrapper_class='col-md-6'), Field('project', wrapper_class='col-md-6'),),
                Row( Field('category', wrapper_class='col-md-6'), Field('subcategory', wrapper_class='col-md-6'),)
            ),
            Fieldset(
                 _('Сроки'),
                 Row( Field('start_date', wrapper_class='col-md-4'), Field('deadline', wrapper_class='col-md-4'), Field('estimated_time', wrapper_class='col-md-4'),)
            ),
            Fieldset(
                 _('Участники'),
                 'responsible_user',
                 'executors',
                 'watchers'
            )
        )

    def clean_estimated_time(self):
        """Валидирует и конвертирует строку времени в timedelta."""
        # ... (код clean_estimated_time без изменений) ...
        duration_str = self.cleaned_data.get("estimated_time")
        if not duration_str: return None
        pattern = re.compile(r"\s*(?:(?P<days>\d+)\s*(?:d|д))?\s*(?:(?P<hours>\d+)\s*(?:h|ч))?\s*(?:(?P<minutes>\d+)\s*(?:m|м))?\s*$", re.IGNORECASE)
        match = pattern.match(duration_str)
        if match:
            time_params = {k: int(v) for k, v in match.groupdict().items() if v}
            if time_params: return timedelta(**time_params)
        raise ValidationError( _("Неверный формат времени. Используйте, например: '1d 2h 30m', '2ч', '45м'."), code='invalid_timedelta')


    def clean(self):
        """Общая валидация формы."""
        # ... (код clean без изменений) ...
        cleaned_data = super().clean()
        start_date = cleaned_data.get("start_date"); deadline_datetime = cleaned_data.get("deadline")
        if start_date and deadline_datetime:
            deadline_date = deadline_datetime.date()
            if start_date > deadline_date: self.add_error('start_date', ValidationError(_("Дата начала не может быть позже дедлайна."))); self.add_error('deadline', ValidationError(_("Дедлайн не может быть раньше даты начала.")))
        category = cleaned_data.get("category"); subcategory = cleaned_data.get("subcategory")
        if subcategory and not category: self.add_error('subcategory', ValidationError(_("Нельзя выбрать подкатегорию без выбора категории.")))
        elif subcategory and category and subcategory.category != category: self.add_error('subcategory', ValidationError(_("Выбранная подкатегория не принадлежит выбранной категории.")))
        responsible = cleaned_data.get("responsible_user"); executors = cleaned_data.get("executors", User.objects.none()); watchers = cleaned_data.get("watchers", User.objects.none())
        if responsible:
            if executors and responsible in executors: self.add_error('executors', ValidationError(_("Ответственный не может быть одновременно исполнителем.")))
            if watchers and responsible in watchers: self.add_error('watchers', ValidationError(_("Ответственный не может быть одновременно наблюдателем.")))
        return cleaned_data

    @transaction.atomic
    def save(self, commit=True):
        """Сохраняет задачу и обновляет роли пользователей."""
        task = super().save(commit=False) # Не сохраняем сразу

        if not task.pk and self.request_user:
            task.created_by = self.request_user

        if commit:
            task.save() # Сохраняем основную задачу

            if TaskUserRole and User: # Проверяем, что модели импортировались
                responsible_user = self.cleaned_data.get('responsible_user')
                executors = self.cleaned_data.get('executors')
                watchers = self.cleaned_data.get('watchers')
                # Получаем текущие роли для этой задачи
                current_user_roles = {ur.user_id: ur for ur in TaskUserRole.objects.filter(task=task)}

                new_roles_to_create = []
                roles_to_update = [] # Список для обновляемых ролей

                # --- Обработка Ответственного ---
                if responsible_user:
                    user_id = responsible_user.id
                    if user_id in current_user_roles:
                        # Пользователь уже имеет какую-то роль в этой задаче
                        ur = current_user_roles.pop(user_id) # Удаляем из словаря, чтобы не удалить позже
                        if ur.role != TaskUserRole.RoleChoices.RESPONSIBLE:
                            ur.role = TaskUserRole.RoleChoices.RESPONSIBLE
                            roles_to_update.append(ur) # Добавляем в список на обновление
                    else:
                        # Пользователя нет в ролях этой задачи, создаем новую
                        new_roles_to_create.append(
                            TaskUserRole(task=task, user=responsible_user, role=TaskUserRole.RoleChoices.RESPONSIBLE)
                        )

                # --- Обработка Исполнителей ---
                if executors:
                    for user in executors:
                        user_id = user.id
                        # Ответственный не может быть исполнителем
                        if responsible_user and user_id == responsible_user.id:
                            continue # Пропускаем ответственного

                        if user_id in current_user_roles:
                            ur = current_user_roles.pop(user_id)
                            if ur.role != TaskUserRole.RoleChoices.EXECUTOR:
                                ur.role = TaskUserRole.RoleChoices.EXECUTOR
                                roles_to_update.append(ur)
                        else:
                            new_roles_to_create.append(
                                TaskUserRole(task=task, user=user, role=TaskUserRole.RoleChoices.EXECUTOR)
                            )

                # --- Обработка Наблюдателей ---
                if watchers:
                     for user in watchers:
                        user_id = user.id
                        # Ответственный и исполнитель не могут быть наблюдателями
                        if (responsible_user and user_id == responsible_user.id) or \
                           (executors and user in executors):
                            continue # Пропускаем

                        if user_id in current_user_roles:
                            ur = current_user_roles.pop(user_id)
                            if ur.role != TaskUserRole.RoleChoices.WATCHER:
                                ur.role = TaskUserRole.RoleChoices.WATCHER
                                roles_to_update.append(ur)
                        else:
                             new_roles_to_create.append(
                                TaskUserRole(task=task, user=user, role=TaskUserRole.RoleChoices.WATCHER)
                             )

                # --- Выполняем операции с БД ---
                # Создаем новые роли
                if new_roles_to_create:
                    TaskUserRole.objects.bulk_create(new_roles_to_create)
                    logger.info(f"Created {len(new_roles_to_create)} new roles for Task {task.id}")

                # Обновляем измененные роли
                if roles_to_update:
                    # bulk_update требует указания полей для обновления
                    TaskUserRole.objects.bulk_update(roles_to_update, ['role'])
                    logger.info(f"Updated {len(roles_to_update)} existing roles for Task {task.id}")


                # Удаляем старые роли (те, что остались в current_user_roles)
                roles_to_delete_pks = [ur.pk for ur in current_user_roles.values()]
                if roles_to_delete_pks:
                    deleted_count, _ = TaskUserRole.objects.filter(pk__in=roles_to_delete_pks).delete()
                    logger.info(f"Deleted {deleted_count} old roles for Task {task.id}")

        return task


# ============================================================================== #
# Task Photo Form
# ============================================================================== #
class TaskPhotoForm(forms.ModelForm):
    class Meta:
        model = TaskPhoto
        fields = ["photo", "description"]
        widgets = {
            "photo": forms.ClearableFileInput(attrs={"class": FILE_INPUT_CLASSES}),
            "description": forms.Textarea(attrs={"rows": 2, 'class': TEXTAREA_CLASSES, 'placeholder': _('Описание фото')}),
        }


# ============================================================================== #
# Task Comment Form
# ============================================================================== #
class TaskCommentForm(forms.ModelForm):
    class Meta:
        model = TaskComment
        fields = ["text"]
        widgets = {
            "text": forms.Textarea(attrs={ "rows": 3, "placeholder": _("Введите ваш комментарий..."), "class": TEXTAREA_CLASSES }),
        }