# checklists/admin.py
from django.contrib import admin
from django.urls import path, reverse
from django.utils.html import format_html
from django.utils.translation import gettext_lazy as _
from django.db import models
from django.template.response import TemplateResponse
from django.shortcuts import get_object_or_404, redirect
from django.contrib import messages
from django.utils import timezone
from django.db import transaction
from django.forms import inlineformset_factory
from django.contrib.admin import SimpleListFilter

from .models import (
    Location,
    ChecklistPoint,
    ChecklistTemplate,
    ChecklistTemplateItem,
    Checklist,
    ChecklistResult,
    ChecklistItemStatus,
)
from .forms import ChecklistResultFormSet  # Import formset for perform view


from django.forms import inlineformset_factory
from django.contrib.admin import SimpleListFilter
# Safely import TaskCategory for filtering
try:
    from tasks.models import TaskCategory
except ImportError:
    TaskCategory = None


class ChecklistTemplateItemInline(admin.TabularInline):
    model = ChecklistTemplateItem
    formset = inlineformset_factory( # Use inlineformset_factory here for consistency
        ChecklistTemplate, ChecklistTemplateItem,
        fields=('order', 'item_text', 'target_point'), # Add target_point
        extra=1, can_delete=True, can_order=False,
        widgets={
            'item_text': admin.widgets.AdminTextInputWidget(attrs={'size': '60'}),
            'order': admin.widgets.AdminIntegerFieldWidget(attrs={'style': 'width: 4em;'}),
            'target_point': admin.widgets.ForeignKeyRawIdWidget( # Use Raw ID or Autocomplete
                 ChecklistTemplateItem._meta.get_field('target_point').remote_field, admin.site
             )
        }
    )
    fields = ('order', 'item_text', 'target_point') # Fields to display
    extra = 1
    ordering = ('order',)
    autocomplete_fields = ['target_point']
    verbose_name = _("Пункт шаблона")
    verbose_name_plural = _("Пункты шаблона")


