# user_profiles/admin.py
from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.db import models
from django.urls import reverse
from django.utils.html import format_html
from django.utils.translation import gettext_lazy as _

from .models import User, Team, Department, TaskUserRole, Role

# --- Inlines for User Admin ---

class TeamMembershipInline(admin.TabularInline):
    """
    Displays Team memberships for a User (Read-Only).
    Membership is managed via the TeamAdmin's filter_horizontal interface.
    """
    model = Team.members.through # Intermediate model for ManyToMany
    verbose_name = _("Членство в команде")
    verbose_name_plural = _("Членства в командах")
    extra = 0
    fields = ('team',)
    readonly_fields = ('team',) # Display only, editing done on Team page
    can_delete = False # Cannot delete membership from user page via this inline

    def has_add_permission(self, request, obj=None):
        # Prevent adding memberships from the user side here
        return False

class TaskUserRoleInlineForUser(admin.TabularInline):
    """Displays Task roles assigned to a User (Read-Only)."""
    model = TaskUserRole
    verbose_name = _("Роль в задаче")
    verbose_name_plural = _("Роли в задачах")
    extra = 0
    fields = ('task_link', 'role', 'created_at')
    readonly_fields = ('task_link', 'role', 'created_at') # Roles assigned via Task admin
    ordering = ('-created_at',)
    can_delete = False

    def task_link(self, obj):
        """Link to the related task in the admin."""
        if obj.task:
            link = reverse("admin:tasks_task_change", args=[obj.task.id])
            # Display task number and title for clarity
            return format_html('<a href="{}">[{}] {}</a>', link, obj.task.task_number or obj.task.id, obj.task.title[:40])
        return "-"
    task_link.short_description = _("Задача")

    def has_add_permission(self, request, obj=None):
        return False

# --- ModelAdmins ---

@admin.register(User)
class UserAdmin(BaseUserAdmin):
    """Admin configuration for the custom User model."""
    list_display = (
        'username', 'email', 'first_name', 'last_name', 'department_link',
        'job_title', 'is_staff', 'is_active'
    )
    list_filter = ('is_staff', 'is_superuser', 'is_active', 'groups', 'department', 'roles')
    search_fields = (
        'username', 'first_name', 'last_name', 'email',
        'department__name', 'job_title', 'roles__name'
    )
    ordering = ('last_name', 'first_name', 'username')

    # Define fieldsets for the change form, grouping related fields
    fieldsets = (
        # BaseUserAdmin standard fields
        (None, {'fields': ('username', 'password')}),
        (_('Personal info'), {'fields': ('first_name', 'last_name', 'email', 'image', 'phone_number')}),
        (_('Organization'), {'fields': ('job_title', 'department', 'roles')}), # Group org info
        (_('Permissions'), {'fields': ('is_active', 'is_staff', 'is_superuser', 'groups', 'user_permissions')}),
        (_('Important dates'), {'fields': ('last_login', 'date_joined')}),
        # Custom settings field if it exists
        # (_('Settings'), {'fields': ('settings',)}),
    )

    # Define fields for the add form
    add_fieldsets = (
        (None, {
            'classes': ('wide',),
            'fields': ('username', 'email', 'password', 'password2'), # Standard creation fields
        }),
         (_('Personal info'), {'fields': ('first_name', 'last_name', 'image', 'phone_number')}),
         (_('Organization'), {'fields': ('job_title', 'department', 'roles')}), # Add org info on creation
    )

    # Use filter_horizontal for easier management of ManyToMany fields
    filter_horizontal = ('groups', 'user_permissions', 'roles') # Add 'roles' here

    # Fields that should not be edited directly in the admin
    readonly_fields = ('last_login', 'date_joined',)

    # Enable autocomplete for ForeignKey fields
    autocomplete_fields = ['department'] # Add 'groups', 'roles' if needed and configured

    # Inlines to display related information
    inlines = [TeamMembershipInline, TaskUserRoleInlineForUser]

    def department_link(self, obj):
        """Link to the user's department in the admin."""
        if obj.department:
            link = reverse("admin:user_profiles_department_change", args=[obj.department.id])
            return format_html('<a href="{}">{}</a>', link, obj.department.name)
        return "-"
    department_link.short_description = _("Отдел")
    department_link.admin_order_field = 'department__name'


