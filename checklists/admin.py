# checklists/admin.py
from django.contrib import admin
from django.utils.translation import gettext_lazy as _
from .models import (
    ChecklistTemplate,
    ChecklistTemplateItem,
    Checklist,
    ChecklistResult
)
from tasks.models import TaskCategory # To use in filter

class ChecklistTemplateItemInline(admin.TabularInline):
    model = ChecklistTemplateItem
    extra = 1
    fields = ('order', 'item_text')
    ordering = ('order',)
    verbose_name = _("Пункт шаблона")
    verbose_name_plural = _("Пункты шаблона")

@admin.register(ChecklistTemplate)
class ChecklistTemplateAdmin(admin.ModelAdmin):
    list_display = ('name', 'category', 'item_count', 'is_active', 'created_at')
    list_filter = ('is_active', 'category')
    search_fields = ('name', 'description', 'category__name')
    inlines = [ChecklistTemplateItemInline]
    list_select_related = ('category',)

    def item_count(self, obj):
        return obj.items.count()
    item_count.short_description = _("Кол-во пунктов")

class ChecklistResultInline(admin.TabularInline):
    model = ChecklistResult
    extra = 0 # Don't add empty ones by default when viewing history
    fields = ('template_item_display', 'status', 'comments', 'recorded_at')
    readonly_fields = ('template_item_display', 'recorded_at')
    ordering = ('template_item__order',)
    can_delete = False # Usually don't delete individual results from history view

    def template_item_display(self, obj):
        return obj.template_item.item_text
    template_item_display.short_description = _("Пункт чеклиста")

    def has_add_permission(self, request, obj=None):
        # Prevent adding results directly through the admin inline for past runs
        return False

@admin.register(Checklist)
class ChecklistAdmin(admin.ModelAdmin):
    list_display = ('template', 'performed_by', 'performed_at', 'is_complete', 'has_issues_display', 'related_task', 'location')
    list_filter = ('is_complete', 'performed_at', 'template', 'performed_by', ('template__category', admin.RelatedOnlyFieldListFilter))
    search_fields = ('template__name', 'performed_by__username', 'related_task__title', 'location', 'notes')
    readonly_fields = ('template', 'performed_by', 'performed_at', 'completion_time')
    list_select_related = ('template', 'performed_by', 'related_task', 'template__category')
    inlines = [ChecklistResultInline]
    date_hierarchy = 'performed_at'

    fieldsets = (
        (None, {'fields': ('template', 'performed_by', 'performed_at', 'is_complete', 'completion_time')}),
        (_("Дополнительная информация"), {'fields': ('related_task', 'location', 'notes'), 'classes': ('collapse',)}),
    )

    def has_add_permission(self, request):
        # Checklists should be created via the 'Perform Checklist' view, not admin
        return False

    def has_change_permission(self, request, obj=None):
        # Prevent changing historical checklist data easily
        return False # Or return request.user.is_superuser

    def has_issues_display(self, obj):
        return obj.has_issues
    has_issues_display.boolean = True
    has_issues_display.short_description = _("Проблемы?")

@admin.register(ChecklistResult)
class ChecklistResultAdmin(admin.ModelAdmin):
    list_display = ('checklist_run', 'template_item', 'status', 'comments_excerpt', 'recorded_at')
    list_filter = ('status', 'recorded_at', 'checklist_run__template')
    search_fields = ('template_item__item_text', 'comments', 'checklist_run__template__name')
    list_select_related = ('checklist_run', 'template_item', 'checklist_run__template')
    readonly_fields = ('checklist_run', 'template_item', 'recorded_at')

    def comments_excerpt(self, obj):
        return obj.comments[:50] + '...' if obj.comments and len(obj.comments) > 50 else obj.comments
    comments_excerpt.short_description = _("Комментарий (начало)")

    def has_add_permission(self, request): return False
    def has_change_permission(self, request, obj=None): return False # Results shouldn't be changed historically
    def has_delete_permission(self, request, obj=None): return False