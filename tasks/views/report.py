# tasks/views/report.py
import io
import base64
import urllib.parse
import pandas as pd
import matplotlib.pyplot as plt
import plotly.express as px
from datetime import timedelta

from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.paginator import Paginator
from django.db.models import Count, Avg, F, Case, When, Value, CharField, Q, ExpressionWrapper, DurationField
from django.http import HttpResponse
from django.shortcuts import render
from django.utils import timezone
from django.utils.timezone import make_naive
from django.utils.translation import gettext_lazy as _
from django.views.generic import TemplateView

from ..models import Task

REPORT_PAGINATE_BY = 20

@login_required
def export_tasks_to_excel(request):
    """Экспорт задач в Excel."""
    # Выбираем все необходимые поля, включая связанные
    tasks_qs = Task.objects.select_related(
        'project', 'category', 'subcategory', 'assignee', 'team', 'created_by'
    ).all().values(
        "task_number", "title", "description", "status", "priority",
        "project__name", "category__name", "subcategory__name",
        "assignee__username", "team__name", "created_by__username",
        "start_date", "deadline", "completion_date", "created_at", "updated_at"
    )
    df = pd.DataFrame(list(tasks_qs))

    # Преобразование дат в наивные (UTC -> None)
    date_cols = ["start_date", "deadline", "completion_date", "created_at", "updated_at"]
    for col in date_cols:
         if col in df.columns:
             # Преобразуем в datetime, игнорируя ошибки, затем убираем timezone
             df[col] = pd.to_datetime(df[col], errors='coerce').dt.tz_localize(None)
             # Заменяем NaT (Not a Time) на None (пустая ячейка в Excel)
             df[col] = df[col].where(pd.notna(df[col]), None)

    # Перевод статусов и приоритетов в читаемый вид
    status_map = dict(Task.TASK_STATUS_CHOICES)
    priority_map = dict(Task.PRIORITY_CHOICES)
    df['status'] = df['status'].map(status_map).fillna(df['status'])
    df['priority'] = df['priority'].map(priority_map).fillna(df['priority'])


    # Переименовываем колонки для Excel
    df.rename(columns={
        'task_number': 'Номер задачи', 'title': 'Название', 'description': 'Описание',
        'status': 'Статус', 'priority': 'Приоритет', 'project__name': 'Проект',
        'category__name': 'Категория', 'subcategory__name': 'Подкатегория',
        'assignee__username': 'Исполнитель', 'team__name': 'Команда',
        'created_by__username': 'Создатель', 'start_date': 'Дата начала',
        'deadline': 'Срок', 'completion_date': 'Дата завершения',
        'created_at': 'Дата создания', 'updated_at': 'Дата обновления'
    }, inplace=True)

    # Формируем ответ
    response = HttpResponse(content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    filename = f'tasks_export_{timezone.now().strftime("%Y%m%d_%H%M")}.xlsx'
    response["Content-Disposition"] = f'attachment; filename="{filename}"'

    # Записываем DataFrame в Excel
    with pd.ExcelWriter(response, engine="xlsxwriter", datetime_format='yyyy-mm-dd hh:mm:ss') as writer:
        df.to_excel(writer, index=False, sheet_name="Задачи")
        worksheet = writer.sheets["Задачи"]
        # Примерная автоподгонка ширины
        for i, col in enumerate(df.columns):
            try:
                column_len = max(df[col].astype(str).map(len).max(), len(col)) + 2
                worksheet.set_column(i, i, min(column_len, 60)) # Ограничим макс. ширину
            except Exception: # На случай пустых колонок или других ошибок
                worksheet.set_column(i, i, len(col) + 2)

    return response


@login_required
def completed_tasks_report(request):
    """Отчет по завершенным задачам за последние 30 дней."""
    start_date = timezone.now() - timedelta(days=30)
    completed_tasks_qs = Task.objects.filter(
        status=Task.StatusChoices.COMPLETED, completion_date__gte=start_date
    ).select_related("assignee", "project", "team").order_by('-completion_date')

    paginator = Paginator(completed_tasks_qs, REPORT_PAGINATE_BY)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    context = {
        "page_obj": page_obj,
        "is_paginated": page_obj.has_other_pages(),
        "start_date": start_date,
        "end_date": timezone.now(),
        "page_title": _("Отчет: Завершенные задачи"),
    }
    return render(request, "reports/completed_tasks_report.html", context)


@login_required
def overdue_tasks_report(request):
    """Отчет по просроченным задачам."""
    overdue_tasks_qs = Task.objects.filter(
        deadline__lt=timezone.now(),
        status__in=[Task.StatusChoices.NEW, Task.StatusChoices.IN_PROGRESS, Task.StatusChoices.ON_HOLD]
    ).select_related("assignee", "project", "team").order_by('deadline')

    paginator = Paginator(overdue_tasks_qs, REPORT_PAGINATE_BY)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    context = {
        "page_obj": page_obj,
        "is_paginated": page_obj.has_other_pages(),
        "page_title": _("Отчет: Просроченные задачи"),
    }
    return render(request, "reports/overdue_tasks_report.html", context)

@login_required
def active_tasks_report(request):
    """Отчет по активным (незавершенным) задачам."""
    active_tasks_qs = Task.objects.filter(
         status__in=[Task.StatusChoices.NEW, Task.StatusChoices.IN_PROGRESS, Task.StatusChoices.ON_HOLD]
    ).select_related("assignee", "project", "team").order_by('priority', 'deadline')

    paginator = Paginator(active_tasks_qs, REPORT_PAGINATE_BY)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    context = {
        "page_obj": page_obj,
        "is_paginated": page_obj.has_other_pages(),
        "page_title": _("Отчет: Активные задачи"),
    }
    return render(request, "reports/active_tasks_report.html", context)


@login_required
def team_performance_report(request):
    """Отчет по производительности исполнителей (по количеству завершенных задач)."""
    performance_data = (
        Task.objects.filter(status=Task.StatusChoices.COMPLETED, assignee__isnull=False)
        .values("assignee__username")
        .annotate(total_tasks=Count("id"))
        .order_by('-total_tasks')
    )
    context = {
        "performance_data": performance_data,
        "page_title": _("Отчет: Производительность исполнителей"),
    }
    return render(request, "reports/team_performance_report.html", context)

@login_required
def employee_workload_report(request):
    """Отчет по загрузке исполнителей (по количеству активных задач)."""
    workload_data = (
        Task.objects.filter(
            status__in=[Task.StatusChoices.NEW, Task.StatusChoices.IN_PROGRESS, Task.StatusChoices.ON_HOLD],
            assignee__isnull=False
        )
        .values("assignee__username")
        .annotate(total_tasks=Count("id"))
        .order_by('-total_tasks')
    )
    context = {
        "workload_data": workload_data,
        "page_title": _("Отчет: Загрузка исполнителей"),
    }
    return render(request, "reports/employee_workload_report.html", context)

@login_required
def abc_analysis_report(request):
    """Отчет: ABC-анализ задач по приоритетам."""
    tasks = Task.objects.annotate(
        priority_group=Case(
            When(priority=Task.PriorityChoices.HIGHEST, then=Value("A")),
            When(priority__in=[Task.PriorityChoices.HIGH, Task.PriorityChoices.MEDIUM], then=Value("B")),
            When(priority__in=[Task.PriorityChoices.LOW, Task.PriorityChoices.LOWEST], then=Value("C")),
            default=Value("Unknown"),
            output_field=CharField(),
        )
    ).values("priority_group").annotate(total_tasks=Count("id")).order_by('priority_group')

    context = {
        "tasks": tasks,
        "page_title": _("Отчет: ABC-анализ задач"),
    }
    return render(request, "reports/abc_analysis_report.html", context)

@login_required
def sla_report(request):
    """Отчет по соблюдению SLA (срок выполнения <= дедлайн)."""
    sla_data = (
        Task.objects.filter(
            status=Task.StatusChoices.COMPLETED,
            deadline__isnull=False,
            completion_date__isnull=False
        )
        .annotate(
            sla_met=Case(
                When(completion_date__lte=F("deadline"), then=Value("Met")),
                default=Value("Not Met"),
                output_field=CharField(),
            )
        )
        .values("sla_met")
        .annotate(total_tasks=Count("id"))
        .order_by('sla_met')
    )
    context = {
        "sla_data": sla_data,
        "page_title": _("Отчет: Соблюдение SLA"),
    }
    return render(request, "reports/sla_report.html", context)

@login_required
def task_progress_chart(request):
    """График: Прогресс выполнения задач по статусам."""
    status_labels = dict(Task.TASK_STATUS_CHOICES)
    status_counts = Task.objects.values("status").annotate(total=Count("id")).order_by('status')
    plot_data = {status_labels.get(item['status'], item['status']): item['total'] for item in status_counts}

    chart_uri = None
    message = None
    if plot_data:
        try:
            plt.figure(figsize=(10, 6))
            plt.bar(plot_data.keys(), plot_data.values())
            plt.xlabel(_("Статус"))
            plt.ylabel(_("Количество задач"))
            plt.title(_("Прогресс выполнения задач по статусам"))
            plt.xticks(rotation=45, ha="right")
            plt.tight_layout()

            buf = io.BytesIO()
            plt.savefig(buf, format="png")
            buf.seek(0)
            string = base64.b64encode(buf.read())
            chart_uri = "data:image/png;base64," + urllib.parse.quote(string)
            plt.close() # Важно закрыть фигуру
        except Exception as e:
            logger.error(f"Error generating task progress chart: {e}")
            message = _("Ошибка при генерации графика.")
    else:
         message = _("Нет данных для построения графика.")

    context = {
        "chart": chart_uri,
        "message": message,
        "page_title": _("График: Прогресс выполнения задач"),
    }
    return render(request, "reports/task_progress_chart.html", context)

@login_required
def gantt_chart(request):
    """График: Диаграмма Ганта задач."""
    tasks_qs = Task.objects.filter(
        start_date__isnull=False, deadline__isnull=False
    ).values("task_number", "title", "start_date", "deadline", "status")
    df = pd.DataFrame(list(tasks_qs))

    chart_html = None
    message = None
    if not df.empty:
        try:
             # Добавим перевод статусов
            status_map = dict(Task.TASK_STATUS_CHOICES)
            df['status_display'] = df['status'].map(status_map).fillna(df['status'])

            df['label'] = df['task_number'].astype(str) + ': ' + df['title'].str.slice(0, 50) # Ограничим длину названия

            fig = px.timeline(
                df,
                x_start="start_date",
                x_end="deadline",
                y="label",
                color="status_display", # Используем переведенный статус
                title=_("Диаграмма Ганта задач"),
                labels={"label": _("Задача"), "start_date": _("Начало"), "deadline": _("Срок"), "status_display": _("Статус")}
            )
            fig.update_yaxes(autorange="reversed", categoryorder='array', categoryarray=df.sort_values('start_date')['label'].unique()) # Сортировка по дате начала
            chart_html = fig.to_html(full_html=False, include_plotlyjs='cdn')
        except Exception as e:
            logger.error(f"Error generating gantt chart: {e}")
            message = _("Ошибка при генерации диаграммы Ганта.")
    else:
         message = _("Нет данных для построения диаграммы Ганта (требуется дата начала и срок).")

    context = {
        "chart": chart_html,
        "message": message,
        "page_title": _("Диаграмма Ганта"),
    }
    return render(request, "reports/gantt_chart.html", context)


@login_required
def task_duration_report(request):
    """Отчет: Длительность выполнения завершенных задач."""
    duration_data_qs = (
        Task.objects.filter(
            status=Task.StatusChoices.COMPLETED,
            start_date__isnull=False,
            completion_date__isnull=False
        )
        # Аннотируем длительность как DurationField
        .annotate(duration=ExpressionWrapper(F('completion_date') - F('start_date'), output_field=DurationField()))
        .filter(duration__isnull=False) # Исключаем задачи с некорректной длительностью
        .values("task_number", "title", "duration")
        .order_by('-duration')
    )

    paginator = Paginator(duration_data_qs, REPORT_PAGINATE_BY)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    # Форматируем duration в шаблоне или здесь
    for item in page_obj:
        duration = item.get('duration')
        if isinstance(duration, timedelta):
             total_seconds = int(duration.total_seconds())
             days, remainder = divmod(total_seconds, 86400)
             hours, remainder = divmod(remainder, 3600)
             minutes, seconds = divmod(remainder, 60)
             duration_str = ""
             if days > 0: duration_str += f"{days} дн "
             if hours > 0: duration_str += f"{hours} ч "
             if minutes > 0: duration_str += f"{minutes} мин "
             # Показываем секунды только если нет дней/часов/минут, или всегда? Решим показывать всегда для точности.
             duration_str += f"{seconds} сек"
             item['duration_formatted'] = duration_str.strip() if duration_str else "0 сек"
        else:
             item['duration_formatted'] = "N/A"

    context = {
        "page_obj": page_obj,
        "is_paginated": page_obj.has_other_pages(),
        "page_title": _("Отчет: Длительность выполнения задач"),
    }
    return render(request, "reports/task_duration_report.html", context)


@login_required
def issues_report(request):
    """Отчет по задачам, похожим на 'баги'."""
    # Уточните ключевые слова для поиска багов
    issue_keywords = ['баг', 'bug', 'ошибка', 'дефект', 'issue']
    query = Q()
    for keyword in issue_keywords:
        query |= Q(title__icontains=keyword) | Q(description__icontains=keyword)

    issues_qs = Task.objects.filter(query).select_related(
        "assignee", "project", "team"
    ).order_by('-created_at')

    paginator = Paginator(issues_qs, REPORT_PAGINATE_BY)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    context = {
        "page_obj": page_obj,
        "is_paginated": page_obj.has_other_pages(),
        "page_title": _("Отчет: Возможные баги/дефекты"),
    }
    return render(request, "reports/issues_report.html", context)

@login_required
def delay_reasons_report(request):
    """Отчет по просроченным задачам (для анализа причин задержки)."""
    # Этот отчет дублирует overdue_tasks_report.
    # Для реального анализа причин нужно добавить поле "причина задержки" в модель Task.
    # Пока просто выведем просроченные задачи.
    delayed_tasks_qs = Task.objects.filter(
        deadline__lt=timezone.now(),
        status__in=[Task.StatusChoices.NEW, Task.StatusChoices.IN_PROGRESS, Task.StatusChoices.ON_HOLD]
    ).select_related("assignee", "project", "team").order_by('deadline')

    paginator = Paginator(delayed_tasks_qs, REPORT_PAGINATE_BY)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    context = {
        "page_obj": page_obj,
        "is_paginated": page_obj.has_other_pages(),
        "page_title": _("Отчет: Просроченные задачи (для анализа причин)"),
        "report_info": _("Примечание: Для анализа причин задержки рекомендуется добавить соответствующее поле в модель Задачи."),
    }
    return render(request, "reports/delay_reasons_report.html", context)


@login_required
def cancelled_tasks_report(request):
    """Отчет по отмененным задачам."""
    cancelled_tasks_qs = Task.objects.filter(
        status=Task.StatusChoices.CANCELLED
    ).select_related("assignee", "project", "team", "created_by").order_by('-updated_at')

    paginator = Paginator(cancelled_tasks_qs, REPORT_PAGINATE_BY)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    context = {
        "page_obj": page_obj,
        "is_paginated": page_obj.has_other_pages(),
        "page_title": _("Отчет: Отмененные задачи"),
    }
    return render(request, "reports/cancelled_tasks_report.html", context)


class TaskSummaryReportView(LoginRequiredMixin, TemplateView):
    """ Отображение сводного отчета (если есть шаблон) """
    template_name = "reports/task_summary_report.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['page_title'] = _("Сводный отчет по задачам")
        # Добавьте сюда логику генерации данных для сводного отчета
        # context['summary_data'] = ...
        return context