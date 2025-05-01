# checklists/admin.py
import logging
from django.contrib import admin, messages
from django.urls import path, reverse
from django.utils.html import format_html
from django.utils.translation import gettext_lazy as _
from django.db import models
from django.template.response import TemplateResponse
from django.shortcuts import get_object_or_404, redirect
from django.utils import timezone
from django.db import transaction
from django.forms import inlineformset_factory # Import for inline formset definition
from django.contrib.admin import SimpleListFilter # For custom filters if needed

from .models import (
    Location,
    ChecklistPoint,
    ChecklistTemplate,
    ChecklistTemplateItem,
    Checklist,
    ChecklistResult,
    ChecklistItemStatus,
)
from .forms import ChecklistResultFormSet # Import formset for perform view

# Safely import TaskCategory for filtering
try:
    from tasks.models import TaskCategory
except ImportError:
    TaskCategory = None

logger = logging.getLogger(__name__)


# --- Inlines ---

class ChecklistTemplateItemInline(admin.TabularInline):
    model = ChecklistTemplateItem
    formset = inlineformset_factory( # Use inlineformset_factory here for consistency
        ChecklistTemplate, ChecklistTemplateItem,
        fields=('order', 'item_text', 'target_point'), # Add target_point
        extra=1, can_delete=True, can_order=False,
        # Use admin widgets for better integration
        widgets={
            'item_text': admin.widgets.AdminTextareaWidget(attrs={'rows': 2, 'cols': '60'}),
            'order': admin.widgets.AdminIntegerFieldWidget(attrs={'style': 'width: 4em;'}),
            'target_point': admin.widgets.ForeignKeyRawIdWidget( # Use Raw ID or Autocomplete
                 ChecklistTemplateItem._meta.get_field('target_point').remote_field, admin.site
             )
        }
    )
    fields = ('order', 'item_text', 'target_point') # Fields to display in the inline
    extra = 1
    ordering = ('order',)
    autocomplete_fields = ['target_point'] # Enable autocomplete if ChecklistPointAdmin is set up
    verbose_name = _("Пункт шаблона")
    verbose_name_plural = _("Пункты шаблона")


class ChecklistResultInline(admin.TabularInline):
    model = ChecklistResult
    # Define the fields editable by the formset (exclude non-editable ones like recorded_at, template_item_display)
    formset = inlineformset_factory(
        Checklist, ChecklistResult,
        fields=('status', 'comments'), # Only editable fields here
        extra=0, can_delete=False
    )
    # Define fields to DISPLAY in the inline, including read-only ones
    fields = ('template_item_display', 'status', 'comments', 'recorded_at')
    readonly_fields = (
        "template_item_display",
        "recorded_at",
        "status",
        "comments",
    )  # Readonly in history view
    ordering = ("template_item__order",)
    verbose_name = _("Результат пункта")
    verbose_name_plural = _("Результаты пунктов")

    def template_item_display(self, obj):
        """Display the text of the related template item."""
        return obj.template_item.item_text if obj.template_item else "N/A"
    template_item_display.short_description = _("Пункт")

    # Prevent modifications through the history inline
    def has_add_permission(self, request, obj=None): return False
    def has_change_permission(self, request, obj=None): return False
    def has_delete_permission(self, request, obj=None): return False


# --- ModelAdmins ---

@admin.register(Location)
class LocationAdmin(admin.ModelAdmin):
    list_display = ('name', 'parent', 'description_excerpt')
    search_fields = ('name', 'description', 'parent__name')
    list_filter = ('parent',)
    autocomplete_fields = ('parent',)
    ordering = ('name',)

    def description_excerpt(self, obj):
        if obj.description:
            return obj.description[:50] + '...' if len(obj.description) > 50 else obj.description
        return "-"
    description_excerpt.short_description = _("Описание")

@admin.register(ChecklistPoint)
class ChecklistPointAdmin(admin.ModelAdmin):
    list_display = ('name', 'location_link', 'description_excerpt')
    search_fields = ('name', 'description', 'location__name')
    list_filter = ('location',)
    autocomplete_fields = ('location',) # Enable search/select for location
    ordering = ('location__name', 'name')

    def location_link(self, obj):
        if obj.location:
            link = reverse("admin:checklists_location_change", args=[obj.location.id])
            return format_html('<a href="{}">{}</a>', link, obj.location.name)
        return "-"
    location_link.short_description = _("Местоположение")
    location_link.admin_order_field = 'location__name'

    def description_excerpt(self, obj):
        if obj.description:
            return obj.description[:50] + '...' if len(obj.description) > 50 else obj.description
        return "-"
    description_excerpt.short_description = _("Описание")

