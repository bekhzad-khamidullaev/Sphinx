from django.contrib import admin
from .models import User, UserProfile, Team, TaskUserRole

admin.site.register(User)
admin.site.register(UserProfile)


# --- КОМАНДЫ ---
@admin.register(Team)
class TeamAdmin(admin.ModelAdmin):
    list_display = ("name", "team_leader", "created_at", "updated_at")
    search_fields = ("name", "description", "team_leader__username")
    list_filter = ("team_leader", "name", "team_leader")
    fieldsets = (
        (None, {"fields": ("name", "description", "team_leader", "members")}),
    )
    filter_horizontal = ("members", "members")

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