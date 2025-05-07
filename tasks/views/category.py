# tasks/views/category.py
from django.contrib.auth.mixins import LoginRequiredMixin
from django.urls import reverse_lazy
from django.utils.translation import gettext_lazy as _
from django.views.generic import ListView, CreateView, UpdateView, DeleteView, DetailView
from django.contrib import messages
from django.db.models import Count

from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
import logging

from ..models import TaskCategory
from ..forms import TaskCategoryForm
from ..filters import TaskCategoryFilter
from .mixins import SuccessMessageMixin, WebSocketNotificationMixin


logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class TaskCategoryListView(LoginRequiredMixin, ListView):
    model = TaskCategory
    template_name = 'tasks/category_list.html' # Убедитесь, что шаблон существует
    context_object_name = 'categories'
    paginate_by = 20

    def get_queryset(self):
        queryset = super().get_queryset().annotate(
            task_count=Count('tasks'),
            subcategory_count=Count('subcategories')
        ).prefetch_related('tasks', 'subcategories')
        self.filterset = TaskCategoryFilter(self.request.GET, queryset=queryset, request=self.request)
        return self.filterset.qs.distinct().order_by('name')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['filterset'] = self.filterset
        context['page_title'] = _('Категории Задач')
        context['ws_group_name'] = 'categories_list'
        return context

class TaskCategoryDetailView(LoginRequiredMixin, DetailView):
    model = TaskCategory
    template_name = "tasks/category_detail.html" # Убедитесь, что шаблон существует
    context_object_name = "category"

    def get_queryset(self):
        return super().get_queryset().prefetch_related('subcategories', 'tasks')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        category = self.object
        context["page_title"] = _("Категория: %(name)s") % {'name': category.name}
        context['subcategories_list'] = category.subcategories.all() # Переименовал для ясности
        context['tasks_in_category_count'] = category.tasks.count() # Используем count() для эффективности
        context['ws_group_name'] = f'category_{category.id}'
        return context

class TaskCategoryCreateView(LoginRequiredMixin, SuccessMessageMixin, WebSocketNotificationMixin, CreateView):
    model = TaskCategory
    form_class = TaskCategoryForm
    template_name = 'tasks/category_form.html' # Убедитесь, что шаблон существует
    success_url = reverse_lazy('tasks:category_list')
    success_message = _("Категория '%(name)s' успешно создана.")

    ws_group_name = "categories_list"
    ws_event_type = "category_update" # Должен соответствовать методу в консьюмере

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['page_title'] = _('Создание новой категории')
        context['form_action_label'] = _('Создать категорию')
        return context
    
    def form_valid(self, form):
        response = super().form_valid(form)
        self.send_ws_notification(action="create", instance=self.object)
        return response

class TaskCategoryUpdateView(LoginRequiredMixin, SuccessMessageMixin, WebSocketNotificationMixin, UpdateView):
    model = TaskCategory
    form_class = TaskCategoryForm
    template_name = 'tasks/category_form.html'
    success_url = reverse_lazy('tasks:category_list')
    success_message = _("Категория '%(name)s' успешно обновлена.")
    context_object_name = 'category'

    ws_event_type = "category_update"

    def get_ws_group_name(self):
        return "categories_list" # Или f"category_{self.object.id}" для деталей

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['page_title'] = _('Редактирование категории: %(name)s') % {'name': self.object.name}
        context['form_action_label'] = _('Сохранить изменения')
        return context

    def form_valid(self, form):
        response = super().form_valid(form)
        self.send_ws_notification(action="update", instance=self.object)
        return response

class TaskCategoryDeleteView(LoginRequiredMixin, DeleteView):
    model = TaskCategory
    template_name = 'tasks/category_confirm_delete.html' # Убедитесь, что шаблон существует
    success_url = reverse_lazy('tasks:category_list')
    context_object_name = 'category'

    ws_group_name_on_delete = "categories_list"
    ws_event_type_on_delete = "category_update"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['page_title'] = _('Удаление категории: %(name)s') % {'name': self.object.name}
        return context

    def form_valid(self, form):
        category_name = self.object.name
        category_id = self.object.id
        response = super().form_valid(form)
        messages.success(self.request, _("Категория '%(name)s' была успешно удалена.") % {'name': category_name})
        
        try:
            channel_layer = get_channel_layer()
            if channel_layer:
                async_to_sync(channel_layer.group_send)(
                    self.ws_group_name_on_delete,
                    {"type": self.ws_event_type_on_delete,
                     "message": {"action": "delete", "model": "taskcategory", "id": category_id}}
                )
        except Exception as e:
            logger.error(f"Failed sending WS delete notification for TaskCategory ID {category_id}: {e}")
        return response