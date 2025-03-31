# tasks/admin.py
import logging # Добавим логгер
from django.contrib import admin
from django.urls import path, reverse
from django.utils.translation import gettext_lazy as _
from django.db import models
from django.utils.html import format_html
from django.shortcuts import redirect, render
# Импортируем представления отчетов
from .views import report as report_views
# Импортируем модели
from .models import ( Project, TaskCategory, TaskSubcategory, Task, TaskPhoto )
from user_profiles.models import TaskUserRole

logger = logging.getLogger(__name__)

# --- Inlines ---
class TaskPhotoInline(admin.TabularInline):
    model = TaskPhoto; extra = 1; fields = ('photo', 'thumbnail', 'description', 'uploaded_by', 'created_at'); readonly_fields = ('created_at', 'uploaded_by', 'thumbnail'); verbose_name = _("Фотография"); verbose_name_plural = _("Фотографии"); autocomplete_fields = ('uploaded_by',)
    def save_formset(self, request, form, formset, change): instances = formset.save(commit=False); [setattr(inst, 'uploaded_by', request.user) for inst in instances if not inst.pk and not inst.uploaded_by]; formset.save(); formset.save_m2m()
    def thumbnail(self, obj): return format_html('<img src="{}" style="max-height: 40px; max-width: 70px;" />', obj.photo.url) if obj.photo else "-"; thumbnail.short_description = _("Миниатюра")

class TaskUserRoleInline(admin.TabularInline):
    model = TaskUserRole; extra = 1; fields = ('user', 'role', 'created_at'); readonly_fields = ('created_at',); autocomplete_fields = ('user',); verbose_name = _("Роль пользователя"); verbose_name_plural = _("Роли пользователей")

# --- ModelAdmins ---

@admin.register(Project)
class ProjectAdmin(admin.ModelAdmin):
    list_display = ("name", "start_date", "end_date", "created_at", "task_count"); search_fields = ("name", "description"); list_filter = ("start_date", "end_date", "created_at"); date_hierarchy = "created_at"; fieldsets = ((None, {"fields": ("name", "description")}), (_("Даты"), {"fields": ("start_date", "end_date")}),)
    def get_queryset(self, request): return super().get_queryset(request).annotate(models.Count('tasks'))
    def task_count(self, obj): count = getattr(obj, 'tasks__count', None); return count if count is not None else obj.tasks.count(); task_count.short_description = _("Кол-во задач"); task_count.admin_order_field = 'tasks__count'

@admin.register(TaskCategory)
class TaskCategoryAdmin(admin.ModelAdmin): list_display = ("name", "created_at", "updated_at"); search_fields = ("name", "description")

@admin.register(TaskSubcategory)
class TaskSubcategoryAdmin(admin.ModelAdmin): list_display = ("name", "category", "created_at", "updated_at"); list_filter = ("category",); search_fields = ("name", "description", "category__name"); autocomplete_fields = ('category',)

