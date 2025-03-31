# tasks/filters.py

import logging # Добавим логгер
import django_filters
from django import forms
from django.db.models import Q
from django.utils.translation import gettext_lazy as _
from django.contrib.auth import get_user_model

from .models import Task, Project, TaskCategory, TaskSubcategory
from user_profiles.models import Team, User, TaskUserRole # Убедитесь, что все импорты верны

logger = logging.getLogger(__name__) # Инициализация логгера

# --- Базовый класс фильтра ---
class BaseFilter(django_filters.FilterSet):
    def __init__(self, *args, **kwargs):
        self.render_form = kwargs.pop('render_form', True)
        super().__init__(*args, **kwargs)
        if not self.render_form:
            self.form.fields = {}

    class Meta:
        abstract = True

# --- Фильтры для других моделей ---
class ProjectFilter(BaseFilter):
    name = django_filters.CharFilter(
        lookup_expr='icontains',
        label=_('Название проекта'),
        widget=forms.TextInput(attrs={'placeholder': _('Найти проект...')})
    )
    class Meta:
        model = Project
        fields = ['name']

class TaskCategoryFilter(BaseFilter):
    name = django_filters.CharFilter(
        lookup_expr='icontains',
        label=_('Название категории'),
        widget=forms.TextInput(attrs={'placeholder': _('Найти категорию...')})
    )
    class Meta:
        model = TaskCategory
        fields = ['name']

class TaskSubcategoryFilter(BaseFilter):
    name = django_filters.CharFilter(
        lookup_expr='icontains',
        label=_('Название подкатегории'),
        widget=forms.TextInput(attrs={'placeholder': _('Найти подкатегорию...')})
    )
    category = django_filters.ModelChoiceFilter(
        queryset=TaskCategory.objects.all(),
        label=_('Категория'),
        widget=forms.Select(attrs={'class': 'form-select'})
    )
    class Meta:
        model = TaskSubcategory
        fields = ['name', 'category']


