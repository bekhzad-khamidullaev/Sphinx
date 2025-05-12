import logging
from django.contrib import admin, messages
from django.urls import path, reverse
from django.utils.translation import gettext_lazy as _
from django.db.models import Count, Prefetch
from django.utils.html import format_html
from django.contrib.auth import get_user_model

from .views import report as report_views
from .models import Project, TaskCategory, TaskSubcategory, Task, TaskPhoto, TaskAssignment, TaskComment

User = get_user_model()
logger = logging.getLogger(__name__)

class TaskAssignmentInline(admin.TabularInline):
    model = TaskAssignment
    extra = 1
    fields = ('user', 'role', 'assigned_by_link', 'created_at_formatted')
    readonly_fields = ('created_at_formatted', 'assigned_by_link')
    autocomplete_fields = ('user', 'assigned_by')
    verbose_name = _("Участник задачи")
    verbose_name_plural = _("Участники задачи")

    def assigned_by_link(self, obj):
        if obj.assigned_by:
            try:
                link = reverse(f"admin:{obj.assigned_by._meta.app_label}_{obj.assigned_by._meta.model_name}_change", args=[obj.assigned_by.pk])
                return format_html('<a href="{}">{}</a>', link, obj.assigned_by.get_username())
            except Exception: return obj.assigned_by.get_username()
        return "—"
    assigned_by_link.short_description = _("Кем назначено")

    def created_at_formatted(self, obj):
        return obj.created_at.strftime("%d.%m.%Y %H:%M") if obj.created_at else "—"
    created_at_formatted.short_description = _("Дата назначения")

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        if db_field.name == "assigned_by":
            kwargs['initial'] = request.user.id
            kwargs['disabled'] = True
        return super().formfield_for_foreignkey(db_field, request, **kwargs)

    def save_formset(self, request, form, formset, change):
        instances = formset.save(commit=False)
        for assignment_instance in instances:
            if not assignment_instance.pk and not assignment_instance.assigned_by_id:
                assignment_instance.assigned_by = request.user
        formset.save()


class TaskPhotoInline(admin.TabularInline):
    model = TaskPhoto
    extra = 0
    fields = ('photo', 'thumbnail_preview', 'description', 'uploaded_by_link', 'created_at')
    readonly_fields = ('created_at', 'uploaded_by_link', 'thumbnail_preview')
    autocomplete_fields = ('uploaded_by',)
    verbose_name = _("Фотография")
    verbose_name_plural = _("Фотографии")

    def uploaded_by_link(self, obj):
        if obj.uploaded_by:
            try:
                link = reverse(f"admin:{obj.uploaded_by._meta.app_label}_{obj.uploaded_by._meta.model_name}_change", args=[obj.uploaded_by.pk])
                return format_html('<a href="{}">{}</a>', link, obj.uploaded_by.get_username())
            except Exception: return obj.uploaded_by.get_username()
        return "—"
    uploaded_by_link.short_description = _("Загрузил")

    def save_formset(self, request, form, formset, change):
        instances = formset.save(commit=False)
        for inst in instances:
            if not inst.pk and not inst.uploaded_by_id: inst.uploaded_by = request.user
            inst.save()
        formset.save_m2m()

    def thumbnail_preview(self, obj):
        if obj.photo and hasattr(obj.photo, 'url'):
            return format_html('<a href="{0}" target="_blank"><img src="{0}" style="max-height:40px;max-width:70px;object-fit:cover;" /></a>', obj.photo.url)
        return "—"
    thumbnail_preview.short_description = _("Миниатюра")


class TaskCommentInline(admin.TabularInline):
    model = TaskComment
    extra = 0
    fields = ('author_link', 'text_snippet', 'created_at_formatted')
    readonly_fields = ('author_link', 'created_at_formatted', 'text_snippet')
    verbose_name = _("Комментарий")
    verbose_name_plural = _("Комментарии")
    can_delete = False

    def author_link(self, obj):
        if obj.author:
            try:
                link = reverse(f"admin:{obj.author._meta.app_label}_{obj.author._meta.model_name}_change", args=[obj.author.pk])
                return format_html('<a href="{}">{}</a>', link, obj.author.get_username())
            except: return obj.author.get_username()
        return _("Аноним")
    author_link.short_description = _("Автор")

    def text_snippet(self, obj):
        return (obj.text[:75] + "...") if len(obj.text) > 75 else obj.text
    text_snippet.short_description = _("Текст")

    def created_at_formatted(self, obj):
        return obj.created_at.strftime("%d.%m.%Y %H:%M") if obj.created_at else "—"
    created_at_formatted.short_description = _("Дата")

    def has_add_permission(self, request, obj=None): return False
    def has_change_permission(self, request, obj=None): return False

