# tasks/views/task.py
import logging
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import Q
from django.forms.models import inlineformset_factory
from django.http import Http404
from django.shortcuts import redirect
from django.urls import reverse_lazy
from django.utils.translation import gettext_lazy as _
from django.views.generic import DetailView, CreateView, UpdateView, DeleteView
from django_filters.views import FilterView

# Локальные импорты
from ..models import Task, TaskPhoto
from ..forms import TaskForm, TaskPhotoForm
from ..filters import TaskFilter
from user_profiles.models import TaskUserRole, Team # Импорт из другого приложения
from .mixins import SuccessMessageMixin

logger = logging.getLogger(__name__)

class TaskListView(LoginRequiredMixin, FilterView):
    model = Task
    template_name = "tasks/task_list.html"
    context_object_name = "tasks"
    paginate_by = 10
    filterset_class = TaskFilter

    def get_base_queryset(self):
        return Task.objects.select_related(
            "project", "category", "subcategory", "assignee", "team", "created_by"
        ).prefetch_related('photos').order_by('priority', '-created_at')

    def get_queryset(self):
        user = self.request.user
        queryset = self.get_base_queryset()
        if user.is_superuser or user.has_perm('tasks.view_task'):
            pass
        elif hasattr(user, "user_profile"):
            user_teams = user.user_profile.teams.all()
            queryset = queryset.filter(
                Q(assignee=user) | Q(team__in=user_teams) | Q(created_by=user)
            ).distinct()
        else:
            queryset = queryset.filter(Q(assignee=user) | Q(created_by=user)).distinct()
        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        filterset = self.filterset
        context['filterset'] = filterset
        context['page_title'] = _("Список Задач")
        view_type = self.request.GET.get('view', 'kanban')
        context['view_type'] = view_type
        status_mapping = dict(Task.TASK_STATUS_CHOICES)
        context['status_mapping'] = status_mapping
        filtered_tasks_qs = filterset.qs

        if view_type == 'list':
            pass
        else:
            tasks_by_status = {key: [] for key in status_mapping}
            for task in filtered_tasks_qs:
                 if task.status in tasks_by_status:
                     tasks_by_status[task.status].append(task)
            context['tasks_by_status'] = tasks_by_status
            context.pop('paginator', None)
            context.pop('page_obj', None)
            context.pop('is_paginated', None)
            context['all_filtered_tasks'] = filtered_tasks_qs
        return context


class TaskDetailView(LoginRequiredMixin, DetailView):
    model = Task
    template_name = "tasks/task_detail.html"
    context_object_name = "task"

    def get_queryset(self):
        return super().get_queryset().select_related(
            "project", "category", "subcategory", "assignee", "team", "created_by"
        ).prefetch_related('photos', 'task_roles__user')

    def check_permissions(self, task):
        user = self.request.user
        if user.is_superuser or user.has_perm('tasks.view_task'): return True
        if TaskUserRole.objects.filter(task=task, user=user).exists(): return True
        # Проверка на членство в команде, если профиль существует
        if hasattr(user, 'user_profile') and user.user_profile and task.team in user.user_profile.teams.all(): return True
        if task.assignee == user: return True
        if task.created_by == user: return True
        return False

    def get_object(self, queryset=None):
        obj = super().get_object(queryset=queryset)
        if not self.check_permissions(obj):
            raise Http404(_("Вы не имеете доступа к этой задаче."))
        return obj

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['page_title'] = f"Задача: {self.object.title}"
        context['executors'] = self.object.task_roles.filter(role=TaskUserRole.RoleChoices.EXECUTOR)
        context['watchers'] = self.object.task_roles.filter(role=TaskUserRole.RoleChoices.WATCHER)
        return context


