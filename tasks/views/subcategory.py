# tasks/views/subcategory.py
from django.contrib.auth.mixins import LoginRequiredMixin
from django.urls import reverse_lazy
from django.utils.translation import gettext_lazy as _
from django.views.generic import ListView, CreateView, UpdateView, DeleteView
from django_filters.views import FilterView

from ..models import TaskSubcategory
from ..forms import TaskSubcategoryForm
from ..filters import TaskSubcategoryFilter
from .mixins import SuccessMessageMixin, WebSocketNotificationMixin

class TaskSubcategoryListView(LoginRequiredMixin, FilterView):
    model = TaskSubcategory
    queryset = TaskSubcategory.objects.select_related('category').order_by('category__name', 'name')
    template_name = "tasks/subcategory_list.html"
    context_object_name = "subcategories"
    paginate_by = 15
    filterset_class = TaskSubcategoryFilter

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['filterset'] = context.pop('filter', self.filterset)
        context['page_title'] = _("Список Подкатегорий Задач")
        return context

class TaskSubcategoryCreateView(LoginRequiredMixin, SuccessMessageMixin, WebSocketNotificationMixin, CreateView):
    model = TaskSubcategory
    form_class = TaskSubcategoryForm
    template_name = "tasks/subcategory_form.html"
    success_url = reverse_lazy("tasks:subcategory_list")
    success_message = _("Подкатегория '%(name)s' успешно создана!")
    ws_group_name = "subcategories"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['page_title'] = _("Создать Подкатегорию")
        context['form_action'] = _("Создать")
        return context

    def form_valid(self, form):
        response = super().form_valid(form)
        self.send_ws_notification({"action": "create", "id": self.object.id, "name": self.object.name})
        return response

class TaskSubcategoryUpdateView(LoginRequiredMixin, SuccessMessageMixin, WebSocketNotificationMixin, UpdateView):
    model = TaskSubcategory
    form_class = TaskSubcategoryForm
    template_name = "tasks/subcategory_form.html"
    success_url = reverse_lazy("tasks:subcategory_list")
    success_message = _("Подкатегория '%(name)s' успешно обновлена!")
    ws_group_name = "subcategories"
    permission_required = 'tasks.change_tasksubcategory'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['page_title'] = _("Редактировать Подкатегорию: %s") % self.object.name
        context['form_action'] = _("Сохранить")
        return context

    def form_valid(self, form):
        response = super().form_valid(form)
        self.send_ws_notification({"action": "update", "id": self.object.id, "name": self.object.name})
        return response

class TaskSubcategoryDeleteView(LoginRequiredMixin, SuccessMessageMixin, WebSocketNotificationMixin, DeleteView):
    model = TaskSubcategory
    template_name = "tasks/subcategory_confirm_delete.html"
    success_url = reverse_lazy("tasks:subcategory_list")
    success_message = _("Подкатегория удалена!")
    ws_group_name = "subcategories"
    permission_required = 'tasks.delete_tasksubcategory'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['page_title'] = _("Удалить Подкатегорию: %s") % self.object.name
        return context

    def form_valid(self, form):
        subcategory_id = self.object.id
        super(SuccessMessageMixin, self).form_valid(form)
        self.send_ws_notification({"action": "delete", "id": subcategory_id})
        return super(TaskSubcategoryDeleteView, self).form_valid(form) # Corrected super call