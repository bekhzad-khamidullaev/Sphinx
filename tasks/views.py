from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST
import json
from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
import logging
import pandas as pd
from django.utils.timezone import make_naive
from django.db.models import Q, Count, Avg, F, Case, When, Value, CharField
from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.paginator import Paginator
from django.http import HttpResponse, Http404, HttpResponseNotAllowed, JsonResponse
from django.shortcuts import render, redirect, get_object_or_404
from django.urls import reverse_lazy
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from django.views import generic
from django.views.generic.edit import FormView, View
from django.views.generic.base import TemplateView
from django.forms.models import inlineformset_factory
from django_filters.views import FilterView
from django.views.generic import ListView, CreateView, UpdateView, DeleteView, DetailView
import django_filters
from django_filters import FilterSet, ChoiceFilter, ModelChoiceFilter, rest_framework as filters
from django_filters.views import FilterView
from rest_framework import viewsets, permissions
from rest_framework.permissions import IsAuthenticated, DjangoModelPermissions
from .forms import (
    LoginForm, TaskPhotoForm, TaskForm, CampaignForm, UserCreateForm,
    RoleForm, TaskCategoryForm, TaskSubcategoryForm, TeamForm
)
from .models import Campaign, TaskCategory, TaskSubcategory, Task, TaskPhoto
from .reports import task_summary_report
from .serializers import (
    CampaignSerializer, TaskCategorySerializer, TaskSubcategorySerializer,
    TaskSerializer, TaskPhotoSerializer
)
from .signals import task_completed
from .filters import TaskFilter
import matplotlib.pyplot as plt
import io
import urllib, base64
import plotly.express as px

from user_profiles.models import TaskUserRole

channel_layer = get_channel_layer()
logger = logging.getLogger(__name__)
User = get_user_model()


# ------------------------ Миксины для общих операций ------------------------

class WebSocketNotificationMixin:
    """Миксин для отправки уведомлений через WebSocket."""

    def send_ws_notification(self, group_name, message):
        """Отправляет уведомление в группу WebSocket."""
        async_to_sync(channel_layer.group_send)(group_name, message)


class SuccessMessageMixin:
    """Миксин для добавления сообщений об успешном выполнении."""

    success_message = None

    def form_valid(self, form):
        if self.success_message:
            messages.success(self.request, self.success_message)
        return super().form_valid(form)


# ------------------------ API ViewSets ------------------------

class CampaignViewSet(viewsets.ModelViewSet):
    queryset = Campaign.objects.all()
    serializer_class = CampaignSerializer
    permission_classes = [permissions.IsAuthenticatedOrReadOnly]


class TaskCategoryViewSet(viewsets.ModelViewSet):
    queryset = TaskCategory.objects.all()
    serializer_class = TaskCategorySerializer
    permission_classes = [permissions.IsAuthenticatedOrReadOnly]


class TaskSubcategoryViewSet(viewsets.ModelViewSet):
    queryset = TaskSubcategory.objects.all()
    serializer_class = TaskSubcategorySerializer
    permission_classes = [permissions.IsAuthenticatedOrReadOnly]


class TaskViewSet(viewsets.ModelViewSet):
    queryset = Task.objects.all().select_related(
        "campaign", "category", "subcategory", "assignee", "team", "created_by"
    )
    serializer_class = TaskSerializer
    permission_classes = [IsAuthenticated, DjangoModelPermissions]
    filter_backends = [filters.DjangoFilterBackend]
    filterset_fields = [
        "status", "priority", "category", "subcategory", "campaign", "team", "assignee", "created_by"
    ]


class TaskPhotoViewSet(viewsets.ModelViewSet):
    queryset = TaskPhoto.objects.all()
    serializer_class = TaskPhotoSerializer
    permission_classes = [permissions.IsAuthenticatedOrReadOnly]


# ------------------------ CRUD Функции для Кампаний ------------------------

@login_required
def campaign_list(request):
    campaigns = Campaign.objects.all()

    return render(request, "tasks/campaign_list.html", {"campaigns": campaigns})



@login_required
def modal_create_campaign(request):
    form = CampaignForm()
    return render(request, "modals/campaign_form.html", {"form": form})


