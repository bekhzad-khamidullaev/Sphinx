# tasks/views/report.py
import io
import base64
import urllib.parse
import pandas as pd
import matplotlib
matplotlib.use('Agg') # Устанавливаем бэкенд ПЕРЕД импортом pyplot
import matplotlib.pyplot as plt
import plotly.express as px
from datetime import timedelta
import logging

from django.contrib.admin.views.decorators import staff_member_required
from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger # Добавляем ошибки пагинатора
from django.db.models import Count, F, Case, When, Value, CharField, Q, ExpressionWrapper, DurationField
from django.http import HttpResponse
from django.shortcuts import render, redirect # Добавляем redirect
from django.urls import reverse # Добавляем reverse
from django.utils import timezone
from django.utils.timezone import make_naive
from django.utils.translation import gettext_lazy as _
from django.views.generic import TemplateView
from django.contrib.auth.mixins import UserPassesTestMixin
from django.contrib import messages # Для сообщений об ошибках в админке

# Правильные импорты моделей
from ..models import Task, Project, TaskCategory, TaskSubcategory
from user_profiles.models import TaskUserRole, User # Импортируем User

logger = logging.getLogger(__name__)

REPORT_PAGINATE_BY = 25

# --- Helper Function to get base admin context ---
def get_admin_base_context(page_title="Отчет"):
    """Возвращает базовый контекст для шаблонов админки."""
    return {
        'title': page_title,
        'site_title': _('Администрирование Sphinx'),
        'site_header': _('Администрирование Sphinx'),
        'has_permission': True, # Предполагаем, что декоратор staff_member_required отработал
        'is_popup': False,
        'is_nav_sidebar_enabled': True,
        'opts': Task._meta, # Всегда передаем мета Task для навигации
        'app_label': Task._meta.app_label,
    }

# ==============================================================================
# Отчеты
# ==============================================================================

