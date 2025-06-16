from django.contrib import admin
from django.urls import reverse
from django.utils.html import format_html
from django.utils.translation import gettext_lazy as _

from .models import (
    Location, ChecklistPoint, ChecklistTemplate, ChecklistSection,
    ChecklistTemplateItem, Checklist, ChecklistResult, AnswerType,
    ChecklistItemStatus, ChecklistRunStatus # Import new models/enums
)

# --- Admin Configuration ---

@admin.register(Location)
class LocationAdmin(admin.ModelAdmin):
    list_display = ('name', 'parent', 'created_at', 'updated_at')
    list_filter = ('parent',)
    search_fields = ('name', 'description')
    ordering = ('name',)

@admin.register(ChecklistPoint)
class ChecklistPointAdmin(admin.ModelAdmin):
    list_display = ('name', 'location', 'created_at', 'updated_at')
    list_filter = ('location',)
    search_fields = ('name', 'description', 'location__name')
    ordering = ('location__name', 'name')
    raw_id_fields = ('location',) # Use raw_id_fields for large number of locations

class ChecklistSectionInline(admin.StackedInline):
    model = ChecklistSection
    extra = 1
    fields = ('title', 'order',) # Removed parent_section as per model structure
    verbose_name = _("Секция")
    verbose_name_plural = _("Секции")
    ordering = ('order', 'title')

class ChecklistTemplateItemInline(admin.StackedInline):
    model = ChecklistTemplateItem
    extra = 1
    # Added answer_type, help_text, default_value, parent_item
    fields = ('section', 'order', 'item_text', 'answer_type', 'target_point', 'help_text', 'default_value', 'parent_item',)
    raw_id_fields = ('section', 'target_point', 'parent_item',) # Use raw_id_fields if many sections/points/items/parents
    verbose_name = _("Пункт шаблона")
    verbose_name_plural = _("Пункты шаблона")
    # Order by section order, then item order
    ordering = ('section__order', 'order',)


@admin.register(ChecklistTemplate)
class ChecklistTemplateAdmin(admin.ModelAdmin):
    list_display = ('name', 'version', 'is_active', 'is_archived', 'target_location', 'category', 'frequency', 'created_at')
    list_filter = ('is_active', 'is_archived', 'category', 'target_location', 'frequency')
    search_fields = ('name', 'description', 'tags__name')
    raw_id_fields = ('category', 'target_location', 'target_point') # Use raw_id_fields for FKs
    # filter_horizontal = ('tags',) # Removed tags due to admin.E013 error
    inlines = [ChecklistSectionInline, ChecklistTemplateItemInline] # Add sections and items as inlines
    # prepopulated_fields = {} # Add if you had a slug field or similar
    fieldsets = (
        (None, {
            'fields': ('name', 'description', 'uuid', 'version', 'is_active', 'is_archived', 'tags')
        }),
        (_('Целевые объекты'), {
            'fields': ('category', 'target_location', 'target_point',) # Reordered fields
        }),
        (_('Планирование'), {
            'fields': ('frequency', 'next_due_date')
        }),
        (_('Метаданные'), {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',) # Hide by default
        })
    )
    readonly_fields = ('uuid', 'created_at', 'updated_at')
    save_on_top = True # Save buttons at the top

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        # Optimize template listing by selecting related objects
        return qs.select_related('category', 'target_location', 'target_point').prefetch_related('tags')

    # Override save_model to apply .clean() validation explicitly if needed
    # Django admin automatically calls clean() on save, so usually not needed.
    # def save_model(self, request, obj, form, change):
    #     obj.clean() # Ensure model-level clean is run
    #     super().save_model(request, obj, form, change)