@login_required
def create_campaign(request):
    if request.method == "POST":
        form = CampaignForm(request.POST)
        if form.is_valid():
            campaign = form.save()
            WebSocketNotificationMixin().send_ws_notification(
                "campaigns",
                {"type": "updateCampaigns", "message": {"action": "create", "id": campaign.id, "name": campaign.name}}
            )
            messages.success(request, "Кампания успешно создана!")
            return HttpResponse('<script>location.reload()</script>')
    return HttpResponse(status=400)


@login_required
def modal_update_campaign(request, pk):
    campaign = get_object_or_404(Campaign, pk=pk)
    if request.method == "POST":
        form = CampaignForm(request.POST, instance=campaign)
        if form.is_valid():
            form.save()
            return HttpResponse('<script>location.reload()</script>')
    else:
        form = CampaignForm(instance=campaign)
    return render(request, "modals/campaign_form.html", {"form": form})


@login_required
def modal_delete_campaign(request, pk):
    campaign = get_object_or_404(Campaign, pk=pk)
    if request.method == "POST":
        campaign.delete()
        return HttpResponse('<script>location.reload()</script>')
    return render(request, "modals/campaign_confirm_delete.html", {"campaign": campaign})


@login_required
def delete_campaign(request, pk):
    campaign = get_object_or_404(Campaign, pk=pk)
    campaign.delete()
    WebSocketNotificationMixin().send_ws_notification(
        "campaigns",
        {"type": "updateCampaigns", "message": {"action": "delete", "id": pk}}
    )
    messages.success(request, "Кампания удалена!")
    return HttpResponse('<script>location.reload()</script>')


# ------------------------ CRUD Функции для Категорий ------------------------

@login_required
def category_list(request):
    categories = TaskCategory.objects.all()
    return render(request, "tasks/category_list.html", {"categories": categories})


@login_required
def modal_create_category(request):
    if request.method == "POST":
        form = TaskCategoryForm(request.POST)
        if form.is_valid():
            form.save()
            return HttpResponse('<script>location.reload()</script>')
    else:
        form = TaskCategoryForm()
    return render(request, "modals/category_form.html", {"form": form})


@login_required
def create_category(request):
    if request.method == "POST":
        form = TaskCategoryForm(request.POST)
        if form.is_valid():
            category = form.save()
            WebSocketNotificationMixin().send_ws_notification(
                "categories",
                {"type": "updateData", "message": {"action": "create", "name": category.name}}
            )
            messages.success(request, "Категория успешно создана!")
            return HttpResponse('<script>location.reload()</script>')
    return render(request, "modals/category_form.html", {"form": form})


@login_required
def modal_update_category(request, pk):
    category = get_object_or_404(TaskCategory, pk=pk)
    if request.method == "POST":
        form = TaskCategoryForm(request.POST, instance=category)
        if form.is_valid():
            form.save()
            return HttpResponse('<script>location.reload()</script>')
    else:
        form = TaskCategoryForm(instance=category)
    return render(request, "modals/category_form.html", {"form": form})


@login_required
def update_category(request, pk):
    category = get_object_or_404(TaskCategory, pk=pk)
    if request.method == "POST":
        form = TaskCategoryForm(request.POST, instance=category)
        if form.is_valid():
            form.save()
            return HttpResponse('<script>location.reload()</script>')
    else:
        form = TaskCategoryForm(instance=category)
    return render(request, "modals/category_form.html", {"form": form})


@login_required
def modal_delete_category(request, pk):
    category = get_object_or_404(TaskCategory, pk=pk)
    if request.method == "POST":
        category.delete()
        return HttpResponse('<script>location.reload()</script>')
    return render(request, "modals/category_confirm_delete.html", {"category": category})


@login_required
def delete_category(request, pk):
    category = get_object_or_404(TaskCategory, pk=pk)
    category.delete()
    WebSocketNotificationMixin().send_ws_notification(
        "categories",
        {"type": "updateData", "message": {"action": "delete", "id": pk}}
    )
    messages.success(request, "Категория удалена!")
    return HttpResponse('<script>location.reload()</script>')


# ------------------------ CRUD Функции для Подкатегорий ------------------------

@login_required
def subcategory_list(request):
    subcategories = TaskSubcategory.objects.all()
    return render(request, "tasks/subcategory_list.html", {"subcategories": subcategories})


@login_required
def modal_create_subcategory(request):
    if request.method == "POST":
        form = TaskSubcategoryForm(request.POST)
        if form.is_valid():
            form.save()
            return HttpResponse('<script>location.reload()</script>')
    else:
        form = TaskSubcategoryForm()
    return render(request, "modals/subcategory_form.html", {"form": form})


