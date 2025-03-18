from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST
import json

from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
import logging
import pandas as pd
from django.utils.timezone import make_naive
from django.db.models import Q

from django.contrib import messages
from django.contrib.auth import get_user_model, login, logout, authenticate
from django.contrib.auth.views import LoginView as DjangoLoginView, LogoutView as DjangoLogoutView
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.messages.views import SuccessMessageMixin
from django.db.models import Q
from django.forms import inlineformset_factory
from django.http import HttpResponse, Http404, HttpResponseNotAllowed, JsonResponse
from django.shortcuts import render, redirect, get_object_or_404
from django.urls import reverse_lazy
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from django.views import generic
from django.views.generic.edit import FormView, View
from django.views.generic.base import TemplateView

import django_filters
from django_filters import FilterSet, ChoiceFilter, ModelChoiceFilter, rest_framework as filters
from django_filters.views import FilterView
from rest_framework import viewsets, permissions, parsers, status
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated, DjangoModelPermissions
from rest_framework.response import Response

from .forms import (
    LoginForm, TaskPhotoForm, TaskForm, CampaignForm, UserCreateForm, 
    RoleForm, TaskCategoryForm, TaskSubcategoryForm, TeamForm
)
from .models import (
    Campaign, TaskCategory, TaskSubcategory, Task, TaskPhoto
)
from .reports import task_summary_report
from .serializers import (
    CampaignSerializer, TaskCategorySerializer, TaskSubcategorySerializer,
    TaskSerializer, TaskPhotoSerializer
)
from .signals import task_completed
from .filters import TaskFilter


channel_layer = get_channel_layer()

logger = logging.getLogger(__name__)
User = get_user_model()

# ------------------------ Auth Views ------------------------

# class LoginView(DjangoLoginView):
#     template_name = "auth/login.html"
#     redirect_authenticated_user = True

#     def get_success_url(self):
#         # Параметр 'next' в URL или по умолчанию редиректим на 'tasks:task_list'
#         return self.request.GET.get('next', reverse_lazy('tasks:task_list'))

# class LogoutView(DjangoLogoutView):
#     next_page = reverse_lazy("tasks:login")

#     def dispatch(self, request, *args, **kwargs):
#         messages.success(request, _('Вы успешно вышли из системы.'))
#         return super().dispatch(request, *args, **kwargs)

# def clear_messages(request):
#     # Очищаем сообщения
#     get_messages(request).clear()
#     # Редиректим обратно на страницу входа или на главную
#     return HttpResponseRedirect(reverse('tasks:login'))
    
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
    queryset = Task.objects.all().select_related("campaign", "category", "subcategory", "assignee", "team", "created_by")
    serializer_class = TaskSerializer
    permission_classes = [IsAuthenticated, DjangoModelPermissions]
    filter_backends = [filters.DjangoFilterBackend]
    filterset_fields = ["status", "priority", "category", "subcategory", "campaign", "team", "assignee", "created_by"]

class TaskPhotoViewSet(viewsets.ModelViewSet):
    """Manage task photos."""
    queryset = TaskPhoto.objects.all()
    serializer_class = TaskPhotoSerializer
    permission_classes = [permissions.IsAuthenticatedOrReadOnly]
    
# ------------------------ CRUD ФУНКЦИИ ------------------------

@login_required
def campaign_list(request):
    campaigns = Campaign.objects.all()
    return render(request, "campaign_list.html", {"campaigns": campaigns})

@login_required
def modal_create_campaign(request):
    form = CampaignForm()
    return render(request, "modals/campaign_form.html", {"form": form})

@login_required
def modal_update_campaign(request, pk):
    campaign = get_object_or_404(Campaign, pk=pk)
    form = CampaignForm(instance=campaign)
    return render(request, "modals/campaign_form.html", {"form": form})

@login_required
def modal_delete_campaign(request, pk):
    campaign = get_object_or_404(Campaign, pk=pk)
    return render(request, "modals/campaign_delete.html", {"campaign": campaign})

@login_required
def create_campaign(request):
    if request.method == "POST":
        form = CampaignForm(request.POST)
        if form.is_valid():
            campaign = form.save()
            async_to_sync(channel_layer.group_send)(
                "campaigns", {"type": "updateCampaigns", "message": {"action": "create", "id": campaign.id, "name": campaign.name}}
            )
            messages.success(request, "Кампания успешно создана!")
            return HttpResponse('<script>location.reload()</script>')
    return HttpResponse(status=400)