@admin.register(ChecklistTemplate)
class ChecklistTemplateAdmin(admin.ModelAdmin):
    list_display = ('name', 'category_display', 'target_location', 'target_point', 'item_count', 'is_active', 'perform_link') # Added location/point
    list_filter = ('is_active', 'category', 'target_location') # Added location filter
    search_fields = ('name', 'description', 'category__name', 'items__item_text', 'target_location__name', 'target_point__name') # Added search fields
    inlines = [ChecklistTemplateItemInline]
    list_select_related = ('category', 'target_location', 'target_point') # Add related fields
    autocomplete_fields = ['category', 'target_location', 'target_point'] # Enable autocomplete
    actions = ["activate_templates", "deactivate_templates"]

    def get_queryset(self, request):
        # Annotate with item count
        return (
            super().get_queryset(request).annotate(item_count_agg=models.Count("items"))
        )

    def item_count(self, obj):
        # Use annotated value
        return obj.item_count_agg

    item_count.short_description = _("Пунктов")
    item_count.admin_order_field = "item_count_agg"

    def category_display(self, obj):
        return obj.category.name if obj.category else "-"

    category_display.short_description = _("Категория")
    category_display.admin_order_field = "category__name"

    def perform_link(self, obj):
        if obj.is_active:
            url = reverse("admin:checklists_checklisttemplate_perform", args=[obj.pk])
            # Use standard admin button styles
            return format_html(
                '<a href="{}" class="button">{}</a>', url, _("Выполнить")
            )
        return "---"

    perform_link.short_description = _("Запустить")
    perform_link.allow_tags = True

    # --- Actions ---
    @admin.action(description=_("Активировать выбранные шаблоны"))
    def activate_templates(self, request, queryset):
        updated = queryset.update(is_active=True)
        self.message_user(
            request,
            _("%(count)d шаблонов было активировано.") % {"count": updated},
            messages.SUCCESS,
        )

    @admin.action(description=_("Деактивировать выбранные шаблоны"))
    def deactivate_templates(self, request, queryset):
        updated = queryset.update(is_active=False)
        self.message_user(
            request,
            _("%(count)d шаблонов было деактивировано.") % {"count": updated},
            messages.SUCCESS,
        )

    # --- Custom Perform View URL and Logic ---
    def get_urls(self):
        urls = super().get_urls()
        custom_urls = [
            path(
                "<int:template_pk>/perform/",
                self.admin_site.admin_view(self.perform_checklist_view),
                name="checklists_checklisttemplate_perform",
            ),
        ]
        return custom_urls + urls

    def perform_checklist_view(self, request, template_pk):
        """Renders and handles the checklist perform form within the admin."""
        template = get_object_or_404(ChecklistTemplate, pk=template_pk, is_active=True)
        checklist_run = None
        today = timezone.now().date()
        existing_run = Checklist.objects.filter(
            template=template,
            performed_by=request.user,
            performed_at__date=today,
            is_complete=False,
        ).first()

        if request.method == "POST":
            # Try to find the run based on hidden input if form submitted
            run_id = request.POST.get("checklist_run_id")
            if run_id:
                checklist_run = get_object_or_404(
                    Checklist,
                    pk=run_id,
                    template=template,
                    performed_by=request.user,
                    is_complete=False,
                )
            elif existing_run:
                checklist_run = existing_run
            else:
                # This case shouldn't happen with proper GET handling but handle defensively
                messages.error(
                    request, _("Не удалось найти активный прогон для сохранения.")
                )
                return redirect(
                    reverse("admin:checklists_checklisttemplate_changelist")
                )

            formset = ChecklistResultFormSet(
                request.POST, instance=checklist_run, prefix="results"
            )
            if formset.is_valid():
                try:
                    with transaction.atomic():
                        formset.save()
                        checklist_run.mark_complete()
                        messages.success(
                            request,
                            _("Чеклист '%(name)s' успешно завершен.")
                            % {"name": template.name},
                        )
                        return redirect(
                            reverse("admin:checklists_checklist_changelist")
                        )
                except Exception as e:
                    messages.error(
                        request, _("Ошибка сохранения: %(error)s") % {"error": e}
                    )
            else:
                messages.error(
                    request, _("Пожалуйста, исправьте ошибки в пунктах чеклиста.")
                )
        else:  # GET request
            checklist_run = existing_run
            if not checklist_run:
                # Create new run and initial results
                checklist_run = Checklist.objects.create(
                    template=template, performed_by=request.user
                )
                results_to_create = []
                for item in template.items.order_by("order"):
                    results_to_create.append(
                        ChecklistResult(checklist_run=checklist_run, template_item=item)
                    )
                if results_to_create:
                    ChecklistResult.objects.bulk_create(results_to_create)
                # Fetch the created results for the formset
                queryset = (
                    ChecklistResult.objects.filter(checklist_run=checklist_run)
                    .select_related("template_item")
                    .order_by("template_item__order")
                )
            else:
                # Use existing results for the found run
                queryset = checklist_run.results.select_related(
                    "template_item"
                ).order_by("template_item__order")

            formset = ChecklistResultFormSet(
                instance=checklist_run, prefix="results", queryset=queryset
            )

        # Prepare admin context
        context = {
            **self.admin_site.each_context(request),
            "title": _("Выполнение: %s") % template.name,
            "template": template,
            "checklist_run": checklist_run,  # Pass the specific run instance
            "formset": formset,
            "opts": self.model._meta,
            "media": self.media + formset.media,
            "has_view_permission": self.has_view_permission(request, obj=template),
            "has_change_permission": False,  # Cannot change template here
            "has_delete_permission": False,
            "has_add_permission": False,
        }
        # Render using the admin template
        return TemplateResponse(
            request, "admin/checklists/perform_checklist.html", context
        )


class ChecklistResultInline(admin.TabularInline):
    model = ChecklistResult
    formset = inlineformset_factory(
        Checklist, ChecklistResult,
        fields=('status', 'comments'), # Only editable fields here
        # template_item_display is added dynamically/read-only by the form/inline definition below
        extra=0, can_delete=False
    )
    # Define fields to DISPLAY in the inline, including read-only ones
    fields = ('template_item_display', 'status', 'comments', 'recorded_at')
    readonly_fields = (
        "template_item_display",
        "recorded_at",
        "status",
        "comments",
    )  # Readonly in history
    ordering = ("template_item__order",)
    verbose_name = _("Результат пункта")
    verbose_name_plural = _("Результаты пунктов")

    def template_item_display(self, obj):
        return obj.template_item.item_text if obj.template_item else "N/A"

    template_item_display.short_description = _("Пункт")

    def has_add_permission(self, request, obj=None):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(Checklist)