@login_required
def create_subcategory(request):
    if request.method == "POST":
        form = TaskSubcategoryForm(request.POST)
        if form.is_valid():
            subcategory = form.save()
            WebSocketNotificationMixin().send_ws_notification(
                "subcategories",
                {"type": "updateData", "message": {"action": "create", "name": subcategory.name}}
            )
            messages.success(request, "Подкатегория успешно создана!")
            return HttpResponse('<script>location.reload()</script>')
    return render(request, "modals/subcategory_form.html", {"form": form})


@login_required
def modal_update_subcategory(request, pk):
    subcategory = get_object_or_404(TaskSubcategory, pk=pk)
    if request.method == "POST":
        form = TaskSubcategoryForm(request.POST, instance=subcategory)
        if form.is_valid():
            form.save()
            return HttpResponse('<script>location.reload()</script>')
    else:
        form = TaskSubcategoryForm(instance=subcategory)
    return render(request, "modals/subcategory_form.html", {"form": form})


@login_required
def update_subcategory(request, pk):
    subcategory = get_object_or_404(TaskSubcategory, pk=pk)
    if request.method == "POST":
        form = TaskSubcategoryForm(request.POST, instance=subcategory)
        if form.is_valid():
            form.save()
            return HttpResponse('<script>location.reload()</script>')
    else:
        form = TaskSubcategoryForm(instance=subcategory)
    return render(request, "modals/subcategory_form.html", {"form": form})


@login_required
def modal_delete_subcategory(request, pk):
    subcategory = get_object_or_404(TaskSubcategory, pk=pk)
    if request.method == "POST":
        subcategory.delete()
        return HttpResponse('<script>location.reload()</script>')
    return render(request, "modals/subcategory_confirm_delete.html", {"subcategory": subcategory})


@login_required
def delete_subcategory(request, pk):
    subcategory = get_object_or_404(TaskSubcategory, pk=pk)
    subcategory.delete()
    WebSocketNotificationMixin().send_ws_notification(
        "subcategories",
        {"type": "updateData", "message": {"action": "delete", "id": pk}}
    )
    messages.success(request, "Подкатегория удалена!")
    return HttpResponse('<script>location.reload()</script>')


# ------------------------ Tasks ------------------------

class TaskListView(LoginRequiredMixin, FilterView):
    model = Task
    template_name = "tasks/task_list.html"
    context_object_name = "tasks"
    paginate_by = 10
    filterset_class = TaskFilter
    

    def get_queryset(self):
        """Optimized query + filtering based on user permissions."""
        user = self.request.user
        if user.is_superuser:
            queryset = Task.objects.select_related(
                "campaign", "category", "subcategory", "assignee", "team", "created_by"
            )
        elif hasattr(user, "user_profile") and user.user_profile.team:
            queryset = Task.objects.filter(Q(assignee=user) | Q(team=user.user_profile.team)).select_related(
                "campaign", "category", "subcategory", "assignee", "team", "created_by"
            )
        else:
            queryset = Task.objects.filter(assignee=user).select_related(
                "campaign", "category", "subcategory", "assignee", "team", "created_by"
            )
        return queryset

    def get_context_data(self, **kwargs):
        """Add pagination, status grouping, and view type to context."""
        context = super().get_context_data(**kwargs)

        # Determine view type (list or kanban). Default to kanban.
        view_type = self.request.GET.get('view', 'kanban')
        context['view_type'] = view_type

        # Status grouping (for both list and kanban)
        status_mapping = {status[0]: status[1] for status in Task.TASK_STATUS_CHOICES}
        context['status_mapping'] = status_mapping

        tasks_by_status = {key: [] for key in status_mapping}
        all_tasks = self.get_queryset() # Get *all* tasks (filtered, but not paginated)

        if view_type == 'list':
            # Pagination is handled automatically by ListView/FilterView if paginate_by is set.
            #  No need to manually create a Paginator object.
             for task in context['page_obj']:  # Iterate over the *paginated* tasks
                tasks_by_status[task.status].append(task)

        else:  # Kanban view: no pagination
            for task in all_tasks: # all tasks without pagination
                tasks_by_status[task.status].append(task)

        context['tasks_by_status'] = tasks_by_status
        context['filterset'] = self.filterset # Pass the filterset to the template
        return context