@admin.register(ChecklistTemplate)
class ChecklistTemplateAdmin(admin.ModelAdmin):
    list_display = ('name', 'category_display', 'target_location', 'target_point', 'item_count', 'is_active', 'perform_link')
    list_filter = ('is_active', 'category', 'target_location')
    search_fields = ('name', 'description', 'category__name', 'items__item_text', 'target_location__name', 'target_point__name')
    inlines = [ChecklistTemplateItemInline]
    list_select_related = ('category', 'target_location', 'target_point')
    autocomplete_fields = ['category', 'target_location', 'target_point'] # Enable autocomplete
    actions = ["activate_templates", "deactivate_templates"]
    save_on_top = True

    fieldsets = (
        (None, {'fields': ('name', 'category', 'description', 'is_active')}),
        (_("Целевое Местоположение/Точка (Общее)"), {'fields': ('target_location', 'target_point'), 'classes': ('collapse',)}),
        # Inlines will appear after fieldsets
    )

    def get_queryset(self, request):
        # Annotate with item count
        return super().get_queryset(request).annotate(item_count_agg=models.Count('items'))

    def item_count(self, obj):
        # Use annotated value
        return obj.item_count_agg
    item_count.short_description = _("Пунктов")
    item_count.admin_order_field = 'item_count_agg'

    def category_display(self, obj):
        return obj.category.name if obj.category else '-'
    category_display.short_description = _("Категория")
    category_display.admin_order_field = 'category__name'

    def perform_link(self, obj):
        """Link to start performing this checklist template."""
        if obj.is_active:
            url = reverse('admin:checklists_checklisttemplate_perform', args=[obj.pk])
            # Use standard admin button styles if available or simple link
            return format_html('<a href="{}" class="button">{}</a>', url, _("Выполнить"))
        return _("Неактивен")
    perform_link.short_description = _("Запустить")
    perform_link.allow_tags = True # Important for rendering HTML

    # --- Actions ---
    @admin.action(description=_("Активировать выбранные шаблоны"))
    def activate_templates(self, request, queryset):
        updated = queryset.update(is_active=True)
        self.message_user(request, _("%(count)d шаблонов было активировано.") % {'count': updated}, messages.SUCCESS)

    @admin.action(description=_("Деактивировать выбранные шаблоны"))
    def deactivate_templates(self, request, queryset):
        updated = queryset.update(is_active=False)
        self.message_user(request, _("%(count)d шаблонов было деактивировано.") % {'count': updated}, messages.SUCCESS)

    # --- Custom Perform View URL and Logic ---
    def get_urls(self):
        urls = super().get_urls()
        custom_urls = [
            path('<int:template_pk>/perform/', self.admin_site.admin_view(self.perform_checklist_view), name='checklists_checklisttemplate_perform'),
        ]
        return custom_urls + urls

    def perform_checklist_view(self, request, template_pk):
        """ Renders and handles the checklist perform form within the admin. """
        template = get_object_or_404(ChecklistTemplate, pk=template_pk, is_active=True)
        checklist_run = None
        today = timezone.now().date()
        existing_run = Checklist.objects.filter(
            template=template, performed_by=request.user,
            performed_at__date=today, is_complete=False
        ).first()

        if request.method == 'POST':
            run_id = request.POST.get('checklist_run_id')
            if run_id:
                checklist_run = get_object_or_404(Checklist, pk=run_id, template=template, performed_by=request.user, is_complete=False)
            elif existing_run:
                 checklist_run = existing_run
            else:
                 messages.error(request, _("Не удалось найти активный прогон для сохранения."))
                 return redirect(reverse('admin:checklists_checklisttemplate_changelist'))

            # Pass the existing run instance to the formset
            formset = ChecklistResultFormSet(request.POST, instance=checklist_run, prefix='results')
            if formset.is_valid():
                try:
                    with transaction.atomic():
                        formset.save()
                        checklist_run.mark_complete()
                        messages.success(request, _("Чеклист '%(name)s' успешно завершен.") % {'name': template.name})
                        return redirect(reverse('admin:checklists_checklist_changelist')) # Redirect to history list
                except Exception as e:
                    logger.exception(f"Admin: Error saving checklist run {checklist_run.id}: {e}")
                    messages.error(request, _("Ошибка сохранения чеклиста: %(error)s") % {'error': e})
            else:
                 logger.warning(f"Admin: Invalid ChecklistResultFormSet for run {checklist_run.id}: {formset.errors}")
                 messages.error(request, _("Пожалуйста, исправьте ошибки в пунктах чеклиста."))
        else: # GET request
            checklist_run = existing_run
            if not checklist_run:
                # Create new run and initial results
                checklist_run = Checklist.objects.create(
                    template=template, performed_by=request.user,
                    location=template.target_location, point=template.target_point
                )
                results_to_create = []
                items_queryset = template.items.order_by('order')
                # Filter items by run's point only if the run has a point specified
                if checklist_run.point:
                     items_queryset = items_queryset.filter(Q(target_point__isnull=True) | Q(target_point=checklist_run.point))
                elif checklist_run.location:
                      items_queryset = items_queryset.filter(Q(target_point__isnull=True) | Q(target_point__location=checklist_run.location))

                for item in items_queryset:
                    results_to_create.append(ChecklistResult(checklist_run=checklist_run, template_item=item))
                if results_to_create:
                    ChecklistResult.objects.bulk_create(results_to_create)

            # Get queryset ordered correctly for the formset
            queryset = checklist_run.results.select_related('template_item').order_by('template_item__order')
            formset = ChecklistResultFormSet(instance=checklist_run, prefix='results', queryset=queryset)

        # Prepare admin context
        context = {
            **self.admin_site.each_context(request),
            'title': _("Выполнение: %s") % template.name,
            'template': template,
            'checklist_run': checklist_run, # Pass the specific run instance
            'formset': formset,
            'opts': self.model._meta,
            'media': self.media + formset.media, # Combine admin and formset media
            'has_view_permission': self.has_view_permission(request, obj=template),
            'has_change_permission': False,
            'has_delete_permission': False,
            'has_add_permission': False,
        }
        # Render using the admin template
        return TemplateResponse(request, "admin/checklists/perform_checklist.html", context)

