# tasks/views/category.py
from django.contrib.auth.mixins import LoginRequiredMixin
from django.urls import reverse_lazy
from django.utils.translation import gettext_lazy as _
from django.views.generic import ListView, CreateView, UpdateView, DeleteView
from django_filters.views import FilterView

from ..models import TaskCategory
from ..forms import TaskCategoryForm
from ..filters import TaskCategoryFilter
from .mixins import SuccessMessageMixin, WebSocketNotificationMixin

class TaskCategoryListView(LoginRequiredMixin, FilterView):
    model = TaskCategory
    template_name = "tasks/category_list.html"
    context_object_name = "categories"
    paginate_by = 15
    filterset_class = TaskCategoryFilter
    queryset = TaskCategory.objects.all().order_by('name')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['filterset'] = context.pop('filter', self.filterset)
        context['page_title'] = _("Список Категорий Задач")
        return context

class TaskCategoryCreateView(LoginRequiredMixin, SuccessMessageMixin, WebSocketNotificationMixin, CreateView):
    model = TaskCategory
    form_class = TaskCategoryForm
    template_name = "tasks/category_form.html"
    success_url = reverse_lazy("tasks:category_list")
    success_message = _("Категория '%(name)s' успешно создана!")
    ws_group_name = "categories"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['page_title'] = _("Создать Категорию")
        context['form_action'] = _("Создать")
        return context

    def form_valid(self, form):
        response = super().form_valid(form)
        self.send_ws_notification({"action": "create", "id": self.object.id, "name": self.object.name})
        return response

class TaskCategoryUpdateView(LoginRequiredMixin, SuccessMessageMixin, WebSocketNotificationMixin, UpdateView):
    model = TaskCategory
    form_class = TaskCategoryForm
    template_name = "tasks/category_form.html"
    success_url = reverse_lazy("tasks:category_list")
    success_message = _("Категория '%(name)s' успешно обновлена!")
    ws_group_name = "categories"
    permission_required = 'tasks.change_taskcategory'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['page_title'] = _("Редактировать Категорию: %s") % self.object.name
        context['form_action'] = _("Сохранить")
        return context

    def form_valid(self, form):
        response = super().form_valid(form)
        self.send_ws_notification({"action": "update", "id": self.object.id, "name": self.object.name})
        return response

class TaskCategoryDeleteView(LoginRequiredMixin, SuccessMessageMixin, WebSocketNotificationMixin, DeleteView):
    model = TaskCategory
    template_name = "tasks/category_confirm_delete.html"
    success_url = reverse_lazy("tasks:category_list")
    success_message = _("Категория удалена!")
    ws_group_name = "categories"
    permission_required = 'tasks.delete_taskcategory'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['page_title'] = _("Удалить Категорию: %s") % self.object.name
        return context

    def form_valid(self, form):
        category_id = self.object.id
        super(SuccessMessageMixin, self).form_valid(form)
        self.send_ws_notification({"action": "delete", "id": category_id})
        return super(TaskCategoryDeleteView, self).form_valid(form) # Corrected super call