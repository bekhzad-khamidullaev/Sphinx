# checklists/filters.py
import django_filters
from django import forms
from django.utils.translation import gettext_lazy as _
from django.contrib.auth import get_user_model
from .models import Checklist, ChecklistTemplate, ChecklistItemStatus
from tasks.models import TaskCategory # Assuming filtering by TaskCategory is desired
from django.db.models import Q

User = get_user_model()

class ChecklistHistoryFilter(django_filters.FilterSet):
    # Filter by Template Name (contains)
    template_name = django_filters.CharFilter(
        field_name='template__name',
        lookup_expr='icontains',
        label=_('Шаблон'),
        widget=forms.TextInput(attrs={'placeholder': _('Название шаблона...')})
    )

    # Filter by Template Category
    category = django_filters.ModelChoiceFilter(
        field_name='template__category',
        queryset=TaskCategory.objects.all() if TaskCategory else TaskCategory.objects.none(), # Handle if TaskCategory not available
        label=_('Категория шаблона'),
        widget=forms.Select
    )

    # Filter by User who performed the checklist
    performed_by = django_filters.ModelChoiceFilter(
        queryset=User.objects.filter(is_active=True).order_by('username'),
        label=_('Кем выполнен'),
        widget=forms.Select
    )

    # Filter by Date Range (Performed At)
    performed_at_after = django_filters.DateFilter(
        field_name='performed_at',
        lookup_expr='date__gte',
        label=_('Выполнен после'),
        widget=forms.DateInput(attrs={'type': 'date', 'class': 'flatpickr-date'}) # Add class for JS picker
    )
    performed_at_before = django_filters.DateFilter(
        field_name='performed_at',
        lookup_expr='date__lte',
        label=_('Выполнен до'),
        widget=forms.DateInput(attrs={'type': 'date', 'class': 'flatpickr-date'}) # Add class for JS picker
    )

    # Filter by location (contains)
    location = django_filters.CharFilter(
        lookup_expr='icontains',
        label=_('Местоположение'),
        widget=forms.TextInput(attrs={'placeholder': _('Зона, объект...')})
    )

    # Filter by presence of issues ('Not OK' status in results)
    has_issues = django_filters.BooleanFilter(
        label=_('Есть проблемы?'),
        method='filter_has_issues',
        widget=forms.NullBooleanSelect # Provides "Yes", "No", "Any" options
    )

    # Filter by related task (using task number or title) - More complex
    # related_task_search = django_filters.CharFilter(
    #     method='filter_related_task',
    #     label=_('Связанная задача'),
    #     widget=forms.TextInput(attrs={'placeholder': _('Номер или название задачи...')})
    # )

    class Meta:
        model = Checklist
        # Specify fields included in the filterset
        # Note: fields mentioned above are automatically included if using field_name
        # Add any direct model fields here if needed, e.g., 'is_complete' (though view filters this)
        fields = [
            'template_name',
            'category',
            'performed_by',
            'performed_at_after',
            'performed_at_before',
            'location',
            'has_issues',
            # 'related_task_search',
        ]

    def filter_has_issues(self, queryset, name, value):
        """ Custom filter method for the 'has_issues' BooleanFilter. """
        if value is True:
            # Return runs where at least one result has 'not_ok' status
            return queryset.filter(results__status=ChecklistItemStatus.NOT_OK).distinct()
        elif value is False:
            # Return runs where *no* result has 'not_ok' status
            return queryset.exclude(results__status=ChecklistItemStatus.NOT_OK).distinct()
        # If value is None (Any), return the original queryset
        return queryset

    # Optional: Implement filter_related_task if needed
    def filter_related_task(self, queryset, name, value):
        if value:
            return queryset.filter(
                Q(related_task__task_number__icontains=value) |
                Q(related_task__title__icontains=value)
            ).distinct()
        return queryset