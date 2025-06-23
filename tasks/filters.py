# tasks/filters.py
# -*- coding: utf-8 -*-

import logging
import django_filters
from django import forms
from django.db.models import Q
from django.utils.translation import gettext_lazy as _
from django.contrib.auth import get_user_model

from .models import Task, Project, TaskCategory, TaskSubcategory, TaskAssignment
from profiles.models import Team, Department # Убедитесь, что этот импорт корректен

logger = logging.getLogger(__name__)
User = get_user_model()

class BaseFilter(django_filters.FilterSet):
    def __init__(self, *args, **kwargs):
        self.render_form = kwargs.pop('render_form', True)
        # Сохраняем request, если он передан, для использования в callable querysets
        self.request = kwargs.get('request', None)
        super().__init__(*args, **kwargs)
        if not self.render_form:
            for field in self.form.fields.values():
                field.widget = forms.HiddenInput()

class ProjectFilter(BaseFilter):
    name = django_filters.CharFilter(
        lookup_expr='icontains', label=_('Название проекта'),
        widget=forms.TextInput(attrs={'placeholder': _('Найти проект...')})
    )
    class Meta:
        model = Project
        fields = ['name']

class TaskCategoryFilter(BaseFilter):
    name = django_filters.CharFilter(
        lookup_expr='icontains', label=_('Название категории'),
        widget=forms.TextInput(attrs={'placeholder': _('Найти категорию...')})
    )
    class Meta:
        model = TaskCategory
        fields = ['name']

class TaskSubcategoryFilter(BaseFilter):
    name = django_filters.CharFilter(
        lookup_expr='icontains', label=_('Название подкатегории'),
        widget=forms.TextInput(attrs={'placeholder': _('Найти подкатегорию...')})
    )
    category = django_filters.ModelChoiceFilter(
        queryset=TaskCategory.objects.all(), label=_('Категория'),
        widget=forms.Select(attrs={'class': 'form-select'})
    )
    class Meta:
        model = TaskSubcategory
        fields = ['name', 'category']

class TaskFilter(BaseFilter):
    q = django_filters.CharFilter(
        method='search_filter', label=_('Поиск'),
        widget=forms.TextInput(attrs={'placeholder': _('Номер, название, описание...')})
    )
    due_date_after = django_filters.DateFilter(
        field_name='due_date', lookup_expr='gte', label=_('Срок не ранее'),
        widget=forms.DateInput(attrs={'type': 'date', 'class': 'form-control'})
    )
    due_date_before = django_filters.DateFilter(
        field_name='due_date', lookup_expr='lte', label=_('Срок не позднее'),
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
    team = django_filters.ModelChoiceFilter(
        queryset=lambda request: Team.objects.all().order_by('name'),
        label=_('Команда задачи'),
        widget=forms.Select(attrs={'class': 'form-select'})
    )
    department = django_filters.ModelChoiceFilter(
        queryset=lambda request: Department.objects.all().order_by('name'),
        label=_('Отдел задачи'),
        widget=forms.Select(attrs={'class': 'form-select'})
    )
    responsible = django_filters.ModelChoiceFilter(
        queryset=User.objects.filter(is_active=True).order_by('username'),
        label=_('Ответственный'),
        method='filter_by_assignment_role',
        widget=forms.Select(attrs={'class': 'form-select'})
    )
    executor = django_filters.ModelChoiceFilter(
        queryset=User.objects.filter(is_active=True).order_by('username'),
        label=_('Исполнитель'),
        method='filter_by_assignment_role',
        widget=forms.Select(attrs={'class': 'form-select'})
    )
    watcher = django_filters.ModelChoiceFilter(
         queryset=User.objects.filter(is_active=True).order_by('username'),
         label=_('Наблюдатель'),
         method='filter_by_assignment_role',
         widget=forms.Select(attrs={'class': 'form-select'})
     )
    participant = django_filters.ModelChoiceFilter(
        queryset=User.objects.filter(is_active=True).order_by('username'),
        field_name='assignments__user',
        label=_('Участник (любая роль)'),
        widget=forms.Select(attrs={'class': 'form-select'})
    )
    status = django_filters.ChoiceFilter(
        choices=Task.StatusChoices.choices,
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
            'q', 'status', 'priority', 'project', 'team', 'department',
            'responsible', 'executor', 'watcher', 'participant',
            'category', 'subcategory', 'created_by',
            'due_date_after', 'due_date_before',
            'created_at_after', 'created_at_before',
        ]

    def search_filter(self, queryset, name, value):
        if not value: return queryset
        return queryset.filter(
            Q(task_number__icontains=value) |
            Q(title__icontains=value) |
            Q(description__icontains=value)
        ).distinct()

    def filter_by_assignment_role(self, queryset, name, value):
         role_to_filter = None
         if name == 'responsible': role_to_filter = TaskAssignment.RoleChoices.RESPONSIBLE
         elif name == 'executor': role_to_filter = TaskAssignment.RoleChoices.EXECUTOR
         elif name == 'watcher': role_to_filter = TaskAssignment.RoleChoices.WATCHER
         else: logger.warning(f"filter_by_assignment_role called with unexpected filter name: {name}"); return queryset
         if value and role_to_filter: return queryset.filter(assignments__user=value, assignments__role=role_to_filter).distinct()
         return queryset