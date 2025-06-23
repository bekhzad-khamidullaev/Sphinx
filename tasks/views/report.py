import io
import base64
import urllib.parse
import logging
from datetime import timedelta
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import plotly.express as px

from django.contrib.admin.views.decorators import staff_member_required
from django.db.models import Count, F, Case, When, Value, CharField, Q, ExpressionWrapper, DurationField, Prefetch
from django.http import HttpResponse
from django.shortcuts import render, redirect
from django.urls import reverse, reverse_lazy
from django.utils import timezone
from django.utils.timezone import make_naive
from django.utils.translation import gettext_lazy as _
from django.views.generic import TemplateView, ListView
from django.contrib.auth.mixins import UserPassesTestMixin
from django.contrib import messages
from django.views import View
from django.contrib.auth import get_user_model


from ..models import Task, Project, TaskCategory, TaskSubcategory, TaskAssignment
User = get_user_model()
try:
    from profiles.models import Team, Department
except ImportError:
    Team, Department = None, None


logger = logging.getLogger(__name__)

REPORT_PAGINATE_BY = 25

def get_admin_base_context(page_title="Отчет", request=None):
    is_staff = request.user.is_staff if request and hasattr(request, 'user') else False
    context = {
        'title': page_title, 'site_title': _('Администрирование Sphinx'),
        'site_header': _('Администрирование Sphinx'), 'has_permission': is_staff,
        'is_popup': False, 'is_nav_sidebar_enabled': True,
        'opts': Task._meta, 'app_label': Task._meta.app_label,
    }
    return context

class StaffReportMixin(UserPassesTestMixin):
    raise_exception = False
    login_url = reverse_lazy('admin:login')

    def test_func(self):
        return self.request.user.is_authenticated and self.request.user.is_staff

    def handle_no_permission(self):
        if self.request.user.is_authenticated:
            messages.error(self.request, _("Доступ запрещен. Требуются права персонала."))
            return redirect(reverse_lazy('admin:index'))
        return super().handle_no_permission()

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        admin_context = get_admin_base_context(context.get('page_title', _("Отчет")), self.request)
        context.update(admin_context)
        return context