class ChecklistAdmin(admin.ModelAdmin):
    list_display = ('name', 'category_display', 'target_location', 'target_point', 'item_count', 'is_active', 'perform_link') # Added location/point
    list_filter = ('is_active', 'category', 'target_location') # Added location filter
    search_fields = ('name', 'description', 'category__name', 'items__item_text', 'target_location__name', 'target_point__name') # Added search fields
    readonly_fields = (
        "template",
        "performed_by",
        "performed_at",
        "completion_time",
        "checklist_link",
    )
    list_select_related = (
        "template",
        "performed_by",
        "related_task",
        "template__category",
    )
    inlines = [ChecklistResultInline]
    date_hierarchy = "performed_at"

    fieldsets = (
        (
            None,
            {
                "fields": (
                    "checklist_link",
                    "template",
                    "performed_by",
                    "performed_at",
                    "is_complete",
                    "completion_time",
                )
            },
        ),
        (
            _("Доп. инфо"),
            {"fields": ("related_task", "location", "notes"), "classes": ("collapse",)},
        ),
    )

    def checklist_link(self, obj):
        if obj.pk:
            url = reverse("admin:checklists_checklist_change", args=[obj.pk])
            return format_html(
                '<a href="{}">{} {}</a>',
                url,
                _("Просмотр/Редактирование прогона #"),
                obj.pk,
            )
        return "-"

    checklist_link.short_description = _("Ссылка на прогон")

    def performed_by_link(self, obj):
        if obj.performed_by:
            link = reverse(
                "admin:user_profiles_user_change", args=[obj.performed_by.id]
            )
            return format_html(
                '<a href="{}">{}</a>', link, obj.performed_by.display_name
            )
        return "-"

    performed_by_link.short_description = _("Кем выполнен")
    performed_by_link.admin_order_field = "performed_by__username"

    def related_task_link(self, obj):
        if obj.related_task:
            link = reverse("admin:tasks_task_change", args=[obj.related_task.id])
            return format_html(
                '<a href="{}">{}</a>',
                link,
                obj.related_task.task_number or obj.related_task.id,
            )
        return "-"

    related_task_link.short_description = _("Связанная задача")
    related_task_link.admin_order_field = "related_task"

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False  # Prevent editing history

    def has_delete_permission(self, request, obj=None):
        return request.user.is_superuser  # Allow deletion only for superusers

    def has_issues_display(self, obj):
        return obj.has_issues

    has_issues_display.boolean = True
    has_issues_display.short_description = _("Проблемы?")


@admin.register(Location)
class LocationAdmin(admin.ModelAdmin):
    list_display = ('name', 'parent', 'description_excerpt')
    search_fields = ('name', 'description', 'parent__name')
    list_filter = ('parent',)
    autocomplete_fields = ('parent',)

    def description_excerpt(self, obj):
        return obj.description[:50] + '...' if obj.description and len(obj.description) > 50 else obj.description
    description_excerpt.short_description = _("Описание")

@admin.register(ChecklistPoint)
class ChecklistPointAdmin(admin.ModelAdmin):
    list_display = ('name', 'location_link', 'description_excerpt')
    search_fields = ('name', 'description', 'location__name')
    list_filter = ('location',)
    autocomplete_fields = ('location',)
    ordering = ('location__name', 'name')

    def location_link(self, obj):
        if obj.location:
            link = reverse("admin:checklists_location_change", args=[obj.location.id])
            return format_html('<a href="{}">{}</a>', link, obj.location.name)
        return "-"
    location_link.short_description = _("Местоположение")
    location_link.admin_order_field = 'location__name'

    def description_excerpt(self, obj):
        return obj.description[:50] + '...' if obj.description and len(obj.description) > 50 else obj.description
    description_excerpt.short_description = _("Описание")

