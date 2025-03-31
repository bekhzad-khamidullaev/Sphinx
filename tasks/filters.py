# tasks/filters.py

import django_filters
from django import forms
from django.db.models import Q
from django.utils.translation import gettext_lazy as _
from django.contrib.auth import get_user_model


from .models import Task, Project, TaskCategory, TaskSubcategory
from user_profiles.models import Team, User

# User = get_user_model()

# --- Базовый класс фильтра ---
class BaseFilter(django_filters.FilterSet):
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
        queryset=Project.objects.all(), label=_('Проект'),
        widget=forms.Select(attrs={'class': 'form-select'})
    )
    category = django_filters.ModelChoiceFilter(
        queryset=TaskCategory.objects.all(), label=_('Категория'),
        widget=forms.Select(attrs={'class': 'form-select'})
    )
    subcategory = django_filters.ModelChoiceFilter(
        queryset=TaskSubcategory.objects.select_related('category'), label=_('Подкатегория'),
        widget=forms.Select(attrs={'class': 'form-select'})
    )
    assignee = django_filters.ModelChoiceFilter(
        queryset=User.objects.filter(is_active=True).order_by('username'), label=_('Исполнитель'),
        widget=forms.Select(attrs={'class': 'form-select'})
    )
    team = django_filters.ModelChoiceFilter(
        queryset=Team.objects.all().order_by('name'), label=_('Команда'),
        widget=forms.Select(attrs={'class': 'form-select'})
    )
    created_by = django_filters.ModelChoiceFilter(
        queryset=User.objects.filter(is_active=True).order_by('username'), label=_('Создатель'),
        widget=forms.Select(attrs={'class': 'form-select'})
    )

    # --- ИСПОЛЬЗУЕМ ПРАВИЛЬНЫЕ choices ИЗ МОДЕЛИ ---
    status = django_filters.ChoiceFilter(
        # Используем список кортежей, определенный в модели Task
        choices=Task.TASK_STATUS_CHOICES,
        label=_('Статус'),
        widget=forms.Select(attrs={'class': 'form-select'})
    )
    priority = django_filters.ChoiceFilter(
        # Используем .choices атрибут у вложенного класса TaskPriority модели Task
        choices=Task.TaskPriority.choices,
        label=_('Приоритет'),
        widget=forms.Select(attrs={'class': 'form-select'})
    )
    # --- КОНЕЦ ИСПРАВЛЕНИЙ ---

    class Meta:
        model = Task
        fields = [
            'q', 'status', 'priority', 'project', 'team', 'assignee',
            'category', 'subcategory', 'created_by', 'deadline_after',
            'deadline_before', 'created_at_after', 'created_at_before',
        ]

    def search_filter(self, queryset, name, value):
        if not value:
            return queryset
        # Предполагаем, что task_number может быть строкой или числом, icontains безопаснее
        return queryset.filter(
            Q(title__icontains=value) |
            Q(description__icontains=value) |
            Q(task_number__icontains=value)
        ).distinct()