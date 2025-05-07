# tasks/admin.py
import logging
from django.contrib import admin, messages
from django.db import models
from django.urls import path, reverse
from django.utils import timezone
from django.utils.html import format_html
from django.utils.translation import gettext_lazy as _

# Import models first
from .models import Project, TaskCategory, TaskSubcategory, Task, TaskPhoto, TaskComment

# Import views after models
from .views import report as report_views

# Conditional import for TaskUserRole from user_profiles app
try:
    from user_profiles.models import TaskUserRole, User # Adjust if your User model is different
except ImportError:
    TaskUserRole = None
    User = None
    logging.warning("TaskUserRole or User model not found. Task admin features related to user roles might be limited or use default User.")

logger = logging.getLogger(__name__)

# ==============================================================================
# Inlines for TaskAdmin (No changes needed here)
# ==============================================================================
# ... (TaskPhotoInline, TaskUserRoleInline, TaskCommentInline code as before) ...
class TaskPhotoInline(admin.TabularInline):
    """Inline for managing Task Photos within the Task admin page."""
    model = TaskPhoto
    extra = 1 # Show one empty form for adding a new photo
    fields = ('photo', 'thumbnail_preview', 'description', 'uploaded_by_link_admin', 'created_at')
    readonly_fields = ('thumbnail_preview', 'uploaded_by_link_admin', 'created_at')
    verbose_name = _("Фотография")
    verbose_name_plural = _("Фотографии")
    classes = ('collapse',) # Start collapsed
    # autocomplete_fields = ('uploaded_by',) # Enable if User admin has search_fields

    @admin.display(description=_("Загрузил"))
    def uploaded_by_link_admin(self, obj):
        """Displays the uploader with a link to their admin page."""
        if obj.uploaded_by:
            try:
                link = reverse("admin:%s_%s_change" % (obj.uploaded_by._meta.app_label, obj.uploaded_by._meta.model_name), args=[obj.uploaded_by.id])
                return format_html('<a href="{}">{}</a>', link, obj.uploaded_by.display_name or obj.uploaded_by.username)
            except Exception: # Handle cases where user model or URL might not resolve
                 return obj.uploaded_by.display_name or obj.uploaded_by.username
        return "—"

    @admin.display(description=_("Миниатюра"))
    def thumbnail_preview(self, obj):
        """Displays a thumbnail preview of the photo."""
        if obj.photo and hasattr(obj.photo, 'url'):
            # Consider using easy-thumbnails or sorl-thumbnail for proper thumbnails
            return format_html('<a href="{0}" target="_blank"><img src="{0}" style="max-height: 50px; max-width: 100px; object-fit: cover;" /></a>', obj.photo.url)
        return "—"

    def save_formset(self, request, form, formset, change):
        """Sets the uploader for newly added photos."""
        instances = formset.save(commit=False)
        for instance in instances:
            if not instance.pk and not instance.uploaded_by_id: # Only for new photos not yet saved
                instance.uploaded_by = request.user
            instance.save() # Сохраняем каждую инстанцию
        formset.save_m2m() # Стандартный вызов


# Only define TaskUserRoleInline if the model was successfully imported
if TaskUserRole:
    class TaskUserRoleInline(admin.TabularInline):
        """Inline for managing User Roles within the Task admin page."""
        model = TaskUserRole
        extra = 1
        fields = ('user', 'role', 'created_at')
        readonly_fields = ('created_at',)
        autocomplete_fields = ('user',) # Assumes User admin is registered with search_fields
        verbose_name = _("Роль пользователя в задаче")
        verbose_name_plural = _("Роли пользователей в задаче")
        classes = ('collapse',)
else:
    TaskUserRoleInline = None # Placeholder if model not available