class TaskCreateView(LoginRequiredMixin, SuccessMessageMixin, CreateView):
    model = Task
    form_class = TaskForm
    template_name = "modals/modal_task_form.html"  # Consistent naming
    success_url = reverse_lazy("tasks:task_list")
    success_message = _("Задача успешно создана!")

    def get_form_kwargs(self):
        """Pass current user to form to filter assignees."""
        kwargs = super().get_form_kwargs()
        kwargs['user'] = self.request.user
        return kwargs

    def form_valid(self, form):
        form.instance.created_by = self.request.user

        # Logic for setting status to 'new'
        form.instance.status = 'new'

        # Save the task instance
        task = form.save()

        # Handle assignees and watchers
        self.handle_assignees_and_watchers(task)

        return super().form_valid(form)

    def handle_assignees_and_watchers(self, task):
        """Assign roles based on team/assignee selection."""
        # Clear existing roles
        TaskUserRole.objects.filter(task=task).delete()

        if task.team:
            # If a team is assigned, make the team leader an EXECUTOR
            if task.team.team_leader:
                TaskUserRole.objects.get_or_create(
                    task=task, user=task.team.team_leader, role=TaskUserRole.RoleChoices.EXECUTOR
                )

            # Make other team members WATCHERS
            for member in task.team.members.exclude(id=task.team.team_leader.id if task.team.team_leader else None):
                TaskUserRole.objects.get_or_create(
                    task=task, user=member, role=TaskUserRole.RoleChoices.WATCHER
                )

        elif task.assignee:
            # If a specific assignee is selected, make them the EXECUTOR
            TaskUserRole.objects.get_or_create(
                task=task, user=task.assignee, role=TaskUserRole.RoleChoices.EXECUTOR
            )

            # Optionally, allow adding other watchers manually through a separate field
            # Example:  watchers = form.cleaned_data.get('watchers')
            # for watcher in watchers:
            #     TaskUserRole.objects.get_or_create(task=task, user=watcher, role=TaskUserRole.RoleChoices.WATCHER)

class TaskDetailView(LoginRequiredMixin, DetailView):
    model = Task
    template_name = "tasks/task_detail.html"
    context_object_name = "task"

    def get_object(self, queryset=None):
        obj = super().get_object(queryset=queryset)
        if not self.request.user.is_superuser and obj.assignee != self.request.user and (not obj.team or self.request.user not in obj.team.members.all()):
            raise Http404(_("Вы не имеете доступа к этой задаче."))  # More specific check
        return obj


class TaskUpdateView(LoginRequiredMixin, SuccessMessageMixin, UpdateView):
    model = Task
    form_class = TaskForm
    template_name = "modals/modal_task_form.html"
    success_url = reverse_lazy("tasks:task_list")
    success_message = _("Задача обновлена!")

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['user'] = self.request.user
        return kwargs

    def get_queryset(self):
        user = self.request.user
        queryset = super().get_queryset()
        if not user.is_superuser:
            queryset = queryset.filter(Q(assignee=user) | Q(team__in=[team.id for team in user.user_profile.teams.all()]))  # Corrected this line
        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        # Use extra=1 for a single additional form, max_num for safety
        TaskPhotoFormSet = inlineformset_factory(Task, TaskPhoto, form=TaskPhotoForm, extra=1, max_num=10, can_delete=True)
        if self.request.POST:
            context["photo_formset"] = TaskPhotoFormSet(self.request.POST, self.request.FILES, instance=self.object)
        else:
            context["photo_formset"] = TaskPhotoFormSet(instance=self.object)
        return context

    def form_valid(self, form):
        task = form.save()  # Get the saved task instance

        # Handle assignees and watchers
        self.handle_assignees_and_watchers(task)

        context = self.get_context_data()
        photo_formset = context["photo_formset"]
        if photo_formset.is_valid():
            photo_formset.instance = self.object  # Set the instance before saving
            photo_formset.save()
            return super().form_valid(form)
        return self.form_invalid(form)


    def handle_assignees_and_watchers(self, task):
        """Assign roles based on team/assignee selection."""
        # Clear existing roles
        TaskUserRole.objects.filter(task=task).delete()

        if task.team:
            # If a team is assigned, make the team leader an EXECUTOR
            if task.team.team_leader:
                TaskUserRole.objects.get_or_create(
                    task=task, user=task.team.team_leader, role=TaskUserRole.RoleChoices.EXECUTOR
                )

            # Make other team members WATCHERS
            for member in task.team.members.exclude(id=task.team.team_leader.id if task.team.team_leader else None):
                TaskUserRole.objects.get_or_create(
                    task=task, user=member, role=TaskUserRole.RoleChoices.WATCHER
                )

        elif task.assignee:
            # If a specific assignee is selected, make them the EXECUTOR
            TaskUserRole.objects.get_or_create(
                task=task, user=task.assignee, role=TaskUserRole.RoleChoices.EXECUTOR
            )

            # Optionally, allow adding other watchers manually through a separate field
            # Example:  watchers = form.cleaned_data.get('watchers')
            # for watcher in watchers:
            #     TaskUserRole.objects.get_or_create(task=task, user=watcher, role=TaskUserRole.RoleChoices.WATCHER)


