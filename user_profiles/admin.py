# user_profiles/admin.py
from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.db import models
from django.urls import reverse
from django.utils.html import format_html
from django.utils.translation import gettext_lazy as _

# Import models from this app - REMOVE old Role, ADD JobTitle
from .models import User, Team, Department, TaskUserRole, JobTitle

# --- Inlines for User Admin (TeamMembershipInline, TaskUserRoleInlineForUser remain the same) ---

class TeamMembershipInline(admin.TabularInline):
    model = Team.members.through
    verbose_name = _("Членство в команде")
    verbose_name_plural = _("Членства в командах")
    extra = 0
    fields = ('team_link',)
    readonly_fields = ('team_link',)
    can_delete = False
    autocomplete_fields = ('team',)

    def team_link(self, instance):
        team = instance.team
        link = reverse("admin:user_profiles_team_change", args=[team.id])
        return format_html('<a href="{}">{}</a>', link, team.name)
    team_link.short_description = _("Команда")

    def has_add_permission(self, request, obj=None): return False

class TaskUserRoleInlineForUser(admin.TabularInline):
    model = TaskUserRole
    verbose_name = _("Роль в задаче")
    verbose_name_plural = _("Роли в задачах")
    extra = 0
    fields = ('task_link', 'role', 'created_at')
    readonly_fields = ('task_link', 'role', 'created_at')
    ordering = ('-created_at',)
    can_delete = False
    max_num = 10 # Limit display

    def task_link(self, obj):
        if obj.task:
            link = reverse("admin:tasks_task_change", args=[obj.task.id])
            return format_html('<a href="{}">[{}] {}</a>', link, obj.task.task_number or obj.task.id, obj.task.title[:40])
        return "-"
    task_link.short_description = _("Задача")

    def has_add_permission(self, request, obj=None): return False

# --- ModelAdmins ---

@admin.register(User)
class UserAdmin(BaseUserAdmin):
    """Admin configuration for the custom User model."""
    list_display = (
        'username', 'email', 'first_name', 'last_name', 'department_link',
        'job_title', # Display the new JobTitle field
        'get_groups', # Keep displaying Permission Groups
        'is_staff', 'is_active'
    )
    list_select_related = ('department', 'job_title') # Optimize list query
    # Filter by JobTitle and standard Groups
    list_filter = ('is_staff', 'is_superuser', 'is_active', 'groups', 'department', 'job_title')
    search_fields = (
        'username', 'first_name', 'last_name', 'email',
        'department__name', 'job_title__name', 'groups__name' # Search JobTitle and Group names
    )
    ordering = ('last_name', 'first_name', 'username')

    # Update fieldsets to use job_title instead of primary_role/roles
    fieldsets = BaseUserAdmin.fieldsets + (
        (_('Дополнительная информация'), {'fields': ('image', 'phone_number')}),
        (_('Организация'), {'fields': ('job_title', 'department')}), # Use job_title ForeignKey
        # Permissions section (groups, user_permissions) is already in BaseUserAdmin.fieldsets
    )

    # Update add_fieldsets
    add_fieldsets = BaseUserAdmin.add_fieldsets + (
         (_('Дополнительная информация'), {'fields': ('first_name', 'last_name', 'email', 'image', 'phone_number')}),
         (_('Организация'), {'fields': ('job_title', 'department')}), # Use job_title ForeignKey
    )

    # filter_horizontal for standard ManyToMany permission fields
    filter_horizontal = ('groups', 'user_permissions')

    readonly_fields = ('last_login', 'date_joined',)
    autocomplete_fields = ['department', 'job_title', 'groups'] # Autocomplete JobTitle and Groups

    inlines = [TeamMembershipInline, TaskUserRoleInlineForUser]

    def department_link(self, obj):
        if obj.department:
            link = reverse("admin:user_profiles_department_change", args=[obj.department.id])
            return format_html('<a href="{}">{}</a>', link, obj.department.name)
        return "-"
    department_link.short_description = _("Отдел")
    department_link.admin_order_field = 'department__name'

    @admin.display(description=_('Группы прав'))
    def get_groups(self, obj):
        """Display assigned Django groups."""
        return ", ".join([g.name for g in obj.groups.all()])