class TaskCommentInline(admin.TabularInline):
    """Inline for viewing (and limited editing) of Task Comments."""
    model = TaskComment
    extra = 0 # Don't show empty forms for adding comments here
    fields = ('author_link_admin', 'text_preview', 'created_at_formatted', 'updated_at')
    readonly_fields = ('author_link_admin', 'text_preview', 'created_at_formatted', 'updated_at')
    # autocomplete_fields = ('author',) # Usually not needed as author is set
    ordering = ('-created_at',) # Show newest comments first
    verbose_name = _("Комментарий")
    verbose_name_plural = _("Последние комментарии")
    classes = ('collapse',)
    can_delete = False # Usually comments shouldn't be deleted from Task inline

    @admin.display(description=_("Автор"))
    def author_link_admin(self, obj):
        """Displays the author with a link to their admin page."""
        if obj.author:
            try:
                link = reverse("admin:%s_%s_change" % (obj.author._meta.app_label, obj.author._meta.model_name), args=[obj.author.id])
                return format_html('<a href="{}">{}</a>', link, obj.author.display_name or obj.author.username)
            except Exception:
                 return obj.author.display_name or obj.author.username
        return _("Система/Удален")

    @admin.display(description=_("Текст"))
    def text_preview(self, obj):
        """Shows a preview of the comment text."""
        return (obj.text[:100] + '...') if len(obj.text) > 100 else obj.text

    @admin.display(description=_("Создан"), ordering='created_at')
    def created_at_formatted(self, obj):
        if obj.created_at: return obj.created_at.strftime("%d.%m.%Y %H:%M")
        return "—"

    def has_add_permission(self, request, obj=None):
        """Disable adding comments directly via inline."""
        return False

    def has_change_permission(self, request, obj=None):
        """Allow changing comments only for superusers (example)."""
        return request.user.is_superuser # Adjust permissions as needed

# ==============================================================================
# ModelAdmin Classes
# ==============================================================================
# ... (ProjectAdmin, TaskCategoryAdmin, TaskSubcategoryAdmin as before) ...
@admin.register(Project)
class ProjectAdmin(admin.ModelAdmin):
    list_display = ("name_link", "start_date", "end_date", "created_at_formatted", "get_task_count_display")
    search_fields = ("name", "description")
    list_filter = ("start_date", "end_date", "created_at")
    date_hierarchy = "created_at"
    fieldsets = (
        (None, {"fields": ("name", "description")}),
        (_("Даты проекта"), {"fields": ("start_date", "end_date"), "classes": ("collapse",)}),
        (_("Системная информация"), {"fields": ("created_at", "updated_at"), "classes": ("collapse",)}),
    )
    readonly_fields = ("created_at", "updated_at")

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        return qs.annotate(task_count_annotation=models.Count('tasks'))

    @admin.display(description=_("Название проекта"), ordering='name')
    def name_link(self, obj):
        link = reverse("admin:tasks_project_change", args=[obj.pk])
        return format_html('<a href="{}">{}</a>', link, obj.name)

    @admin.display(description=_("Кол-во задач"), ordering='task_count_annotation')
    def get_task_count_display(self, obj):
        # Link to filtered task list in admin
        task_list_url = reverse("admin:tasks_task_changelist") + f"?project__id__exact={obj.pk}"
        return format_html('<a href="{}">{}</a>', task_list_url, obj.task_count_annotation)

    @admin.display(description=_("Создан"), ordering='created_at')
    def created_at_formatted(self, obj):
        if obj.created_at: return obj.created_at.strftime("%d.%m.%Y %H:%M")
        return "—"

