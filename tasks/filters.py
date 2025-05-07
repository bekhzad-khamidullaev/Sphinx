# tasks/filters.py
# -*- coding: utf-8 -*-

import logging
import django_filters
from django import forms
from django.db.models import Q
from django.utils.translation import gettext_lazy as _
from django.contrib.auth import get_user_model

from .models import Task, Project, TaskCategory, TaskSubcategory
# Предполагается, что TaskUserRole определен в user_profiles.models
from user_profiles.models import TaskUserRole

logger = logging.getLogger(__name__)
User = get_user_model()

# Общие классы для виджетов фильтров
FILTER_TEXT_INPUT_CLASSES = "form-input block w-full sm:text-sm border-gray-300 rounded-md dark:bg-gray-700 dark:border-gray-600 dark:text-white"
FILTER_SELECT_CLASSES = "form-select block w-full sm:text-sm border-gray-300 rounded-md dark:bg-gray-700 dark:border-gray-600 dark:text-white"
FILTER_DATE_INPUT_CLASSES = f"{FILTER_TEXT_INPUT_CLASSES} flatpickr-date-filter" # для JS date picker

class BaseFilter(django_filters.FilterSet):
    def __init__(self, *args, **kwargs):
        # Флаг, чтобы решить, рендерить ли полную форму или скрытые поля (для GET-параметров без видимой формы)
        self.render_form = kwargs.pop('render_form', True)
        super().__init__(*args, **kwargs)
        if not self.render_form:
            for field_name, field_obj in self.form.fields.items():
                field_obj.widget = forms.HiddenInput()

class ProjectFilter(BaseFilter):
    name = django_filters.CharFilter(
        lookup_expr='icontains', label=_('Название проекта'),
        widget=forms.TextInput(attrs={'placeholder': _('Поиск по названию...'), 'class': FILTER_TEXT_INPUT_CLASSES})
    )
    # Можно добавить фильтры по датам, если нужно
    # start_date_after = django_filters.DateFilter(field_name='start_date', lookup_expr='gte', label=_('Начало не ранее'), widget=forms.DateInput(attrs={'type': 'date', 'class': FILTER_DATE_INPUT_CLASSES}))
    # end_date_before = django_filters.DateFilter(field_name='end_date', lookup_expr='lte', label=_('Завершение не позднее'), widget=forms.DateInput(attrs={'type': 'date', 'class': FILTER_DATE_INPUT_CLASSES}))

    class Meta:
        model = Project
        fields = ['name'] # 'start_date_after', 'end_date_before']

class TaskCategoryFilter(BaseFilter):
    name = django_filters.CharFilter(
        lookup_expr='icontains', label=_('Название категории'),
        widget=forms.TextInput(attrs={'placeholder': _('Поиск по названию...'), 'class': FILTER_TEXT_INPUT_CLASSES})
    )
    class Meta:
        model = TaskCategory
        fields = ['name']

class TaskSubcategoryFilter(BaseFilter):
    name = django_filters.CharFilter(
        lookup_expr='icontains', label=_('Название подкатегории'),
        widget=forms.TextInput(attrs={'placeholder': _('Поиск по названию...'), 'class': FILTER_TEXT_INPUT_CLASSES})
    )
    category = django_filters.ModelChoiceFilter(
        queryset=TaskCategory.objects.all().order_by('name'), label=_('Категория'),
        widget=forms.Select(attrs={'class': FILTER_SELECT_CLASSES})
    )
    class Meta:
        model = TaskSubcategory
        fields = ['name', 'category']