@staff_member_required(login_url=reverse_lazy('admin:login'))
def export_tasks_to_excel(request):
    try:
        tasks_qs = Task.objects.select_related(
            'project', 'category', 'subcategory', 'created_by', 'team', 'department'
        ).prefetch_related(
            Prefetch('assignments', queryset=TaskAssignment.objects.select_related('user'))
        ).all()

        data_list = []
        for task in tasks_qs:
            participants_list = []
            executors_list = []
            responsible_list = []
            for assign in task.assignments.all():
                user_display = assign.user.display_name or assign.user.username
                participants_list.append(f"{user_display} ({assign.get_role_display()})")
                if assign.role == TaskAssignment.RoleChoices.EXECUTOR:
                    executors_list.append(user_display)
                if assign.role == TaskAssignment.RoleChoices.RESPONSIBLE:
                    responsible_list.append(user_display)

            data_list.append({
                _('Номер'): task.task_number or '-', _('Название'): task.title,
                _('Описание'): task.description or '-', _('Статус'): task.get_status_display(),
                _('Приоритет'): task.get_priority_display(), _('Проект'): task.project.name if task.project else '-',
                _('Категория'): task.category.name if task.category else '-',
                _('Подкатегория'): task.subcategory.name if task.subcategory else '-',
                _('Участники'): ", ".join(participants_list) or '-',
                _('Ответственные'): ", ".join(responsible_list) or '-',
                _('Исполнители'): ", ".join(executors_list) or '-',
                _('Создатель'): task.created_by.display_name if task.created_by else '-',
                _('Команда'): task.team.name if task.team else '-',
                _('Отдел'): task.department.name if task.department else '-',
                _('Начало'): make_naive(task.start_date).strftime('%Y-%m-%d') if task.start_date else None,
                _('Срок'): make_naive(task.due_date).strftime('%Y-%m-%d') if task.due_date else None,
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
         return redirect(reverse('admin:tasks_task_report_index'))

class ReportIndexView(StaffReportMixin, TemplateView):
    template_name = "reports/report_index.html"
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['page_title'] = _("Центр Отчетов")
        info = Task._meta.app_label, Task._meta.model_name
        context['report_links'] = {
            _("Экспорт задач в Excel"): reverse('admin:%s_%s_report_export_excel' % info),
            _("Завершенные задачи"): reverse('admin:%s_%s_report_completed' % info),
            _("Просроченные задачи"): reverse('admin:%s_%s_report_overdue' % info),
            _("Активные задачи"): reverse('admin:%s_%s_report_active' % info),
            _("Производительность"): reverse('admin:%s_%s_report_performance' % info),
            _("Загрузка"): reverse('admin:%s_%s_report_workload' % info),
            _("ABC-анализ"): reverse('admin:%s_%s_report_abc' % info),
            _("Соблюдение SLA"): reverse('admin:%s_%s_report_sla' % info),
            _("Длительность выполнения"): reverse('admin:%s_%s_report_duration' % info),
            _("Возможные баги"): reverse('admin:%s_%s_report_issues' % info),
            _("Причины задержки (Просроченные)"): reverse('admin:%s_%s_report_delay_reasons' % info),
            _("Отмененные задачи"): reverse('admin:%s_%s_report_cancelled' % info),
            _("График: Прогресс"): reverse('admin:%s_%s_report_chart_progress' % info),
            _("График: Диаграмма Ганта"): reverse('admin:%s_%s_report_chart_gantt' % info),
            _("Сводка по статусам"): reverse('admin:%s_%s_report_summary' % info),
        }
        return context

class CompletedTasksReportView(StaffReportMixin, ListView):
    template_name = "reports/completed_tasks_report.html"; context_object_name = "tasks"; paginate_by = REPORT_PAGINATE_BY
    def get_queryset(self):
        start_date = timezone.now() - timedelta(days=30); self.start_date = start_date
        return Task.objects.filter(status=Task.StatusChoices.COMPLETED, completion_date__gte=start_date
        ).select_related("project", "created_by"
        ).prefetch_related(Prefetch('assignments', queryset=TaskAssignment.objects.select_related('user'))
        ).order_by('-completion_date')
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs); context['page_title'] = _("Отчет: Завершенные задачи")
        context['start_date'] = self.start_date; context['end_date'] = timezone.now(); return context

class OverdueTasksReportView(StaffReportMixin, ListView):
    template_name = "reports/overdue_tasks_report.html"; context_object_name = "tasks"; paginate_by = REPORT_PAGINATE_BY
    def get_queryset(self):
        now_tz = timezone.now()
        return Task.objects.filter(due_date__lt=now_tz.date(), status__in=[Task.StatusChoices.NEW, Task.StatusChoices.IN_PROGRESS, Task.StatusChoices.ON_HOLD]
        ).select_related("project", "created_by"
        ).prefetch_related(Prefetch('assignments', queryset=TaskAssignment.objects.select_related('user'))
        ).order_by('due_date')
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs); context['page_title'] = _("Отчет: Просроченные задачи"); return context

class ActiveTasksReportView(StaffReportMixin, ListView):
    template_name = "reports/active_tasks_report.html"; context_object_name = "tasks"; paginate_by = REPORT_PAGINATE_BY
    def get_queryset(self):
        return Task.objects.filter(status__in=[Task.StatusChoices.NEW, Task.StatusChoices.IN_PROGRESS, Task.StatusChoices.ON_HOLD]
        ).select_related("project", "created_by"
        ).prefetch_related(Prefetch('assignments', queryset=TaskAssignment.objects.select_related('user'))
        ).order_by('priority', 'due_date')
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs); context['page_title'] = _("Отчет: Активные задачи"); return context

class TaskDurationReportView(StaffReportMixin, ListView):
    template_name = "reports/task_duration_report.html"; context_object_name = "tasks_with_duration"; paginate_by = REPORT_PAGINATE_BY
    def get_queryset(self):
        return (Task.objects.filter(status=Task.StatusChoices.COMPLETED, start_date__isnull=False, completion_date__isnull=False)
            .annotate(duration=ExpressionWrapper(F('completion_date') - F('start_date'), output_field=DurationField()))
            .filter(duration__isnull=False).values("pk", "task_number", "title", "duration").order_by('-duration'))
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs); context['page_title'] = _("Отчет: Длительность выполнения задач")
        object_list = context[self.context_object_name]
        for item in object_list:
            duration = item.get('duration')
            if isinstance(duration, timedelta):
                 total_seconds = int(duration.total_seconds()); days, rem = divmod(total_seconds, 86400); hours, rem = divmod(rem, 3600); minutes, seconds = divmod(rem, 60); duration_str = ""
                 if days > 0: duration_str += f"{days} д "
                 if hours > 0: duration_str += f"{hours} ч "
                 if minutes > 0: duration_str += f"{minutes} м "
                 if not duration_str or seconds > 0 : duration_str += f"{seconds} с"
                 item['duration_formatted'] = duration_str.strip() if duration_str else "0 с"
            else: item['duration_formatted'] = "N/A"
        return context