class TaskDeleteView(LoginRequiredMixin, DeleteView):  # No need for SuccessMessageMixin here
    model = Task
    template_name = "tasks/task_confirm_delete.html"  # Consistent naming
    success_url = reverse_lazy("tasks:task_list")

    def get_queryset(self):
        user = self.request.user
        queryset = super().get_queryset()
        if not user.is_superuser:
            queryset = queryset.filter(Q(assignee=user) | Q(team__in=[team.id for team in user.user_profile.teams.all()])) # Corrected this line
        return queryset

    def form_valid(self, form):  # Add form_valid to display success message
        messages.success(self.request, _("Задача удалена!"))
        return super().form_valid(form)


class TaskPerformView(LoginRequiredMixin, generic.DetailView):
    model = Task
    template_name = "tasks/task_perform.html"
    context_object_name = "task"


class TaskSummaryReportView(LoginRequiredMixin, TemplateView):
    template_name = "reports/task_summary_report.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        # Add any context data you need for the report
        return context


# ------------------------ Отчёты ------------------------

@login_required
def export_tasks_to_excel(request):
    tasks = Task.objects.all().values("task_number", "description", "deadline", "completion_date")
    df = pd.DataFrame(list(tasks))

    # Преобразование всех дат в наивные
    for col in ["deadline", "completion_date"]:
        df[col] = df[col].apply(lambda x: make_naive(x) if pd.notna(x) else x)

    # Экспорт в Excel
    response = HttpResponse(content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    response["Content-Disposition"] = 'attachment; filename="tasks.xlsx"'

    with pd.ExcelWriter(response, engine="xlsxwriter") as writer:
        df.to_excel(writer, index=False, sheet_name="Tasks")
        worksheet = writer.sheets["Tasks"]
        worksheet.set_column("A:A", 15)  # task_number
        worksheet.set_column("B:B", 50)  # description
        worksheet.set_column("C:C", 20)  # deadline
        worksheet.set_column("D:D", 20)  # completion_date
        writer.save()

    return response


@login_required
def completed_tasks_report(request):
    start_date = timezone.now() - timedelta(days=30)
    completed_tasks = Task.objects.filter(
        status="completed", completion_date__gte=start_date
    ).select_related("assignee", "campaign")

    context = {
        "completed_tasks": completed_tasks,
        "start_date": start_date,
        "end_date": timezone.now(),
    }
    return render(request, "reports/completed_tasks_report.html", context)


@login_required
def overdue_tasks_report(request):
    overdue_tasks = Task.objects.filter(
        deadline__lt=timezone.now(), status__in=["new", "in_progress", "on_hold"]
    ).select_related("assignee", "campaign")

    context = {"overdue_tasks": overdue_tasks}
    return render(request, "reports/overdue_tasks_report.html", context)


@login_required
def active_tasks_report(request):
    active_tasks = Task.objects.filter(
        status__in=["new", "in_progress", "on_hold"]
    ).select_related("assignee", "campaign")

    context = {"active_tasks": active_tasks}
    return render(request, "reports/active_tasks_report.html", context)


@login_required
def team_performance_report(request):
    performance_data = (
        Task.objects.filter(status="completed")
        .values("assignee__username")
        .annotate(
            total_tasks=Count("id"),
            avg_completion_time=Avg(F("completion_date") - F("start_date")),
        )
    )

    context = {"performance_data": performance_data}
    return render(request, "reports/team_performance_report.html", context)


@login_required
def employee_workload_report(request):
    workload_data = (
        Task.objects.filter(status__in=["new", "in_progress", "on_hold"])
        .values("assignee__username")
        .annotate(total_tasks=Count("id"))
    )

    context = {"workload_data": workload_data}
    return render(request, "reports/employee_workload_report.html", context)


@login_required
def abc_analysis_report(request):
    tasks = Task.objects.annotate(
        priority_group=Case(
            When(priority=1, then=Value("A")),
            When(priority__in=[2, 3], then=Value("B")),
            When(priority__in=[4, 5], then=Value("C")),
            default=Value("Unknown"),
            output_field=CharField(),
        )
    ).values("priority_group").annotate(total_tasks=Count("id"))

    context = {"tasks": tasks}
    return render(request, "reports/abc_analysis_report.html", context)


@login_required
def sla_report(request):
    sla_data = (
        Task.objects.filter(status="completed")
        .annotate(
            sla_met=Case(
                When(completion_date__lte=F("deadline"), then=Value("Met")),
                default=Value("Not Met"),
                output_field=CharField(),
            )
        )
        .values("sla_met")
        .annotate(total_tasks=Count("id"))
    )

    context = {"sla_data": sla_data}
    return render(request, "reports/sla_report.html", context)


@login_required
def task_progress_chart(request):
    tasks = Task.objects.all()
    status_counts = tasks.values("status").annotate(total=Count("id"))

    # Создание графика
    plt.figure(figsize=(10, 6))
    plt.bar([x["status"] for x in status_counts], [x["total"] for x in status_counts])
    plt.xlabel("Статус")
    plt.ylabel("Количество задач")
    plt.title("Прогресс выполнения задач")

    # Сохранение графика в буфер
    buf = io.BytesIO()
    plt.savefig(buf, format="png")
    buf.seek(0)
    string = base64.b64encode(buf.read())
    uri = urllib.parse.quote(string)

    context = {"chart": uri}
    return render(request, "reports/task_progress_chart.html", context)


@login_required
def gantt_chart(request):
    tasks = Task.objects.all().values("task_number", "start_date", "deadline", "status")
    df = pd.DataFrame(list(tasks))

    fig = px.timeline(
        df,
        x_start="start_date",
        x_end="deadline",
        y="task_number",
        color="status",
        title="Диаграмма Ганта",
    )
    chart = fig.to_html(full_html=False)

    context = {"chart": chart}
    return render(request, "reports/gantt_chart.html", context)


@login_required
def task_duration_report(request):
    duration_data = (
        Task.objects.filter(status="completed")
        .annotate(duration=F("completion_date") - F("start_date"))
        .values("task_number", "duration")
    )

    context = {"duration_data": duration_data}
    return render(request, "reports/task_duration_report.html", context)


@login_required
def issues_report(request):
    issues = Task.objects.filter(description__icontains="баг").select_related("assignee")

    context = {"issues": issues}
    return render(request, "reports/issues_report.html", context)


@login_required
def delay_reasons_report(request):
    delayed_tasks = Task.objects.filter(
        deadline__lt=timezone.now(), status__in=["new", "in_progress", "on_hold"]
    ).select_related("assignee")

    context = {"delayed_tasks": delayed_tasks}
    return render(request, "reports/delay_reasons_report.html", context)


@login_required
def cancelled_tasks_report(request):
    cancelled_tasks = Task.objects.filter(status="cancelled").select_related("assignee")

    context = {"cancelled_tasks": cancelled_tasks}
    return render(request, "reports/cancelled_tasks_report.html", context)


# ------------------------ AJAX ------------------------

@csrf_exempt
def update_task_status(request, task_id):
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            status = data.get('status')
            if not status:
                return JsonResponse({'error': 'Status not provided'}, status=400)

            task = Task.objects.get(id=task_id)
            task.status = status
            task.save()

            return JsonResponse({'new_status': task.status})

        except json.JSONDecodeError:
            return JsonResponse({'error': 'Invalid JSON'}, status=400)
        except Task.DoesNotExist:
            return JsonResponse({'error': 'Task not found'}, status=404)
        except Exception as e:
            logger.error(f"Error updating task status: {e}")
            return JsonResponse({'error': str(e)}, status=500)
    return JsonResponse({'error': 'Method not allowed'}, status=405)