@login_required
def delete_campaign(request, pk):
    campaign = get_object_or_404(Campaign, pk=pk)
    campaign.delete()
    async_to_sync(channel_layer.group_send)( 
        "campaigns", {"type": "updateCampaigns", "message": {"action": "delete", "id": pk}}
    )
    messages.success(request, "Кампания удалена!")
    return HttpResponse('<script>location.reload()</script>')

# ------------------------ Категории ------------------------

@login_required
def category_list(request):
    categories = TaskCategory.objects.all()
    return render(request, "tasks/category_list.html", {"categories": categories})

@login_required
def modal_create_category(request):
    form = TaskCategoryForm()
    return render(request, "modals/category_form.html", {"form": form})

@login_required
def create_category(request):
    form = TaskCategoryForm(request.POST)
    if form.is_valid():
        category = form.save()
        async_to_sync(channel_layer.group_send)(
            "categories",
            {"type": "updateData", "message": {"action": "create", "name": category.name}}
        )
        messages.success(request, "Категория успешно создана!")
        return HttpResponse('<script>location.reload()</script>')
    return render(request, "modals/category_form.html", {"form": form})

@login_required
def modal_update_category(request, pk):
    category = get_object_or_404(TaskCategory, pk=pk)
    form = TaskCategoryForm(instance=category)
    return render(request, "modals/category_form.html", {"form": form, "category": category})

@login_required
def update_category(request, pk):
    category = get_object_or_404(TaskCategory, pk=pk)
    form = TaskCategoryForm(request.POST, instance=category)
    if form.is_valid():
        form.save()
        async_to_sync(channel_layer.group_send)(
            "categories",
            {"type": "updateData", "message": {"action": "update", "name": category.name}}
        )
        messages.success(request, "Категория обновлена!")
        return HttpResponse('<script>location.reload()</script>')
    return render(request, "modals/category_form.html", {"form": form, "category": category})

@login_required
def modal_delete_category(request, pk):
    category = get_object_or_404(TaskCategory, pk=pk)
    return render(request, "modals/category_delete.html", {"category": category})

@login_required
def delete_category(request, pk):
    category = get_object_or_404(TaskCategory, pk=pk)
    category.delete()
    async_to_sync(channel_layer.group_send)(
        "categories",
        {"type": "updateData", "message": {"action": "delete", "id": pk}}
    )
    messages.success(request, "Категория удалена!")
    return HttpResponse('<script>location.reload()</script>')

# ------------------------ Подкатегории ------------------------

@login_required
def subcategory_list(request):
    subcategories = TaskSubcategory.objects.select_related("category").all()
    return render(request, "tasks/subcategory_list.html", {"subcategories": subcategories})

@login_required
def modal_create_subcategory(request):
    form = TaskSubcategoryForm()
    return render(request, "modals/subcategory_form.html", {"form": form})

@login_required
def create_subcategory(request):
    form = TaskSubcategoryForm(request.POST)
    if form.is_valid():
        subcategory = form.save()
        async_to_sync(channel_layer.group_send)(
            "subcategories",
            {"type": "updateData", "message": {"action": "create", "name": subcategory.name}}
        )
        messages.success(request, "Подкатегория успешно создана!")
        return HttpResponse('<script>location.reload()</script>')
    return render(request, "modals/subcategory_form.html", {"form": form})

@login_required
def modal_update_subcategory(request, pk):
    subcategory = get_object_or_404(TaskSubcategory, pk=pk)
    form = TaskSubcategoryForm(instance=subcategory)
    return render(request, "modals/subcategory_form.html", {"form": form, "subcategory": subcategory})

@login_required
def update_subcategory(request, pk):
    subcategory = get_object_or_404(TaskSubcategory, pk=pk)
    form = TaskSubcategoryForm(request.POST, instance=subcategory)
    if form.is_valid():
        form.save()
        async_to_sync(channel_layer.group_send)(
            "subcategories",
            {"type": "updateData", "message": {"action": "update", "name": subcategory.name}}
        )
        messages.success(request, "Подкатегория обновлена!")
        return HttpResponse('<script>location.reload()</script>')
    return render(request, "modals/subcategory_form.html", {"form": form, "subcategory": subcategory})

@login_required
def modal_delete_subcategory(request, pk):
    subcategory = get_object_or_404(TaskSubcategory, pk=pk)
    return render(request, "modals/subcategory_delete.html", {"subcategory": subcategory})

