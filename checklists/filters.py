import django_filters
from django import forms
from django.utils.translation import gettext_lazy as _
from django.contrib.auth import get_user_model
# Ensure models are imported from the current app
from .models import Checklist, ChecklistTemplate, ChecklistItemStatus, Location, ChecklistPoint, ChecklistRunStatus
try:
    from tasks.models import TaskCategory
except ImportError:
    TaskCategory = None

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
        # Check if TaskCategory exists before querying
        queryset=TaskCategory.objects.all().order_by('name') if TaskCategory else TaskCategory.objects.none(),
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
    performed_at = django_filters.DateFromToRangeFilter(
         field_name='performed_at',
         label=_('Период выполнения'),
         widget=django_filters.widgets.DateRangeWidget(attrs={'placeholder': _('ГГГГ-ММ-ДД'), 'class': 'flatpickr-range'})
    )
    # Example for separate date fields if preferred:
    # performed_at_after = django_filters.DateFilter(
    #     field_name='performed_at',
    #     lookup_expr='date__gte',
    #     label=_('Выполнен после'),
    #     widget=forms.DateInput(attrs={'type': 'date', 'class': 'flatpickr-date'})
    # )
    # performed_at_before = django_filters.DateFilter(
    #     field_name='performed_at',
    #     lookup_expr='date__lte',
    #     label=_('Выполнен до'),
    #     widget=forms.DateInput(attrs={'type': 'date', 'class': 'flatpickr-date'})
    # )


    # Filter by Location (ModelChoiceFilter is better than CharFilter if list is manageable)
    location = django_filters.ModelChoiceFilter(
         queryset=Location.objects.all().order_by('name'),
         label=_('Местоположение'),
         widget=forms.Select
    )

    # Filter by Point (Dependent on Location? Requires JS or custom filter)
    # Simple ModelChoiceFilter for now
    point = django_filters.ModelChoiceFilter(
         queryset=ChecklistPoint.objects.all().order_by('location__name', 'name'),
         label=_('Точка'),
         widget=forms.Select
    )

    # Filter by Status
    status = django_filters.ChoiceFilter(
         choices=ChecklistRunStatus.choices,
         label=_('Статус выполнения'),
         widget=forms.Select
    )

    # Filter by presence of issues ('Not OK' status in results)
    has_issues = django_filters.BooleanFilter(
        label=_('Есть замечания?'),
        method='filter_has_issues',
        widget=forms.NullBooleanSelect # Provides "Yes", "No", "Any" options
    )

    # Filter by specific Checklist Item Status (e.g., show runs with *any* item OK/Not OK/NA)
    # This filters the RUN based on the existence of a RESULT with that status
    item_status = django_filters.ChoiceFilter(
        choices=ChecklistItemStatus.choices,
        label=_('Статус пункта (наличие)'),
        method='filter_by_item_status',
        empty_label=_("Любой статус пункта"),
        widget=forms.Select
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
        # Note: fields mentioned above are automatically included if using field_name or method
        # Add any direct model fields here if needed
        fields = [
            'template_name',
            'category',
            'performed_by',
            'performed_at', # Using DateFromToRangeFilter field name
            # 'performed_at_after', # Alternative separate date fields
            # 'performed_at_before',
            'location',
            'point',
            'status',
            'has_issues',
            'item_status',
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

    def filter_by_item_status(self, queryset, name, value):
         """ Custom filter method to find runs containing at least one item with a specific status. """
         if value:
              return queryset.filter(results__status=value).distinct()
         return queryset # No status selected, return all

    # Optional: Implement filter_related_task if needed
    # def filter_related_task(self, queryset, name, value):
    #     from tasks.models import Task # Ensure Task is importable
    #     if value:
    #         return queryset.filter(
    #             Q(related_task__task_number__icontains=value) |
    #             Q(related_task__title__icontains=value)
    #         ).distinct()
    #     return queryset

    # Add a property to check if the filter has any active values
    @property
    def is_filtered(self):
        return any(field.value for field in self.filters.values() if field.value is not None and field.value != '')