@admin.register(Task)
class TaskAdmin(admin.ModelAdmin):
    inlines = [TaskUserRoleInline, TaskPhotoInline]
    list_display = ("task_number", "title", "project_link", "status_display", "priority_display", "deadline", "get_assigned_users_display", "created_by_link", "created_at")
    list_filter = ("status", "priority", "project", "category", "subcategory", "deadline", "created_at", "user_roles__user", "user_roles__role")
    search_fields = ("task_number", "title", "description", "project__name", "user_roles__user__username", "user_roles__user__first_name", "user_roles__user__last_name", "created_by__username")
    ordering = ("-created_at", "priority", "deadline")
    date_hierarchy = "created_at"
    readonly_fields = ("task_number", "created_at", "updated_at", "created_by_link", "completion_date")
    list_select_related = ('project', 'category', 'subcategory', 'created_by')
    autocomplete_fields = ('project', 'category', 'subcategory', 'created_by')
    fieldsets = ((None, {"fields": ("task_number", "project", "title", "description")}), (_("Классификация и Статус"), {"fields": ("category", "subcategory", "status", "priority")}), (_("Сроки и Оценка"), {"fields": ("start_date", "deadline", "completion_date", "estimated_time"), "classes": ("collapse",)}), (_("Системная информация"), { "fields": ("created_by_link", "created_at", "updated_at"), "classes": ("collapse",),}),)
    # --- ДОБАВЛЯЕМ ШАБЛОН ДЛЯ КНОПОК ---
    change_list_template = "admin/tasks/change_list_with_reports.html"

    # --- ДОБАВЛЯЕМ МЕТОД get_urls ---
    def get_urls(self):
        urls = super().get_urls()
        # Определяем базовый путь для отчетов
        info = self.model._meta.app_label, self.model._meta.model_name

        custom_urls = [
            # --- Основная страница отчетов (новая) ---
            path('reports/', self.admin_site.admin_view(self.report_list_view), name='%s_%s_reports' % info),

            # --- Конкретные отчеты ---
            path('reports/export/excel/', self.admin_site.admin_view(report_views.export_tasks_to_excel), name='%s_%s_report_export_excel' % info),
            path('reports/completed/', self.admin_site.admin_view(report_views.completed_tasks_report), name='%s_%s_report_completed' % info),
            path('reports/overdue/', self.admin_site.admin_view(report_views.overdue_tasks_report), name='%s_%s_report_overdue' % info),
            path('reports/active/', self.admin_site.admin_view(report_views.active_tasks_report), name='%s_%s_report_active' % info),
            path('reports/performance/', self.admin_site.admin_view(report_views.team_performance_report), name='%s_%s_report_performance' % info),
            path('reports/workload/', self.admin_site.admin_view(report_views.employee_workload_report), name='%s_%s_report_workload' % info),
            path('reports/abc/', self.admin_site.admin_view(report_views.abc_analysis_report), name='%s_%s_report_abc' % info), # Убедитесь, что представление адаптировано
            path('reports/sla/', self.admin_site.admin_view(report_views.sla_report), name='%s_%s_report_sla' % info), # Убедитесь, что представление адаптировано
            path('reports/duration/', self.admin_site.admin_view(report_views.task_duration_report), name='%s_%s_report_duration' % info),
            path('reports/issues/', self.admin_site.admin_view(report_views.issues_report), name='%s_%s_report_issues' % info),
            path('reports/delay-reasons/', self.admin_site.admin_view(report_views.delay_reasons_report), name='%s_%s_report_delay_reasons' % info),
            path('reports/cancelled/', self.admin_site.admin_view(report_views.cancelled_tasks_report), name='%s_%s_report_cancelled' % info),
            path('reports/charts/progress/', self.admin_site.admin_view(report_views.task_progress_chart), name='%s_%s_report_chart_progress' % info),
            path('reports/charts/gantt/', self.admin_site.admin_view(report_views.gantt_chart), name='%s_%s_report_chart_gantt' % info),
            path('reports/summary/', self.admin_site.admin_view(report_views.TaskSummaryReportView.as_view()), name='%s_%s_report_summary' % info),
        ]
        return custom_urls + urls

    # --- Новое представление для списка отчетов ---
    def report_list_view(self, request):
        """Отображает страницу со ссылками на все доступные отчеты."""
        context = dict(
           # Базовый контекст админки
           self.admin_site.each_context(request),
           title=_('Отчеты по задачам'),
           opts=self.model._meta,
           app_label=self.model._meta.app_label,
        )
        # Генерируем URL для каждого отчета, чтобы передать в шаблон
        report_urls = {}
        info = self.model._meta.app_label, self.model._meta.model_name
        report_names = [
            'export_excel', 'completed', 'overdue', 'active', 'performance', 'workload',
            'abc', 'sla', 'duration', 'issues', 'delay_reasons', 'cancelled',
            'chart_progress', 'chart_gantt', 'summary'
        ]
        for name in report_names:
             report_urls[name] = reverse(f'admin:%s_%s_report_{name}' % info)

        context['report_urls'] = report_urls
        request.current_app = self.admin_site.name

        # Используем кастомный шаблон для этой страницы
        return render(request, 'admin/tasks/report_list.html', context)

    # --- Методы для ссылок и отображения ---
    def get_assigned_users_display(self, obj):
        users_roles = obj.user_roles.all(); role_order = {TaskUserRole.RoleChoices.RESPONSIBLE: 1, TaskUserRole.RoleChoices.EXECUTOR: 2, TaskUserRole.RoleChoices.WATCHER: 3}; sorted_roles = sorted(users_roles, key=lambda r: role_order.get(r.role, 99)); display_parts = [f"{getattr(r.user, 'display_name', '?')} ({r.get_role_display()[:3]}.)" for r in sorted_roles]; return ", ".join(display_parts) or "---"; get_assigned_users_display.short_description = _("Участники")
    def project_link(self, obj): return format_html('<a href="{}">{}</a>', reverse("admin:tasks_project_change", args=[obj.project.id]), obj.project.name) if obj.project else "-"; project_link.short_description = _("Проект"); project_link.admin_order_field = 'project__name'
    def created_by_link(self, obj): return format_html('<a href="{}">{}</a>', reverse("admin:user_profiles_user_change", args=[obj.created_by.id]), obj.created_by.display_name) if obj.created_by else "-"; created_by_link.short_description = _("Создатель"); created_by_link.admin_order_field = 'created_by__username'

    # --- Admin Actions ---
    @admin.action(description=_("Отметить выбранные задачи как 'Выполнена'"))
    def mark_completed(self, request, queryset):
        # ... (код действия) ...
        updated_count = 0; from django.utils import timezone
        for task in queryset:
             if task.status != Task.StatusChoices.COMPLETED:
                 task.status = Task.StatusChoices.COMPLETED; task.completion_date = timezone.now()
                 try: task.save(update_fields=['status', 'completion_date', 'updated_at']); updated_count += 1
                 except Exception as e: self.message_user(request, f"Ошибка при обновлении задачи {task.task_number}: {e}", level='error')
        self.message_user(request, _(f"{updated_count} задач успешно отмечены как выполненные."), level='success')

    @admin.action(description=_("Отметить выбранные задачи как 'В работе'"))
    def mark_in_progress(self, request, queryset):
        # ... (код действия) ...
        updated_count = 0
        for task in queryset.exclude(status=Task.StatusChoices.COMPLETED):
             if task.status != Task.StatusChoices.IN_PROGRESS:
                 task.status = Task.StatusChoices.IN_PROGRESS; task.completion_date = None
                 try: task.save(update_fields=['status', 'completion_date', 'updated_at']); updated_count += 1
                 except Exception as e: self.message_user(request, f"Ошибка при обновлении задачи {task.task_number}: {e}", level='error')
        self.message_user(request, _(f"{updated_count} задач успешно переведены в статус 'В работе'."), level='success')

    # Опционально: действия, которые просто перенаправляют на страницу отчета
    @admin.action(description=_("Перейти к отчету: Просроченные задачи"))
    def view_overdue_report_action(self, request, queryset):
        return redirect('admin:tasks_task_report_overdue')

    @admin.action(description=_("Перейти к отчету: Активные задачи"))
    def view_active_report_action(self, request, queryset):
        return redirect('admin:tasks_task_report_active')

    actions = ['mark_completed', 'mark_in_progress', 'view_overdue_report_action', 'view_active_report_action'] # Добавляем действия

