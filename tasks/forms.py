# tasks/forms.py
# -*- coding: utf-8 -*-

import datetime
import logging
import re
from datetime import timedelta
from django.utils import timezone
from django import forms
from django.urls import reverse_lazy
from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _
from django.db import transaction # Для атомарных операций сохранения
from crispy_forms.helper import FormHelper
from crispy_forms.layout import Layout, Fieldset, Row, Column, Div, HTML, Submit
from django_select2.forms import (
    Select2Widget, Select2MultipleWidget,
    ModelSelect2Widget, ModelSelect2MultipleWidget
)

from .models import Task, TaskPhoto, Project, TaskCategory, TaskSubcategory, TaskComment
from user_profiles.models import User, TaskUserRole # Предполагается, что TaskUserRole определен

logger = logging.getLogger(__name__)

# Общие CSS классы для полей форм (Tailwind/Bootstrap)
BASE_INPUT_CLASSES = "block w-full px-3 py-2 text-sm placeholder-gray-400 border border-gray-300 rounded-md shadow-sm appearance-none focus:outline-none focus:ring-indigo-500 focus:border-indigo-500 dark:bg-gray-700 dark:border-gray-600 dark:placeholder-gray-400 dark:text-white dark:focus:ring-indigo-500 dark:focus:border-indigo-500"
TEXT_INPUT_CLASSES = f"form-input {BASE_INPUT_CLASSES}"
TEXTAREA_CLASSES = f"form-textarea {BASE_INPUT_CLASSES}"
SELECT_CLASSES = f"form-select {BASE_INPUT_CLASSES}" # Для стандартных select
DATE_INPUT_CLASSES = f"form-input {BASE_INPUT_CLASSES} flatpickr-date"
DATETIME_INPUT_CLASSES = f"form-input {BASE_INPUT_CLASSES} flatpickr-datetime"
FILE_INPUT_CLASSES = "form-input block w-full text-sm text-gray-900 border border-gray-300 rounded-lg cursor-pointer bg-gray-50 dark:text-gray-400 focus:outline-none dark:bg-gray-700 dark:border-gray-600 dark:placeholder-gray-400 file:mr-4 file:py-2 file:px-4 file:rounded-md file:border-0 file:text-sm file:font-semibold file:bg-indigo-50 file:text-indigo-700 hover:file:bg-indigo-100 dark:file:bg-gray-600 dark:file:text-gray-300 dark:hover:file:bg-gray-500"
# Классы для Select2 (могут переопределяться в data-theme)
SELECT2_SINGLE_CLASS = "django-select2-single" # Добавьте свои классы, если нужно
SELECT2_MULTIPLE_CLASS = "django-select2-multiple"

USER_AUTOCOMPLETE_URL_NAME = 'tasks:user_autocomplete' # URL для автокомплита пользователей

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
        self.helper.form_tag = False # Отключаем form tag, если он есть в шаблоне
        self.helper.disable_csrf = True # CSRF токен будет в основном шаблоне

    def clean(self):
        cleaned_data = super().clean()
        start_date = cleaned_data.get("start_date")
        end_date = cleaned_data.get("end_date")

        if not start_date: # Если дата начала не указана, можно установить текущую
             cleaned_data['start_date'] = timezone.now().date()
             start_date = cleaned_data['start_date'] # Обновляем для проверки

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

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.helper = FormHelper()
        self.helper.form_tag = False
        self.helper.disable_csrf = True