class BaseTaskFormView:
    """ Общая логика для Create и Update Task """
    model = Task
    form_class = TaskForm
    template_name = "tasks/task_form.html"

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['user'] = self.request.user
        return kwargs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        num_photos = 10 # Максимальное количество фото
        extra_photos = 1 # Количество пустых форм для добавления
        # Определяем формсет в зависимости от POST-запроса
        if self.request.POST:
            # Если есть объект (UpdateView), используем instance
            if hasattr(self, 'object') and self.object:
                 TaskPhotoFormSet = inlineformset_factory(Task, TaskPhoto, form=TaskPhotoForm, extra=extra_photos, max_num=num_photos, can_delete=True)
                 context['photo_formset'] = TaskPhotoFormSet(self.request.POST, self.request.FILES, instance=self.object, prefix='photos')
            else: # CreateView
                 TaskPhotoFormSet = inlineformset_factory(Task, TaskPhoto, form=TaskPhotoForm, extra=extra_photos, max_num=num_photos, can_delete=False)
                 context['photo_formset'] = TaskPhotoFormSet(self.request.POST, self.request.FILES, prefix='photos')
        else:
             # Если есть объект (UpdateView), используем instance
            if hasattr(self, 'object') and self.object:
                 TaskPhotoFormSet = inlineformset_factory(Task, TaskPhoto, form=TaskPhotoForm, extra=extra_photos, max_num=num_photos, can_delete=True)
                 context['photo_formset'] = TaskPhotoFormSet(instance=self.object, prefix='photos')
            else: # CreateView
                 TaskPhotoFormSet = inlineformset_factory(Task, TaskPhoto, form=TaskPhotoForm, extra=extra_photos, max_num=num_photos, can_delete=False)
                 context['photo_formset'] = TaskPhotoFormSet(prefix='photos')
        return context

    def process_forms(self, form, photo_formset):
        """ Обработка основной формы и формсета """
        if form.is_valid() and photo_formset.is_valid():
            # Установка создателя и статуса для CreateView
            if not hasattr(self, 'object') or not self.object: # Проверка для CreateView
                form.instance.created_by = self.request.user
                form.instance.status = Task.StatusChoices.NEW

            # Сохраняем основную форму
            self.object = form.save()

            # Обновляем роли
            self.handle_assignees_and_watchers(self.object, form)

            # Сохраняем формсет фото
            photo_formset.instance = self.object
            photo_formset.save()

            return True # Формы валидны и сохранены
        else:
            logger.warning(f"Task form/formset invalid. Form errors: {form.errors}. Formset errors: {photo_formset.errors}")
            return False # Формы не валидны

    def handle_assignees_and_watchers(self, task, form):
        """Назначает роли исполнителей и наблюдателей."""
        TaskUserRole.objects.filter(task=task).delete() # Очистка старых ролей
        assignee = form.cleaned_data.get('assignee')
        team = form.cleaned_data.get('team')

        executors = set()
        watchers = set()

        # Добавляем исполнителей
        if team:
            if team.team_leader:
                executors.add(team.team_leader)
            # Члены команды становятся наблюдателями (если они не лидер)
            watchers.update(team.members.exclude(id=team.team_leader_id if team.team_leader else None))
        elif assignee:
            executors.add(assignee)

        # Добавляем создателя как наблюдателя, если он не исполнитель
        if task.created_by not in executors:
            watchers.add(task.created_by)

        # Создаем роли в БД
        TaskUserRole.objects.bulk_create([
            TaskUserRole(task=task, user=user, role=TaskUserRole.RoleChoices.EXECUTOR)
            for user in executors
        ])
        TaskUserRole.objects.bulk_create([
            TaskUserRole(task=task, user=user, role=TaskUserRole.RoleChoices.WATCHER)
            # Исключаем пользователей, которые уже являются исполнителями
            for user in watchers if user not in executors
        ])


class TaskCreateView(LoginRequiredMixin, SuccessMessageMixin, BaseTaskFormView, CreateView):
    success_url = reverse_lazy("tasks:task_list")
    success_message = _("Задача '%(title)s' успешно создана!")
    permission_required = 'tasks.add_task'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['page_title'] = _("Создать Задачу")
        context['form_action'] = _("Создать")
        return context

    def form_valid(self, form):
        context = self.get_context_data()
        photo_formset = context['photo_formset']
        if self.process_forms(form, photo_formset):
            # Вызываем form_valid миксина для сообщения об успехе
            super(SuccessMessageMixin, self).form_valid(form) # Важно вызвать именно миксин
            return redirect(self.get_success_url())
        else:
            # Возвращаем форму с ошибками
            return self.render_to_response(self.get_context_data(form=form))


