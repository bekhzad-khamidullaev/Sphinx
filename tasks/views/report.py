# tasks/views/report.py
import io
import base64
import urllib.parse
import logging
from datetime import timedelta
from django.utils import timezone # Use Django timezone
from django.utils.timezone import make_naive
from django.conf import settings # For SITE_URL
from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger
from django.db.models import Count, F, Case, When, Value, CharField, Q, ExpressionWrapper, DurationField
from django.http import HttpResponse, HttpResponseServerError # Added HttpResponseServerError
from django.shortcuts import render, redirect, reverse # Added reverse
from django.urls import reverse_lazy
from django.utils.translation import gettext_lazy as _
from django.views.generic import TemplateView, ListView
from django.contrib.admin.views.decorators import staff_member_required
from django.contrib.auth.mixins import UserPassesTestMixin
from django.contrib import messages
from django.views import View

# --- Graceful import for heavy dependencies ---
PANDAS_AVAILABLE = False
MATPLOTLIB_AVAILABLE = False
PLOTLY_AVAILABLE = False

try:
    import pandas as pd
    PANDAS_AVAILABLE = True
except ImportError:
    pd = None
    logging.warning("Pandas not found. Excel export and some chart features will be disabled.")

try:
    import matplotlib
    # CRITICAL: Set backend BEFORE importing pyplot
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    MATPLOTLIB_AVAILABLE = True
except ImportError:
    matplotlib = None
    plt = None
    logging.warning("Matplotlib not found. Matplotlib charts will be disabled.")
except Exception as e:
    # Catch other potential errors during matplotlib setup
    matplotlib = None
    plt = None
    logging.error(f"Error initializing Matplotlib: {e}. Matplotlib charts will be disabled.")


try:
    import plotly.express as px
    PLOTLY_AVAILABLE = True
except ImportError:
    px = None
    logging.warning("Plotly not found. Plotly charts (like Gantt) will be disabled.")

# --- Model Imports ---
from ..models import Task, Project, TaskCategory, TaskSubcategory
try:
    from user_profiles.models import TaskUserRole, User
    UserModel = User # Use the imported custom User model
except ImportError:
    TaskUserRole = None
    # Fallback to Django's default user model if user_profiles isn't available or configured
    try:
        from django.contrib.auth import get_user_model
        UserModel = get_user_model()
    except Exception as e:
        logging.error(f"Could not get User model: {e}")
        UserModel = None # Indicate user model is unavailable

logger = logging.getLogger(__name__)

REPORT_PAGINATE_BY = 25

# --- Helper Function for Admin Context (as before) ---
def get_admin_base_context(page_title="Отчет", request=None):
    user = getattr(request, 'user', None)
    is_staff = user.is_staff if user and hasattr(user, 'is_staff') else False
    context = {
        'title': page_title,
        'site_title': _('Администрирование Sphinx'),
        'site_header': _('Администрирование Sphinx'),
        'has_permission': is_staff,
        'is_popup': False,
        'is_nav_sidebar_enabled': True,
        'opts': Task._meta,
        'app_label': Task._meta.app_label,
    }
    return context

# --- Base Mixin (as before) ---
class StaffReportMixin(UserPassesTestMixin):
    raise_exception = False
    login_url = reverse_lazy('admin:login')

    def test_func(self):
        user = getattr(self.request, 'user', None)
        return user and user.is_authenticated and user.is_staff

    def handle_no_permission(self):
        if self.request.user and self.request.user.is_authenticated:
            messages.error(self.request, _("Доступ запрещен. Требуются права персонала."))
            return redirect(reverse_lazy('admin:index'))
        return super().handle_no_permission()

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        admin_context = get_admin_base_context(context.get('page_title', _("Отчет")), self.request)
        context.update(admin_context)
        return context

# ==============================================================================
# FUNCTIONAL VIEW for Excel Export (Check for Pandas)
# ==============================================================================