@admin.register(TaskCategory)
class TaskCategoryAdmin(admin.ModelAdmin):
    list_display = ("name_link", "get_subcategory_count_display", "get_task_count_display", "created_at_formatted")
    search_fields = ("name", "description")
    readonly_fields = ("created_at", "updated_at")

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        return qs.annotate(
            task_count_annotation=models.Count('tasks'),
            subcategory_count_annotation=models.Count('subcategories')
        )

    @admin.display(description=_("Название категории"), ordering='name')
    def name_link(self, obj):
        link = reverse("admin:tasks_taskcategory_change", args=[obj.pk])
        return format_html('<a href="{}">{}</a>', link, obj.name)

    @admin.display(description=_("Подкатегорий"), ordering='subcategory_count_annotation')
    def get_subcategory_count_display(self, obj):
        subcat_list_url = reverse("admin:tasks_tasksubcategory_changelist") + f"?category__id__exact={obj.pk}"
        return format_html('<a href="{}">{}</a>', subcat_list_url, obj.subcategory_count_annotation)

    @admin.display(description=_("Задач"), ordering='task_count_annotation')
    def get_task_count_display(self, obj):
        task_list_url = reverse("admin:tasks_task_changelist") + f"?category__id__exact={obj.pk}"
        return format_html('<a href="{}">{}</a>', task_list_url, obj.task_count_annotation)

    @admin.display(description=_("Создана"), ordering='created_at')
    def created_at_formatted(self, obj):
        if obj.created_at: return obj.created_at.strftime("%d.%m.%Y %H:%M")
        return "—"

@admin.register(TaskSubcategory)
class TaskSubcategoryAdmin(admin.ModelAdmin):
    list_display = ("name_link", "category_link", "get_task_count_display", "created_at_formatted")
    list_filter = ("category",)
    search_fields = ("name", "description", "category__name")
    list_select_related = ('category',)
    autocomplete_fields = ('category',)
    readonly_fields = ("created_at", "updated_at")

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        return qs.annotate(task_count_annotation=models.Count('tasks'))

    @admin.display(description=_("Подкатегория"), ordering='name')
    def name_link(self, obj):
        link = reverse("admin:tasks_tasksubcategory_change", args=[obj.pk])
        return format_html('<a href="{}">{}</a>', link, obj.name)

    @admin.display(description=_("Категория"), ordering='category__name')
    def category_link(self, obj):
        if obj.category:
            link = reverse("admin:tasks_taskcategory_change", args=[obj.category.id])
            return format_html('<a href="{}">{}</a>', link, obj.category.name)
        return "—"

    @admin.display(description=_("Задач"), ordering='task_count_annotation')
    def get_task_count_display(self, obj):
        task_list_url = reverse("admin:tasks_task_changelist") + f"?subcategory__id__exact={obj.pk}"
        return format_html('<a href="{}">{}</a>', task_list_url, obj.task_count_annotation)

    @admin.display(description=_("Создана"), ordering='created_at')
    def created_at_formatted(self, obj):
        if obj.created_at: return obj.created_at.strftime("%d.%m.%Y %H:%M")
        return "—"


