# checklists/filters.py
import django_filters
from django import forms
from django.utils.translation import gettext_lazy as _
from django.contrib.auth import get_user_model

from .models import Checklist, ChecklistTemplate, ChecklistItemStatus
from tasks.models import TaskCategory # Use categories for filtering

User = get_user_model()

# Reusable Tailwind classes (copy from forms.py or define centrally)
BASE_INPUT_CLASSES = "block w-full px-3 py-2 border border-gray-300 rounded-md shadow-sm focus:ring-indigo-500 focus:border-indigo-500 sm:text-sm dark:bg-dark-700 dark:border-dark-600 dark:text-gray-200 dark:placeholder-gray-500"
SELECT_CLASSES = f"form-select {BASE_INPUT_CLASSES}"
DATE_INPUT_CLASSES = f"form-input {BASE_INPUT_CLASSES} flatpickr-date" # Assuming flatpickr

class ChecklistHistoryFilter(django_filters.FilterSet):
    template = django_filters.ModelChoiceFilter(
        queryset=ChecklistTemplate.objects.filter(is_active=True).order_by('name'),
        label=_('Шаблон чеклиста'),
        widget=forms.Select(attrs={'class': SELECT_CLASSES})
    )
    category = django_filters.ModelChoiceFilter(
        field_name='template__category',
        queryset=TaskCategory.objects.all().order_by('name'),
        label=_('Категория шаблона'),
        widget=forms.Select(attrs={'class': SELECT_CLASSES})
    )
    performed_by = django_filters.ModelChoiceFilter(
        queryset=User.objects.filter(is_active=True).order_by('username'),
        label=_('Кем выполнен'),
        widget=forms.Select(attrs={'class': SELECT_CLASSES})
    )
    # Example: Filter by date range
    performed_after = django_filters.DateFilter(
        field_name='performed_at', lookup_expr='date__gte', label=_('Выполнен после'),
        widget=forms.DateInput(attrs={'type': 'date', 'class': DATE_INPUT_CLASSES})
    )
    performed_before = django_filters.DateFilter(
        field_name='performed_at', lookup_expr='date__lte', label=_('Выполнен до'),
        widget=forms.DateInput(attrs={'type': 'date', 'class': DATE_INPUT_CLASSES})
    )
    # Example: Filter by whether issues were found
    has_issues = django_filters.BooleanFilter(
        label=_('Есть проблемы?'),
        method='filter_has_issues',
        widget=forms.Select(choices=[('', '---------'), (True, _('Да')), (False, _('Нет'))], attrs={'class': SELECT_CLASSES})
    )

    class Meta:
        model = Checklist
        fields = ['template', 'category', 'performed_by', 'performed_after', 'performed_before', 'has_issues']

    def filter_has_issues(self, queryset, name, value):
        if value is True:
            # Find runs where at least one result has status NOT_OK
            return queryset.filter(results__status=ChecklistItemStatus.NOT_OK).distinct()
        elif value is False:
            # Find runs where NO result has status NOT_OK
            return queryset.exclude(results__status=ChecklistItemStatus.NOT_OK).distinct()
        return queryset # No filter applied if value is empty/None