@staff_member_required(login_url=reverse_lazy('admin:login'))
def export_tasks_to_excel(request):
    """Экспорт задач в Excel (доступен только персоналу)."""
    if not PANDAS_AVAILABLE:
        logger.error("Pandas library is required for Excel export but not found.")
        messages.error(request, _("Ошибка экспорта: библиотека Pandas не установлена."))
        # Redirect to a safe place, e.g., the report index in admin
        try:
            info = Task._meta.app_label, Task._meta.model_name
            return redirect(reverse('admin:%s_%s_report_index' % info))
        except Exception:
            return redirect(reverse('admin:index')) # Fallback redirect

    page_title = _("Экспорт задач в Excel")
    try:
        tasks_qs = Task.objects.select_related(
            'project', 'category', 'subcategory', 'created_by'
        ).prefetch_related(
            'user_roles__user' # Ensure TaskUserRole is defined and related_name is 'user_roles'
        ).all()

        data_list = []
        for task in tasks_qs:
            # Handle potential absence of TaskUserRole gracefully
            participants = "N/A"
            executors = "N/A"
            responsible = "N/A"
            if TaskUserRole:
                user_roles = task.user_roles.select_related('user').all() # Query user roles for the task
                participants = ", ".join([f"{r.user.display_name if r.user else '?'} ({r.get_role_display()})" for r in user_roles]) or '-'
                executors = ", ".join([r.user.display_name for r in user_roles if r.user and r.role == TaskUserRole.RoleChoices.EXECUTOR]) or '-'
                responsible = ", ".join([r.user.display_name for r in user_roles if r.user and r.role == TaskUserRole.RoleChoices.RESPONSIBLE]) or '-'

            data_list.append({
                _('Номер'): task.task_number or '-',
                _('Название'): task.title,
                _('Описание'): task.description or '-',
                _('Статус'): task.get_status_display(),
                _('Приоритет'): task.get_priority_display(),
                _('Проект'): task.project.name if task.project else '-',
                _('Категория'): task.category.name if task.category else '-',
                _('Подкатегория'): task.subcategory.name if task.subcategory else '-',
                _('Участники'): participants,
                _('Ответственные'): responsible,
                _('Исполнители'): executors,
                _('Создатель'): task.created_by.display_name if task.created_by else '-',
                _('Начало'): make_naive(task.start_date).strftime('%Y-%m-%d') if task.start_date else None,
                _('Срок'): make_naive(task.deadline).strftime('%Y-%m-%d %H:%M') if task.deadline else None,
                _('Завершение'): make_naive(task.completion_date).strftime('%Y-%m-%d %H:%M') if task.completion_date else None,
                _('Создана'): make_naive(task.created_at).strftime('%Y-%m-%d %H:%M') if task.created_at else None,
                _('Обновлена'): make_naive(task.updated_at).strftime('%Y-%m-%d %H:%M') if task.updated_at else None,
                _('Оценка времени'): str(task.estimated_time) if task.estimated_time else None,
            })

        df = pd.DataFrame(data_list)

        response = HttpResponse(content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
        filename = f'tasks_export_{timezone.now():%Y%m%d_%H%M}.xlsx'
        response["Content-Disposition"] = f'attachment; filename="{urllib.parse.quote(filename)}"'

        with pd.ExcelWriter(response, engine="xlsxwriter", datetime_format='yyyy-mm-dd hh:mm', date_format='yyyy-mm-dd') as writer:
            df.to_excel(writer, index=False, sheet_name=_("Задачи"))
            worksheet = writer.sheets[_("Задачи")]
            for i, col in enumerate(df.columns):
                try:
                    column_len = max(df[col].astype(str).map(len).max(), len(col)) + 2
                    worksheet.set_column(i, i, min(column_len, 60))
                except Exception as col_e:
                    logger.warning(f"Could not auto-set width for column '{col}': {col_e}")
                    worksheet.set_column(i, i, len(col) + 5)
        return response

    except Exception as e:
         logger.exception("Error exporting tasks to Excel")
         messages.error(request, _("Произошла ошибка при экспорте в Excel: ") + str(e))
         try:
             info = Task._meta.app_label, Task._meta.model_name
             return redirect(reverse('admin:%s_%s_report_index' % info))
         except Exception:
             return redirect(reverse('admin:index'))

# ==============================================================================
# Report Views (CBVs)
# ==============================================================================

# --- THIS IS THE CLASS THAT WAS CAUSING THE ERROR ---
class ReportIndexView(StaffReportMixin, TemplateView):
    """Displays a list of available reports in the admin context."""
    template_name = "admin/tasks/report_list.html" # Use the admin template

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['page_title'] = _("Центр Отчетов по Задачам")
        info = Task._meta.app_label, Task._meta.model_name

        # Define the reports and their titles, checking for dependencies if needed
        report_definitions = {
            'export_excel': (_("Экспорт задач в Excel"), PANDAS_AVAILABLE),
            'completed': (_("Завершенные задачи"), True),
            'overdue': (_("Просроченные задачи"), True),
            'active': (_("Активные задачи"), True),
            'performance': (_("Производительность"), TaskUserRole is not None and UserModel is not None),
            'workload': (_("Загрузка"), TaskUserRole is not None and UserModel is not None),
            'abc': (_("ABC-анализ"), True),
            'sla': (_("Соблюдение SLA"), True),
            'duration': (_("Длительность выполнения"), True),
            'issues': (_("Возможные баги"), True),
            'delay_reasons': (_("Причины задержки (Просроченные)"), True),
            'cancelled': (_("Отмененные задачи"), True),
            'chart_progress': (_("График: Прогресс"), MATPLOTLIB_AVAILABLE),
            'chart_gantt': (_("График: Диаграмма Ганта"), PLOTLY_AVAILABLE and PANDAS_AVAILABLE),
            'summary': (_("Сводка по статусам"), True),
        }

        report_links = {}
        for name, (title, available) in report_definitions.items():
             if available:
                 try:
                     url = reverse(f'admin:%s_%s_report_{name}' % info)
                     report_links[name] = {'url': url, 'title': title}
                 except Exception as e:
                     logger.warning(f"Could not reverse URL for admin report '{name}'. Check TaskAdmin.get_urls(). Error: {e}")
                     # Optionally add a disabled link:
                     # report_links[name] = {'url': '#', 'title': title + _(" (ошибка URL)"), 'disabled': True}
             else:
                 # Optionally add a disabled link for unavailable reports:
                 # report_links[name] = {'url': '#', 'title': title + _(" (недоступен)"), 'disabled': True}
                 pass # Or just don't include it

        context['report_links'] = report_links
        return context

# --- Paginated Reports using ListView ---

class CompletedTasksReportView(StaffReportMixin, ListView):
    template_name = "reports/completed_tasks_report.html"
    context_object_name = "tasks"
    paginate_by = REPORT_PAGINATE_BY

    def get_queryset(self):
        start_date = timezone.now() - timedelta(days=30)
        self.start_date = start_date # Save for context
        qs = Task.objects.filter(
            status=Task.StatusChoices.COMPLETED, completion_date__gte=start_date
        ).select_related("project", "created_by")
        if TaskUserRole: # Conditionally prefetch roles
            qs = qs.prefetch_related('user_roles__user')
        return qs.order_by('-completion_date')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['page_title'] = _("Отчет: Завершенные задачи")
        context['start_date'] = self.start_date
        context['end_date'] = timezone.now()
        return context

class OverdueTasksReportView(StaffReportMixin, ListView):
    template_name = "reports/overdue_tasks_report.html"
    context_object_name = "tasks"
    paginate_by = REPORT_PAGINATE_BY

    def get_queryset(self):
        now_tz = timezone.now()
        qs = Task.objects.filter(
            deadline__lt=now_tz,
            status__in=[Task.StatusChoices.NEW, Task.StatusChoices.IN_PROGRESS, Task.StatusChoices.ON_HOLD]
        ).select_related("project", "created_by")
        if TaskUserRole:
             qs = qs.prefetch_related('user_roles__user')
        return qs.order_by('deadline')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['page_title'] = _("Отчет: Просроченные задачи")
        return context

class ActiveTasksReportView(StaffReportMixin, ListView):
    template_name = "reports/active_tasks_report.html"
    context_object_name = "tasks"
    paginate_by = REPORT_PAGINATE_BY

    def get_queryset(self):
        qs = Task.objects.filter(
             status__in=[Task.StatusChoices.NEW, Task.StatusChoices.IN_PROGRESS, Task.StatusChoices.ON_HOLD]
        ).select_related("project", "created_by")
        if TaskUserRole:
             qs = qs.prefetch_related('user_roles__user')
        return qs.order_by('priority', 'deadline')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['page_title'] = _("Отчет: Активные задачи")
        return context

class TaskDurationReportView(StaffReportMixin, ListView):
    template_name = "reports/task_duration_report.html"
    context_object_name = "tasks_with_duration"
    paginate_by = REPORT_PAGINATE_BY

    def get_queryset(self):
        # Ensure completion_date and start_date are valid DateTimeField and DateField respectively
        # Note: start_date is DateField, needs careful handling for duration calculation if exact time is needed
        # Convert start_date to datetime at the beginning of the day for comparison
        return (
            Task.objects.filter(
                status=Task.StatusChoices.COMPLETED,
                start_date__isnull=False,
                completion_date__isnull=False
            )
            .annotate(
                duration=ExpressionWrapper(
                    F('completion_date') - F('start_date'), # Direct subtraction works if start_date is DateTimeField
                    # If start_date is DateField, you might need Cast or functions:
                    # Cast(F('start_date'), DateTimeField()) might work on some DBs
                    # Or use database functions if available: datetime(F('start_date'), 'start of day')
                    output_field=DurationField()
                )
            )
            .filter(duration__isnull=False)
            .values("pk", "task_number", "title", "duration") # Use values for pagination efficiency
            .order_by('-duration')
        )


    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['page_title'] = _("Отчет: Длительность выполнения задач")
        object_list = context.get(self.context_object_name, []) # Get paginated list

        # Format duration in the view context for display
        for item in object_list:
            duration = item.get('duration')
            if isinstance(duration, timedelta):
                 total_seconds = int(duration.total_seconds()); days, rem = divmod(total_seconds, 86400); hours, rem = divmod(rem, 3600); minutes, seconds = divmod(rem, 60); duration_str = ""
                 if days > 0: duration_str += f"{days} д "
                 if hours > 0: duration_str += f"{hours} ч "
                 if minutes > 0: duration_str += f"{minutes} м "
                 if not duration_str or seconds > 0: duration_str += f"{seconds} с"
                 item['duration_formatted'] = duration_str.strip() if duration_str else "0 с"
            else:
                item['duration_formatted'] = "N/A" # Handle cases where duration might not be timedelta

        return context

class IssuesReportView(StaffReportMixin, ListView):
    template_name = "reports/issues_report.html"
    context_object_name = "tasks"
    paginate_by = REPORT_PAGINATE_BY

    def get_queryset(self):
        issue_keywords = ['баг', 'bug', 'ошибка', 'дефект', 'issue', 'fix', 'исправить']
        query = Q()
        for keyword in issue_keywords: query |= Q(title__icontains=keyword) | Q(description__icontains=keyword)
        qs = Task.objects.filter(query).select_related("project", "created_by")
        if TaskUserRole:
             qs = qs.prefetch_related('user_roles__user')
        return qs.order_by('-created_at')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['page_title'] = _("Отчет: Возможные баги/дефекты")
        return context

class DelayReasonsReportView(StaffReportMixin, ListView):
    template_name = "reports/delay_reasons_report.html"
    context_object_name = "tasks"
    paginate_by = REPORT_PAGINATE_BY

    def get_queryset(self):
        qs = Task.objects.filter(
            deadline__lt=timezone.now(),
            status__in=[Task.StatusChoices.NEW, Task.StatusChoices.IN_PROGRESS, Task.StatusChoices.ON_HOLD]
        ).select_related("project", "created_by")
        if TaskUserRole:
            qs = qs.prefetch_related('user_roles__user')
        return qs.order_by('deadline')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['page_title'] = _("Отчет: Просроченные задачи (для анализа причин)")
        context['report_info'] = _("Примечание: Для анализа причин задержки рекомендуется добавить соответствующее поле в модель Задачи.")
        return context

class CancelledTasksReportView(StaffReportMixin, ListView):
    template_name = "reports/cancelled_tasks_report.html"
    context_object_name = "tasks"
    paginate_by = REPORT_PAGINATE_BY

    def get_queryset(self):
        qs = Task.objects.filter(
            status=Task.StatusChoices.CANCELLED
        ).select_related("project", "created_by")
        if TaskUserRole:
            qs = qs.prefetch_related('user_roles__user')
        return qs.order_by('-updated_at')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['page_title'] = _("Отчет: Отмененные задачи")
        return context

# --- Non-Paginated Reports using TemplateView ---

class TeamPerformanceReportView(StaffReportMixin, TemplateView):
    template_name = "reports/team_performance_report.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['page_title'] = _("Отчет: Производительность исполнителей")
        if TaskUserRole and UserModel: # Check if models are available
            context['performance_data'] = (
                TaskUserRole.objects.filter(role=TaskUserRole.RoleChoices.EXECUTOR, task__status=Task.StatusChoices.COMPLETED)
                .select_related('user') # Optimize user fetching
                .values("user__username", "user__first_name", "user__last_name") # Select needed fields
                .annotate(total_tasks=Count("task")) # Count tasks per user
                .order_by('-total_tasks') # Order by most tasks completed
            )
        else:
            context['performance_data'] = []
            messages.warning(self.request, _("Модель TaskUserRole или User не найдена, отчет не может быть сгенерирован."))
        return context

class EmployeeWorkloadReportView(StaffReportMixin, TemplateView):
    template_name = "reports/employee_workload_report.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['page_title'] = _("Отчет: Загрузка исполнителей (активные задачи)")
        if TaskUserRole and UserModel:
            context['workload_data'] = (
                 TaskUserRole.objects.filter(
                     role=TaskUserRole.RoleChoices.EXECUTOR,
                     task__status__in=[Task.StatusChoices.NEW, Task.StatusChoices.IN_PROGRESS, Task.StatusChoices.ON_HOLD]
                 )
                .select_related('user')
                .values("user__username", "user__first_name", "user__last_name")
                .annotate(total_tasks=Count("task"))
                .order_by('-total_tasks')
            )
        else:
             context['workload_data'] = []
             messages.warning(self.request, _("Модель TaskUserRole или User не найдена, отчет не может быть сгенерирован."))
        return context

class AbcAnalysisReportView(StaffReportMixin, TemplateView):
    template_name = "reports/abc_analysis_report.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['page_title'] = _("Отчет: ABC-анализ задач по приоритету")
        context['tasks_data'] = Task.objects.annotate(
            priority_group=Case(
                When(priority=Task.TaskPriority.HIGH, then=Value("A")),
                When(priority__in=[Task.TaskPriority.MEDIUM_HIGH, Task.TaskPriority.MEDIUM], then=Value("B")),
                When(priority__in=[Task.TaskPriority.MEDIUM_LOW, Task.TaskPriority.LOW], then=Value("C")),
                default=Value("?"), output_field=CharField(),
            )
        ).values("priority_group").annotate(total_tasks=Count("id")).order_by('priority_group')
        return context

class SlaReportView(StaffReportMixin, TemplateView):
    template_name = "reports/sla_report.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['page_title'] = _("Отчет: Соблюдение SLA (срок выполнения)")
        context['sla_data'] = (
            Task.objects.filter(
                status=Task.StatusChoices.COMPLETED,
                deadline__isnull=False,
                completion_date__isnull=False
            )
            .annotate(
                sla_met=Case(
                    When(completion_date__lte=F("deadline"), then=Value("Met")), # Completed on or before deadline
                    default=Value("Not Met"),
                    output_field=CharField()
                )
            )
            .values("sla_met") # Group by the result
            .annotate(total_tasks=Count("id")) # Count tasks in each group
            .order_by('sla_met') # Order results
        )
        return context

# --- Chart Views (Check for library availability) ---
class TaskProgressChartView(StaffReportMixin, TemplateView):
    template_name = "reports/task_progress_chart.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['page_title'] = _("График: Прогресс выполнения задач по статусам")
        chart_uri, message = None, None

        if not MATPLOTLIB_AVAILABLE:
            message = _("Библиотека Matplotlib не установлена. График не может быть построен.")
        else:
            try:
                status_labels = dict(Task.StatusChoices.choices)
                status_counts = Task.objects.values("status").annotate(total=Count("id")).order_by('status')
                plot_data = {status_labels.get(item['status'], item['status']): item['total'] for item in status_counts}

                if plot_data:
                    fig, ax = plt.subplots(figsize=(10, 6))
                    ax.bar(plot_data.keys(), plot_data.values())
                    ax.set_xlabel(_("Статус")); ax.set_ylabel(_("Количество задач")); ax.set_title(context['page_title'])
                    plt.xticks(rotation=45, ha="right"); plt.tight_layout()
                    buf = io.BytesIO(); plt.savefig(buf, format="png", dpi=96); buf.seek(0)
                    string = base64.b64encode(buf.read()); chart_uri = "data:image/png;base64," + urllib.parse.quote(string)
                    plt.close(fig) # Close the figure to free memory
                else:
                    message = _("Нет данных для построения графика.")
            except Exception as e:
                 logger.exception("Error generating task progress chart")
                 message = _("Ошибка при генерации графика: %(error)s") % {'error': str(e)}
                 if plt and 'fig' in locals(): plt.close(fig) # Ensure figure is closed on error

        context.update({"chart": chart_uri, "message": message})
        return context

class GanttChartView(StaffReportMixin, TemplateView):
    template_name = "reports/gantt_chart.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['page_title'] = _("Диаграмма Ганта (Задачи со сроками)")
        chart_html, message = None, None

        if not PLOTLY_AVAILABLE or not PANDAS_AVAILABLE:
             message = _("Библиотеки Plotly и Pandas не установлены. Диаграмма Ганта не может быть построена.")
        else:
            try:
                # Fetch tasks with both start_date and deadline
                tasks_qs = Task.objects.filter(start_date__isnull=False, deadline__isnull=False).values(
                    "task_number", "title", "start_date", "deadline", "status"
                )
                df = pd.DataFrame(list(tasks_qs))

                if not df.empty:
                    # Prepare data for Plotly timeline
                    status_map = dict(Task.StatusChoices.choices)
                    df['status_display'] = df['status'].map(status_map).fillna(df['status'])
                    df['label'] = df['task_number'].astype(str) + ': ' + df['title'].str.slice(0, 50) # Task label

                    # Ensure dates are datetime objects (start_date might be just date)
                    df['start_dt'] = pd.to_datetime(df['start_date']) # Convert start_date to datetime
                    df['deadline_dt'] = pd.to_datetime(df['deadline'])

                    # Create Plotly figure
                    fig = px.timeline(
                        df,
                        x_start="start_dt",
                        x_end="deadline_dt",
                        y="label",
                        color="status_display",
                        title=context['page_title'],
                        labels={"label": _("Задача"), "x": _("Время"), "status_display": _("Статус")}
                    )
                    # Improve layout
                    fig.update_yaxes(autorange="reversed", categoryorder='array', categoryarray=df.sort_values('start_dt')['label'].unique())
                    fig.update_layout(xaxis_title="", yaxis_title="") # Cleaner axes

                    # Export to HTML (partial for embedding, using CDN for JS)
                    chart_html = fig.to_html(full_html=False, include_plotlyjs='cdn')
                else:
                    message = _("Нет задач с установленными датами начала и срока для построения диаграммы Ганта.")
            except Exception as e:
                 logger.exception("Error generating gantt chart")
                 message = _("Ошибка при генерации диаграммы Ганта: %(error)s") % {'error': str(e)}

        context.update({"chart": chart_html, "message": message})
        return context

class TaskSummaryReportView(StaffReportMixin, TemplateView):
    template_name = "reports/task_summary_report.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['page_title'] = _("Сводный отчет по задачам (статусы)")
        status_counts = Task.objects.values('status').annotate(count=Count('id')).order_by('status')
        status_map = dict(Task.StatusChoices.choices)
        report_data = [(status_map.get(item['status'], item['status']), item['count']) for item in status_counts]
        context['report_data'] = report_data
        context['total_tasks'] = Task.objects.count()
        return context

# --- Function-based view aliases (kept for compatibility with existing admin URLs if needed) ---
# These simply call the .as_view() of the corresponding CBV.

@staff_member_required(login_url=reverse_lazy('admin:login'))
def completed_tasks_report(request):
    return CompletedTasksReportView.as_view()(request)

@staff_member_required(login_url=reverse_lazy('admin:login'))
def overdue_tasks_report(request):
    return OverdueTasksReportView.as_view()(request)

@staff_member_required(login_url=reverse_lazy('admin:login'))
def active_tasks_report(request):
    return ActiveTasksReportView.as_view()(request)

@staff_member_required(login_url=reverse_lazy('admin:login'))
def team_performance_report(request):
    return TeamPerformanceReportView.as_view()(request)

@staff_member_required(login_url=reverse_lazy('admin:login'))
def employee_workload_report(request):
    return EmployeeWorkloadReportView.as_view()(request)

@staff_member_required(login_url=reverse_lazy('admin:login'))
def abc_analysis_report(request):
    return AbcAnalysisReportView.as_view()(request)

@staff_member_required(login_url=reverse_lazy('admin:login'))
def sla_report(request):
    return SlaReportView.as_view()(request)

@staff_member_required(login_url=reverse_lazy('admin:login'))
def task_duration_report(request):
    return TaskDurationReportView.as_view()(request)

@staff_member_required(login_url=reverse_lazy('admin:login'))
def issues_report(request):
    return IssuesReportView.as_view()(request)

@staff_member_required(login_url=reverse_lazy('admin:login'))
def delay_reasons_report(request):
    return DelayReasonsReportView.as_view()(request)

@staff_member_required(login_url=reverse_lazy('admin:login'))
def cancelled_tasks_report(request):
    return CancelledTasksReportView.as_view()(request)

@staff_member_required(login_url=reverse_lazy('admin:login'))
def task_progress_chart(request):
    return TaskProgressChartView.as_view()(request)

@staff_member_required(login_url=reverse_lazy('admin:login'))
def gantt_chart(request):
    return GanttChartView.as_view()(request)

# Note: TaskSummaryReportView is already a CBV, its alias is not strictly needed
# but kept here for consistency if you reference it via the function name elsewhere.
@staff_member_required(login_url=reverse_lazy('admin:login'))
def task_summary_report(request):
    return TaskSummaryReportView.as_view()(request)