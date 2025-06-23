# profiles/admin.py
from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.db import models
from django.urls import reverse
from django.utils.html import format_html
from django.utils.translation import gettext_lazy as _

from .models import User, Team, Department, JobTitle, TeamMembershipUser

class UserTeamsInline(admin.TabularInline):
    model = TeamMembershipUser
    fk_name = 'user'
    verbose_name = _("Участие в команде")
    verbose_name_plural = _("Участия в командах")
    extra = 1
    autocomplete_fields = ('team',)
    fields = ('team', 'date_joined')
    readonly_fields = ('date_joined',)


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    list_display = (
        'username', 'email', 'first_name', 'last_name', 'department_link',
        'job_title_name',
        'get_groups_display',
        'get_teams_display',
        'is_staff', 'is_active'
    )
    list_select_related = ('department', 'job_title')
    list_filter = ('is_staff', 'is_superuser', 'is_active', 'groups', 'teams', 'department', 'job_title')
    search_fields = (
        'username', 'first_name', 'last_name', 'email',
        'department__name', 'job_title__name', 'groups__name', 'teams__name'
    )
    ordering = ('last_name', 'first_name', 'username')

    fieldsets = (
        (None, {"fields": ("username", "password")}),
        (_("Personal info"), {"fields": ("first_name", "last_name", "email", "phone_number", "image")}),
        (_("Organization"), {"fields": ("job_title", "department")}),
        (
            _("Permissions"),
            {
                "fields": (
                    "is_active",
                    "is_staff",
                    "is_superuser",
                    "groups",
                    "user_permissions",
                ),
            },
        ),
        (_("Important dates"), {"fields": ("last_login", "date_joined")}),
    )
    add_fieldsets = (
        (None, {"classes": ("wide",), "fields": ("username", "email", "password", "password2")}),
        (_("Personal info"), {"fields": ("first_name", "last_name", "phone_number", "image")}),
        (_("Organization"), {"fields": ("job_title", "department")}),
        (_("Permissions"), {"fields": ("is_active", "is_staff", "is_superuser", "groups")}),
    )

    filter_horizontal = ('groups', 'user_permissions')
    readonly_fields = ('last_login', 'date_joined')
    autocomplete_fields = ['department', 'job_title', 'groups']

    inlines = [UserTeamsInline]

    def department_link(self, obj):
        if obj.department:
            link = reverse("admin:profiles_department_change", args=[obj.department.id])
            return format_html('<a href="{}">{}</a>', link, obj.department.name)
        return "-"
    department_link.short_description = _("Отдел")
    department_link.admin_order_field = 'department__name'

    @admin.display(description=_('Должность'))
    def job_title_name(self, obj):
        return obj.job_title.name if obj.job_title else "-"
    job_title_name.admin_order_field = 'job_title__name'

    @admin.display(description=_('Группы прав'))
    def get_groups_display(self, obj):
        return ", ".join([g.name for g in obj.groups.all()])

    @admin.display(description=_('Команды'))
    def get_teams_display(self, obj):
        return ", ".join([t.name for t in obj.teams.all()])


@admin.register(Department)
class DepartmentAdmin(admin.ModelAdmin):
    list_display = ('name', 'parent_link', 'head_link', 'employee_count_display')
    search_fields = ('name', 'description', 'head__username', 'parent__name')
    list_filter = ('parent',)
    ordering = ('name',)
    autocomplete_fields = ('parent', 'head')
    fieldsets = (
        (None, {'fields': ('name', 'description')}),
        (_("Структура"), {'fields': ('parent', 'head')}),
    )

    def get_queryset(self, request):
        qs = super().get_queryset(request).annotate(
            employee_count_agg=models.Count('employees', distinct=True)
        ).select_related('parent', 'head')
        return qs

    @admin.display(description=_("Сотрудников"), ordering='employee_count_agg')
    def employee_count_display(self, obj):
        return obj.employee_count_agg

    def parent_link(self, obj):
        if obj.parent:
            link = reverse("admin:profiles_department_change", args=[obj.parent.id])
            return format_html('<a href="{}">{}</a>', link, obj.parent.name)
        return "-"
    parent_link.short_description = _("Вышестоящий отдел")
    parent_link.admin_order_field = 'parent__name'

    def head_link(self, obj):
        if obj.head:
            link = reverse("admin:profiles_user_change", args=[obj.head.id])
            return format_html('<a href="{}">{}</a>', link, obj.head.display_name)
        return "-"
    head_link.short_description = _("Руководитель")
    head_link.admin_order_field = 'head__username'

class TeamMembersInline(admin.TabularInline):
    model = TeamMembershipUser 
    fk_name = 'team'
    verbose_name = _("Участник команды")
    verbose_name_plural = _("Участники команды")
    extra = 1
    fields = ('user', 'date_joined')
    readonly_fields = ('date_joined',)
    autocomplete_fields = ('user',)


@admin.register(Team)
class TeamAdmin(admin.ModelAdmin):
    list_display = ("name", "team_leader_link", "department_link", "member_count_display", "created_at")
    search_fields = ("name", "description", "team_leader__username", "department__name")
    list_filter = ("department",)
    ordering = ('name',)
    autocomplete_fields = ('team_leader', 'department')
    fieldsets = (
        (None, {"fields": ("name", "description", "team_leader", "department")}),
    )
    inlines = [TeamMembersInline]

    def get_queryset(self, request):
        qs = super().get_queryset(request).annotate(
            member_count_agg=models.Count('members', distinct=True)
        ).select_related('team_leader', 'department')
        return qs

    @admin.display(description=_("Участников"), ordering='member_count_agg')
    def member_count_display(self, obj):
        return obj.members.count()

    def team_leader_link(self, obj):
        if obj.team_leader:
            link = reverse("admin:profiles_user_change", args=[obj.team_leader.id])
            return format_html('<a href="{}">{}</a>', link, obj.team_leader.display_name)
        return "-"
    team_leader_link.short_description = _("Лидер команды")
    team_leader_link.admin_order_field = 'team_leader__username'

    def department_link(self, obj):
        if obj.department:
            link = reverse("admin:profiles_department_change", args=[obj.department.id])
            return format_html('<a href="{}">{}</a>', link, obj.department.name)
        return "-"
    department_link.short_description = _("Отдел")
    department_link.admin_order_field = 'department__name'


@admin.register(JobTitle)
class JobTitleAdmin(admin.ModelAdmin):
    list_display = ('name', 'description_excerpt')
    search_fields = ('name', 'description')
    ordering = ('name',)

    def description_excerpt(self, obj):
        if obj.description:
            return obj.description[:75] + '...' if len(obj.description) > 75 else obj.description
        return "-"
    description_excerpt.short_description = _("Описание (начало)")