@admin.register(Department)
class DepartmentAdmin(admin.ModelAdmin):
    """Admin configuration for the Department model."""
    list_display = ('name', 'parent_link', 'head_link', 'employee_count')
    search_fields = ('name', 'description', 'head__username', 'parent__name')
    list_filter = ('parent', 'head')
    ordering = ('name',)
    autocomplete_fields = ('parent', 'head') # Make FK fields easier to select

    # Group fields logically in the admin form
    fieldsets = (
        (None, {'fields': ('name', 'parent', 'head', 'description')}),
        (_('Сотрудники'), {'fields': ('get_employees_list',)}),
    )
    readonly_fields = ('get_employees_list',)

    def get_queryset(self, request):
        """Annotate queryset with employee count for efficiency."""
        qs = super().get_queryset(request)
        qs = qs.annotate(models.Count('employees', distinct=True)) # Ensure distinct count
        return qs

    def employee_count(self, obj):
        """Display the annotated employee count."""
        return obj.employees__count
    employee_count.short_description = _("Кол-во сотрудников")
    employee_count.admin_order_field = 'employees__count' # Allow sorting

    def get_employees_list(self, obj):
        """Display a preview list of employees with links."""
        employees = obj.employees.all()[:20] # Limit preview for performance
        if not employees:
            return "---"
        links = []
        for emp in employees:
            link = reverse("admin:user_profiles_user_change", args=[emp.id])
            links.append(format_html('<a href="{}">{}</a>', link, emp.display_name))
        output = ", ".join(links)
        total_count = getattr(obj, 'employees__count', obj.employees.count()) # Use annotation if available
        if total_count > 20:
             output += format_html(" … ({} {})", total_count, _('всего'))
        return format_html(output)
    get_employees_list.short_description = _("Сотрудники (первые 20)")

    def parent_link(self, obj):
        """Link to the parent department."""
        if obj.parent:
            link = reverse("admin:user_profiles_department_change", args=[obj.parent.id])
            return format_html('<a href="{}">{}</a>', link, obj.parent.name)
        return "-"
    parent_link.short_description = _("Вышестоящий отдел")
    parent_link.admin_order_field = 'parent__name'

    def head_link(self, obj):
        """Link to the department head."""
        if obj.head:
            link = reverse("admin:user_profiles_user_change", args=[obj.head.id])
            return format_html('<a href="{}">{}</a>', link, obj.head.display_name)
        return "-"
    head_link.short_description = _("Руководитель")
    head_link.admin_order_field = 'head__username'


@admin.register(Team)
class TeamAdmin(admin.ModelAdmin):
    """Admin configuration for the Team model."""
    list_display = ("name", "team_leader_link", "department_link", "member_count", "created_at")
    search_fields = ("name", "description", "team_leader__username", "department__name", "members__username")
    list_filter = ("department", "team_leader")
    ordering = ('name',)
    filter_horizontal = ("members",) # Standard way to manage M2M for team members
    autocomplete_fields = ('team_leader', 'department') # Autocomplete for FKs

    fieldsets = (
        (None, {"fields": ("name", "description", "team_leader", "department")}),
        (_("Участники команды"), {"fields": ("members",)}),
    )

    def get_queryset(self, request):
        """Annotate with member count."""
        qs = super().get_queryset(request)
        qs = qs.annotate(models.Count('members', distinct=True))
        qs = qs.select_related('team_leader', 'department') # Optimize related fields
        return qs

    def member_count(self, obj):
        """Display annotated member count."""
        return obj.members__count
    member_count.short_description = _("Кол-во участников")
    member_count.admin_order_field = 'members__count'

    def team_leader_link(self, obj):
        """Link to the team leader."""
        if obj.team_leader:
            link = reverse("admin:user_profiles_user_change", args=[obj.team_leader.id])
            return format_html('<a href="{}">{}</a>', link, obj.team_leader.display_name)
        return "-"
    team_leader_link.short_description = _("Лидер команды")
    team_leader_link.admin_order_field = 'team_leader__username'

    def department_link(self, obj):
        """Link to the team's department."""
        if obj.department:
            link = reverse("admin:user_profiles_department_change", args=[obj.department.id])
            return format_html('<a href="{}">{}</a>', link, obj.department.name)
        return "-"
    department_link.short_description = _("Отдел")
    department_link.admin_order_field = 'department__name'


@admin.register(TaskUserRole)
class TaskUserRoleAdmin(admin.ModelAdmin):
    """Admin configuration for TaskUserRole (primarily for viewing/debugging)."""
    list_display = ("task_link", "user_link", "role", "created_at")
    list_filter = ("role", "task__project", "user__department")
    search_fields = ("task__task_number", "task__title", "user__username", "user__first_name", "user__last_name")
    list_select_related = ('task', 'user', 'task__project') # Optimize queries
    autocomplete_fields = ('task', 'user')
    readonly_fields = ('created_at',)
    date_hierarchy = 'created_at'

    def task_link(self, obj):
        """Link to the related task."""
        if obj.task:
            link = reverse("admin:tasks_task_change", args=[obj.task.id])
            return format_html('<a href="{}">{}</a>', link, obj.task.task_number or f"Task {obj.task.id}")
        return "-"
    task_link.short_description = _("Задача")
    task_link.admin_order_field = 'task__task_number' # Sort by task number

    def user_link(self, obj):
        """Link to the related user."""
        if obj.user:
            link = reverse("admin:user_profiles_user_change", args=[obj.user.id])
            return format_html('<a href="{}">{}</a>', link, obj.user.display_name)
        return "-"
    user_link.short_description = _("Пользователь")
    user_link.admin_order_field = 'user__username' # Sort by username


@admin.register(Role)
class RoleAdmin(admin.ModelAdmin):
    """Admin configuration for user Roles."""
    list_display = ('name', 'description_excerpt') # Assuming a 'description' field exists
    search_fields = ('name', 'description')
    ordering = ('name',)

    def description_excerpt(self, obj):
        if hasattr(obj, 'description') and obj.description:
             return obj.description[:75] + '...' if len(obj.description) > 75 else obj.description
        return "-"
    description_excerpt.short_description = _("Описание (начало)")