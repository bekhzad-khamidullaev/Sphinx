# user_profiles/admin.py
from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.utils.translation import gettext_lazy as _

from .models import User, Team, Department, TaskUserRole

# --- Inlines ---

class TeamMembershipInline(admin.TabularInline):
    """Inline to show teams a user is a member of."""
    model = Team.members.through # Access the intermediate M2M model
    extra = 0
    verbose_name = _("Членство в команде")
    verbose_name_plural = _("Членства в командах")
    fields = ('team',)
    readonly_fields = ('team',)
    can_delete = False # Usually manage membership via the Team admin

class TaskUserRoleInlineForUser(admin.TabularInline):
    """Inline to show task roles assigned to a user."""
    model = TaskUserRole
    extra = 0
    fields = ('task', 'role', 'created_at')
    readonly_fields = ('task', 'role', 'created_at') # Roles usually assigned via Task admin
    verbose_name = _("Роль в задаче")
    verbose_name_plural = _("Роли в задачах")
    can_delete = False

# Remove UserProfileInline if UserProfile model is removed
# class UserProfileInline(admin.StackedInline):
#     model = UserProfile
#     can_delete = False
#     verbose_name_plural = _('Профиль')
#     fields = ('team', 'department') # Add fields from profile


# --- ModelAdmins ---

@admin.register(User)
class UserAdmin(BaseUserAdmin):
    """Customize the User admin."""
    # Add custom fields to list display, fieldsets, filter, search
    list_display = ('username', 'email', 'first_name', 'last_name', 'is_staff', 'department', 'job_title')
    list_filter = ('is_staff', 'is_superuser', 'is_active', 'groups', 'department')
    search_fields = ('username', 'first_name', 'last_name', 'email', 'department__name', 'job_title')
    ordering = ('last_name', 'first_name', 'username')

    # Add custom fields to the fieldsets
    # Extend the default fieldsets
    fieldsets = BaseUserAdmin.fieldsets + (
        (_('Дополнительная информация'), {'fields': ('phone_number', 'job_title', 'department', 'image')}),
    )
    # Add custom fields to the add form fieldsets as well
    add_fieldsets = BaseUserAdmin.add_fieldsets + (
        (_('Дополнительная информация'), {'fields': ('first_name', 'last_name', 'email', 'phone_number', 'job_title', 'department', 'image')}),
    )

    inlines = [TeamMembershipInline, TaskUserRoleInlineForUser] # Add inlines
    autocomplete_fields = ['department'] # Autocomplete for department


@admin.register(Department)
class DepartmentAdmin(admin.ModelAdmin):
    """Admin for Company Departments."""
    list_display = ('name', 'parent', 'head', 'employee_count')
    search_fields = ('name', 'description', 'head__username', 'parent__name')
    list_filter = ('parent', 'head')
    ordering = ('name',)
    autocomplete_fields = ('parent', 'head')
    fieldsets = (
        (None, {'fields': ('name', 'parent', 'head', 'description')}),
        (_('Сотрудники'), {'fields': ('get_employees_list',)}), # Display employees
    )
    readonly_fields = ('get_employees_list',)

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        # Annotate with employee count
        qs = qs.annotate(models.Count('employees'))
        return qs

    def employee_count(self, obj):
        return obj.employees__count
    employee_count.short_description = _("Кол-во сотрудников")
    employee_count.admin_order_field = 'employees__count'

    def get_employees_list(self, obj):
        """Display a list of employees in this department."""
        from django.utils.html import format_html
        from django.urls import reverse
        employees = obj.employees.all()[:20] # Limit display for performance
        if not employees:
            return "---"
        links = []
        for emp in employees:
            link = reverse("admin:user_profiles_user_change", args=[emp.id])
            links.append(format_html('<a href="{}">{}</a>', link, emp.display_name))
        output = ", ".join(links)
        if obj.employees.count() > 20:
             output += f" ... ({obj.employees.count()} {_('всего')})"
        return format_html(output)
    get_employees_list.short_description = _("Сотрудники (макс. 20)")


@admin.register(Team)
class TeamAdmin(admin.ModelAdmin):
    list_display = ("name", "team_leader", "department", "member_count", "created_at")
    search_fields = ("name", "description", "team_leader__username", "department__name")
    list_filter = ("department", "team_leader")
    ordering = ('name',)
    filter_horizontal = ("members",) # Use filter_horizontal for easier M2M selection
    autocomplete_fields = ('team_leader', 'department') # Autocomplete for FKs
    fieldsets = (
        (None, {"fields": ("name", "description", "team_leader", "department")}),
        (_("Участники команды"), {"fields": ("members",)}),
    )

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        # Annotate with member count
        qs = qs.annotate(models.Count('members'))
        return qs

    def member_count(self, obj):
        return obj.members__count
    member_count.short_description = _("Кол-во участников")
    member_count.admin_order_field = 'members__count'


@admin.register(TaskUserRole)
class TaskUserRoleAdmin(admin.ModelAdmin):
    """Admin for Task User Roles (primarily for viewing/debugging)."""
    list_display = ("task_link", "user_link", "role", "created_at")
    list_filter = ("role", "task__project", "user__department") # Filter by project/department
    search_fields = ("task__task_number", "task__title", "user__username", "user__first_name", "user__last_name")
    list_select_related = ('task', 'user') # Optimize list view
    autocomplete_fields = ('task', 'user') # Use autocomplete
    readonly_fields = ('created_at',)

    def task_link(self, obj):
        """Link to the task."""
        from django.urls import reverse
        from django.utils.html import format_html
        if obj.task:
            link = reverse("admin:tasks_task_change", args=[obj.task.id])
            return format_html('<a href="{}">{}</a>', link, obj.task.task_number or f"Task {obj.task.id}")
        return "-"
    task_link.short_description = _("Задача")
    task_link.admin_order_field = 'task'

    def user_link(self, obj):
        """Link to the user."""
        from django.urls import reverse
        from django.utils.html import format_html
        if obj.user:
            link = reverse("admin:user_profiles_user_change", args=[obj.user.id])
            return format_html('<a href="{}">{}</a>', link, obj.user.display_name)
        return "-"
    user_link.short_description = _("Пользователь")
    user_link.admin_order_field = 'user'

# Unregister the original Group model if you are not using it extensively
# admin.site.unregister(Group)

# Register standalone Role model if it's kept
# from .models import Role
# @admin.register(Role)
# class RoleAdmin(admin.ModelAdmin):
#     list_display = ('name',)
#     search_fields = ('name',)