@admin.register(Task)
class TaskAdmin(admin.ModelAdmin):
    inlines = [inline for inline in [TaskUserRoleInline, TaskCommentInline, TaskPhotoInline] if inline is not None]

    list_display = (
        "task_number_link", "title_trimmed", "project_link", "status_colored",
        "priority_colored", "deadline_relative", "assigned_users_display",
        "created_by_link", "created_at_formatted"
    )

    # --- CORRECTED list_filter ---
    list_filter_base = [
        "status", "priority", "project", "category",
        ('deadline', admin.DateFieldListFilter),
        ('created_at', admin.DateFieldListFilter),
    ]
    if TaskUserRole: # Conditionally add filters
        list_filter_base.extend([
            # Use tuple format: ('field_lookup', FilterClass)
            ('user_roles__user', admin.RelatedOnlyFieldListFilter), # Filter by users who have any role
            ('user_roles__role', admin.ChoicesFieldListFilter),     # Filter by role type
        ])
    list_filter = list_filter_base
    # --- End Correction ---

    search_fields = (
        "task_number", "title", "description", "project__name",
        "created_by__username", "created_by__first_name", "created_by__last_name",
        *(("user_roles__user__username",) if TaskUserRole else ()),
        *(("user_roles__user__first_name",) if TaskUserRole else ()),
        *(("user_roles__user__last_name",) if TaskUserRole else ()),
    )
    search_fields = [f for f in search_fields if f is not None]

    ordering = ("-created_at", "priority", "deadline")
    date_hierarchy = "created_at"
    readonly_fields = ("task_number", "created_by_link", "created_at", "updated_at", "completion_date")
    list_select_related = ('project', 'category', 'subcategory', 'created_by')
    list_prefetch_related = ('user_roles__user',) if TaskUserRole else ()
    autocomplete_fields = ('project', 'category', 'subcategory', 'created_by')

    fieldsets = (
        (None, {"fields": ("task_number", "project", "title", "description")}),
        (_("Классификация и Статус"), {"fields": ("category", "subcategory", "status", "priority")}),
        (_("Сроки и Оценка"), {"fields": ("start_date", "deadline", "completion_date", "estimated_time"), "classes": ("collapse",)}),
        (_("Системная информация"), {"fields": ("created_by_link", "created_at", "updated_at"), "classes": ("collapse",)}),
    )
    change_list_template = "admin/tasks/task/change_list_with_reports.html"

    # --- Display Methods (as before) ---
    @admin.display(description=_("Номер"), ordering='task_number')
    def task_number_link(self, obj):
        url = reverse('admin:tasks_task_change', args=[obj.id])
        return format_html('<a href="{}">{}</a>', url, obj.task_number or f"ID:{obj.id}")

    @admin.display(description=_("Название"), ordering='title')
    def title_trimmed(self, obj):
        return (obj.title[:75] + '...') if len(obj.title) > 75 else obj.title

    @admin.display(description=_("Статус"), ordering='status')
    def status_colored(self, obj):
        status_colors = {
            Task.StatusChoices.NEW: "#6b7280", Task.StatusChoices.IN_PROGRESS: "#f59e0b",
            Task.StatusChoices.ON_HOLD: "#3b82f6", Task.StatusChoices.COMPLETED: "#16a34a",
            Task.StatusChoices.CANCELLED: "#9ca3af", Task.StatusChoices.OVERDUE: "#ef4444",
        }
        color = status_colors.get(obj.status, "#1f2937")
        style = "font-weight: 500;"
        if obj.status == Task.StatusChoices.CANCELLED: style += "text-decoration: line-through;"
        return format_html('<span style="color: {}; {}">{}</span>', color, style, obj.get_status_display())

    @admin.display(description=_("Приоритет"), ordering='priority')
    def priority_colored(self, obj):
        priority_colors = {
            Task.TaskPriority.HIGH: "#ef4444", Task.TaskPriority.MEDIUM_HIGH: "#f97316",
            Task.TaskPriority.MEDIUM: "#eab308", Task.TaskPriority.MEDIUM_LOW: "#2563eb",
            Task.TaskPriority.LOW: "#16a34a",
        }
        color = priority_colors.get(obj.priority, "#6b7280")
        icons = {
             Task.TaskPriority.HIGH: "fa-flag", Task.TaskPriority.MEDIUM_HIGH:"fa-angle-double-up",
             Task.TaskPriority.MEDIUM:"fa-equals", Task.TaskPriority.MEDIUM_LOW:"fa-angle-double-down",
             Task.TaskPriority.LOW:"fa-angle-down",
        }
        icon = icons.get(obj.priority, "fa-question-circle")
        return format_html('<span style="color: {};"><i class="fas {} fa-fw mr-1"></i>{}</span>',
                           color, icon, obj.get_priority_display())

    @admin.display(description=_("Срок"), ordering='deadline')
    def deadline_relative(self, obj):
        if not obj.deadline: return "—"
        now = timezone.now()
        delta = obj.deadline - now
        days = delta.days
        absolute_date = obj.deadline.strftime("%d.%m.%Y %H:%M")
        color = "inherit"; icon = "fa-calendar-alt"; relative = ""
        if obj.is_overdue:
            color, icon = "#ef4444", "fa-exclamation-triangle"
            relative = _("просрочено") + f" ({abs(days)} дн.)" if days < -1 else _("сегодня (просроч.)") if days == 0 else _("вчера")
        elif obj.status == Task.StatusChoices.COMPLETED:
            color, icon, relative = "#16a34a", "fa-calendar-check", _("выполнено")
        elif days == 0: color, icon, relative = "#f59e0b", "fa-clock", _("сегодня")
        elif days == 1: relative = _("завтра")
        elif days < 7: relative = _("через %(d)d дн.") % {'d': days}
        else: relative = absolute_date[:10]

        return format_html('<span style="color:{};" title="{}"><i class="far {} fa-fw mr-1"></i>{}</span>',
                           color, absolute_date, icon, relative)

    @admin.display(description=_("Участники"))
    def assigned_users_display(self, obj):
        if not TaskUserRole: return "N/A"
        roles = obj.user_roles.all()
        if not roles: return "—"
        resp = [f"{r.user.display_name}" for r in roles if r.role == TaskUserRole.RoleChoices.RESPONSIBLE and r.user]
        execs = [f"{r.user.display_name}" for r in roles if r.role == TaskUserRole.RoleChoices.EXECUTOR and r.user]
        parts = []
        if resp: parts.append(f"<strong>{_('Отв')}:</strong> {', '.join(resp)}")
        if execs: parts.append(f"<strong>{_('Исп')}:</strong> {', '.join(execs)}")
        return format_html("<br>".join(parts)) if parts else "—"

    @admin.display(description=_("Создана"), ordering='created_at')
    def created_at_formatted(self, obj):
        if obj.created_at: return obj.created_at.strftime("%d.%m.%Y %H:%M")
        return "—"

    @admin.display(description=_("Создатель"), ordering='created_by__username')
    def created_by_link(self, obj):
        if obj.created_by:
            try:
                link = reverse("admin:%s_%s_change" % (obj.created_by._meta.app_label, obj.created_by._meta.model_name), args=[obj.created_by.id])
                return format_html('<a href="{}">{}</a>', link, obj.created_by.display_name or obj.created_by.username)
            except Exception: return obj.created_by.display_name or obj.created_by.username
        return "—"

    @admin.display(description=_("Проект"), ordering='project__name')
    def project_link(self, obj):
        if obj.project:
            link = reverse("admin:tasks_project_change", args=[obj.project.id])
            return format_html('<a href="{}">{}</a>', link, obj.project.name)
        return "—"

    # --- URLs for Reports Integration (Corrected) ---
    def get_urls(self):
        urls = super().get_urls()
        info = self.model._meta.app_label, self.model._meta.model_name

        # Map names to VIEW FUNCTIONS or CLASSES
        report_map = {
            'export_excel': getattr(report_views, 'export_tasks_to_excel', None),
            'completed': getattr(report_views, 'CompletedTasksReportView', None),
            'overdue': getattr(report_views, 'OverdueTasksReportView', None),
            'active': getattr(report_views, 'ActiveTasksReportView', None),
            'performance': getattr(report_views, 'TeamPerformanceReportView', None),
            'workload': getattr(report_views, 'EmployeeWorkloadReportView', None),
            'abc': getattr(report_views, 'AbcAnalysisReportView', None),
            'sla': getattr(report_views, 'SlaReportView', None),
            'duration': getattr(report_views, 'TaskDurationReportView', None),
            'issues': getattr(report_views, 'IssuesReportView', None),
            'delay_reasons': getattr(report_views, 'DelayReasonsReportView', None),
            'cancelled': getattr(report_views, 'CancelledTasksReportView', None),
            'chart_progress': getattr(report_views, 'TaskProgressChartView', None),
            'chart_gantt': getattr(report_views, 'GanttChartView', None),
            'summary': getattr(report_views, 'TaskSummaryReportView', None),
        }

        custom_urls = [
            # Use ReportIndexView class directly, get the view callable
            path('reports/', self.admin_site.admin_view(report_views.ReportIndexView.as_view()), name='%s_%s_report_index' % info),
        ]

        # Dynamically add report URLs
        for name, view_class_or_func in report_map.items():
            view_callable = None
            if view_class_or_func:
                if isinstance(view_class_or_func, type): # CBV Class
                    if hasattr(view_class_or_func, 'as_view'):
                        view_callable = view_class_or_func.as_view()
                    else: logger.error(f"Report item '{name}' is a class but not a valid CBV.")
                elif callable(view_class_or_func): # FBV function
                    view_callable = view_class_or_func
                else: logger.error(f"Report item '{name}' is not callable or a class type.")

            if view_callable:
                custom_urls.append(
                    path(f'reports/{name}/', self.admin_site.admin_view(view_callable), name=f'%s_%s_report_{name}' % info)
                )
            else:
                 logger.warning(f"Report view for '{name}' not found or invalid. Skipping admin URL.")

        return custom_urls + urls

    # --- Admin Actions (as before) ---
    @admin.action(description=_("Отметить выбранные задачи как 'Выполнена'"))
    def mark_completed(self, request, queryset):
        # ... (code as before) ...
        updated_count = 0
        for task in queryset.exclude(status=Task.StatusChoices.COMPLETED):
            task.status = Task.StatusChoices.COMPLETED
            try:
                task.save(update_fields=['status', 'completion_date', 'updated_at'])
                updated_count += 1
            except Exception as e:
                self.message_user(request, _("Ошибка при обновлении задачи %(num)s: %(err)s") % {'num': task.task_number, 'err': e}, level=messages.ERROR)
        if updated_count > 0:
            self.message_user(request, _("%(count)d задач успешно отмечены как выполненные.") % {'count': updated_count}, level=messages.SUCCESS)

    @admin.action(description=_("Отметить выбранные задачи как 'В работе'"))
    def mark_in_progress(self, request, queryset):
        # ... (code as before) ...
        updated_count = 0
        for task in queryset.exclude(status__in=[Task.StatusChoices.COMPLETED, Task.StatusChoices.CANCELLED, Task.StatusChoices.IN_PROGRESS]):
            task.status = Task.StatusChoices.IN_PROGRESS
            try:
                task.save(update_fields=['status', 'completion_date', 'updated_at'])
                updated_count += 1
            except Exception as e:
                self.message_user(request, _("Ошибка при обновлении задачи %(num)s: %(err)s") % {'num': task.task_number, 'err': e}, level=messages.ERROR)
        if updated_count > 0:
            self.message_user(request, _("%(count)d задач успешно переведены в статус 'В работе'.") % {'count': updated_count}, level=messages.SUCCESS)

    actions = ['mark_completed', 'mark_in_progress']

    # --- Save Model Override (as before) ---
    def save_model(self, request, obj: Task, form, change):
        if not obj.pk and not obj.created_by_id:
            obj.created_by = request.user
        super().save_model(request, obj, form, change)

    def save_related(self, request, form, formsets, change):
        super().save_related(request, form, formsets, change)