class IssuesReportView(StaffReportMixin, ListView):
    template_name = "reports/issues_report.html"; context_object_name = "tasks"; paginate_by = REPORT_PAGINATE_BY
    def get_queryset(self):
        issue_keywords = ['баг', 'bug', 'ошибка', 'дефект', 'issue', 'fix', 'исправить']; query = Q()
        for keyword in issue_keywords: query |= Q(title__icontains=keyword) | Q(description__icontains=keyword)
        return Task.objects.filter(query).select_related("project", "created_by"
        ).prefetch_related(Prefetch('assignments', queryset=TaskAssignment.objects.select_related('user'))
        ).order_by('-created_at')
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs); context['page_title'] = _("Отчет: Возможные баги/дефекты"); return context

class DelayReasonsReportView(StaffReportMixin, ListView):
    template_name = "reports/delay_reasons_report.html"; context_object_name = "tasks"; paginate_by = REPORT_PAGINATE_BY
    def get_queryset(self):
        return Task.objects.filter(due_date__lt=timezone.now().date(), status__in=[Task.StatusChoices.NEW, Task.StatusChoices.IN_PROGRESS, Task.StatusChoices.ON_HOLD]
        ).select_related("project", "created_by"
        ).prefetch_related(Prefetch('assignments', queryset=TaskAssignment.objects.select_related('user'))
        ).order_by('due_date')
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs); context['page_title'] = _("Отчет: Просроченные задачи (для анализа причин)")
        context['report_info'] = _("Примечание: Для анализа причин задержки рекомендуется добавить соответствующее поле в модель Задачи."); return context

class CancelledTasksReportView(StaffReportMixin, ListView):
    template_name = "reports/cancelled_tasks_report.html"; context_object_name = "tasks"; paginate_by = REPORT_PAGINATE_BY
    def get_queryset(self):
        return Task.objects.filter(status=Task.StatusChoices.CANCELLED
        ).select_related("project", "created_by"
        ).prefetch_related(Prefetch('assignments', queryset=TaskAssignment.objects.select_related('user'))
        ).order_by('-updated_at')
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs); context['page_title'] = _("Отчет: Отмененные задачи"); return context

class TeamPerformanceReportView(StaffReportMixin, TemplateView):
    template_name = "reports/team_performance_report.html"
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs); context['page_title'] = _("Отчет: Производительность исполнителей")
        context['performance_data'] = (TaskAssignment.objects.filter(role=TaskAssignment.RoleChoices.EXECUTOR, task__status=Task.StatusChoices.COMPLETED)
            .select_related('user').values("user__username", "user__first_name", "user__last_name")
            .annotate(total_tasks=Count("task")).order_by('-total_tasks'))
        return context

class EmployeeWorkloadReportView(StaffReportMixin, TemplateView):
    template_name = "reports/employee_workload_report.html"
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs); context['page_title'] = _("Отчет: Загрузка исполнителей")
        context['workload_data'] = (TaskAssignment.objects.filter(role=TaskAssignment.RoleChoices.EXECUTOR, task__status__in=[Task.StatusChoices.NEW, Task.StatusChoices.IN_PROGRESS, Task.StatusChoices.ON_HOLD])
            .select_related('user').values("user__username", "user__first_name", "user__last_name")
            .annotate(total_tasks=Count("task")).order_by('-total_tasks'))
        return context

