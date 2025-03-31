# tasks/views/project.py
from django.contrib.auth.mixins import LoginRequiredMixin
from django.urls import reverse_lazy
from django.utils.translation import gettext_lazy as _
from django.views.generic import ListView, CreateView, UpdateView, DeleteView
from django_filters.views import FilterView

from ..models import Project
from ..forms import ProjectForm
from ..filters import ProjectFilter
from .mixins import SuccessMessageMixin, WebSocketNotificationMixin

class ProjectListView(LoginRequiredMixin, FilterView):
    model = Project
    template_name = "tasks/project_list.html"
    context_object_name = "projects"
    paginate_by = 15
    filterset_class = ProjectFilter
    queryset = Project.objects.all().order_by('-created_at')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['filterset'] = context.pop('filter', self.filterset)
        context['page_title'] = _("Список Кампаний")
        return context

class ProjectCreateView(LoginRequiredMixin, SuccessMessageMixin, WebSocketNotificationMixin, CreateView):
    model = Project
    form_class = ProjectForm
    template_name = "tasks/project_form.html"
    success_url = reverse_lazy("tasks:project_list")
    success_message = _("Кампания '%(name)s' успешно создана!")
    ws_group_name = "projects"
    ws_event_type = "updateProjects"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['page_title'] = _("Создать Кампанию")
        context['form_action'] = _("Создать")
        return context

    def form_valid(self, form):
        form.instance.created_by = self.request.user
        response = super().form_valid(form)
        project = self.object
        self.send_ws_notification({"action": "create", "id": project.id, "name": project.name})
        return response

class ProjectUpdateView(LoginRequiredMixin, SuccessMessageMixin, WebSocketNotificationMixin, UpdateView):
    model = Project
    form_class = ProjectForm
    template_name = "tasks/project_form.html"
    success_url = reverse_lazy("tasks:project_list")
    success_message = _("Кампания '%(name)s' успешно обновлена!")
    ws_group_name = "projects"
    ws_event_type = "updateProjects"
    permission_required = 'tasks.change_project'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['page_title'] = _("Редактировать Кампанию: %s") % self.object.name
        context['form_action'] = _("Сохранить")
        return context

    def form_valid(self, form):
         response = super().form_valid(form)
         project = self.object
         self.send_ws_notification({"action": "update", "id": project.id, "name": project.name})
         return response

class ProjectDeleteView(LoginRequiredMixin, SuccessMessageMixin, WebSocketNotificationMixin, DeleteView):
    model = Project
    template_name = "tasks/project_confirm_delete.html"
    success_url = reverse_lazy("tasks:project_list")
    success_message = _("Кампания удалена!")
    ws_group_name = "projects"
    ws_event_type = "updateProjects"
    permission_required = 'tasks.delete_project'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['page_title'] = _("Удалить Кампанию: %s") % self.object.name
        return context

    def form_valid(self, form):
        project_id = self.object.id
        super(SuccessMessageMixin, self).form_valid(form)
        self.send_ws_notification({"action": "delete", "id": project_id})
        # Вызываем form_valid родительского DeleteView для удаления
        # Используем super(DeleteView, self) для явного вызова родителя
        return super(ProjectDeleteView, self).form_valid(form) # Corrected super call