@admin.register(Project)
class ProjectAdmin(admin.ModelAdmin):
    list_display = ("name", "owner_link", "start_date_formatted", "end_date_formatted", "is_active", "task_count_display")
    search_fields = ("name", "description", "owner__username", "owner__first_name", "owner__last_name")
    list_filter = ("is_active", "start_date", "owner"); date_hierarchy = "created_at"; autocomplete_fields = ('owner',)
    fieldsets = ((None, {"fields": ("name", "description", "owner", "is_active")}), (_("Даты проекта"), {"fields": ("start_date", "end_date")}), (_("Системная информация"), {"fields": ("created_at", "updated_at"), "classes": ("collapse",)}))
    readonly_fields = ("created_at", "updated_at")
    def get_queryset(self, request): return super().get_queryset(request).annotate(task_count=Count('tasks'))
    def task_count_display(self, obj): return obj.task_count
    task_count_display.short_description = _("Задач"); task_count_display.admin_order_field = 'task_count'
    def owner_link(self, obj):
        if obj.owner:
            try: link = reverse(f"admin:{obj.owner._meta.app_label}_{obj.owner._meta.model_name}_change", args=[obj.owner.pk]); return format_html('<a href="{}">{}</a>', link, obj.owner.get_username())
            except: return obj.owner.get_username()
        return "—"
    owner_link.short_description = _("Владелец"); owner_link.admin_order_field = 'owner__username'
    def start_date_formatted(self, obj): return obj.start_date.strftime("%d.%m.%Y") if obj.start_date else "—"
    start_date_formatted.short_description = _("Начало"); start_date_formatted.admin_order_field = 'start_date'
    def end_date_formatted(self, obj): return obj.end_date.strftime("%d.%m.%Y") if obj.end_date else "—"
    end_date_formatted.short_description = _("Конец"); end_date_formatted.admin_order_field = 'end_date'

@admin.register(TaskCategory)
class TaskCategoryAdmin(admin.ModelAdmin):
    list_display = ("name", "description_snippet", "created_at_formatted"); search_fields = ("name", "description"); readonly_fields = ("created_at", "updated_at")
    def description_snippet(self, obj): return (obj.description[:75] + '...') if obj.description and len(obj.description) > 75 else (obj.description or "—")
    description_snippet.short_description = _("Описание")
    def created_at_formatted(self,obj): return obj.created_at.strftime("%d.%m.%Y %H:%M")
    created_at_formatted.short_description = _("Создана"); created_at_formatted.admin_order_field = 'created_at'

@admin.register(TaskSubcategory)
class TaskSubcategoryAdmin(admin.ModelAdmin):
    list_display = ("name", "category_link", "description_snippet", "created_at_formatted"); list_filter = ("category",); search_fields = ("name", "description", "category__name")
    list_select_related = ('category',); autocomplete_fields = ('category',); readonly_fields = ("created_at", "updated_at")
    def category_link(self, obj):
        if obj.category: link = reverse("admin:tasks_taskcategory_change", args=[obj.category.pk]); return format_html('<a href="{}">{}</a>', link, obj.category.name)
        return "—"
    category_link.short_description = _("Категория"); category_link.admin_order_field = 'category__name'
    def description_snippet(self, obj): return (obj.description[:75] + '...') if obj.description and len(obj.description) > 75 else (obj.description or "—")
    description_snippet.short_description = _("Описание")
    def created_at_formatted(self,obj): return obj.created_at.strftime("%d.%m.%Y %H:%M")
    created_at_formatted.short_description = _("Создана"); created_at_formatted.admin_order_field = 'created_at'

