# tasks/views/category.py
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.messages.views import SuccessMessageMixin
from django.urls import reverse_lazy
from django.utils.translation import gettext_lazy as _
from django.views.generic import ListView, CreateView, UpdateView, DeleteView
from django.contrib import messages
from ..models import TaskCategory
from ..forms import TaskCategoryForm
from ..filters import TaskCategoryFilter # Assuming filter exists


class TaskCategoryListView(LoginRequiredMixin, ListView):
    model = TaskCategory
    template_name = 'tasks/category_list.html'
    context_object_name = 'object_list'
    paginate_by = 20

    def get_queryset(self):
        queryset = super().get_queryset().prefetch_related('tasks', 'subcategories') # Optimize
        self.filterset = TaskCategoryFilter(self.request.GET, queryset=queryset)
        return self.filterset.qs.distinct()

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['filterset'] = self.filterset
        context['page_title'] = _('Категории Задач')
        return context


class TaskCategoryCreateView(LoginRequiredMixin, SuccessMessageMixin, CreateView):
    model = TaskCategory
    form_class = TaskCategoryForm
    template_name = 'tasks/category_form.html'
    success_url = reverse_lazy('tasks:category_list')
    success_message = _("Категория '%(name)s' успешно создана.")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['page_title'] = _('Создание новой категории')
        context['form_action'] = _('Создать категорию')
        return context

    # Optional: Permission check
    # def dispatch(self, request, *args, **kwargs):
    #     if not request.user.has_perm('tasks.add_taskcategory'):
    #         messages.error(request, _("У вас нет прав для создания категорий."))
    #         return self.handle_no_permission()
    #     return super().dispatch(request, *args, **kwargs)


class TaskCategoryUpdateView(LoginRequiredMixin, SuccessMessageMixin, UpdateView):
    model = TaskCategory
    form_class = TaskCategoryForm
    template_name = 'tasks/category_form.html'
    success_url = reverse_lazy('tasks:category_list')
    success_message = _("Категория '%(name)s' успешно обновлена.")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['page_title'] = _('Редактирование категории') + f': {self.object.name}'
        context['form_action'] = _('Сохранить изменения')
        return context

    # Optional: Permission check
    # def dispatch(self, request, *args, **kwargs):
    #     if not request.user.has_perm('tasks.change_taskcategory'):
    #         messages.error(request, _("У вас нет прав для редактирования этой категории."))
    #         return self.handle_no_permission()
    #     return super().dispatch(request, *args, **kwargs)


class TaskCategoryDeleteView(LoginRequiredMixin, DeleteView): # SuccessMessageMixin doesn't work well here
    model = TaskCategory
    template_name = 'tasks/category_confirm_delete.html'
    success_url = reverse_lazy('tasks:category_list')
    context_object_name = 'category' # More specific name for template

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['page_title'] = _('Удаление категории') + f': {self.object.name}'
        return context

    def form_valid(self, form):
        category_name = self.object.name
        response = super().form_valid(form)
        messages.success(self.request, _("Категория '%(name)s' была успешно удалена.") % {'name': category_name})
        return response

    # Optional: Permission check
    # def dispatch(self, request, *args, **kwargs):
    #     if not request.user.has_perm('tasks.delete_taskcategory'):
    #          messages.error(request, _("У вас нет прав для удаления этой категории."))
    #          return self.handle_no_permission()
    #     return super().dispatch(request, *args, **kwargs)