class ChecklistResultInline(admin.StackedInline):
    model = ChecklistResult
    extra = 0 # Don't add empty forms by default
    # Exclude all specific value fields, they will be read-only or handled differently
    exclude = ('value', 'numeric_value', 'boolean_value', 'date_value', 'datetime_value', 'time_value', 'file_attachment', 'media_url')
    # Display only fields relevant in admin for review/correction
    fields = ('template_item', 'display_value_admin', 'status', 'is_corrected', 'comments', 'recorded_at', 'created_by', 'updated_by')
    readonly_fields = ('template_item', 'display_value_admin', 'recorded_at', 'created_by', 'updated_by') # Make value fields read-only in admin
    raw_id_fields = ('template_item', 'created_by', 'updated_by') # Use raw_id_fields for FKs
    verbose_name = _("Результат пункта")
    verbose_name_plural = _("Результаты пунктов")
    ordering = ('template_item__section__order', 'template_item__order',) # Order by item order within section

    def display_value_admin(self, obj):
        """Helper to display the correct value type in admin."""
        return obj.display_value
    display_value_admin.short_description = _("Ответ") # Column header

    def get_queryset(self, request):
         qs = super().get_queryset(request)
         # Prefetch template item for ordering and display
         return qs.select_related('template_item', 'template_item__section', 'template_item__target_point', 'created_by', 'updated_by')

    # Optional: Define a custom form if you need complex validation in the inline
    # form = YourChecklistResultAdminForm


@admin.register(Checklist)
class ChecklistAdmin(admin.ModelAdmin):
    list_display = ('__str__', 'template', 'status', 'performed_at', 'performed_by', 'location', 'point', 'is_complete', 'score', 'approved_at', 'view_link')
    list_filter = ('status', 'is_complete', 'template', 'location', 'point', 'performed_by', 'approved_by', 'template__category') # Added template category filter
    search_fields = ('template__name', 'notes', 'performed_by__username', 'location__name', 'point__name', 'external_reference')
    raw_id_fields = ('template', 'performed_by', 'related_task', 'location', 'point', 'approved_by')
    inlines = [ChecklistResultInline]
    # score is calculated, completion/approval time/status are set by logic/status changes
    readonly_fields = ('created_at', 'updated_at', 'completion_time', 'approved_at', 'score')
    fieldsets = (
        (None, {
            'fields': ('template', 'performed_by', 'performed_at', 'status', 'is_complete', 'completion_time', 'score')
        }),
        (_('Связанные объекты'), {
            'fields': ('related_task', 'location', 'point', 'external_reference') # Added external_reference
        }),
        (_('Примечания'), { # Renamed section
            'fields': ('notes',)
        }),
        (_('Одобрение/Проверка'), { # Renamed section
            'fields': ('approved_by', 'approved_at',),
            'classes': ('collapse',)
        }),
         (_('Метаданные'), {
            'fields': ('id', 'created_at', 'updated_at'), # Added id
            'classes': ('collapse',)
        })
    )
    ordering = ('-performed_at',)
    save_on_top = True

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        # Optimize checklist listing
        return qs.select_related('template', 'performed_by', 'location', 'point', 'approved_by', 'template__category', 'related_task')

    def view_link(self, obj):
        if obj.pk:
            # Use the history_list detail view name
            url = reverse('checklists:checklist_detail', kwargs={'pk': obj.pk})
<<<<<<< HEAD
            return format_html('<a href="{}" target="_blank"><i class="fas fa-external-link-alt"></i> {}</a>', url, _('Просмотр'))
        return "-"

=======
            return format_html('<a href="{}">{}</a>', url, _('Просмотр'))
        return "-"
    view_link.short_description = _("Ссылка")

    # You might want to override save_model or formfield_for_foreignkey
    # to handle specific logic, e.g., setting status to IN_PROGRESS on first save
    # or limiting location/point choices based on template.
    # Admin handles basic FK saving, signals handle initial result creation.


# Register other models if needed, but they might be covered by inlines or less frequently edited
# admin.site.register(ChecklistSection) # Usually managed via Template inline
# admin.site.register(ChecklistTemplateItem) # Usually managed via Template inline
# admin.site.register(ChecklistResult) # Usually managed via Checklist run inline
>>>>>>> servicedesk
