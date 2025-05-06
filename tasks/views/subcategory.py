# tasks/views/subcategory.py
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
    context_object_name = "object_list" # Use object_list for consistency with ListView
    paginate_by = 15
    filterset_class = TaskSubcategoryFilter

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['filterset'] = context.get('filter') # FilterView uses 'filter' by default
        context['page_title'] = _("Подкатегории Задач")
        return context

class TaskSubcategoryDetailView(LoginRequiredMixin, DetailView):
    model = TaskSubcategory
    template_name = "tasks/subcategory_detail.html"
    context_object_name = "subcategory"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["page_title"] = _("Детали подкатегории") + f": {self.object.name}"
        # context['tasks'] = self.object.tasks.all()[:10]
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
        context['form_action'] = _("Создать")
        return context

    def form_valid(self, form):
        response = super().form_valid(form)
        self.send_ws_notification({"action": "create", "id": self.object.id, "name": self.object.name, "category": self.object.category.name})
        return response

class TaskSubcategoryUpdateView(LoginRequiredMixin, SuccessMessageMixin, WebSocketNotificationMixin, UpdateView):
    model = TaskSubcategory
    form_class = TaskSubcategoryForm
    template_name = "tasks/subcategory_form.html"
    success_url = reverse_lazy("tasks:subcategory_list")
    success_message = _("Подкатегория '%(name)s' успешно обновлена!")
    ws_group_name = "subcategories_list"
    ws_event_type = "subcategory_update"
    context_object_name = 'subcategory'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['page_title'] = _("Редактировать Подкатегорию: %s") % self.object.name
        context['form_action'] = _("Сохранить")
        return context

    def form_valid(self, form):
        response = super().form_valid(form)
        self.send_ws_notification({"action": "update", "id": self.object.id, "name": self.object.name, "category": self.object.category.name})
        return response

class TaskSubcategoryDeleteView(LoginRequiredMixin, DeleteView): # Removed WS and Success Mixins, handling manually
    model = TaskSubcategory
    template_name = "tasks/subcategory_confirm_delete.html"
    success_url = reverse_lazy("tasks:subcategory_list")
    ws_group_name = "subcategories_list" # For manual sending
    ws_event_type = "subcategory_update" # For manual sending
    context_object_name = 'subcategory'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['page_title'] = _("Удалить Подкатегорию: %s") % self.object.name
        return context

    # Overriding form_valid to send success message and WS notification manually
    def form_valid(self, form):
        subcategory_id = self.object.id
        subcategory_name = self.object.name
        response = super().form_valid(form) # Perform deletion
        messages.success(self.request, _("Подкатегория '%(name)s' удалена!") % {'name': subcategory_name})
        # Manually send WS notification after successful deletion
        ws_mixin = WebSocketNotificationMixin() # Instantiate mixin manually
        ws_mixin.ws_group_name = self.ws_group_name
        ws_mixin.ws_event_type = self.ws_event_type
        ws_mixin.send_ws_notification({"action": "delete", "id": subcategory_id})
        return response