class TaskUpdateView(LoginRequiredMixin, SuccessMessageMixin, BaseTaskFormView, UpdateView):
    success_message = _("Задача '%(title)s' обновлена!")

    def get_success_url(self):
        return reverse_lazy('tasks:task_detail', kwargs={'pk': self.object.pk})

    def get_queryset(self):
        return Task.objects.select_related(
            "project", "category", "subcategory", "assignee", "team", "created_by"
        ).prefetch_related('photos')

    def check_edit_permissions(self, task):
        user = self.request.user
        if user.is_superuser or user.has_perm('tasks.change_task'): return True
        # Разрешаем редактирование создателю, исполнителю или лидеру команды
        if task.created_by == user: return True
        if TaskUserRole.objects.filter(task=task, user=user, role=TaskUserRole.RoleChoices.EXECUTOR).exists(): return True
        if task.team and task.team.team_leader == user: return True
        return False

    def get_object(self, queryset=None):
        obj = super().get_object(queryset=queryset)
        if not self.check_edit_permissions(obj):
            raise Http404(_("У вас нет прав на редактирование этой задачи."))
        return obj

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['page_title'] = _("Редактировать Задачу: %s") % self.object.title
        context['form_action'] = _("Сохранить")
        return context

    def form_valid(self, form):
        context = self.get_context_data()
        photo_formset = context['photo_formset']
        if self.process_forms(form, photo_formset):
            super(SuccessMessageMixin, self).form_valid(form)
            return redirect(self.get_success_url())
        else:
            return self.render_to_response(self.get_context_data(form=form))


class TaskDeleteView(LoginRequiredMixin, SuccessMessageMixin, DeleteView):
    model = Task
    template_name = "tasks/task_confirm_delete.html"
    success_url = reverse_lazy("tasks:task_list")
    success_message = _("Задача удалена!")

    def check_delete_permissions(self, task):
        user = self.request.user
        if user.is_superuser or user.has_perm('tasks.delete_task'): return True
        if task.created_by == user: return True
        if task.team and task.team.team_leader == user: return True
        return False

    def get_object(self, queryset=None):
        obj = super().get_object(queryset=queryset)
        if not self.check_delete_permissions(obj):
            raise Http404(_("У вас нет прав на удаление этой задачи."))
        return obj

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['page_title'] = _("Удалить Задачу: %s") % self.object.title
        return context

    def form_valid(self, form):
        super(SuccessMessageMixin, self).form_valid(form)
        return super(TaskDeleteView, self).form_valid(form) # Corrected super call


class TaskPerformView(LoginRequiredMixin, DetailView):
    """ Представление для 'выполнения' задачи (просмотр деталей в специфичном контексте) """
    model = Task
    template_name = "tasks/task_perform.html"
    context_object_name = "task"

    # Используем те же методы get_queryset и get_object, что и TaskDetailView
    # для консистентности прав доступа и оптимизации
    def get_queryset(self):
        return Task.objects.select_related(
            "project", "category", "subcategory", "assignee", "team", "created_by"
        ).prefetch_related('photos', 'task_roles__user')

    # Используем проверку прав из TaskDetailView
    def check_permissions(self, task):
        # Эта логика идентична TaskDetailView.check_permissions
        user = self.request.user
        if user.is_superuser or user.has_perm('tasks.view_task'): return True
        if TaskUserRole.objects.filter(task=task, user=user).exists(): return True
        if hasattr(user, 'user_profile') and user.user_profile and task.team in user.user_profile.teams.all(): return True
        if task.assignee == user: return True
        if task.created_by == user: return True
        return False

    def get_object(self, queryset=None):
        obj = super().get_object(queryset=queryset)
        # Проверяем права, но можно сделать специфичную проверку для 'выполнения'
        if not self.check_permissions(obj):
             # Можно также проверить, является ли пользователь исполнителем
             # if not TaskUserRole.objects.filter(task=obj, user=self.request.user, role=TaskUserRole.RoleChoices.EXECUTOR).exists():
             raise Http404(_("Вы не имеете доступа к выполнению этой задачи."))
        return obj

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['page_title'] = f"Выполнение задачи: {self.object.title}"
        # Можно добавить специфичный контекст для выполнения
        return context