@admin.register(TaskAssignment)
class TaskAssignmentAdmin(admin.ModelAdmin):
    list_display = ('task_link', 'user_link', 'role_display_admin', 'assigned_by_link', 'created_at_formatted')
    list_filter = ('role', 'task__project', 'user__is_staff', 'assigned_by')
    search_fields = ('task__title', 'task__task_number', 'user__username', 'user__first_name', 'user__last_name', 'user__email', 'assigned_by__username')
    autocomplete_fields = ('task', 'user', 'assigned_by'); list_select_related = ('task', 'user', 'assigned_by', 'task__project'); readonly_fields = ("created_at", "updated_at")
    def task_link(self, obj): link = reverse("admin:tasks_task_change", args=[obj.task.pk]); return format_html('<a href="{}">{}</a>', link, obj.task.task_number or obj.task.title[:30])
    task_link.short_description = _("Задача"); task_link.admin_order_field = 'task__task_number'
    def user_link(self, obj):
        try: link = reverse(f"admin:{obj.user._meta.app_label}_{obj.user._meta.model_name}_change", args=[obj.user.pk]); return format_html('<a href="{}">{}</a>', link, obj.user.get_username())
        except: return obj.user.get_username()
    user_link.short_description = _("Пользователь"); user_link.admin_order_field = 'user__username'
    def assigned_by_link(self, obj):
        if obj.assigned_by:
            try: link = reverse(f"admin:{obj.assigned_by._meta.app_label}_{obj.assigned_by._meta.model_name}_change", args=[obj.assigned_by.pk]); return format_html('<a href="{}">{}</a>', link, obj.assigned_by.get_username())
            except: return obj.assigned_by.get_username()
        return "—"
    assigned_by_link.short_description = _("Кем назначено"); assigned_by_link.admin_order_field = 'assigned_by__username'
    def role_display_admin(self, obj): return obj.get_role_display()
    role_display_admin.short_description = _("Роль"); role_display_admin.admin_order_field = 'role'
    def created_at_formatted(self,obj): return obj.created_at.strftime("%d.%m.%Y %H:%M")
    created_at_formatted.short_description = _("Назначен(а)"); created_at_formatted.admin_order_field = 'created_at'