# --- Основной фильтр для Task ---
class TaskFilter(BaseFilter):
    q = django_filters.CharFilter(
        method='search_filter',
        label=_('Поиск'),
        widget=forms.TextInput(attrs={'placeholder': _('Номер, название, описание...')})
    )
    deadline_after = django_filters.DateFilter(
        field_name='deadline', lookup_expr='gte', label=_('Срок не ранее'),
        widget=forms.DateInput(attrs={'type': 'date', 'class': 'form-control'})
    )
    deadline_before = django_filters.DateFilter(
        field_name='deadline', lookup_expr='lte', label=_('Срок не позднее'),
        widget=forms.DateInput(attrs={'type': 'date', 'class': 'form-control'})
    )
    created_at_after = django_filters.DateFilter(
        field_name='created_at', lookup_expr='gte', label=_('Создана после'),
        widget=forms.DateInput(attrs={'type': 'date', 'class': 'form-control'})
    )
    created_at_before = django_filters.DateFilter(
        field_name='created_at', lookup_expr='lte', label=_('Создана до'),
        widget=forms.DateInput(attrs={'type': 'date', 'class': 'form-control'})
    )
    project = django_filters.ModelChoiceFilter(
        queryset=Project.objects.all().order_by('name'), label=_('Проект'),
        widget=forms.Select(attrs={'class': 'form-select'})
    )
    category = django_filters.ModelChoiceFilter(
        queryset=TaskCategory.objects.all().order_by('name'), label=_('Категория'),
        widget=forms.Select(attrs={'class': 'form-select'})
    )
    subcategory = django_filters.ModelChoiceFilter(
        queryset=TaskSubcategory.objects.select_related('category').order_by('category__name', 'name'),
        label=_('Подкатегория'),
        widget=forms.Select(attrs={'class': 'form-select'})
    )
    created_by = django_filters.ModelChoiceFilter(
        queryset=User.objects.filter(is_active=True).order_by('username'), label=_('Создатель'),
        widget=forms.Select(attrs={'class': 'form-select'})
    )

    # --- ИСПРАВЛЕНИЕ ЗДЕСЬ: Убираем 'extra' из определений фильтров ---
    responsible = django_filters.ModelChoiceFilter(
        queryset=User.objects.filter(is_active=True).order_by('username'),
        field_name='user_roles__user',
        label=_('Ответственный'),
        method='filter_by_role', # Используем кастомный метод
        # АРГУМЕНТ 'extra' УДАЛЕН
        widget=forms.Select(attrs={'class': 'form-select'})
    )
    executor = django_filters.ModelChoiceFilter(
        queryset=User.objects.filter(is_active=True).order_by('username'),
        field_name='user_roles__user',
        label=_('Исполнитель'),
        method='filter_by_role',
        # АРГУМЕНТ 'extra' УДАЛЕН
        widget=forms.Select(attrs={'class': 'form-select'})
    )
    watcher = django_filters.ModelChoiceFilter(
         queryset=User.objects.filter(is_active=True).order_by('username'),
         field_name='user_roles__user',
         label=_('Наблюдатель'),
         method='filter_by_role',
         # АРГУМЕНТ 'extra' УДАЛЕН
         widget=forms.Select(attrs={'class': 'form-select'})
     )
    # --- КОНЕЦ ИСПРАВЛЕНИЯ ---

    participant = django_filters.ModelChoiceFilter(
        queryset=User.objects.filter(is_active=True).order_by('username'),
        field_name='user_roles__user',
        label=_('Участник (любая роль)'),
        widget=forms.Select(attrs={'class': 'form-select'})
    )

    status = django_filters.ChoiceFilter(
        choices=Task.StatusChoices.choices, # Используем правильные choices
        label=_('Статус'),
        widget=forms.Select(attrs={'class': 'form-select'})
    )
    priority = django_filters.ChoiceFilter(
        choices=Task.TaskPriority.choices,
        label=_('Приоритет'),
        widget=forms.Select(attrs={'class': 'form-select'})
    )

    class Meta:
        model = Task
        fields = [
            'q', 'status', 'priority', 'project',
            'responsible', 'executor', 'watcher', 'participant',
            'category', 'subcategory', 'created_by',
            'deadline_after', 'deadline_before',
            'created_at_after', 'created_at_before',
        ]

    def search_filter(self, queryset, name, value):
        if not value:
            return queryset
        return queryset.filter(
            Q(task_number__icontains=value) |
            Q(title__icontains=value) |
            Q(description__icontains=value)
        ).distinct()

    # --- ИСПРАВЛЕНИЕ ЗДЕСЬ: Обновляем метод для работы без 'extra' ---
    def filter_by_role(self, queryset, name, value):
         """
         Кастомный метод для фильтрации по пользователю с определенной ролью.
         Определяет роль на основе имени фильтра ('responsible', 'executor', 'watcher').
         """
         role_to_filter = None
         if name == 'responsible':
             role_to_filter = TaskUserRole.RoleChoices.RESPONSIBLE
         elif name == 'executor':
             role_to_filter = TaskUserRole.RoleChoices.EXECUTOR
         elif name == 'watcher':
             role_to_filter = TaskUserRole.RoleChoices.WATCHER
         else:
             # Если метод вызван для другого фильтра (не должно быть), не фильтруем
             logger.warning(f"filter_by_role called with unexpected filter name: {name}")
             return queryset

         # Фильтруем задачи, если пользователь выбран (value - это ID пользователя)
         if value:
             # Фильтруем по пользователю и определенной роли
             return queryset.filter(user_roles__user=value, user_roles__role=role_to_filter).distinct()
         # Если пользователь не выбран, не применяем фильтр по роли
         return queryset
     # --- КОНЕЦ ИСПРАВЛЕНИЯ ---