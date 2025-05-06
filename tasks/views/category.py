# tasks/views/category.py
from django.contrib.auth.mixins import LoginRequiredMixin
from django.urls import reverse_lazy
from django.utils.translation import gettext_lazy as _
from django.views.generic import ListView, CreateView, UpdateView, DeleteView, DetailView
from django.contrib import messages
from ..models import TaskCategory
from ..forms import TaskCategoryForm
from ..filters import TaskCategoryFilter
from .mixins import SuccessMessageMixin # Using Django's built-in

class TaskCategoryListView(LoginRequiredMixin, ListView):
    model = TaskCategory
    template_name = 'tasks/category_list.html'
    context_object_name = 'object_list'
    paginate_by = 20

    def get_queryset(self):
        queryset = super().get_queryset().prefetch_related('tasks', 'subcategories')
        self.filterset = TaskCategoryFilter(self.request.GET, queryset=queryset)
        return self.filterset.qs.distinct()

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['filterset'] = self.filterset
        context['page_title'] = _('Категории Задач')
        return context

class TaskCategoryDetailView(LoginRequiredMixin, DetailView):
    model = TaskCategory
    template_name = "tasks/category_detail.html"
    context_object_name = "category"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["page_title"] = _("Детали категории") + f": {self.object.name}"
        context['subcategories'] = self.object.subcategories.all()
        context['tasks_count'] = self.object.tasks.count()
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

class TaskCategoryUpdateView(LoginRequiredMixin, SuccessMessageMixin, UpdateView):
    model = TaskCategory
    form_class = TaskCategoryForm
    template_name = 'tasks/category_form.html'
    success_url = reverse_lazy('tasks:category_list')
    success_message = _("Категория '%(name)s' успешно обновлена.")
    context_object_name = 'category'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['page_title'] = _('Редактирование категории') + f': {self.object.name}'
        context['form_action'] = _('Сохранить изменения')
        return context

class TaskCategoryDeleteView(LoginRequiredMixin, DeleteView):
    model = TaskCategory
    template_name = 'tasks/category_confirm_delete.html'
    success_url = reverse_lazy('tasks:category_list')
    context_object_name = 'category'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['page_title'] = _('Удаление категории') + f': {self.object.name}'
        return context

    def form_valid(self, form):
        category_name = self.object.name
        response = super().form_valid(form)
        messages.success(self.request, _("Категория '%(name)s' была успешно удалена.") % {'name': category_name})
        return response