# tasks/views/task.py
import logging
import json
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.urls import reverse_lazy, reverse
from django.utils.translation import gettext_lazy as _
from django.views.generic import ListView, DetailView, CreateView, UpdateView, DeleteView, View
from django.shortcuts import get_object_or_404, redirect, render
from django.http import Http404, JsonResponse
from django.db.models import Prefetch, Q
from django.forms import modelformset_factory
from django.contrib import messages
from django.core.serializers.json import DjangoJSONEncoder
from django.contrib.auth.decorators import login_required

from ..models import Task, TaskPhoto, TaskComment
from ..forms import TaskForm, TaskPhotoForm, TaskCommentForm
from ..filters import TaskFilter
from .mixins import SuccessMessageMixin

try:
    from user_profiles.models import TaskUserRole, User
except ImportError:
    TaskUserRole = None
    User = None

logger = logging.getLogger(__name__)

TaskPhotoFormSet = modelformset_factory(
    TaskPhoto, form=TaskPhotoForm, fields=('photo', 'description'), extra=1, can_delete=True
)

class TaskListView(LoginRequiredMixin, ListView):
    model = Task
    template_name = 'tasks/task_list.html'
    context_object_name = 'tasks_list'
    paginate_by = 10

    def get_queryset(self):
        queryset = Task.objects.select_related(
            'project', 'category', 'subcategory', 'created_by'
        ).prefetch_related(
            Prefetch('user_roles', queryset=TaskUserRole.objects.select_related('user').order_by('role')),
            'photos'
        ).order_by('-created_at')
        # Add permission filtering if necessary
        # if not self.request.user.is_staff:
        #     queryset = queryset.filter(Q(created_by=self.request.user) | Q(user_roles__user=self.request.user)).distinct()
        self.filterset = TaskFilter(self.request.GET, queryset=queryset, request=self.request)
        filtered_qs = self.filterset.qs.distinct()
        sort_param = self.request.GET.get('sort', '-created_at')
        allowed_sort_fields = ['task_number', 'title', 'project__name', 'status', 'priority', 'deadline', 'created_at']
        sort_field = sort_param.lstrip('-')
        if sort_field in allowed_sort_fields:
            self.active_queryset = filtered_qs.order_by(sort_param)
        else:
            self.active_queryset = filtered_qs.order_by('-created_at')
        return self.active_queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['filterset'] = self.filterset
        context['page_title'] = _('Задачи')
        context['current_sort'] = self.request.GET.get('sort', '-created_at')
        all_tasks_for_kanban = self.active_queryset
        tasks_by_status = {code: [] for code, _ in Task.StatusChoices.choices}
        for task in all_tasks_for_kanban: tasks_by_status.setdefault(task.status, []).append(task)
        context['tasks_by_status'] = tasks_by_status
        context['status_mapping'] = dict(Task.StatusChoices.choices)
        context['status_mapping_json'] = json.dumps(context['status_mapping'], cls=DjangoJSONEncoder)
        context['status_choices'] = Task.StatusChoices.choices
        context['page_obj'] = context['page_obj']
        return context