@staff_member_required
def export_tasks_to_excel(request):
    """Экспорт задач в Excel (доступен только персоналу)."""
    page_title = _("Экспорт задач в Excel")
    try:
        tasks_qs = Task.objects.select_related(
            'project', 'category', 'subcategory', 'created_by'
        ).prefetch_related(
            'user_roles__user' # Prefetch для участников
        ).all()

        data_list = []
        for task in tasks_qs:
            # Собираем участников из user_roles
            participants = ", ".join(
                [f"{r.user.display_name} ({r.get_role_display()})"
                 for r in task.user_roles.all() if r.user]
            )
            # Собираем исполнителей отдельно (если нужно)
            executors = ", ".join(
                [r.user.display_name for r in task.user_roles.all()
                 if r.user and r.role == TaskUserRole.RoleChoices.EXECUTOR]
            )
            # Собираем ответственных отдельно (если нужно)
            responsible = ", ".join(
                [r.user.display_name for r in task.user_roles.all()
                 if r.user and r.role == TaskUserRole.RoleChoices.RESPONSIBLE]
            )

            data_list.append({
                'Номер задачи': task.task_number,
                'Название': task.title,
                'Описание': task.description,
                'Статус': task.get_status_display(),
                'Приоритет': task.get_priority_display(),
                'Проект': task.project.name if task.project else '-',
                'Категория': task.category.name if task.category else '-',
                'Подкатегория': task.subcategory.name if task.subcategory else '-',
                'Участники': participants or '-', # Показываем всех участников
                'Ответственные': responsible or '-', # Отдельно ответственных
                'Исполнители': executors or '-', # Отдельно исполнителей
                'Создатель': task.created_by.display_name if task.created_by else '-',
                'Дата начала': make_naive(task.start_date) if task.start_date else None,
                'Срок': make_naive(task.deadline) if task.deadline else None,
                'Дата завершения': make_naive(task.completion_date) if task.completion_date else None,
                'Дата создания': make_naive(task.created_at) if task.created_at else None,
                'Дата обновления': make_naive(task.updated_at) if task.updated_at else None,
                'Оценка времени': str(task.estimated_time) if task.estimated_time else None,
            })

        df = pd.DataFrame(data_list)

        response = HttpResponse(content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
        filename = f'tasks_export_{timezone.now().strftime("%Y%m%d_%H%M")}.xlsx'
        response["Content-Disposition"] = f'attachment; filename="{filename}"'
        with pd.ExcelWriter(response, engine="xlsxwriter", datetime_format='yyyy-mm-dd hh:mm:ss') as writer:
            df.to_excel(writer, index=False, sheet_name="Задачи")
            worksheet = writer.sheets["Задачи"]
            for i, col in enumerate(df.columns):
                try:
                    column_len = max(df[col].astype(str).map(len).max(), len(col)) + 2
                    worksheet.set_column(i, i, min(column_len, 60))
                except Exception:
                    worksheet.set_column(i, i, len(col) + 2)
        return response

    except Exception as e:
         logger.exception("Error exporting tasks to Excel")
         messages.error(request, _("Произошла ошибка при экспорте в Excel: ") + str(e))
         return redirect(reverse('admin:tasks_task_changelist'))

@staff_member_required
def completed_tasks_report(request):
    """Отчет по завершенным задачам за последние 30 дней."""
    page_title = _("Отчет: Завершенные задачи")
    start_date = timezone.now() - timedelta(days=30)
    completed_tasks_qs = Task.objects.filter(
        status=Task.StatusChoices.COMPLETED, completion_date__gte=start_date
    ).select_related(
        "project", "created_by" # Убраны assignee, team
    ).prefetch_related(
        'user_roles__user' # Prefetch участников
    ).order_by('-completion_date')

    paginator = Paginator(completed_tasks_qs, REPORT_PAGINATE_BY)
    page_number = request.GET.get('page')
    try:
        page_obj = paginator.page(page_number)
    except PageNotAnInteger:
        page_obj = paginator.page(1)
    except EmptyPage:
        page_obj = paginator.page(paginator.num_pages)

    context = get_admin_base_context(page_title) # Получаем базовый контекст
    context.update({
        "page_obj": page_obj,
        "paginator": paginator,
        "is_paginated": page_obj.has_other_pages(),
        "start_date": start_date,
        "end_date": timezone.now(),
        "page_title": page_title, # Переопределяем для заголовка h1
    })
    return render(request, "reports/completed_tasks_report.html", context)


@staff_member_required
def overdue_tasks_report(request):
    """Отчет по просроченным задачам."""
    page_title = _("Отчет: Просроченные задачи")
    overdue_tasks_qs = Task.objects.filter(
        deadline__lt=timezone.now(),
        status__in=[Task.StatusChoices.NEW, Task.StatusChoices.IN_PROGRESS, Task.StatusChoices.ON_HOLD]
    ).select_related(
        "project", "created_by" # Убраны assignee, team
    ).prefetch_related(
        'user_roles__user' # Prefetch участников
    ).order_by('deadline')

    paginator = Paginator(overdue_tasks_qs, REPORT_PAGINATE_BY)
    page_number = request.GET.get('page')
    try:
        page_obj = paginator.page(page_number)
    except PageNotAnInteger:
        page_obj = paginator.page(1)
    except EmptyPage:
        page_obj = paginator.page(paginator.num_pages)

    context = get_admin_base_context(page_title)
    context.update({
        "page_obj": page_obj,
        "paginator": paginator,
        "is_paginated": page_obj.has_other_pages(),
        "page_title": page_title,
    })
    return render(request, "reports/overdue_tasks_report.html", context)

@staff_member_required
def active_tasks_report(request):
    """Отчет по активным (незавершенным) задачам."""
    page_title = _("Отчет: Активные задачи")
    active_tasks_qs = Task.objects.filter(
         status__in=[Task.StatusChoices.NEW, Task.StatusChoices.IN_PROGRESS, Task.StatusChoices.ON_HOLD]
    ).select_related(
        "project", "created_by" # Убраны assignee, team
    ).prefetch_related(
        'user_roles__user' # Prefetch участников
    ).order_by('priority', 'deadline')

    paginator = Paginator(active_tasks_qs, REPORT_PAGINATE_BY)
    page_number = request.GET.get('page')
    try:
        page_obj = paginator.page(page_number)
    except PageNotAnInteger:
        page_obj = paginator.page(1)
    except EmptyPage:
        page_obj = paginator.page(paginator.num_pages)

    context = get_admin_base_context(page_title)
    context.update({
        "page_obj": page_obj,
        "paginator": paginator,
        "is_paginated": page_obj.has_other_pages(),
        "page_title": page_title,
    })
    return render(request, "reports/active_tasks_report.html", context)


@staff_member_required
def team_performance_report(request):
    """Отчет по производительности ИСПОЛНИТЕЛЕЙ."""
    page_title = _("Отчет: Производительность исполнителей")
    performance_data = (
        TaskUserRole.objects.filter(
            role=TaskUserRole.RoleChoices.EXECUTOR, # Фильтр по роли
            task__status=Task.StatusChoices.COMPLETED # Фильтр по статусу задачи
        )
        .select_related('user') # Оптимизация
        .values(
            "user__username",
            "user__first_name",
            "user__last_name"
        )
        .annotate(total_tasks=Count("task")) # Считаем задачи
        .order_by('-total_tasks')
    )
    context = get_admin_base_context(page_title)
    context.update({
        "performance_data": performance_data,
        "page_title": page_title,
    })
    return render(request, "reports/team_performance_report.html", context)

@staff_member_required
def employee_workload_report(request):
    """Отчет по загрузке ИСПОЛНИТЕЛЕЙ."""
    page_title = _("Отчет: Загрузка исполнителей")
    workload_data = (
         TaskUserRole.objects.filter(
            role=TaskUserRole.RoleChoices.EXECUTOR, # Фильтр по роли
            task__status__in=[Task.StatusChoices.NEW, Task.StatusChoices.IN_PROGRESS, Task.StatusChoices.ON_HOLD] # Активные задачи
        )
        .select_related('user') # Оптимизация
        .values(
            "user__username",
            "user__first_name",
            "user__last_name"
        )
        .annotate(total_tasks=Count("task")) # Считаем задачи
        .order_by('-total_tasks')
    )
    context = get_admin_base_context(page_title)
    context.update({
        "workload_data": workload_data,
        "page_title": page_title,
    })
    return render(request, "reports/employee_workload_report.html", context)

# Отчеты ABC и SLA остаются без изменений в запросах, т.к. не зависят от assignee/team
@staff_member_required
def abc_analysis_report(request):
    """Отчет: ABC-анализ задач по приоритетам."""
    page_title = _("Отчет: ABC-анализ задач")
    tasks = Task.objects.annotate(
        priority_group=Case(
            # --- Используем правильные значения приоритетов ---
            When(priority=Task.TaskPriority.HIGH, then=Value("A")),
            When(priority__in=[Task.TaskPriority.MEDIUM_HIGH, Task.TaskPriority.MEDIUM], then=Value("B")),
            When(priority__in=[Task.TaskPriority.MEDIUM_LOW, Task.TaskPriority.LOW], then=Value("C")),
            # --- ---
            default=Value("Unknown"),
            output_field=CharField(),
        )
    ).values("priority_group").annotate(total_tasks=Count("id")).order_by('priority_group')

    context = get_admin_base_context(page_title)
    context.update({
        "tasks": tasks,
        "page_title": page_title,
    })
    return render(request, "reports/abc_analysis_report.html", context)

@staff_member_required
def sla_report(request):
    """Отчет по соблюдению SLA."""
    page_title = _("Отчет: Соблюдение SLA")
    sla_data = (
        Task.objects.filter(
            status=Task.StatusChoices.COMPLETED,
            deadline__isnull=False,
            completion_date__isnull=False
        )
        .annotate( sla_met=Case( When(completion_date__lte=F("deadline"), then=Value("Met")), default=Value("Not Met"), output_field=CharField()))
        .values("sla_met")
        .annotate(total_tasks=Count("id"))
        .order_by('sla_met')
    )
    context = get_admin_base_context(page_title)
    context.update({
        "sla_data": sla_data,
        "page_title": page_title,
    })
    return render(request, "reports/sla_report.html", context)

@staff_member_required
def task_progress_chart(request):
    """График: Прогресс выполнения задач по статусам."""
    page_title = _("График: Прогресс выполнения задач")
    # --- Используем правильные choices ---
    status_labels = dict(Task.StatusChoices.choices)
    # --- ---
    status_counts = Task.objects.values("status").annotate(total=Count("id")).order_by('status')
    plot_data = {status_labels.get(item['status'], item['status']): item['total'] for item in status_counts}
    chart_uri = None; message = None
    if plot_data:
        try:
            plt.figure(figsize=(10, 6)); plt.bar(plot_data.keys(), plot_data.values()); plt.xlabel(_("Статус")); plt.ylabel(_("Количество задач")); plt.title(page_title); plt.xticks(rotation=45, ha="right"); plt.tight_layout(); buf = io.BytesIO(); plt.savefig(buf, format="png"); buf.seek(0); string = base64.b64encode(buf.read()); chart_uri = "data:image/png;base64," + urllib.parse.quote(string); plt.close()
        except Exception as e: logger.exception("Error generating task progress chart"); message = _("Ошибка при генерации графика.")
    else: message = _("Нет данных для построения графика.")
    context = get_admin_base_context(page_title)
    context.update({ "chart": chart_uri, "message": message, "page_title": page_title, })
    return render(request, "reports/task_progress_chart.html", context)

@staff_member_required
def gantt_chart(request):
    """График: Диаграмма Ганта задач."""
    page_title = _("Диаграмма Ганта")
    tasks_qs = Task.objects.filter(start_date__isnull=False, deadline__isnull=False).values("task_number", "title", "start_date", "deadline", "status")
    df = pd.DataFrame(list(tasks_qs))
    chart_html = None; message = None
    if not df.empty:
        try:
            # --- Используем правильные choices ---
            status_map = dict(Task.StatusChoices.choices)
            # --- ---
            df['status_display'] = df['status'].map(status_map).fillna(df['status'])
            df['label'] = df['task_number'].astype(str) + ': ' + df['title'].str.slice(0, 50)
            fig = px.timeline(df, x_start="start_date", x_end="deadline", y="label", color="status_display", title=page_title, labels={"label": _("Задача"), "start_date": _("Начало"), "deadline": _("Срок"), "status_display": _("Статус")})
            fig.update_yaxes(autorange="reversed", categoryorder='array', categoryarray=df.sort_values('start_date')['label'].unique())
            chart_html = fig.to_html(full_html=False, include_plotlyjs='cdn')
        except Exception as e: logger.exception("Error generating gantt chart"); message = _("Ошибка при генерации диаграммы Ганта.")
    else: message = _("Нет данных для построения диаграммы Ганта (требуется дата начала и срок).")
    context = get_admin_base_context(page_title)
    context.update({ "chart": chart_html, "message": message, "page_title": page_title, })
    return render(request, "reports/gantt_chart.html", context)

@staff_member_required
def task_duration_report(request):
    """Отчет: Длительность выполнения завершенных задач."""
    page_title = _("Отчет: Длительность выполнения задач")
    duration_data_qs = (
        Task.objects.filter( status=Task.StatusChoices.COMPLETED, start_date__isnull=False, completion_date__isnull=False)
        .annotate(duration=ExpressionWrapper(F('completion_date') - F('start_date'), output_field=DurationField()))
        .filter(duration__isnull=False)
        .values("pk", "task_number", "title", "duration") # Добавляем pk для ссылки
        .order_by('-duration')
    )
    paginator = Paginator(duration_data_qs, REPORT_PAGINATE_BY)
    page_number = request.GET.get('page')
    try: page_obj = paginator.page(page_number)
    except PageNotAnInteger: page_obj = paginator.page(1)
    except EmptyPage: page_obj = paginator.page(paginator.num_pages)

    for item in page_obj:
        duration = item.get('duration')
        if isinstance(duration, timedelta):
             total_seconds = int(duration.total_seconds()); days, rem = divmod(total_seconds, 86400); hours, rem = divmod(rem, 3600); minutes, seconds = divmod(rem, 60); duration_str = ""
             if days > 0: duration_str += f"{days} д "
             if hours > 0: duration_str += f"{hours} ч "
             if minutes > 0: duration_str += f"{minutes} м "
             if not duration_str or seconds > 0 : duration_str += f"{seconds} с" # Показываем секунды, если нужно
             item['duration_formatted'] = duration_str.strip() if duration_str else "0 с"
        else: item['duration_formatted'] = "N/A"

    context = get_admin_base_context(page_title)
    context.update({ "page_obj": page_obj, "paginator": paginator, "is_paginated": page_obj.has_other_pages(), "page_title": page_title, })
    return render(request, "reports/task_duration_report.html", context)

@staff_member_required
def issues_report(request):
    """Отчет по задачам, похожим на 'баги'."""
    page_title = _("Отчет: Возможные баги/дефекты")
    issue_keywords = ['баг', 'bug', 'ошибка', 'дефект', 'issue', 'fix', 'исправить'] # Расширяем список
    query = Q()
    for keyword in issue_keywords: query |= Q(title__icontains=keyword) | Q(description__icontains=keyword)
    issues_qs = Task.objects.filter(query).select_related(
        "project", "created_by" # Убраны assignee/team
    ).prefetch_related('user_roles__user').order_by('-created_at')

    paginator = Paginator(issues_qs, REPORT_PAGINATE_BY)
    page_number = request.GET.get('page')
    try: page_obj = paginator.page(page_number)
    except PageNotAnInteger: page_obj = paginator.page(1)
    except EmptyPage: page_obj = paginator.page(paginator.num_pages)

    context = get_admin_base_context(page_title)
    context.update({ "page_obj": page_obj, "paginator": paginator, "is_paginated": page_obj.has_other_pages(), "page_title": page_title, })
    return render(request, "reports/issues_report.html", context)

@staff_member_required
def delay_reasons_report(request):
    """Отчет по просроченным задачам (для анализа причин задержки)."""
    page_title = _("Отчет: Просроченные задачи (для анализа причин)")
    delayed_tasks_qs = Task.objects.filter(
        deadline__lt=timezone.now(),
        status__in=[Task.StatusChoices.NEW, Task.StatusChoices.IN_PROGRESS, Task.StatusChoices.ON_HOLD]
    ).select_related("project", "created_by").prefetch_related('user_roles__user').order_by('deadline')

    paginator = Paginator(delayed_tasks_qs, REPORT_PAGINATE_BY)
    page_number = request.GET.get('page')
    try: page_obj = paginator.page(page_number)
    except PageNotAnInteger: page_obj = paginator.page(1)
    except EmptyPage: page_obj = paginator.page(paginator.num_pages)

    context = get_admin_base_context(page_title)
    context.update({
        "page_obj": page_obj, "paginator": paginator, "is_paginated": page_obj.has_other_pages(), "page_title": page_title,
        "report_info": _("Примечание: Для анализа причин задержки рекомендуется добавить соответствующее поле в модель Задачи."),
    })
    return render(request, "reports/delay_reasons_report.html", context)

@staff_member_required
def cancelled_tasks_report(request):
    """Отчет по отмененным задачам."""
    page_title = _("Отчет: Отмененные задачи")
    cancelled_tasks_qs = Task.objects.filter(
        status=Task.StatusChoices.CANCELLED
    ).select_related("project", "created_by").prefetch_related('user_roles__user').order_by('-updated_at') # Сортируем по дате отмены

    paginator = Paginator(cancelled_tasks_qs, REPORT_PAGINATE_BY)
    page_number = request.GET.get('page')
    try: page_obj = paginator.page(page_number)
    except PageNotAnInteger: page_obj = paginator.page(1)
    except EmptyPage: page_obj = paginator.page(paginator.num_pages)

    context = get_admin_base_context(page_title)
    context.update({ "page_obj": page_obj, "paginator": paginator, "is_paginated": page_obj.has_other_pages(), "page_title": page_title, })
    return render(request, "reports/cancelled_tasks_report.html", context)

# --- CBV для сводного отчета ---
class AdminReportMixin(UserPassesTestMixin):
    raise_exception = True
    def test_func(self): return self.request.user.is_staff
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs); context.update(get_admin_base_context(context.get('page_title', _("Отчет")))); return context

class TaskSummaryReportView(AdminReportMixin, TemplateView):
    template_name = "reports/task_summary_report.html"
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs); context['page_title'] = _("Сводный отчет по задачам"); context['title'] = context['page_title']
        # TODO: Добавить логику генерации summary_data
        # context['summary_data'] = {'total': Task.objects.count(), ...}
        return context