@admin.register(TaskPhoto)
class TaskPhotoAdmin(admin.ModelAdmin):
    list_display = ("id", "task_link_admin", "thumbnail_preview", "description_trimmed", "uploaded_by_link_admin", "created_at_formatted")
    list_filter = ("created_at", "task__project", "uploaded_by")
    search_fields = ("description", "task__task_number", "task__title", "uploaded_by__username")
    list_select_related = ('task', 'uploaded_by', 'task__project')
    readonly_fields = ("thumbnail_preview", "uploaded_by_link_admin", "created_at", "updated_at")
    autocomplete_fields = ('task', 'uploaded_by')
    fieldsets = (
        (None, {"fields": ("task", "photo", "thumbnail_preview", "description")}),
        (_("Системная информация"), {"fields": ("uploaded_by_link_admin", "created_at", "updated_at"), "classes": ("collapse",)}),
    )

    @admin.display(description=_("Задача"), ordering='task__task_number')
    def task_link_admin(self, obj):
        if obj.task:
            link = reverse("admin:tasks_task_change", args=[obj.task.id])
            title = (obj.task.title[:30] + '...') if len(obj.task.title) > 30 else obj.task.title
            return format_html('<a href="{}">[{}] {}</a>', link, obj.task.task_number or obj.task.id, title)
        return "—"

    @admin.display(description=_("Описание"))
    def description_trimmed(self, obj):
        return (obj.description[:50] + '...') if len(obj.description) > 50 else obj.description

    @admin.display(description=_("Миниатюра"))
    def thumbnail_preview(self, obj):
        if obj.photo and hasattr(obj.photo, 'url'):
            return format_html('<a href="{0}" target="_blank"><img src="{0}" style="max-height: 50px; max-width: 100px; object-fit: cover;" /></a>', obj.photo.url)
        return "—"

    @admin.display(description=_("Загрузил"), ordering='uploaded_by__username')
    def uploaded_by_link_admin(self, obj):
        if obj.uploaded_by:
            try:
                link = reverse("admin:%s_%s_change" % (obj.uploaded_by._meta.app_label, obj.uploaded_by._meta.model_name), args=[obj.uploaded_by.id])
                return format_html('<a href="{}">{}</a>', link, obj.uploaded_by.display_name or obj.uploaded_by.username)
            except Exception:
                 return obj.uploaded_by.display_name or obj.uploaded_by.username
        return "—"

    @admin.display(description=_("Создано"), ordering='created_at')
    def created_at_formatted(self, obj):
        if obj.created_at: return obj.created_at.strftime("%d.%m.%Y %H:%M")
        return "—"

    def save_model(self, request, obj, form, change):
        if not obj.pk and not obj.uploaded_by_id:
            obj.uploaded_by = request.user
        super().save_model(request, obj, form, change)

