# tasks/views/project.py
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.messages.views import SuccessMessageMixin
from django.urls import reverse_lazy
from django.utils.translation import gettext_lazy as _
from django.views.generic import ListView, CreateView, UpdateView, DeleteView
from django.contrib import messages
from ..models import Project
from ..forms import ProjectForm
from ..filters import ProjectFilter # Assuming you might use filters

class ProjectListView(LoginRequiredMixin, ListView):
    model = Project
    template_name = 'tasks/project_list.html'
    context_object_name = 'object_list' # Explicitly set for clarity
    paginate_by = 15 # Example pagination

    def get_queryset(self):
        # Prefetch tasks count if Project model doesn't annotate it by default
        # Adjust if using annotation in model manager or ProjectAdmin
        queryset = super().get_queryset().prefetch_related('tasks')
        self.filterset = ProjectFilter(self.request.GET, queryset=queryset)
        return self.filterset.qs.distinct() # Return filtered queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['filterset'] = self.filterset
        context['page_title'] = _('Проекты')
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

    # Optional: Add permission checks if needed
    # def dispatch(self, request, *args, **kwargs):
    #     if not request.user.has_perm('tasks.add_project'):
    #         messages.error(request, _("У вас нет прав для создания проектов."))
    #         return self.handle_no_permission()
    #     return super().dispatch(request, *args, **kwargs)


class ProjectUpdateView(LoginRequiredMixin, SuccessMessageMixin, UpdateView):
    model = Project
    form_class = ProjectForm
    template_name = 'tasks/project_form.html'
    success_url = reverse_lazy('tasks:project_list')
    success_message = _("Проект '%(name)s' успешно обновлен.")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['page_title'] = _('Редактирование проекта') + f': {self.object.name}'
        context['form_action'] = _('Сохранить изменения')
        return context

    # Optional: Add permission checks
    # def dispatch(self, request, *args, **kwargs):
    #     obj = self.get_object() # Example: Check ownership or specific perm
    #     if not request.user.has_perm('tasks.change_project'): # Or custom logic
    #          messages.error(request, _("У вас нет прав для редактирования этого проекта."))
    #          return self.handle_no_permission()
    #     return super().dispatch(request, *args, **kwargs)


class ProjectDeleteView(LoginRequiredMixin, DeleteView): # SuccessMessageMixin doesn't work well here
    model = Project
    template_name = 'tasks/project_confirm_delete.html'
    success_url = reverse_lazy('tasks:project_list')
    context_object_name = 'project' # More specific name for template

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['page_title'] = _('Удаление проекта') + f': {self.object.name}'
        return context

    def form_valid(self, form):
         # Success message needs to be set before deletion
        project_name = self.object.name
        response = super().form_valid(form)
        messages.success(self.request, _("Проект '%(name)s' и все связанные задачи были успешно удалены.") % {'name': project_name})
        return response

    # Optional: Add permission checks
    # def dispatch(self, request, *args, **kwargs):
    #     if not request.user.has_perm('tasks.delete_project'): # Or custom logic
    #          messages.error(request, _("У вас нет прав для удаления этого проекта."))
    #          return self.handle_no_permission()
    #     return super().dispatch(request, *args, **kwargs)