@admin.register(Department)
class DepartmentAdmin(admin.ModelAdmin):
    # ... (DepartmentAdmin as before) ...
    list_display = ('name', 'parent_link', 'head_link', 'employee_count')
    search_fields = ('name', 'description', 'head__username', 'parent__name')
    list_filter = ('parent', 'head')
    ordering = ('name',)
    autocomplete_fields = ('parent', 'head')
    fieldsets = (
        (None, {'fields': ('name', 'parent', 'head', 'description')}),
    )
    def get_queryset(self, request):
        qs = super().get_queryset(request).annotate(employee_count_agg=models.Count('employees', distinct=True))
        qs = qs.select_related('parent', 'head')
        return qs
    def employee_count(self, obj): return obj.employee_count_agg
    employee_count.short_description = _("Сотрудников")
    employee_count.admin_order_field = 'employee_count_agg'
    def parent_link(self, obj):
        if obj.parent: link = reverse("admin:user_profiles_department_change", args=[obj.parent.id]); return format_html('<a href="{}">{}</a>', link, obj.parent.name)
        return "-"
    parent_link.short_description = _("Вышестоящий отдел"); parent_link.admin_order_field = 'parent__name'
    def head_link(self, obj):
        if obj.head: link = reverse("admin:user_profiles_user_change", args=[obj.head.id]); return format_html('<a href="{}">{}</a>', link, obj.head.display_name)
        return "-"
    head_link.short_description = _("Руководитель"); head_link.admin_order_field = 'head__username'

@admin.register(Team)
class TeamAdmin(admin.ModelAdmin):
    # ... (TeamAdmin as before, ensure autocomplete_fields includes 'members') ...
    list_display = ("name", "team_leader_link", "department_link", "member_count", "created_at")
    search_fields = ("name", "description", "team_leader__username", "department__name", "members__username")
    list_filter = ("department", "team_leader")
    ordering = ('name',)
    filter_horizontal = ("members",)
    autocomplete_fields = ('team_leader', 'department', 'members') # Added members
    fieldsets = ( (None, {"fields": ("name", "description", "team_leader", "department")}), (_("Участники команды"), {"fields": ("members",)}),)
    def get_queryset(self, request): qs = super().get_queryset(request).annotate(member_count_agg=models.Count('members', distinct=True)); qs = qs.select_related('team_leader', 'department'); return qs
    def member_count(self, obj): return obj.member_count_agg
    member_count.short_description = _("Участников"); member_count.admin_order_field = 'member_count_agg'
    def team_leader_link(self, obj):
        if obj.team_leader: link = reverse("admin:user_profiles_user_change", args=[obj.team_leader.id]); return format_html('<a href="{}">{}</a>', link, obj.team_leader.display_name)
        return "-"
    team_leader_link.short_description = _("Лидер команды"); team_leader_link.admin_order_field = 'team_leader__username'
    def department_link(self, obj):
        if obj.department: link = reverse("admin:user_profiles_department_change", args=[obj.department.id]); return format_html('<a href="{}">{}</a>', link, obj.department.name)
        return "-"
    department_link.short_description = _("Отдел"); department_link.admin_order_field = 'department__name'


@admin.register(TaskUserRole)
class TaskUserRoleAdmin(admin.ModelAdmin):
    # ... (TaskUserRoleAdmin as before) ...
    list_display = ("task_link", "user_link", "role", "created_at")
    list_filter = ("role", "task__project", "user__department", "user__job_title") # Filter by job title
    search_fields = ("task__task_number", "task__title", "user__username", "user__first_name", "user__last_name", "user__job_title__name") # Search job title
    list_select_related = ('task', 'user', 'task__project', 'user__job_title') # Select job title
    autocomplete_fields = ('task', 'user')
    readonly_fields = ('created_at',)
    date_hierarchy = 'created_at'
    def task_link(self, obj):
        if obj.task: link = reverse("admin:tasks_task_change", args=[obj.task.id]); return format_html('<a href="{}">{}</a>', link, obj.task.task_number or f"Task {obj.task.id}")
        return "-"
    task_link.short_description = _("Задача"); task_link.admin_order_field = 'task__task_number'
    def user_link(self, obj):
        if obj.user: link = reverse("admin:user_profiles_user_change", args=[obj.user.id]); return format_html('<a href="{}">{}</a>', link, obj.user.display_name)
        return "-"
    user_link.short_description = _("Пользователь"); user_link.admin_order_field = 'user__username'

# --- Register NEW JobTitle Model ---
@admin.register(JobTitle)
class JobTitleAdmin(admin.ModelAdmin):
    """Admin configuration for Job Titles."""
    list_display = ('name', 'description_excerpt')
    search_fields = ('name', 'description')
    ordering = ('name',)

    def description_excerpt(self, obj):
        if hasattr(obj, 'description') and obj.description:
             return obj.description[:75] + '...' if len(obj.description) > 75 else obj.description
        return "-"
    description_excerpt.short_description = _("Описание (начало)")

# --- REMOVE registration for the old standalone Role model ---
# @admin.register(Role)
# class RoleAdmin(admin.ModelAdmin): ...