class TaskSubcategoryForm(forms.ModelForm):
    category = forms.ModelChoiceField(
        queryset=TaskCategory.objects.all().order_by("name"), label=_("Родительская категория"),
        widget=Select2Widget(attrs={'data-placeholder': _("Выберите категорию..."), 'class': f'{SELECT_CLASSES} {SELECT2_SINGLE_CLASS}', 'data-theme': 'bootstrap-5'})
    ) # Используем data-theme для стилизации Select2 под Bootstrap, если нужно

    class Meta:
        model = TaskSubcategory
        fields = ["category", "name", "description"]
        widgets = {
            "name": forms.TextInput(attrs={'class': TEXT_INPUT_CLASSES, 'placeholder': _('Название подкатегории')}),
            "description": forms.Textarea(attrs={"rows": 3, 'class': TEXTAREA_CLASSES, 'placeholder': _('Описание подкатегории')}),
        }
        labels = {"name": _("Название подкатегории"), "description": _("Описание")}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.helper = FormHelper()
        self.helper.form_tag = False
        self.helper.disable_csrf = True

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
    title = forms.CharField(label=_('Название задачи'), max_length=255, widget=forms.TextInput(attrs={'class': TEXT_INPUT_CLASSES, 'placeholder': _('Краткое название задачи')}))
    description = forms.CharField(label=_('Описание задачи'), required=False, widget=forms.Textarea(attrs={'class': TEXTAREA_CLASSES, 'rows': 5, 'placeholder': _('Подробное описание, цели, критерии выполнения...')}))
    deadline = forms.DateTimeField(label=_('Срок выполнения'), required=False, input_formats=['%Y-%m-%dT%H:%M', '%Y-%m-%d %H:%M'], widget=forms.DateTimeInput(format='%Y-%m-%dT%H:%M', attrs={'type': 'datetime-local', 'class': DATETIME_INPUT_CLASSES}))
    estimated_time = forms.CharField(label=_('Планируемое время'), required=False, help_text=_("Формат: 'Xd Yh Zm'. Пример: 1d 2h 30m"), widget=forms.TextInput(attrs={'class': TEXT_INPUT_CLASSES, 'placeholder': _('Напр., 2h 30m или 1d 4h')}))
    priority = forms.ChoiceField(label=_('Приоритет'), choices=[], widget=forms.Select(attrs={'class': SELECT_CLASSES}))
    project = forms.ModelChoiceField(label=_('Проект'), queryset=Project.objects.all().order_by("name"), required=True, widget=Select2Widget(attrs={'data-placeholder': _('Выберите проект...'), 'class': f'{SELECT2_SINGLE_CLASS} {SELECT_CLASSES}'}))
    category = forms.ModelChoiceField(label=_('Категория'), queryset=TaskCategory.objects.all().order_by("name"), required=False, widget=Select2Widget(attrs={'id': 'id_category', 'data-placeholder': _('Выберите категорию...'), 'class': f'{SELECT2_SINGLE_CLASS} {SELECT_CLASSES}'}))
    subcategory = forms.ModelChoiceField(label=_('Подкатегория'), queryset=TaskSubcategory.objects.none(), required=False, widget=Select2Widget(attrs={'id': 'id_subcategory', 'disabled': True, 'data-placeholder': _('Сначала выберите категорию...'), 'class': f'{SELECT2_SINGLE_CLASS} {SELECT_CLASSES}'}))
    start_date = forms.DateField(label=_('Дата начала'), required=True, input_formats=['%Y-%m-%d'], widget=forms.DateInput(format='%Y-%m-%d', attrs={'type': 'date', 'class': DATE_INPUT_CLASSES}))

    # Поля для назначения пользователей (если TaskUserRole определен)
    if User and TaskUserRole:
        user_select_widget_attrs = {
            'data-ajax--url': reverse_lazy(USER_AUTOCOMPLETE_URL_NAME), # URL для AJAX-запросов
            'data-ajax--cache': 'true',
            'data-ajax--delay': 250, # Задержка перед отправкой запроса
            'data-minimum-input-length': 1, # Минимальное количество символов для начала поиска
            'class': f'{SELECT_CLASSES} {SELECT2_SINGLE_CLASS}', # Базовые классы + select2
            'data-theme': 'bootstrap-5', # Или другая тема Select2
            'data-project-field': 'id_project' # JS будет использовать это для передачи ID проекта
        }
        responsible_user = forms.ModelChoiceField(
            label=_('Ответственный'), queryset=User.objects.filter(is_active=True), required=True,
            widget=ModelSelect2Widget(
                model=User,
                search_fields=['username__icontains', 'first_name__icontains', 'last_name__icontains', 'email__icontains'],
                attrs={**user_select_widget_attrs, 'data-placeholder': _('Выберите ответственного...')}
            )
        )
        executors = forms.ModelMultipleChoiceField(
            label=_('Исполнители'), queryset=User.objects.filter(is_active=True), required=False,
            widget=ModelSelect2MultipleWidget(
                model=User,
                search_fields=['username__icontains', 'first_name__icontains', 'last_name__icontains', 'email__icontains'],
                attrs={**user_select_widget_attrs, 'class': f'{SELECT_CLASSES} {SELECT2_MULTIPLE_CLASS}', 'data-placeholder': _('Выберите исполнителей...')}
            )
        )
        watchers = forms.ModelMultipleChoiceField(
            label=_('Наблюдатели'), queryset=User.objects.filter(is_active=True), required=False,
            widget=ModelSelect2MultipleWidget(
                model=User,
                search_fields=['username__icontains', 'first_name__icontains', 'last_name__icontains', 'email__icontains'],
                attrs={**user_select_widget_attrs, 'class': f'{SELECT_CLASSES} {SELECT2_MULTIPLE_CLASS}', 'data-placeholder': _('Выберите наблюдателей...')}
            )
        )
    else: # Fallback, если User или TaskUserRole не доступны
        responsible_user = forms.CharField(label=_('Ответственный (недоступно)'), required=False, disabled=True)
        executors = forms.CharField(label=_('Исполнители (недоступно)'), required=False, disabled=True)
        watchers = forms.CharField(label=_('Наблюдатели (недоступно)'), required=False, disabled=True)


    class Meta:
        model = Task
        fields = [
            "title", "description", "priority", "project",
            "category", "subcategory", "start_date", "deadline", "estimated_time",
            # Поля для ролей добавляются в self.fields, если они существуют
        ]
        # Статус обычно управляется через workflow/действия, а не прямое поле в форме создания/редактирования.
        # created_by устанавливается в методе save формы/представления.

    def __init__(self, *args, **kwargs):
        self.request_user = kwargs.pop('user', None) # Получаем пользователя из представления
        instance = kwargs.get("instance")
        initial_data = kwargs.get("initial", {})

        # Если редактируем задачу, предзаполняем поля ролей
        if instance and instance.pk and User and TaskUserRole:
            roles_data = TaskUserRole.objects.filter(task=instance).values_list("user_id", "role")
            initial_data.setdefault("responsible_user", next((uid for uid, r in roles_data if r == TaskUserRole.RoleChoices.RESPONSIBLE), None))
            initial_data.setdefault("executors", [uid for uid, r in roles_data if r == TaskUserRole.RoleChoices.EXECUTOR])
            initial_data.setdefault("watchers", [uid for uid, r in roles_data if r == TaskUserRole.RoleChoices.WATCHER])
        kwargs["initial"] = initial_data

        super().__init__(*args, **kwargs)

        # Динамическое добавление полей ролей в self.fields, если они определены
        if 'responsible_user' in self.fields and 'executors' in self.fields and 'watchers' in self.fields:
             # Это уже сделано через if User and TaskUserRole выше, здесь только для примера, если бы они не были объявлены сразу
             pass


        if hasattr(Task, 'TaskPriority'): # Проверка на случай, если модель еще не синхронизирована
            self.fields['priority'].choices = Task.TaskPriority.choices
            # Устанавливаем значение по умолчанию, если оно не задано и не редактируется существующая задача с приоритетом
            if not self.initial.get('priority') and not (instance and instance.priority):
                self.fields['priority'].initial = Task.TaskPriority.MEDIUM
        
        if not self.initial.get('start_date') and not (instance and instance.start_date):
            self.fields['start_date'].initial = timezone.now().date()


        # Логика для зависимого выпадающего списка подкатегорий
        category_id = self.initial.get('category') or (instance and instance.category_id)
        if category_id:
            try: # Убедимся, что category_id это PK, а не объект
                cat_pk = category_id.pk if hasattr(category_id, 'pk') else int(category_id)
                self.fields['subcategory'].queryset = TaskSubcategory.objects.filter(category_id=cat_pk).order_by('name')
                self.fields['subcategory'].widget.attrs.pop('disabled', None)
            except (ValueError, TypeError):
                logger.warning(f"Invalid category_id format for subcategory queryset: {category_id}")
                self.fields['subcategory'].queryset = TaskSubcategory.objects.none()
                self.fields['subcategory'].widget.attrs['disabled'] = True

        else:
            self.fields['subcategory'].queryset = TaskSubcategory.objects.none()
            self.fields['subcategory'].widget.attrs['disabled'] = True


        # Настройка Crispy Forms
        self.helper = FormHelper(self)
        self.helper.form_method = 'post'
        self.helper.form_tag = False # Отключаем form tag
        self.helper.disable_csrf = True # CSRF токен будет в основном шаблоне
        # Пример макета с использованием Tailwind-подобных классов для колонок
        self.helper.layout = Layout(
            Fieldset(_('Основная информация'),
                'title',
                'description',
                css_class='mb-6 p-4 border rounded-md dark:border-gray-700'
            ),
            Row(
                Column('project', css_class='md:w-1/2 px-2 mb-4'),
                Column('priority', css_class='md:w-1/2 px-2 mb-4'),
                css_class='flex flex-wrap -mx-2 mb-2'
            ),
            Row(
                Column('category', css_class='md:w-1/2 px-2 mb-4'),
                Column('subcategory', css_class='md:w-1/2 px-2 mb-4'),
                css_class='flex flex-wrap -mx-2 mb-2'
            ),
            Row(
                Column('start_date', css_class='md:w-1/3 px-2 mb-4'),
                Column('deadline', css_class='md:w-1/3 px-2 mb-4'),
                Column('estimated_time', css_class='md:w-1/3 px-2 mb-4'),
                css_class='flex flex-wrap -mx-2 mb-2'
            ),
        )
        if User and TaskUserRole: # Добавляем поля ролей в макет, если они есть
            self.helper.layout.append(
                Fieldset(_('Участники задачи'),
                    'responsible_user',
                    'executors',
                    'watchers',
                    css_class='mb-6 p-4 border rounded-md dark:border-gray-700'
                )
            )


    def clean_estimated_time(self):
        duration_string = self.cleaned_data.get("estimated_time")
        if not duration_string:
            return None # Поле не обязательное

        normalized_duration = duration_string.lower().replace(' ', '')
        # Паттерн для "Xd Yh Zm", "Xd Yh", "Xd Zm", "Yh Zm", "Xd", "Yh", "Zm"
        # d - дни, h - часы, m - минуты
        pattern = re.compile(
            r"^(?:(?P<days>\d+)(?:d|д))?"
            r"(?:(?P<hours>\d+)(?:h|ч))?"
            r"(?:(?P<minutes>\d+)(?:m|м))?$"
        )
        match = pattern.match(normalized_duration)

        if match and match.group(0): # Убеждаемся, что вся строка совпала
            time_parameters = {k: int(v) for k, v in match.groupdict().items() if v is not None}
            if time_parameters: # Если хоть что-то было найдено
                return timedelta(**time_parameters)

        raise ValidationError(
            _("Неверный формат времени. Используйте Xd (дни), Yh (часы), Zm (минуты). Пример: '1d 2h 30m'."),
            code='invalid_timedelta'
        )

    def clean(self):
        cleaned_data = super().clean()
        category = cleaned_data.get("category")
        subcategory = cleaned_data.get("subcategory")
        start_date = cleaned_data.get("start_date")
        deadline_dt = cleaned_data.get("deadline") # Это уже datetime объект

        if subcategory and not category:
            # Это условие должно было быть обработано логикой зависимого списка,
            # но на всякий случай оставляем валидацию.
            # Если категория не выбрана, подкатегория должна быть пустой.
            # Либо, если подкатегория выбрана, а категория нет, можно попытаться установить категорию из подкатегории.
            # cleaned_data['category'] = subcategory.category # Вариант авто-установки
            self.add_error('subcategory', _("Нельзя выбрать подкатегорию без категории."))
        elif subcategory and category and subcategory.category != category:
            self.add_error('subcategory', _("Выбранная подкатегория не принадлежит указанной категории."))
        
        if start_date and deadline_dt:
            # deadline_dt уже aware datetime, если Django правильно его обработал
            # start_date это date. Преобразуем start_date в aware datetime (начало дня) для сравнения.
            start_datetime = timezone.make_aware(datetime.combine(start_date, datetime.min.time()))
            if deadline_dt < start_datetime:
                self.add_error('deadline', _("Срок выполнения не может быть раньше даты начала."))

        # Валидация ролей (если они есть)
        if User and TaskUserRole and 'responsible_user' in cleaned_data:
            responsible = cleaned_data.get("responsible_user")
            executors = cleaned_data.get("executors") or User.objects.none() # queryset
            watchers = cleaned_data.get("watchers") or User.objects.none() # queryset

            if responsible:
                if hasattr(executors, '__iter__') and responsible in executors:
                    self.add_error('executors', _("Ответственный не может быть одновременно исполнителем."))
                if hasattr(watchers, '__iter__') and responsible in watchers:
                    self.add_error('watchers', _("Ответственный не может быть одновременно наблюдателем."))
        return cleaned_data

    @transaction.atomic # Гарантируем, что все изменения ролей и задачи будут в одной транзакции
    def save(self, commit=True):
        task_instance = super().save(commit=False) # Сначала получаем экземпляр задачи

        # Устанавливаем создателя, если это новая задача и пользователь передан
        if not task_instance.pk and self.request_user and hasattr(task_instance, 'created_by') and not task_instance.created_by_id:
            task_instance.created_by = self.request_user
        
        # Флаг для model.save(), чтобы избежать двойной очистки, если это необходимо
        # setattr(task_instance, '_called_from_form_save', True)

        if commit:
            task_instance.save() # Сохраняем задачу (вызовет model.full_clean())
            # super().save_m2m() # Для любых прямых M2M полей в форме (здесь нет)

            # Обработка ролей пользователей, если они есть в форме
            if User and TaskUserRole and 'responsible_user' in self.cleaned_data:
                responsible_user_new = self.cleaned_data.get('responsible_user')
                executors_new = self.cleaned_data.get('executors') or User.objects.none()
                watchers_new = self.cleaned_data.get('watchers') or User.objects.none()
                
                # Текущие роли для этой задачи
                current_roles = TaskUserRole.objects.filter(task=task_instance)
                current_responsible_ids = list(current_roles.filter(role=TaskUserRole.RoleChoices.RESPONSIBLE).values_list('user_id', flat=True))
                current_executor_ids = list(current_roles.filter(role=TaskUserRole.RoleChoices.EXECUTOR).values_list('user_id', flat=True))
                current_watcher_ids = list(current_roles.filter(role=TaskUserRole.RoleChoices.WATCHER).values_list('user_id', flat=True))

                # Обновляем ответственного
                # Удаляем старых ответственных, если новый не совпадает или если новый не указан, а старые были
                if responsible_user_new:
                    if responsible_user_new.id not in current_responsible_ids:
                        TaskUserRole.objects.filter(task=task_instance, role=TaskUserRole.RoleChoices.RESPONSIBLE).delete()
                        TaskUserRole.objects.update_or_create(
                            task=task_instance, user=responsible_user_new,
                            defaults={'role': TaskUserRole.RoleChoices.RESPONSIBLE}
                        )
                else: # Новый ответственный не указан, удаляем всех текущих ответственных
                     TaskUserRole.objects.filter(task=task_instance, role=TaskUserRole.RoleChoices.RESPONSIBLE).delete()


                # Обновляем исполнителей
                new_executor_ids = [user.id for user in executors_new]
                # Удалить роли тех, кто больше не исполнитель
                TaskUserRole.objects.filter(task=task_instance, role=TaskUserRole.RoleChoices.EXECUTOR).exclude(user_id__in=new_executor_ids).delete()
                # Добавить/обновить новых исполнителей
                for user_id in new_executor_ids:
                    if user_id != (responsible_user_new.id if responsible_user_new else None): # Исполнитель не может быть ответственным
                        TaskUserRole.objects.update_or_create(
                            task=task_instance, user_id=user_id,
                            defaults={'role': TaskUserRole.RoleChoices.EXECUTOR}
                        )
                
                # Обновляем наблюдателей
                new_watcher_ids = [user.id for user in watchers_new]
                 # Удалить роли тех, кто больше не наблюдатель
                TaskUserRole.objects.filter(task=task_instance, role=TaskUserRole.RoleChoices.WATCHER).exclude(user_id__in=new_watcher_ids).delete()
                # Добавить/обновить новых наблюдателей
                for user_id in new_watcher_ids:
                    if user_id != (responsible_user_new.id if responsible_user_new else None) and user_id not in new_executor_ids: # Наблюдатель не может быть ответственным или исполнителем
                        TaskUserRole.objects.update_or_create(
                            task=task_instance, user_id=user_id,
                            defaults={'role': TaskUserRole.RoleChoices.WATCHER}
                        )
            
        # if hasattr(task_instance, '_called_from_form_save'):
        #    delattr(task_instance, '_called_from_form_save')
        return task_instance

class TaskPhotoForm(forms.ModelForm):
    class Meta:
        model = TaskPhoto
        fields = ["photo", "description"]
        widgets = {
            "photo": forms.ClearableFileInput(attrs={"class": FILE_INPUT_CLASSES, 'accept': 'image/*'}), # Позволяет загружать только изображения
            "description": forms.Textarea(attrs={"rows": 2, 'class': TEXTAREA_CLASSES, 'placeholder': _('Краткое описание фотографии')}),
        }
        labels = {"photo": _("Файл фотографии"), "description": _("Описание")}

class TaskCommentForm(forms.ModelForm):
    class Meta:
        model = TaskComment
        fields = ["text"]
        widgets = {
            "text": forms.Textarea(attrs={
                "rows": 3,
                "placeholder": _("Введите ваш комментарий..."),
                "class": TEXTAREA_CLASSES,
                "aria-label": _("Текст комментария") # для доступности
            })
        }
        labels = {"text": ""} # Убираем стандартный лейбл, если placeholder достаточно