@admin.register(Task)
class TaskAdmin(admin.ModelAdmin):
    inlines = [TaskAssignmentInline, TaskPhotoInline, TaskCommentInline]
    list_display = ("task_number_link", "title", "project_link", "status_colored_display", "priority", "due_date_formatted", "assigned_users_display", "created_by_link", "created_at_formatted")
    list_filter = ("status", "priority", "project", "category", "due_date", "created_by", ('assignments__user', admin.RelatedOnlyFieldListFilter), 'assignments__role')
    search_fields = ("task_number", "title", "description", "project__name", "created_by__username", "created_by__first_name", "created_by__last_name", "assignments__user__username", "assignments__user__first_name", "assignments__user__last_name")
    ordering = ("-priority", "due_date", "-created_at")
    date_hierarchy = "created_at"
    readonly_fields = ("task_number", "created_at", "updated_at", "created_by_link", "completion_date", "status_colored_detail_display")
    list_select_related = ('project', 'category', 'subcategory', 'created_by')
    autocomplete_fields = ('project', 'category', 'subcategory', 'created_by')
    fieldsets = (
        (_("Основная информация"), {"fields": ("task_number", "project", "title", "description")}),
        (_("Классификация, Статус и Приоритет"), {"fields": ("category", "subcategory", ("status", "status_colored_detail_display"), "priority")}),
        (_("Сроки и Оценка"), {"fields": (("start_date", "due_date"), "completion_date", "estimated_time"), "classes": ("collapse",)}),
        (_("Авторство и Даты"), {"fields": ("created_by_link", ("created_at", "updated_at")), "classes": ("collapse",)}),
    )
    # change_list_template = "admin/tasks/task/change_list.html"
    # change_form_template = "admin/tasks/task/change_form.html"

    def task_number_link(self, obj: Task):
        url = reverse('admin:tasks_task_change', args=[obj.id])
        return format_html('<a href="{}"><strong>{}</strong></a>', url, obj.task_number or f"ID:{obj.pk}")
    task_number_link.short_description = _("Номер"); task_number_link.admin_order_field = "task_number"

    def status_colored_display(self, obj: Task):
        colors = {Task.StatusChoices.BACKLOG: "#6c757d", Task.StatusChoices.NEW: "#0dcaf0", Task.StatusChoices.IN_PROGRESS: "#ffc107", Task.StatusChoices.ON_HOLD: "#6f42c1", Task.StatusChoices.COMPLETED: "#198754", Task.StatusChoices.CANCELLED: "#dc3545", Task.StatusChoices.OVERDUE: "#ff453a",}
        color = colors.get(obj.status, "#343a40")
        return format_html('<span style="color:{}; font-weight:bold;">●</span> {}', color, obj.get_status_display())
    status_colored_display.short_description = _("Статус"); status_colored_display.admin_order_field = "status"

    def status_colored_detail_display(self, obj: Task):
        return self.status_colored_display(obj)
    status_colored_detail_display.short_description = _("Текущий статус")

    def due_date_formatted(self, obj: Task):
        if obj.due_date:
            due_date_str = obj.due_date.strftime("%d.%m.%Y")
            if obj.is_overdue: return format_html('<span style="color:red; font-weight:bold;">{}</span>', due_date_str)
            return due_date_str
        return "—"
    due_date_formatted.short_description = _("Срок"); due_date_formatted.admin_order_field = "due_date"

    def assigned_users_display(self, obj: Task):
        roles = obj.assignments.select_related('user').all()
        if not roles: return "—"
        role_order_map = {TaskAssignment.RoleChoices.RESPONSIBLE: 1, TaskAssignment.RoleChoices.EXECUTOR: 2, TaskAssignment.RoleChoices.REPORTER: 3, TaskAssignment.RoleChoices.WATCHER: 4}
        sorted_roles = sorted(roles, key=lambda r: role_order_map.get(r.role, 99))
        display_parts = [f"{r.user.get_full_name() or r.user.get_username()} ({r.get_role_display()[:3].upper()})" for r in sorted_roles if r.user]
        return ", ".join(display_parts) or "—"
    assigned_users_display.short_description = _("Участники")

    def project_link(self, obj: Task):
        if obj.project: link = reverse("admin:tasks_project_change", args=[obj.project.pk]); return format_html('<a href="{}">{}</a>', link, obj.project.name)
        return "—"
    project_link.short_description = _("Проект"); project_link.admin_order_field = 'project__name'

    def created_by_link(self, obj: Task):
        if obj.created_by:
            try: link = reverse(f"admin:{obj.created_by._meta.app_label}_{obj.created_by._meta.model_name}_change", args=[obj.created_by.pk]); return format_html('<a href="{}">{}</a>', link, obj.created_by.get_username())
            except: return obj.created_by.get_username()
        return "—"
    created_by_link.short_description = _("Инициатор"); created_by_link.admin_order_field = 'created_by__username'

    def created_at_formatted(self, obj: Task): return obj.created_at.strftime("%d.%m.%Y %H:%M")
    created_at_formatted.short_description = _("Создана"); created_at_formatted.admin_order_field = 'created_at'

    @admin.action(description=_("Установить статус 'Выполнена' (COMPLETED) для выбранных задач"))
    def mark_status_done(self, request, queryset):
        updated_count, permission_denied_count = 0, 0
        for task_item in queryset.exclude(status__in=[Task.StatusChoices.COMPLETED, Task.StatusChoices.CANCELLED]):
            if task_item.can_change_status(request.user, Task.StatusChoices.COMPLETED):
                original_status = task_item.status; task_item.status = Task.StatusChoices.COMPLETED
                try:
                    setattr(task_item, '_initiator_user_id', request.user.id)
                    task_item.save(update_fields=['status', 'completion_date', 'updated_at']); updated_count += 1
                except Exception as e: task_item.status = original_status; self.message_user(request, _("Ошибка обновления задачи %(num)s: %(err)s") % {'num': task_item.task_number, 'err': str(e)}, messages.ERROR)
                finally:
                    if hasattr(task_item, '_initiator_user_id'): delattr(task_item, '_initiator_user_id')
            else: permission_denied_count +=1
        if updated_count > 0: self.message_user(request, _("%(count)d задач успешно отмечены как 'Выполнена'.") % {'count': updated_count}, messages.SUCCESS)
        if permission_denied_count > 0: self.message_user(request, _("Нет прав на изменение статуса для %(count)d задач.") % {'count': permission_denied_count}, messages.WARNING)
    actions = ['mark_status_done']

    def save_model(self, request, obj: Task, form, change):
        if not obj.pk and not obj.created_by_id: obj.created_by = request.user
        setattr(obj, '_called_from_form_save', True)
        setattr(obj, '_initiator_user_id', request.user.id)
        super().save_model(request, obj, form, change)
        if hasattr(obj, '_initiator_user_id'): delattr(obj, '_initiator_user_id')
        if hasattr(obj, '_called_from_form_save'): delattr(obj, '_called_from_form_save')

    def save_related(self, request, form, formsets, change):
        task_instance = form.instance
        initiator_id = request.user.id
        setattr(task_instance, '_initiator_user_id', initiator_id)

        for formset in formsets:
            instances = formset.save(commit=False)
            for inst in instances:
                if isinstance(inst, TaskAssignment):
                    if not inst.pk and not inst.assigned_by_id: inst.assigned_by = request.user
                elif isinstance(inst, TaskPhoto):
                    if not inst.pk and not inst.uploaded_by_id: inst.uploaded_by = request.user
                setattr(inst, '_initiator_user_id', initiator_id)
                inst.save()
            formset.save_m2m()
            for inst in instances:
                if hasattr(inst, '_initiator_user_id'): delattr(inst, '_initiator_user_id')

        super().save_related(request, form, formsets, change)
        if hasattr(task_instance, '_initiator_user_id'): delattr(task_instance, '_initiator_user_id')

    def get_queryset(self, request):
        return super().get_queryset(request).prefetch_related(Prefetch('assignments', queryset=TaskAssignment.objects.select_related('user')))

    def get_urls(self):
        urls = super().get_urls()
        info = self.model._meta.app_label, self.model._meta.model_name
        report_map = {
            'index': (report_views.ReportIndexView, 'reports/'),
            'export_excel': (report_views.export_tasks_to_excel, 'reports/export/excel/'),
            'summary': (report_views.TaskSummaryReportView, 'reports/summary/'),
            'completed': (report_views.CompletedTasksReportView, 'reports/completed/'),
            'overdue': (report_views.OverdueTasksReportView, 'reports/overdue/'),
            'active': (report_views.ActiveTasksReportView, 'reports/active/'),
            'duration': (report_views.TaskDurationReportView, 'reports/duration/'),
            'issues': (report_views.IssuesReportView, 'reports/issues/'),
            'cancelled': (report_views.CancelledTasksReportView, 'reports/cancelled/'),
            'delay_reasons': (report_views.DelayReasonsReportView, 'reports/delay-reasons/'),
            'performance': (report_views.TeamPerformanceReportView, 'reports/performance/'),
            'workload': (report_views.EmployeeWorkloadReportView, 'reports/workload/'),
            'abc': (report_views.AbcAnalysisReportView, 'reports/abc-analysis/'),
            'sla': (report_views.SlaReportView, 'reports/sla-compliance/'),
            'chart_progress': (report_views.TaskProgressChartView, 'reports/charts/progress/'),
            'chart_gantt': (report_views.GanttChartView, 'reports/charts/gantt/'),
        }
        custom_urls = [path(path_str, self.admin_site.admin_view(view_class_or_func.as_view() if isinstance(view_class_or_func, type) else view_class_or_func), name=f'%s_%s_report_{name_key}' % info) for name_key, (view_class_or_func, path_str) in report_map.items()]
        return custom_urls + urls