@admin.register(Checklist)
class ChecklistAdmin(admin.ModelAdmin):
    list_display = ('__str__', 'performed_by_link', 'performed_at', 'is_complete', 'has_issues_display', 'related_task_link')
    list_filter = ('is_complete', 'performed_at', 'template', 'performed_by', 'location', 'point', ('template__category', admin.RelatedOnlyFieldListFilter))
    search_fields = ('template__name', 'performed_by__username', 'related_task__title', 'location__name', 'point__name', 'notes', 'id') # Search by UUID too
    readonly_fields = ('template', 'performed_by', 'performed_at', 'completion_time', 'checklist_link', 'location', 'point', 'notes', 'related_task') # Make more fields readonly in history view
    list_select_related = ('template', 'performed_by', 'related_task', 'template__category', 'location', 'point')
    inlines = [ChecklistResultInline]
    date_hierarchy = 'performed_at'

    fieldsets = (
        (None, {'fields': ('checklist_link','template', 'performed_by', 'performed_at', 'is_complete', 'completion_time')}),
        (_("Контекст прогона"), {'fields': ('related_task_link_field', 'location', 'point', 'notes'), 'classes': ('collapse',)}), # Use link field
    )
    readonly_fields = ('template', 'performed_by', 'performed_at', 'completion_time', 'checklist_link', 'location', 'point', 'notes', 'related_task_link_field') # Add link field here

    def checklist_link(self, obj):
        """Link to view/edit this specific run."""
        if obj.pk:
             url = reverse('admin:checklists_checklist_change', args=[obj.pk])
             return format_html('<a href="{}">{} {}</a>', url, _("Просмотр Прогона #"), obj.pk)
        return "-"
    checklist_link.short_description = _("Ссылка")

    def performed_by_link(self, obj):
        if obj.performed_by:
            link = reverse("admin:user_profiles_user_change", args=[obj.performed_by.id])
            return format_html('<a href="{}">{}</a>', link, obj.performed_by.display_name)
        return "-"
    performed_by_link.short_description = _("Кем выполнен")
    performed_by_link.admin_order_field = 'performed_by__username'

    def related_task_link(self, obj):
        """Link for list display."""
        if obj.related_task:
             link = reverse("admin:tasks_task_change", args=[obj.related_task.id])
             return format_html('<a href="{}">{}</a>', link, obj.related_task.task_number or obj.related_task.id)
        return "-"
    related_task_link.short_description = _("Связанная задача")
    related_task_link.admin_order_field = 'related_task__task_number'

    def related_task_link_field(self, obj):
        """Link for display within fieldsets (read-only)."""
        return self.related_task_link(obj) # Reuse list display logic
    related_task_link_field.short_description = _("Связанная задача")

    def location_link(self, obj): # For list display
        if obj.location:
            link = reverse("admin:checklists_location_change", args=[obj.location.id])
            return format_html('<a href="{}">{}</a>', link, obj.location.name)
        return "-"
    location_link.short_description = _("Место")
    location_link.admin_order_field = 'location__name'

    def point_link(self, obj): # For list display
        if obj.point:
            link = reverse("admin:checklists_checklistpoint_change", args=[obj.point.id])
            return format_html('<a href="{}">{}</a>', link, obj.point.name)
        return "-"
    point_link.short_description = _("Точка")
    point_link.admin_order_field = 'point__name'

    def has_issues_display(self, obj):
        return obj.has_issues
    has_issues_display.boolean = True
    has_issues_display.short_description = _("Проблемы?")

    # --- Permissions ---
    def has_add_permission(self, request):
        # Prevent creating runs directly in admin
        return False
    def has_change_permission(self, request, obj=None):
         # Allow changing notes maybe, but not results history
        return False # Or check specific user permissions
    def has_delete_permission(self, request, obj=None):
        # Allow deletion only for superusers for cleanup
        return request.user.is_superuser

# Note: ChecklistResultAdmin is usually not needed as results are viewed via ChecklistAdmin inline
# If needed, register it similar to other models.
# @admin.register(ChecklistResult)
# class ChecklistResultAdmin(admin.ModelAdmin): ...