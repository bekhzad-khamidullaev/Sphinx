# tasks/admin.py
import logging
from django.contrib import admin
from django.urls import path, reverse
from django.utils.translation import gettext_lazy as _
from django.db import models
from django.utils.html import format_html
from django.shortcuts import redirect, render
from django.utils import timezone
from django.contrib import messages # Import messages framework

# Import views using the alias established in the previous step
from .views import report as report_views
from .models import Project, TaskCategory, TaskSubcategory, Task, TaskPhoto
# Ensure TaskUserRole is correctly imported or handle potential ImportError
import logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

try:
    from user_profiles.models import TaskUserRole
except ImportError:
    TaskUserRole = None
    logger.warning("TaskUserRole model not found. Task admin features related to user roles might be limited.")

logger = logging.getLogger(__name__)

# --- Inlines ---
class TaskPhotoInline(admin.TabularInline):
    model = TaskPhoto
    extra = 1
    fields = ('photo', 'thumbnail_preview', 'description', 'uploaded_by', 'created_at')
    readonly_fields = ('created_at', 'uploaded_by', 'thumbnail_preview')
    verbose_name = _("Фотография")
    verbose_name_plural = _("Фотографии")
    autocomplete_fields = ('uploaded_by',) # Assuming User model is registered with search_fields

    def save_formset(self, request, form, formset, change):
        instances = formset.save(commit=False)
        for inst in instances:
            if not inst.pk and not inst.uploaded_by_id: # Set uploader only for new photos if not already set
                inst.uploaded_by = request.user
        # Save instances to the database
        formset.save()
        # Save many-to-many relationships if the inline model had any (TaskPhoto doesn't)
        # formset.save_m2m() # Not needed for TaskPhoto but good practice if M2M exists

    def thumbnail_preview(self, obj):
        if obj.photo:
            # Provide link to full image along with thumbnail
            return format_html('<a href="{0}" target="_blank"><img src="{0}" style="max-height: 40px; max-width: 70px;" /></a>', obj.photo.url)
        return "-"
    thumbnail_preview.short_description = _("Миниатюра")

# Only define TaskUserRoleInline if the model was successfully imported
if TaskUserRole:
    class TaskUserRoleInline(admin.TabularInline):
        model = TaskUserRole
        extra = 1
        fields = ('user', 'role', 'created_at')
        readonly_fields = ('created_at',)
        autocomplete_fields = ('user',) # Assumes User model is registered for autocomplete
        verbose_name = _("Роль пользователя")
        verbose_name_plural = _("Роли пользователей")
else:
    # Define a placeholder or simply don't use it in TaskAdmin.inlines
    TaskUserRoleInline = None

# --- ModelAdmins ---

@admin.register(Project)
class ProjectAdmin(admin.ModelAdmin):
    list_display = ("name", "start_date", "end_date", "created_at", "display_task_count")
    search_fields = ("name", "description")
    list_filter = ("start_date", "end_date", "created_at")
    date_hierarchy = "created_at"
    fieldsets = (
        (None, {"fields": ("name", "description")}),
        (_("Даты"), {"fields": ("start_date", "end_date")}),
    )

    def get_queryset(self, request):
        # Annotate directly in the admin queryset for efficiency
        qs = super().get_queryset(request).annotate(
            task_count_annotation=models.Count('tasks')
        )
        return qs

    def display_task_count(self, obj):
        # Use the annotated value
        return obj.task_count_annotation
    display_task_count.short_description = _("Кол-во задач")
    display_task_count.admin_order_field = 'task_count_annotation' # Enable sorting

@admin.register(TaskCategory)
class TaskCategoryAdmin(admin.ModelAdmin):
    list_display = ("name", "created_at", "updated_at")
    search_fields = ("name", "description")

@admin.register(TaskSubcategory)
class TaskSubcategoryAdmin(admin.ModelAdmin):
    list_display = ("name", "category", "created_at", "updated_at")
    list_filter = ("category",)
    search_fields = ("name", "description", "category__name")
    list_select_related = ('category',) # Optimize fetching category name
    autocomplete_fields = ('category',) # Assuming TaskCategoryAdmin is registered