@login_required
def delete_subcategory(request, pk):
    subcategory = get_object_or_404(TaskSubcategory, pk=pk)
    subcategory.delete()
    async_to_sync(channel_layer.group_send)(
        "subcategories",
        {"type": "updateData", "message": {"action": "delete", "id": pk}}
    )
    messages.success(request, "Подкатегория удалена!")
    return HttpResponse('<script>location.reload()</script>')

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

    return response

# ------------------------ Tasks ------------------------


class TaskListView(LoginRequiredMixin, FilterView):
    model = Task
    template_name = "tasks/task_list.html"
    context_object_name = "tasks"
    paginate_by = 10
    filterset_class = TaskFilter

    def get_queryset(self):
        """Оптимизированный запрос + Фильтрация по правам пользователя"""
        user = self.request.user

        # ✅ Суперюзер видит все задачи
        if user.is_superuser:
            return Task.objects.select_related("campaign", "category", "subcategory", "assignee", "team", "created_by")

        # ✅ Лидер команды видит свои задачи + задачи своей команды
        if hasattr(user, "team") and user.team:
            return Task.objects.filter(Q(assignee=user) | Q(team=user.team)).select_related(
                "campaign", "category", "subcategory", "assignee", "team", "created_by"
            )

        # ✅ Обычный пользователь видит только свои задачи
        return Task.objects.filter(assignee=user).select_related(
            "campaign", "category", "subcategory", "assignee", "team", "created_by"
        )

    def get_context_data(self, **kwargs):
        """Группировка задач по статусу + доступные задачи"""
        context = super().get_context_data(**kwargs)

        all_statuses = dict(Task.TASK_STATUS_CHOICES).values()
        tasks_by_status = {status: [] for status in all_statuses}  # Создаём пустые колонки

        for task in context["tasks"]:
            status = task.get_status_display()
            tasks_by_status[status].append(task)

        context["tasks_by_status"] = tasks_by_status
        return context

    def post(self, request, *args, **kwargs):
        return HttpResponseNotAllowed(["GET"])



class TaskCreateView(LoginRequiredMixin, generic.CreateView):
    model = Task
    form_class = TaskForm
    template_name = "modals/modal_task_form.html"
    success_url = reverse_lazy("tasks:task_list")

    def form_valid(self, form):
        form.instance.created_by = self.request.user
        messages.success(self.request, _("Задача успешно создана!"))
        return super().form_valid(form)

class TaskDetailView(LoginRequiredMixin, generic.DetailView):
    model = Task
    template_name = "tasks/task_detail.html"
    context_object_name = "task"

    def get_object(self, queryset=None):
        obj = super().get_object(queryset=queryset)
        if not self.request.user.is_superuser and obj.assignee != self.request.user:
            raise Http404(_("Вы не имеете доступа к этой задаче."))
        return obj

class TaskUpdateView(LoginRequiredMixin, generic.UpdateView):
    model = Task
    form_class = TaskForm
    template_name = "modals/modal_task_form.html"
    success_url = reverse_lazy("tasks:task_list")

    def form_valid(self, form):
        messages.success(self.request, _("Задача обновлена!"))
        return super().form_valid(form)

class TaskDeleteView(LoginRequiredMixin, generic.DeleteView):
    model = Task
    template_name = "tasks/task_confirm_delete.html"
    success_url = reverse_lazy("tasks:task_list")

    def delete(self, request, *args, **kwargs):
        messages.success(request, _("Задача удалена!"))
        return super().delete(request, *args, **kwargs)

class TaskPerformView(LoginRequiredMixin, generic.View):
    def post(self, request, pk):
        task = get_object_or_404(Task, pk=pk)
        if task.status == "completed":
            messages.info(request, _(f"Задача '{task.task_number}' уже выполнена."))
        else:
            task.status = "completed"
            task.completion_date = timezone.now()
            task.save()
            task_completed.send(sender=Task, task=task)
            messages.success(request, _(f"Задача '{task.task_number}' выполнена!"))
        return redirect("tasks:task_detail", pk=pk)

class TaskSummaryReportView(TemplateView):
    template_name = 'tasks/task_summary_report.html'

@csrf_exempt
def update_task_status(request, task_id):
    if request.method == 'POST':
        if request.content_type != 'application/json':
            return JsonResponse({'error': f'Invalid content type {request.content_type}'}, status=415)

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
            return JsonResponse({'error': str(e)}, status=500)
