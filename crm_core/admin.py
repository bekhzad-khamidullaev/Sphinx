from django.contrib import admin
from django.utils.translation import gettext_lazy as _
from .models import (
    Campaign, Team, TaskCategory, TaskSubcategory,
    Task, TaskPhoto, TaskUserRole
)

# --- КАМПАНИИ ---
@admin.register(Campaign)
class CampaignAdmin(admin.ModelAdmin):
    list_display = ("name", "start_date", "end_date", "created_at")
    search_fields = ("name", "description")
    list_filter = ("start_date", "end_date")
    date_hierarchy = "created_at"
    fieldsets = (
        (None, {"fields": ("name", "description")}),
        (_("Даты"), {"fields": ("start_date", "end_date"), "classes": ("collapse",)}),
    )

# --- КОМАНДЫ ---
@admin.register(Team)
class TeamAdmin(admin.ModelAdmin):
    list_display = ("name", "team_leader", "created_at", "updated_at")
    search_fields = ("name", "description", "team_leader__username")
    list_filter = ("team_leader", "task_categories")
    fieldsets = (
        (None, {"fields": ("name", "description", "team_leader", "members", "task_categories")}),
    )
    filter_horizontal = ("members", "task_categories")

# --- КАТЕГОРИИ ---
@admin.register(TaskCategory)
class TaskCategoryAdmin(admin.ModelAdmin):
    list_display = ("name", "created_at", "updated_at")
    search_fields = ("name", "description")

@admin.register(TaskSubcategory)
class TaskSubcategoryAdmin(admin.ModelAdmin):
    list_display = ("name", "category", "created_at", "updated_at")
    list_filter = ("category",)
    search_fields = ("name", "description", "category__name")

# --- INLINE КЛАССЫ ---
class TaskPhotoInline(admin.TabularInline):
    model = TaskPhoto
    extra = 1

class TaskUserRoleInline(admin.TabularInline):
    model = TaskUserRole
    extra = 1
    fk_name = "task"

# --- РОЛИ В ЗАДАЧАХ ---
@admin.register(TaskUserRole)
class TaskUserRoleAdmin(admin.ModelAdmin):
    list_display = ("task", "user", "role")
    list_filter = ("role", "task", "user")
    search_fields = ("task__task_number", "user__username", "role")

# --- ЗАДАЧИ ---
@admin.register(Task)
class TaskAdmin(admin.ModelAdmin):
    inlines = [TaskPhotoInline, TaskUserRoleInline]
    list_display = ("task_number", "campaign", "status", "priority", "deadline", "assignee", "created_at")
    list_filter = ("status", "priority", "category", "subcategory", "campaign", "team", "assignee", "deadline", "created_at")
    search_fields = ("task_number", "description", "campaign__name", "assignee__username", "team__name")
    ordering = ("task_number",)
    date_hierarchy = "created_at"
    
    fieldsets = (
        (None, {"fields": ("task_number", "campaign", "description")}),
        (_("Подробности"), {"fields": ("category", "subcategory", "status", "priority", "assignee", "team")}),
        (_("Сроки"), {"fields": ("deadline", "start_date", "completion_date"), "classes": ("collapse",)}),
        (_("Фото/Вложения"), {"fields": ("task_photos",), "classes": ("collapse",)}),
        (_("Системная информация"), {
            "fields": ("created_by", "created_at", "updated_at"),
            "classes": ("collapse", "wide"),
            "description": _("Системная информация (только для чтения)"),
        }),
    )

    readonly_fields = ("task_number", "created_at", "updated_at", "created_by")

    def save_model(self, request, obj, form, change):
        """Автоматически устанавливает автора задачи при создании."""
        if not obj.created_by:
            obj.created_by = request.user
        super().save_model(request, obj, form, change)


# --- ФОТО К ЗАДАЧАМ ---
@admin.register(TaskPhoto)
class TaskPhotoAdmin(admin.ModelAdmin):
    list_display = ("task", "uploaded_at", "description")
    list_filter = ("uploaded_at", "task")
    search_fields = ("description", "task__task_number")
    date_hierarchy = "uploaded_at"
    fieldsets = (
        (None, {"fields": ("task", "photo", "description")}),
        (_("Системная информация"), {
            "fields": ("uploaded_at",),
            "classes": ("collapse", "wide"),
            "description": _("Системная информация (только для чтения)")
        }),
    )
    readonly_fields = ("uploaded_at",)