@admin.register(Task)
class TaskAdmin(admin.ModelAdmin):
    # Dynamically set inlines based on whether TaskUserRoleInline is available
    inlines = [inline for inline in [TaskUserRoleInline, TaskPhotoInline] if inline is not None]

    list_display = (
        "task_number", "title", "project_link", "status_display",
        "priority_display", "deadline", "assigned_users_display",
        "created_by_link", "created_at"
    )
    list_filter = (
        "status", "priority", "project", "category", "subcategory",
        "deadline", "created_at",
        # Only add user role filters if TaskUserRole exists
        *(("user_roles__user", "user_roles__role") if TaskUserRole else ())
    )
    search_fields = (
        "task_number", "title", "description", "project__name",
        "created_by__username",
        # Only add user role search fields if TaskUserRole exists
        *(("user_roles__user__username", "user_roles__user__first_name", "user_roles__user__last_name") if TaskUserRole else ())
    )
    ordering = ("-created_at", "priority", "deadline")
    date_hierarchy = "created_at"
    readonly_fields = ("task_number", "created_at", "updated_at", "created_by_link", "completion_date")
    list_select_related = ('project', 'category', 'subcategory', 'created_by')
    autocomplete_fields = ('project', 'category', 'subcategory', 'created_by')
    fieldsets = (
        (None, {"fields": ("task_number", "project", "title", "description")}),
        (_("Классификация и Статус"), {"fields": ("category", "subcategory", "status", "priority")}),
        (_("Сроки и Оценка"), {"fields": ("start_date", "deadline", "completion_date", "estimated_time"), "classes": ("collapse",)}),
        (_("Системная информация"), {"fields": ("created_by_link", "created_at", "updated_at"), "classes": ("collapse",)}),
    )
    change_list_template = "admin/tasks/change_list_with_reports.html" # Ensure this template exists

    def get_urls(self):
        urls = super().get_urls()
        info = self.model._meta.app_label, self.model._meta.model_name

        # Define report views to be linked
        # Ensure these functions/classes exist in report_views
        report_map = {
            'export_excel': getattr(report_views, 'export_tasks_to_excel', None),
            'completed': getattr(report_views, 'completed_tasks_report', None),
            'overdue': getattr(report_views, 'overdue_tasks_report', None),
            'active': getattr(report_views, 'active_tasks_report', None),
            'performance': getattr(report_views, 'team_performance_report', None),
            'workload': getattr(report_views, 'employee_workload_report', None),
            'abc': getattr(report_views, 'abc_analysis_report', None),
            'sla': getattr(report_views, 'sla_report', None),
            'duration': getattr(report_views, 'task_duration_report', None),
            'issues': getattr(report_views, 'issues_report', None),
            'delay_reasons': getattr(report_views, 'delay_reasons_report', None),
            'cancelled': getattr(report_views, 'cancelled_tasks_report', None),
            'chart_progress': getattr(report_views, 'task_progress_chart', None),
            'chart_gantt': getattr(report_views, 'gantt_chart', None),
            'summary': getattr(report_views, 'TaskSummaryReportView', None), # Use CBV directly
            'index': getattr(report_views, 'ReportIndexView', None) # Link to index view
        }

        custom_urls = [
            path('reports/', self.admin_site.admin_view(self.report_list_view), name='%s_%s_report_index' % info), # Main report list page
        ]

        # Add paths only if the corresponding view exists
        for name, view_func_or_class in report_map.items():
            if view_func_or_class:
                # Handle CBVs and function views differently
                if isinstance(view_func_or_class, type): # It's a class (CBV)
                    view_to_use = view_func_or_class.as_view()
                else: # It's a function
                    view_to_use = view_func_or_class

                url_pattern = f'reports/{name}/'
                # Special case for index (already added) or export (no trailing slash?)
                if name == 'index': continue # Already handled above
                # if name == 'export_excel': url_pattern = f'reports/export/excel/' # Optional: no trailing slash

                custom_urls.append(
                    path(url_pattern, self.admin_site.admin_view(view_to_use), name=f'%s_%s_report_{name}' % info)
                )
            else:
                 logger.warning(f"Report view '{name}' not found in tasks.views.report. Skipping URL.")


        return custom_urls + urls

    # --- Report List View (for admin interface) ---
    def report_list_view(self, request):
        context = dict(
           self.admin_site.each_context(request),
           title=_('Отчеты по задачам'),
           opts=self.model._meta,
           app_label=self.model._meta.app_label,
        )
        report_urls = {}
        info = self.model._meta.app_label, self.model._meta.model_name
        # Get names from the report_map used in get_urls
        report_names = [
            'export_excel', 'completed', 'overdue', 'active', 'performance', 'workload',
            'abc', 'sla', 'duration', 'issues', 'delay_reasons', 'cancelled',
            'chart_progress', 'chart_gantt', 'summary'
        ]
        for name in report_names:
             try:
                 report_urls[name] = reverse(f'admin:%s_%s_report_{name}' % info)
             except Exception:
                 logger.warning(f"Could not reverse URL for report '{name}'. Check if view and URL pattern exist.")
                 report_urls[name] = None # Or '#'

        context['report_urls'] = report_urls
        request.current_app = self.admin_site.name
        # Ensure this template exists and iterates through report_urls
        return render(request, 'admin/tasks/report_list.html', context)

    # --- Display Methods ---
    def assigned_users_display(self, obj):
        if not TaskUserRole: return "N/A" # Handle missing model
        # Optimized prefetch should be used in get_queryset if performance is critical
        users_roles = obj.user_roles.select_related('user').all()
        role_order = { TaskUserRole.RoleChoices.RESPONSIBLE: 1, TaskUserRole.RoleChoices.EXECUTOR: 2, TaskUserRole.RoleChoices.WATCHER: 3 }
        sorted_roles = sorted(users_roles, key=lambda r: role_order.get(r.role, 99))
        display_parts = [f"{getattr(r.user, 'display_name', '?')} ({r.get_role_display()[:3]}.)" for r in sorted_roles if r.user]
        return ", ".join(display_parts) or "---"
    assigned_users_display.short_description = _("Участники")

    def project_link(self, obj):
        if obj.project:
            link = reverse("admin:tasks_project_change", args=[obj.project.id])
            return format_html('<a href="{}">{}</a>', link, obj.project.name)
        return "-"
    project_link.short_description = _("Проект"); project_link.admin_order_field = 'project__name'

    def created_by_link(self, obj):
        if obj.created_by:
            # Ensure the user_profiles app_label is correct ('user_profiles' or your app name)
            link = reverse("admin:user_profiles_user_change", args=[obj.created_by.id])
            return format_html('<a href="{}">{}</a>', link, obj.created_by.display_name or obj.created_by.username)
        return "-"
    created_by_link.short_description = _("Создатель"); created_by_link.admin_order_field = 'created_by__username'

    # --- Admin Actions ---
    @admin.action(description=_("Отметить выбранные задачи как 'Выполнена'"))
    def mark_completed(self, request, queryset):
        updated_count = 0
        for task in queryset:
             if task.status != Task.StatusChoices.COMPLETED:
                 task.status = Task.StatusChoices.COMPLETED
                 # Let model's save/clean handle completion_date
                 # task.completion_date = timezone.now()
                 try:
                     task.save(update_fields=['status', 'completion_date', 'updated_at']) # Ensure completion_date is included
                     updated_count += 1
                 except Exception as e:
                     self.message_user(request, _("Ошибка при обновлении задачи %(num)s: %(err)s") % {'num': task.task_number, 'err': e}, level=messages.ERROR)
        if updated_count > 0:
            self.message_user(request, _("%(count)d задач успешно отмечены как выполненные.") % {'count': updated_count}, level=messages.SUCCESS)

    @admin.action(description=_("Отметить выбранные задачи как 'В работе'"))
    def mark_in_progress(self, request, queryset):
        updated_count = 0
        for task in queryset.exclude(status=Task.StatusChoices.COMPLETED):
             if task.status != Task.StatusChoices.IN_PROGRESS:
                 task.status = Task.StatusChoices.IN_PROGRESS
                 # Let model's save/clean handle completion_date removal
                 # task.completion_date = None
                 try:
                     task.save(update_fields=['status', 'completion_date', 'updated_at']) # Ensure completion_date is included
                     updated_count += 1
                 except Exception as e:
                      self.message_user(request, _("Ошибка при обновлении задачи %(num)s: %(err)s") % {'num': task.task_number, 'err': e}, level=messages.ERROR)
        if updated_count > 0:
            self.message_user(request, _("%(count)d задач успешно переведены в статус 'В работе'.") % {'count': updated_count}, level=messages.SUCCESS)

    @admin.action(description=_("Перейти к отчету: Просроченные задачи"))
    def view_overdue_report_action(self, request, queryset):
        # Use the correct reversed name from get_urls
        info = self.model._meta.app_label, self.model._meta.model_name
        return redirect('admin:%s_%s_report_overdue' % info)

    @admin.action(description=_("Перейти к отчету: Активные задачи"))
    def view_active_report_action(self, request, queryset):
        info = self.model._meta.app_label, self.model._meta.model_name
        return redirect('admin:%s_%s_report_active' % info)

    actions = ['mark_completed', 'mark_in_progress', 'view_overdue_report_action', 'view_active_report_action']

    def save_model(self, request, obj, form, change):
        if not obj.pk: # If creating new task and creator not set by form
            if not obj.created_by_id:
                obj.created_by = request.user
        # Flag for model's save method if needed
        # setattr(obj, '_called_from_form_save', True)
        super().save_model(request, obj, form, change)
        # if hasattr(obj, '_called_from_form_save'): delattr(obj, '_called_from_form_save')

