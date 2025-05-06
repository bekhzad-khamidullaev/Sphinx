# tasks/views/project.py
from django.contrib.auth.mixins import LoginRequiredMixin
from django.urls import reverse_lazy
from django.utils.translation import gettext_lazy as _
from django.views.generic import ListView, CreateView, UpdateView, DeleteView, DetailView
from django.contrib import messages
from ..models import Project
from ..forms import ProjectForm
from ..filters import ProjectFilter
from .mixins import SuccessMessageMixin # Uses Django's mixin

class ProjectListView(LoginRequiredMixin, ListView):
    model = Project
    template_name = 'tasks/project_list.html'
    context_object_name = 'object_list'
    paginate_by = 15

    def get_queryset(self):
        queryset = super().get_queryset().prefetch_related('tasks')
        self.filterset = ProjectFilter(self.request.GET, queryset=queryset)
        return self.filterset.qs.distinct()

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['filterset'] = self.filterset
        context['page_title'] = _('Проекты')
        return context

class ProjectDetailView(LoginRequiredMixin, DetailView):
    model = Project
    template_name = "tasks/project_detail.html"
    context_object_name = "project"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["page_title"] = _("Детали проекта") + f": {self.object.name}"
        # Example: Add related tasks
        # context['tasks'] = self.object.tasks.all()[:10]
        return context

class ProjectCreateView(LoginRequiredMixin, SuccessMessageMixin, CreateView):
    model = Project
    form_class = ProjectForm
    template_name = 'tasks/project_form.html'
    success_url = reverse_lazy('tasks:project_list')
    success_message = _("Проект '%(name)s' успешно создан.")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['page_title'] = _('Создание нового проекта')
        context['form_action'] = _('Создать проект')
        return context

class ProjectUpdateView(LoginRequiredMixin, SuccessMessageMixin, UpdateView):
    model = Project
    form_class = ProjectForm
    template_name = 'tasks/project_form.html'
    success_url = reverse_lazy('tasks:project_list')
    success_message = _("Проект '%(name)s' успешно обновлен.")
    context_object_name = 'project'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['page_title'] = _('Редактирование проекта') + f': {self.object.name}'
        context['form_action'] = _('Сохранить изменения')
        return context

class ProjectDeleteView(LoginRequiredMixin, DeleteView):
    model = Project
    template_name = 'tasks/project_confirm_delete.html'
    success_url = reverse_lazy('tasks:project_list')
    context_object_name = 'project'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['page_title'] = _('Удаление проекта') + f': {self.object.name}'
        return context

    def form_valid(self, form):
        project_name = self.object.name
        response = super().form_valid(form)
        messages.success(self.request, _("Проект '%(name)s' был успешно удален.") % {'name': project_name})
        return response