@admin.register(TaskPhoto)
class TaskPhotoAdmin(admin.ModelAdmin):
    list_display = ("id", "task_link", "thumbnail_preview", "description_snippet", "uploaded_by_link", "created_at_formatted")
    list_filter = ("created_at", "task__project", "uploaded_by"); search_fields = ("description", "task__task_number", "task__title", "uploaded_by__username")
    list_select_related = ('task', 'uploaded_by', 'task__project'); readonly_fields = ("created_at", "updated_at", "uploaded_by_link", "thumbnail_preview")
    autocomplete_fields = ('task', 'uploaded_by')
    fieldsets = ((None, {"fields": ("task", ("photo", "thumbnail_preview"), "description")}), (_("Системная информация"), {"fields": ("uploaded_by_link", ("created_at", "updated_at")), "classes": ("collapse",)}))
    def task_link(self, obj): link = reverse("admin:tasks_task_change", args=[obj.task.pk]); return format_html('<a href="{}">{} (#{})</a>', link, obj.task.title[:30], obj.task.task_number or obj.task.pk)
    task_link.short_description = _("Задача"); task_link.admin_order_field = 'task__title'
    def thumbnail_preview(self, obj):
        if obj.photo and hasattr(obj.photo, 'url'): return format_html('<a href="{0}" target="_blank"><img src="{0}" style="max-height:50px;max-width:100px;object-fit:cover;" /></a>', obj.photo.url)
        return "—"
    thumbnail_preview.short_description = _("Миниатюра")
    def uploaded_by_link(self, obj):
        if obj.uploaded_by:
            try: link = reverse(f"admin:{obj.uploaded_by._meta.app_label}_{obj.uploaded_by._meta.model_name}_change", args=[obj.uploaded_by.pk]); return format_html('<a href="{}">{}</a>', link, obj.uploaded_by.get_username())
            except: return obj.uploaded_by.get_username()
        return "—"
    uploaded_by_link.short_description = _("Загрузил"); uploaded_by_link.admin_order_field = 'uploaded_by__username'
    def description_snippet(self, obj): return (obj.description[:50] + '...') if obj.description and len(obj.description) > 50 else (obj.description or "—")
    description_snippet.short_description = _("Описание")
    def created_at_formatted(self, obj): return obj.created_at.strftime("%d.%m.%Y %H:%M")
    created_at_formatted.short_description = _("Загружено"); created_at_formatted.admin_order_field = 'created_at'
    def save_model(self, request, obj, form, change):
        if not obj.pk and not obj.uploaded_by_id: obj.uploaded_by = request.user
        setattr(obj, '_initiator_user_id', request.user.id)
        super().save_model(request, obj, form, change)
        if hasattr(obj, '_initiator_user_id'): delattr(obj, '_initiator_user_id')