# TaskPhotoAdmin remains largely the same, just ensure template paths are correct
@admin.register(TaskPhoto)
class TaskPhotoAdmin(admin.ModelAdmin):
    list_display = ("id", "task_link", "thumbnail_preview", "description", "uploaded_by_link", "created_at")
    list_filter = ("created_at", "task__project", "uploaded_by")
    search_fields = ("description", "task__task_number", "task__title", "uploaded_by__username")
    list_select_related = ('task', 'uploaded_by', 'task__project')
    readonly_fields = ("created_at", "updated_at", "uploaded_by_link", "thumbnail_preview") # Added updated_at
    autocomplete_fields = ('task', 'uploaded_by')
    fieldsets = (
        (None, {"fields": ("task", "photo", "thumbnail_preview", "description")}),
        (_("Системная информация"), {"fields": ("uploaded_by_link", "created_at", "updated_at"), "classes": ("collapse",)}),
    )

    def task_link(self, obj):
        if obj.task:
            link = reverse("admin:tasks_task_change", args=[obj.task.id])
            return format_html('<a href="{}">[{}] {}</a>', link, obj.task.task_number or obj.task.id, obj.task.title[:30])
        return "-"
    task_link.short_description = _("Задача"); task_link.admin_order_field = 'task__task_number'

    def thumbnail_preview(self, obj):
        if obj.photo:
            return format_html('<a href="{0}" target="_blank"><img src="{0}" style="max-height: 50px; max-width: 100px;" /></a>', obj.photo.url)
        return "-"
    thumbnail_preview.short_description = _("Миниатюра")

    def uploaded_by_link(self, obj):
        if obj.uploaded_by:
            link = reverse("admin:user_profiles_user_change", args=[obj.uploaded_by.id])
            return format_html('<a href="{}">{}</a>', link, obj.uploaded_by.display_name or obj.uploaded_by.username)
        return "-"
    uploaded_by_link.short_description = _("Загрузил"); uploaded_by_link.admin_order_field = 'uploaded_by__username'

    def save_model(self, request, obj, form, change):
        if not obj.pk and not obj.uploaded_by_id: # Set uploader for new photos if not set
            obj.uploaded_by = request.user
        super().save_model(request, obj, form, change)