class TaskDetailView(LoginRequiredMixin, UserPassesTestMixin, DetailView):
    model = Task
    template_name = 'tasks/task_detail.html'
    context_object_name = 'task'
    comment_form_class = TaskCommentForm

    def test_func(self):
        return self.get_object().has_permission(self.request.user, 'view')

    def handle_no_permission(self):
        messages.error(self.request, _("Нет прав для просмотра этой задачи."))
        return redirect(reverse_lazy('tasks:task_list'))

    def get_queryset(self):
        return super().get_queryset().select_related(
            'project', 'category', 'subcategory', 'created_by'
        ).prefetch_related(
            'photos',
            Prefetch('comments', queryset=TaskComment.objects.select_related('author__userprofile').order_by('created_at')),
            Prefetch('user_roles', queryset=TaskUserRole.objects.select_related('user__userprofile').order_by('role'))
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        task = self.object
        context['page_title'] = _('Задача') + f" #{task.task_number or task.pk}"
        context['can_change_task'] = task.has_permission(self.request.user, 'change')
        context['can_delete_task'] = task.has_permission(self.request.user, 'delete')
        context['can_add_comment'] = task.has_permission(self.request.user, 'add_comment')
        context['responsible_users'] = task.get_responsible_users()
        context['executors'] = task.get_executors()
        context['watchers'] = task.get_watchers()
        context['comments'] = task.comments.all()
        if context['can_add_comment']:
            context['comment_form'] = kwargs.get('comment_form', self.comment_form_class())
        context['task_detail_json_data'] = json.dumps({ "taskId": task.pk, "taskStatus": task.status, }, cls=DjangoJSONEncoder)
        return context

    def post(self, request, *args, **kwargs):
        self.object = self.get_object()
        if not self.object.has_permission(request.user, 'add_comment'):
            messages.error(request, _("Нет прав для добавления комментария."))
            return redirect(self.object.get_absolute_url())

        form = self.comment_form_class(request.POST)
        if form.is_valid():
            try:
                comment = form.save(commit=False)
                comment.task = self.object; comment.author = request.user; comment.save()
                logger.info(f"Comment {comment.id} added to task {self.object.id} by {request.user.username}")
                messages.success(request, _("Комментарий добавлен."))
                return redirect(self.object.get_absolute_url() + '#comments')
            except Exception as e:
                logger.exception(f"Error saving comment for task {self.object.id}: {e}")
                messages.error(request, _("Ошибка сохранения комментария."))
        else:
            logger.warning(f"Invalid comment form task {self.object.id}: {form.errors.as_json()}")
            messages.error(request, _("Исправьте ошибки в форме комментария."))
        return render(request, self.template_name, self.get_context_data(comment_form=form))

class TaskCreateView(LoginRequiredMixin, SuccessMessageMixin, CreateView):
    model = Task
    form_class = TaskForm
    template_name = 'tasks/task_form.html'
    success_message = _("Задача '%(number)s' успешно создана.")

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs(); kwargs['user'] = self.request.user; return kwargs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['page_title'] = _('Создание новой задачи')
        context['form_action'] = _('Создать задачу')
        if self.request.method == 'POST':
            context['photo_formset'] = TaskPhotoFormSet(self.request.POST, self.request.FILES, queryset=TaskPhoto.objects.none(), prefix='photos')
        else:
            context['photo_formset'] = TaskPhotoFormSet(queryset=TaskPhoto.objects.none(), prefix='photos')
        return context

    def form_valid(self, form):
        context = self.get_context_data()
        photo_formset = context['photo_formset']
        if photo_formset.is_valid():
            self.object = form.save()
            instances = photo_formset.save(commit=False)
            for instance in instances:
                instance.task = self.object
                if hasattr(instance, 'uploaded_by') and not instance.uploaded_by_id: instance.uploaded_by = self.request.user
                instance.save()
            photo_formset.save_m2m()
            logger.info(f"Task '{self.object.task_number}' created by {self.request.user.username}.")
            # Format success message AFTER object is saved and has number
            self.success_message = self.get_success_message(form.cleaned_data)
            return super().form_valid(form)
        else:
            logger.warning(f"Task create failed (invalid photo formset): {photo_formset.errors}")
            return self.render_to_response(self.get_context_data(form=form))

    def form_invalid(self, form):
        logger.warning(f"Invalid task create form: {form.errors.as_json()}")
        return self.render_to_response(self.get_context_data(form=form))

    # Override get_success_message for create view specifically
    def get_success_message(self, cleaned_data):
        return self.success_message % {'number': self.object.task_number or self.object.pk}

    def get_success_url(self):
        return reverse('tasks:task_detail', kwargs={'pk': self.object.pk})

class TaskUpdateView(LoginRequiredMixin, UserPassesTestMixin, SuccessMessageMixin, UpdateView):
    model = Task
    form_class = TaskForm
    template_name = 'tasks/task_form.html'
    success_message = _("Задача '#%(number)s' успешно обновлена.") # Use number formatting

    def test_func(self):
        return self.get_object().has_permission(self.request.user, 'change')

    def handle_no_permission(self):
        messages.error(self.request, _("Нет прав для редактирования этой задачи."))
        return redirect(self.get_object().get_absolute_url())

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs(); kwargs['user'] = self.request.user; return kwargs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['page_title'] = _('Редактирование задачи') + f": #{self.object.task_number or self.object.pk}"
        context['form_action'] = _('Сохранить изменения')
        if self.request.method == 'POST':
            context['photo_formset'] = TaskPhotoFormSet(self.request.POST, self.request.FILES, queryset=self.object.photos.all(), prefix='photos')
        else:
            context['photo_formset'] = TaskPhotoFormSet(queryset=self.object.photos.all(), prefix='photos')
        return context

    def form_valid(self, form):
        context = self.get_context_data()
        photo_formset = context['photo_formset']
        if photo_formset.is_valid():
            self.object = form.save()
            for photo_form in photo_formset.deleted_forms:
                 if photo_form.instance.pk and photo_form.instance.task == self.object:
                      try: photo_form.instance.delete(); logger.info(f"Photo {photo_form.instance.pk} deleted for task {self.object.id}")
                      except Exception as e: logger.exception(f"Error deleting photo {photo_form.instance.pk}: {e}")
            instances = photo_formset.save(commit=False)
            for instance in instances:
                 instance.task = self.object
                 if hasattr(instance, 'uploaded_by') and not instance.uploaded_by_id: instance.uploaded_by = self.request.user
                 instance.save()
            photo_formset.save_m2m()
            logger.info(f"Task '{self.object.task_number}' updated by {self.request.user.username}.")
            # Format message AFTER save
            self.success_message = self.get_success_message(form.cleaned_data)
            return super().form_valid(form)
        else:
            logger.warning(f"Task update {self.object.id} failed (invalid photo formset): {photo_formset.errors}")
            return self.render_to_response(self.get_context_data(form=form))

    def form_invalid(self, form):
        logger.warning(f"Invalid task update form {self.object.id}: {form.errors.as_json()}")
        return self.render_to_response(self.get_context_data(form=form))

    def get_success_message(self, cleaned_data):
         # Access object directly as it's saved by the time this is called in UpdateView
        return self.success_message % {'number': self.object.task_number or self.object.pk}

    def get_success_url(self):
        return reverse('tasks:task_detail', kwargs={'pk': self.object.pk})

class TaskDeleteView(LoginRequiredMixin, UserPassesTestMixin, DeleteView):
    model = Task
    template_name = 'tasks/task_confirm_delete.html'
    success_url = reverse_lazy('tasks:task_list')
    context_object_name = 'task'

    def test_func(self):
        return self.get_object().has_permission(self.request.user, 'delete')

    def handle_no_permission(self):
        messages.error(self.request, _("Нет прав для удаления этой задачи."))
        return redirect(self.get_object().get_absolute_url())

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['page_title'] = _('Удаление задачи') + f": #{self.object.task_number or self.object.pk}"
        return context

    def form_valid(self, form):
        task_number = self.object.task_number or self.object.pk
        try:
             response = super().form_valid(form)
             logger.info(f"Task '{task_number}' deleted by {self.request.user.username}.")
             messages.success(self.request, _("Задача '#%(number)s' успешно удалена.") % {'number': task_number})
             return response
        except Exception as e:
             logger.exception(f"Error deleting task '{task_number}': {e}")
             messages.error(self.request, _("Ошибка при удалении задачи."))
             return redirect(self.success_url)

class TaskPerformView(LoginRequiredMixin, UserPassesTestMixin, View):
    def test_func(self):
        return get_object_or_404(Task, pk=self.kwargs['pk']).has_permission(self.request.user, 'change_status')

    def handle_no_permission(self):
        messages.error(self.request, _("Нет прав для выполнения действия."))
        return redirect(get_object_or_404(Task, pk=self.kwargs['pk']).get_absolute_url())

    def get(self, request, *args, **kwargs):
        task = get_object_or_404(Task, pk=kwargs['pk'])
        action = request.GET.get('action', 'toggle')
        original_status = task.status
        msg = ""

        if action == 'complete' and task.status != Task.StatusChoices.COMPLETED:
            task.status = Task.StatusChoices.COMPLETED; msg = _("Задача '#%(num)s' выполнена.")
        elif action == 'start' and task.status not in [Task.StatusChoices.IN_PROGRESS, Task.StatusChoices.COMPLETED, Task.StatusChoices.CANCELLED]:
            task.status = Task.StatusChoices.IN_PROGRESS; msg = _("Задача '#%(num)s' взята в работу.")
        elif action == 'toggle':
            if task.status == Task.StatusChoices.IN_PROGRESS: task.status = Task.StatusChoices.COMPLETED; msg = _("Задача '#%(num)s' выполнена.")
            elif task.status == Task.StatusChoices.COMPLETED: task.status = Task.StatusChoices.IN_PROGRESS; msg = _("Задача '#%(num)s' возвращена в работу.")
            else: task.status = Task.StatusChoices.IN_PROGRESS; msg = _("Задача '#%(num)s' взята в работу.")
        else:
            messages.warning(request, _("Действие '%(action)s' не применимо или статус не изменен.") % {'action': action})
            return redirect(request.META.get('HTTP_REFERER', task.get_absolute_url()))

        if task.status != original_status:
            try:
                task.save()
                logger.info(f"User {request.user.username} action '{action}' on task {task.id}, status: {original_status}->{task.status}")
                messages.success(request, msg % {'num': task.task_number or task.pk})
            except Exception as e:
                logger.exception(f"Error saving task {task.id} after action '{action}': {e}")
                messages.error(request, _("Ошибка сохранения задачи."))
        else:
             messages.info(request, _("Статус задачи '#%(num)s' не изменен.") % {'num': task.task_number or task.pk})
        return redirect(request.META.get('HTTP_REFERER', task.get_absolute_url()))

# --- Function-based view for adding comments ---
@login_required
def add_comment_to_task(request, task_id):
    task = get_object_or_404(Task, pk=task_id)
    if not task.has_permission(request.user, 'add_comment'):
        messages.error(request, _("Нет прав для добавления комментария."))
        return redirect(task.get_absolute_url())

    if request.method == 'POST':
        form = TaskCommentForm(request.POST)
        if form.is_valid():
            comment = form.save(commit=False)
            comment.task = task; comment.author = request.user; comment.save()
            messages.success(request, _("Комментарий добавлен."))
            return redirect(task.get_absolute_url() + '#comments')
        else:
            logger.warning(f"Invalid comment form (FBV) task {task.id}: {form.errors.as_json()}")
            messages.error(request, _("Ошибка в форме комментария."))
            # Redirect back to detail, ideally showing errors (difficult with FBV redirect)
            return redirect(task.get_absolute_url() + '#comment-form')
    else: # GET request
        return redirect(task.get_absolute_url())