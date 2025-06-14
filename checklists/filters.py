# checklists/filters.py
import django_filters
from django import forms
from django.utils.translation import gettext_lazy as _
from django.contrib.auth import get_user_model
from .models import (
    Checklist,
    ChecklistItemStatus,
    Location,
    ChecklistPoint,
    ChecklistRunStatus,
    ChecklistTemplate,
)
try:
    from tasks.models import TaskCategory
except ImportError:
    TaskCategory = None

User = get_user_model()

class ChecklistHistoryFilter(django_filters.FilterSet):
    template_name = django_filters.CharFilter(
        field_name='template__name',
        lookup_expr='icontains',
        label=_('Шаблон'),
        widget=forms.TextInput(attrs={'placeholder': _('Название шаблона...')})
    )

    category_queryset = TaskCategory.objects.none()
    if TaskCategory and hasattr(TaskCategory, '_meta') and TaskCategory._meta.concrete_model:
        category_queryset = TaskCategory.objects.all().order_by('name')

    category = django_filters.ModelChoiceFilter(
        field_name='template__category',
        queryset=category_queryset,
        label=_('Категория шаблона'),
        widget=forms.Select,
        null_label=_("Все категории")
    )

    performed_by = django_filters.ModelChoiceFilter(
        queryset=User.objects.filter(is_active=True).order_by('username'),
        label=_('Кем выполнен'),
        widget=forms.Select,
        null_label=_("Все исполнители")
    )

    performed_at = django_filters.DateFromToRangeFilter(
         field_name='performed_at',
         label=_('Период выполнения'),
         widget=django_filters.widgets.DateRangeWidget(attrs={'placeholder': _('ГГГГ-ММ-ДД'), 'class': 'flatpickr-range'})
    )

    location = django_filters.ModelChoiceFilter(
         queryset=Location.objects.all().order_by('name'),
         label=_('Местоположение'),
         widget=forms.Select,
         null_label=_("Все местоположения")
    )

    point = django_filters.ModelChoiceFilter(
         queryset=ChecklistPoint.objects.all().order_by('location__name', 'name'),
         label=_('Точка'),
         widget=forms.Select,
         null_label=_("Все точки")
    )

    status = django_filters.ChoiceFilter(
         choices=ChecklistRunStatus.choices,
         label=_('Статус выполнения'),
         widget=forms.Select,
         empty_label=_("Все статусы")
    )

    has_issues = django_filters.BooleanFilter(
        label=_('Есть замечания?'),
        method='filter_has_issues',
        widget=forms.NullBooleanSelect
    )

    item_status = django_filters.ChoiceFilter(
        choices=ChecklistItemStatus.choices,
        label=_('Статус пункта (наличие)'),
        method='filter_by_item_status',
        empty_label=_("Любой статус пункта"),
        widget=forms.Select
    )

    class Meta:
        model = Checklist
        fields = []


    def filter_has_issues(self, queryset, name, value):
        if value is True:
            return queryset.filter(results__status=ChecklistItemStatus.NOT_OK).distinct()
        elif value is False:
            return queryset.exclude(results__status=ChecklistItemStatus.NOT_OK).distinct()
        return queryset

    def filter_by_item_status(self, queryset, name, value):
         if value:
              return queryset.filter(results__status=value).distinct()
         return queryset

    @property
    def is_filtered(self):
        if hasattr(self, 'form') and self.form.is_bound and self.form.is_valid():
            for name, field in self.form.fields.items():
                value = self.form.cleaned_data.get(name)
                if isinstance(field, django_filters.fields.RangeField):
                    if value and (value.start or value.stop):
                        return True
                elif isinstance(field, django_filters.fields.ModelChoiceField):
                    if value:
                        return True
                elif isinstance(field, django_filters.fields.ChoiceField):
                    if value not in [None, '']:
                        return True
                elif value:
                    return True
            return False
        return False


class ChecklistTemplateFilter(django_filters.FilterSet):
    """Filter templates by name, category and activity."""

    name = django_filters.CharFilter(
        field_name="name",
        lookup_expr="icontains",
        label=_("Название"),
        widget=forms.TextInput(attrs={"placeholder": _("Название шаблона...")}),
    )

    template_category_queryset = TaskCategory.objects.none()
    if TaskCategory and hasattr(TaskCategory, "_meta") and TaskCategory._meta.concrete_model:
        template_category_queryset = TaskCategory.objects.all().order_by("name")

    category = django_filters.ModelChoiceFilter(
        field_name="category",
        queryset=template_category_queryset,
        label=_("Категория"),
        widget=forms.Select,
        null_label=_("Все категории"),
    )

    is_active = django_filters.BooleanFilter(
        label=_("Активен"),
        field_name="is_active",
        widget=forms.NullBooleanSelect,
    )

    class Meta:
        model = ChecklistTemplate
        fields = []

    @property
    def is_filtered(self):
        if hasattr(self, "form") and self.form.is_bound and self.form.is_valid():
            for name, field in self.form.fields.items():
                value = self.form.cleaned_data.get(name)
                if isinstance(field, django_filters.fields.RangeField):
                    if value and (value.start or value.stop):
                        return True
                elif isinstance(field, django_filters.fields.ModelChoiceField):
                    if value:
                        return True
                elif isinstance(field, django_filters.fields.ChoiceField):
                    if value not in [None, ""]:
                        return True
                elif value:
                    return True
            return False
        return False