class TaskFilter(BaseFilter):
    q = django_filters.CharFilter(
        method='search_filter', label=_('Поиск'),
        widget=forms.TextInput(attrs={'placeholder': _('Номер, название, описание...'), 'class': FILTER_TEXT_INPUT_CLASSES})
    )
    deadline = django_filters.DateRangeFilter(
        label=_('Срок выполнения в диапазоне'),
        # widget можно кастомизировать, если стандартный не подходит
    )
    deadline_after = django_filters.DateFilter(
        field_name='deadline', lookup_expr='gte', label=_('Срок не ранее'),
        widget=forms.DateInput(attrs={'type': 'date', 'class': FILTER_DATE_INPUT_CLASSES})
    )
    deadline_before = django_filters.DateFilter(
        field_name='deadline', lookup_expr='lte', label=_('Срок не позднее'),
        widget=forms.DateInput(attrs={'type': 'date', 'class': FILTER_DATE_INPUT_CLASSES})
    )
    created_at_after = django_filters.DateFilter(
        field_name='created_at', lookup_expr='gte', label=_('Создана после'),
        widget=forms.DateInput(attrs={'type': 'date', 'class': FILTER_DATE_INPUT_CLASSES})
    )
    created_at_before = django_filters.DateFilter(
        field_name='created_at', lookup_expr='lte', label=_('Создана до'),
        widget=forms.DateInput(attrs={'type': 'date', 'class': FILTER_DATE_INPUT_CLASSES})
    )
    project = django_filters.ModelChoiceFilter(
        queryset=Project.objects.all().order_by('name'), label=_('Проект'),
        widget=forms.Select(attrs={'class': FILTER_SELECT_CLASSES})
    )
    category = django_filters.ModelChoiceFilter(
        queryset=TaskCategory.objects.all().order_by('name'), label=_('Категория'),
        widget=forms.Select(attrs={'class': FILTER_SELECT_CLASSES})
    )
    # Для подкатегории можно сделать зависимый фильтр с помощью JS на фронте
    subcategory = django_filters.ModelChoiceFilter(
        queryset=TaskSubcategory.objects.select_related('category').order_by('category__name', 'name'),
        label=_('Подкатегория'),
        widget=forms.Select(attrs={'class': FILTER_SELECT_CLASSES})
    )
    created_by = django_filters.ModelChoiceFilter(
        queryset=User.objects.filter(is_active=True).order_by('username'), label=_('Создатель'),
        widget=forms.Select(attrs={'class': FILTER_SELECT_CLASSES})
    )
    status = django_filters.MultipleChoiceFilter( # Позволяет выбирать несколько статусов
        choices=Task.StatusChoices.choices,
        label=_('Статус'),
        widget=forms.CheckboxSelectMultiple(attrs={'class': 'space-y-1'}) # Или forms.SelectMultiple
    )
    priority = django_filters.MultipleChoiceFilter( # Позволяет выбирать несколько приоритетов
        choices=Task.TaskPriority.choices,
        label=_('Приоритет'),
        widget=forms.CheckboxSelectMultiple(attrs={'class': 'space-y-1'}) # Или forms.SelectMultiple
    )

    # Фильтры по ролям (если TaskUserRole используется)
    responsible = django_filters.ModelChoiceFilter(
        queryset=User.objects.filter(is_active=True, task_roles__role=TaskUserRole.RoleChoices.RESPONSIBLE).distinct().order_by('username'),
        label=_('Ответственный'), method='filter_by_user_role', field_name='responsible', # method для кастомной логики
        widget=forms.Select(attrs={'class': FILTER_SELECT_CLASSES})
    )
    executor = django_filters.ModelChoiceFilter(
        queryset=User.objects.filter(is_active=True, task_roles__role=TaskUserRole.RoleChoices.EXECUTOR).distinct().order_by('username'),
        label=_('Исполнитель'), method='filter_by_user_role', field_name='executor',
        widget=forms.Select(attrs={'class': FILTER_SELECT_CLASSES})
    )
    watcher = django_filters.ModelChoiceFilter(
         queryset=User.objects.filter(is_active=True, task_roles__role=TaskUserRole.RoleChoices.WATCHER).distinct().order_by('username'),
         label=_('Наблюдатель'), method='filter_by_user_role', field_name='watcher',
         widget=forms.Select(attrs={'class': FILTER_SELECT_CLASSES})
     )
    participant = django_filters.ModelChoiceFilter( # Любой участник
        queryset=User.objects.filter(is_active=True, task_roles__isnull=False).distinct().order_by('username'),
        label=_('Участник (любая роль)'), method='filter_by_user_role', field_name='participant',
        widget=forms.Select(attrs={'class': FILTER_SELECT_CLASSES})
    )

    class Meta:
        model = Task
        fields = [ # Порядок полей в форме фильтра
            'q', 'project', 'status', 'priority',
            'responsible', 'executor', 'watcher', 'participant', # Роли
            'category', 'subcategory', 'created_by',
            'deadline_after', 'deadline_before', # Или 'deadline' (DateRangeFilter)
            'created_at_after', 'created_at_before',
        ]

    def search_filter(self, queryset, name, value):
        if not value:
            return queryset
        # Поиск по номеру, названию, описанию
        return queryset.filter(
            Q(task_number__icontains=value) |
            Q(title__icontains=value) |
            Q(description__icontains=value)
        ).distinct()

    def filter_by_user_role(self, queryset, name, value):
         """
         Фильтрует задачи по пользователю и его роли.
         'name' - это field_name, указанный в ModelChoiceFilter.
         'value' - это выбранный User instance.
         """
         if not value: # Если пользователь не выбран, не фильтруем
             return queryset

         role_map = {
             'responsible': TaskUserRole.RoleChoices.RESPONSIBLE,
             'executor': TaskUserRole.RoleChoices.EXECUTOR,
             'watcher': TaskUserRole.RoleChoices.WATCHER,
         }
         if name == 'participant': # Особый случай для любого участника
             return queryset.filter(user_roles__user=value).distinct()
         elif name in role_map:
             return queryset.filter(user_roles__user=value, user_roles__role=role_map[name]).distinct()
         else:
             logger.warning(f"filter_by_user_role called with unexpected filter name: {name}")
             return queryset