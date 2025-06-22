from django.contrib.auth.mixins import LoginRequiredMixin
from django.urls import reverse_lazy
from django.utils.translation import gettext_lazy as _
from django.views.generic import ListView, CreateView, UpdateView, DeleteView, DetailView
from django_filters.views import FilterView
from django.contrib import messages

from ..models import TaskSubcategory
from ..forms import TaskSubcategoryForm
from ..filters import TaskSubcategoryFilter
from .mixins import SuccessMessageMixin, WebSocketNotificationMixin

class TaskSubcategoryListView(LoginRequiredMixin, FilterView):
    model = TaskSubcategory
    queryset = TaskSubcategory.objects.select_related('category').order_by('category__name', 'name')
    template_name = "tasks/subcategory_list.html"
    context_object_name = "object_list"
    paginate_by = 15
    filterset_class = TaskSubcategoryFilter

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['filterset'] = context.get('filter')
        context['page_title'] = _("Подкатегории Задач")
        return context

class TaskSubcategoryDetailView(LoginRequiredMixin, DetailView):
    model = TaskSubcategory
    template_name = "tasks/subcategory_detail.html"
    context_object_name = "subcategory"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["page_title"] = _("Детали подкатегории") + f": {self.object.name}"
        context["tasks_in_subcategory"] = (
            self.object.tasks.select_related("project").all()
        )
        return context

class TaskSubcategoryCreateView(LoginRequiredMixin, SuccessMessageMixin, WebSocketNotificationMixin, CreateView):
    model = TaskSubcategory
    form_class = TaskSubcategoryForm
    template_name = "tasks/subcategory_form.html"
    success_url = reverse_lazy("tasks:subcategory_list")
    success_message = _("Подкатегория '%(name)s' успешно создана!")
    ws_group_name = "subcategories_list"
    ws_event_type = "subcategory_update"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['page_title'] = _("Создать Подкатегорию")
        context['form_action_label'] = _("Создать")
        return context

    def form_valid(self, form):
        response = super().form_valid(form)
        self.send_ws_notification({"action": "create", "id": self.object.id, "name": self.object.name, "category_name": self.object.category.name})
        return response

class TaskSubcategoryUpdateView(LoginRequiredMixin, SuccessMessageMixin, WebSocketNotificationMixin, UpdateView):
    model = TaskSubcategory
    form_class = TaskSubcategoryForm
    template_name = "tasks/subcategory_form.html"
    success_url = reverse_lazy("tasks:subcategory_list")
    success_message = _("Подкатегория '%(name)s' успешно обновлена!")
    ws_group_name = "subcategories_list"
    ws_event_type = "subcategory_update"
    context_object_name = 'object'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['page_title'] = _("Редактировать Подкатегорию: %s") % self.object.name
        context['form_action_label'] = _("Сохранить")
        return context

    def form_valid(self, form):
        response = super().form_valid(form)
        self.send_ws_notification({"action": "update", "id": self.object.id, "name": self.object.name, "category_name": self.object.category.name})
        return response

class TaskSubcategoryDeleteView(LoginRequiredMixin, DeleteView):
    model = TaskSubcategory
    template_name = "tasks/subcategory_confirm_delete.html"
    success_url = reverse_lazy("tasks:subcategory_list")
    ws_group_name = "subcategories_list"
    ws_event_type = "subcategory_update"
    context_object_name = 'object'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['page_title'] = _("Удалить Подкатегорию: %s") % self.object.name
        return context

    def form_valid(self, form):
        object_id = self.object.id
        object_name = self.object.name
        response = super().form_valid(form)
        messages.success(self.request, _("Подкатегория '%(name)s' удалена!") % {'name': object_name})
        ws_mixin = WebSocketNotificationMixin()
        ws_mixin.ws_group_name = self.ws_group_name
        ws_mixin.ws_event_type = self.ws_event_type
        ws_mixin.send_ws_notification({"action": "delete", "id": object_id, "name": object_name})
        return response