# TaskPhotoAdmin без изменений в логике
@admin.register(TaskPhoto)
class TaskPhotoAdmin(admin.ModelAdmin):
    list_display = ("id", "task_link", "thumbnail", "description", "uploaded_by_link", "created_at")
    list_filter = ("created_at", "task__project", "uploaded_by")
    search_fields = ("description", "task__task_number", "task__title", "uploaded_by__username")
    list_select_related = ('task', 'uploaded_by', 'task__project') # Хорошая оптимизация
    # Добавляем updated_at в readonly_fields, т.к. оно обновляется автоматически
    readonly_fields = ("created_at", "updated_at", "uploaded_by_link", "thumbnail")
    autocomplete_fields = ('task', 'uploaded_by')
    fieldsets = (
        (None, {"fields": ("task", "photo", "thumbnail", "description")}),
        # Переносим updated_at в readonly_fields
        (_("Системная информация"), {"fields": ("uploaded_by_link", "created_at", "updated_at"), "classes": ("collapse",)}),
    )

    def task_link(self, obj):
        """Ссылка на связанную задачу."""
        if obj.task:
            link = reverse("admin:tasks_task_change", args=[obj.task.id])
            # Отображаем номер задачи и её название для понятности
            return format_html('<a href="{}">[{}] {}</a>', link, obj.task.task_number or obj.task.id, obj.task.title[:30])
        return "-"
    task_link.short_description = _("Задача")
    task_link.admin_order_field = 'task__task_number' # Сортировка по номеру задачи

    def thumbnail(self, obj):
        """Отображение миниатюры изображения."""
        if obj.photo:
            return format_html('<img src="{}" style="max-height: 50px; max-width: 100px;" />', obj.photo.url)
        return "-"
    thumbnail.short_description = _("Миниатюра")

    def uploaded_by_link(self, obj):
        """Ссылка на пользователя, загрузившего фото."""
        if obj.uploaded_by:
            link = reverse("admin:user_profiles_user_change", args=[obj.uploaded_by.id])
            return format_html('<a href="{}">{}</a>', link, obj.uploaded_by.display_name)
        return "-"
    uploaded_by_link.short_description = _("Загрузил")
    uploaded_by_link.admin_order_field = 'uploaded_by__username'