@admin.register(TaskComment)
class TaskCommentAdmin(admin.ModelAdmin):
    list_display = ('id', 'task_link', 'author_link', 'text_snippet', 'created_at_formatted')
    list_filter = ('created_at', 'task__project', 'author'); search_fields = ('text', 'task__title', 'author__username')
    autocomplete_fields = ('task', 'author'); readonly_fields = ('created_at', 'updated_at')
    list_select_related = ('task', 'author', 'task__project')
    def task_link(self, obj): link = reverse("admin:tasks_task_change", args=[obj.task.id]); return format_html('<a href="{}">{}</a>', link, obj.task.task_number or obj.task.title[:30])
    task_link.short_description = _("Задача"); task_link.admin_order_field = 'task__title'
    def author_link(self, obj):
        if obj.author:
            try: link = reverse(f"admin:{obj.author._meta.app_label}_{obj.author._meta.model_name}_change", args=[obj.author.pk]); return format_html('<a href="{}">{}</a>', link, obj.author.get_username())
            except: return obj.author.get_username()
        return _("Аноним")
    author_link.short_description = _("Автор"); author_link.admin_order_field = 'author__username'
    def text_snippet(self, obj): return (obj.text[:75] + '...') if len(obj.text) > 75 else obj.text
    text_snippet.short_description = _("Текст комментария")
    def created_at_formatted(self,obj): return obj.created_at.strftime("%d.%m.%Y %H:%M")
    created_at_formatted.short_description = _("Создан"); created_at_formatted.admin_order_field = 'created_at'
    def save_model(self, request, obj, form, change):
        setattr(obj, '_initiator_user_id', request.user.id)
        super().save_model(request, obj, form, change)
        if hasattr(obj, '_initiator_user_id'): delattr(obj, '_initiator_user_id')