class AbcAnalysisReportView(StaffReportMixin, TemplateView):
    template_name = "reports/abc_analysis_report.html"
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs); context['page_title'] = _("Отчет: ABC-анализ задач")
        context['tasks_data'] = Task.objects.annotate(
            priority_group=Case(
                When(priority=Task.TaskPriority.HIGH, then=Value("A")),
                When(priority__in=[Task.TaskPriority.MEDIUM_HIGH, Task.TaskPriority.MEDIUM], then=Value("B")),
                When(priority__in=[Task.TaskPriority.MEDIUM_LOW, Task.TaskPriority.LOW], then=Value("C")),
                default=Value("Unknown"), output_field=CharField(),
            )).values("priority_group").annotate(total_tasks=Count("id")).order_by('priority_group')
        return context

class SlaReportView(StaffReportMixin, TemplateView):
    template_name = "reports/sla_report.html"
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs); context['page_title'] = _("Отчет: Соблюдение SLA")
        context['sla_data'] = (Task.objects.filter(status=Task.StatusChoices.COMPLETED, due_date__isnull=False, completion_date__isnull=False)
            .annotate(sla_met=Case(When(completion_date__date__lte=F("due_date"), then=Value("Met")), default=Value("Not Met"), output_field=CharField()))
            .values("sla_met").annotate(total_tasks=Count("id")).order_by('sla_met'))
        return context

class TaskProgressChartView(StaffReportMixin, TemplateView):
    template_name = "reports/task_progress_chart.html"
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs); context['page_title'] = _("График: Прогресс выполнения задач")
        status_labels = dict(Task.StatusChoices.choices)
        status_counts = Task.objects.values("status").annotate(total=Count("id")).order_by('status')
        plot_data = {status_labels.get(item['status'], item['status']): item['total'] for item in status_counts}
        chart_uri, message = None, None
        if plot_data:
            try:
                fig, ax = plt.subplots(figsize=(10, 6)); ax.bar(plot_data.keys(), plot_data.values())
                ax.set_xlabel(_("Статус")); ax.set_ylabel(_("Количество задач")); ax.set_title(context['page_title'])
                plt.xticks(rotation=45, ha="right"); plt.tight_layout()
                buf = io.BytesIO(); plt.savefig(buf, format="png"); buf.seek(0)
                string = base64.b64encode(buf.read()); chart_uri = "data:image/png;base64," + urllib.parse.quote(string); plt.close(fig)
            except Exception as e: logger.exception("Error generating task progress chart"); message = _("Ошибка при генерации графика.")
        else: message = _("Нет данных для построения графика.")
        context.update({"chart": chart_uri, "message": message}); return context

class GanttChartView(StaffReportMixin, TemplateView):
    template_name = "reports/gantt_chart.html"
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs); context['page_title'] = _("Диаграмма Ганта")
        tasks_qs = Task.objects.filter(start_date__isnull=False, due_date__isnull=False).values("task_number", "title", "start_date", "due_date", "status")
        df = pd.DataFrame(list(tasks_qs)); chart_html, message = None, None
        if not df.empty:
            try:
                status_map = dict(Task.StatusChoices.choices); df['status_display'] = df['status'].map(status_map).fillna(df['status'])
                df['label'] = df['task_number'].astype(str) + ': ' + df['title'].str.slice(0, 50)
                df['start_date'] = pd.to_datetime(df['start_date']); df['due_date'] = pd.to_datetime(df['due_date'])
                fig = px.timeline(df, x_start="start_date", x_end="due_date", y="label", color="status_display", title=context['page_title'], labels={"label": _("Задача"), "x": _("Время"), "status_display": _("Статус")})
                fig.update_yaxes(autorange="reversed", categoryorder='array', categoryarray=df.sort_values('start_date')['label'].unique())
                chart_html = fig.to_html(full_html=False, include_plotlyjs='cdn')
            except Exception as e: logger.exception("Error generating gantt chart"); message = _("Ошибка при генерации диаграммы Ганта.")
        else: message = _("Нет данных для построения диаграммы Ганта.")
        context.update({"chart": chart_html, "message": message}); return context

class TaskSummaryReportView(StaffReportMixin, TemplateView):
    template_name = "reports/task_summary_report.html"
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs); context['page_title'] = _("Сводный отчет по задачам")
        status_counts = Task.objects.values('status').annotate(count=Count('id')).order_by('status')
        status_map = dict(Task.StatusChoices.choices)
        report_data = [(status_map.get(item['status'], item['status']), item['count']) for item in status_counts]
        context['report_data'] = report_data; context['total_tasks'] = Task.objects.count(); return context