@admin.register(TaskComment)
class TaskCommentAdmin(admin.ModelAdmin):
    list_display = ('id', 'task_link_comment', 'author_link_comment', 'text_trimmed', 'created_at_formatted')
    list_filter = ('created_at', 'author', 'task__project')
    search_fields = ('text', 'author__username', 'task__title', 'task__task_number')
    readonly_fields = ('task', 'author', 'created_at', 'updated_at')
    list_select_related = ('task', 'author', 'task__project')
    autocomplete_fields = ('task', 'author')

    def get_queryset(self, request):
        return super().get_queryset(request).select_related('task', 'author', 'task__project')

    @admin.display(description=_("Задача"), ordering='task__task_number')
    def task_link_comment(self, obj: TaskComment):
        if obj.task:
            link = reverse('admin:tasks_task_change', args=[obj.task.id])
            return format_html('<a href="{}">{}</a>', link, obj.task.task_number or f"ID:{obj.task_id}")
        return "—"

    @admin.display(description=_("Автор"), ordering='author__username')
    def author_link_comment(self, obj: TaskComment):
        if obj.author:
            try:
                link = reverse("admin:%s_%s_change" % (obj.author._meta.app_label, obj.author._meta.model_name), args=[obj.author.id])
                return format_html('<a href="{}">{}</a>', link, obj.author.display_name or obj.author.username)
            except Exception:
                 return obj.author.display_name or obj.author.username
        return _("Система/Удален")

    @admin.display(description=_("Текст"))
    def text_trimmed(self, obj: TaskComment):
        return (obj.text[:100] + '...') if len(obj.text) > 100 else obj.text

    @admin.display(description=_("Создан"), ordering='created_at')
    def created_at_formatted(self, obj: TaskComment):
        if obj.created_at: return obj.created_at.strftime("%d.%m.%Y %H:%M")
        return "—"

    def has_add_permission(self, request): return False
    def has_change_permission(self, request, obj=None): return request.user.is_superuser
    def has_delete_permission(self, request, obj=None): return request.user.is_superuser
