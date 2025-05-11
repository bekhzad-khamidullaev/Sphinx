import logging
import json
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.urls import reverse_lazy, reverse
from django.utils.translation import gettext_lazy as _
from django.views.generic import ListView, DetailView, CreateView, UpdateView, DeleteView, View
from django.shortcuts import get_object_or_404, redirect, render
from django.http import Http404, JsonResponse, HttpResponseForbidden
from django.db.models import Prefetch, Q
from django.forms import modelformset_factory
from django.contrib import messages
from django.core.serializers.json import DjangoJSONEncoder
from django.contrib.auth.decorators import login_required
from django.db import transaction

from ..models import Task, TaskPhoto, TaskComment, TaskAssignment, Project
from ..forms import TaskForm, TaskPhotoForm, TaskCommentForm
from ..filters import TaskFilter
from .mixins import SuccessMessageMixin

from django.contrib.auth import get_user_model
User = get_user_model()

logger = logging.getLogger(__name__)

TaskPhotoFormSet = modelformset_factory(
    TaskPhoto, form=TaskPhotoForm, fields=('photo', 'description'), extra=1, can_delete=True
)

class TaskListView(LoginRequiredMixin, ListView):
    model = Task
    template_name = 'tasks/task_list.html'
    context_object_name = 'tasks_page_obj'
    paginate_by = 10

    def get_queryset(self):
        base_qs = Task.objects.select_related(
            'project', 'category', 'subcategory', 'created_by', 'team', 'department'
        ).prefetch_related(
            Prefetch('assignments', queryset=TaskAssignment.objects.select_related('user').order_by('role')),
            'photos'
        )
        user = self.request.user
        if not user.is_staff:
            base_qs = base_qs.filter(Q(created_by=user) | Q(assignments__user=user)).distinct()

        self.filterset = TaskFilter(self.request.GET, queryset=base_qs, request=self.request)
        filtered_qs = self.filterset.qs

        sort_param = self.request.GET.get('sort', '-created_at')
        allowed_sort_fields = {
            'number': 'task_number', 'title': 'title', 'project': 'project__name',
            'status': 'status', 'priority': 'priority', 'due_date': 'due_date',
            'created_at': 'created_at', 'team': 'team__name', 'department': 'department__name'
        }
        sort_key_cleaned = sort_param.lstrip('-')
        db_sort_field = allowed_sort_fields.get(sort_key_cleaned, 'created_at') # Default to created_at if invalid
        if sort_param.startswith('-') and not db_sort_field.startswith('-'): db_sort_field = f"-{db_sort_field}"
        elif not sort_param.startswith('-') and db_sort_field.startswith('-'): db_sort_field = db_sort_field.lstrip('-')
        if not db_sort_field.startswith('-') and sort_param.startswith('-'): db_sort_field = f"-{db_sort_field}"


        self.ordered_queryset = filtered_qs.order_by(db_sort_field, '-pk')
        return self.ordered_queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['filterset'] = self.filterset
        context['page_title'] = _('Задачи')
        context['current_sort'] = self.request.GET.get('sort', '-created_at')
        context['create_url'] = reverse_lazy('tasks:task_create')

        all_tasks_for_kanban = list(self.ordered_queryset)
        tasks_by_status_kanban = {code: [] for code, _ in Task.StatusChoices.choices}
        for task_item in all_tasks_for_kanban:
            tasks_by_status_kanban.setdefault(task_item.status, []).append(task_item)
        context['tasks_by_status_kanban'] = tasks_by_status_kanban

        context['status_choices_list'] = Task.StatusChoices.choices
        context['status_mapping_json'] = json.dumps(dict(Task.StatusChoices.choices), cls=DjangoJSONEncoder)

        view_param = self.request.GET.get('view')
        if view_param in ['list', 'kanban']: context['initial_task_view_mode'] = view_param
        else: context['initial_task_view_mode'] = self.request.COOKIES.get('task_view_mode', 'kanban')

        project_id_filter = self.request.GET.get('project')
        if project_id_filter:
            try:
                filtered_project = Project.objects.get(pk=project_id_filter)
                project_title = _("Задачи по проекту: %(name)s") % {'name': filtered_project.name}
                context['page_title'] = project_title
                context['filtered_project'] = filtered_project
            except (Project.DoesNotExist, ValueError): pass
        return context

    def dispatch(self, request, *args, **kwargs):
        response = super().dispatch(request, *args, **kwargs)
        view_param = request.GET.get('view')
        if view_param in ['list', 'kanban'] and hasattr(response, 'set_cookie'):
            response.set_cookie('task_view_mode', view_param, max_age=365 * 24 * 60 * 60, samesite='Lax', httponly=True)
        return response


class TaskDetailView(LoginRequiredMixin, UserPassesTestMixin, DetailView):
    model = Task
    template_name = 'tasks/task_detail.html'
    context_object_name = 'task_instance'
    comment_form_class = TaskCommentForm

    def test_func(self):
        task_instance = self.get_object()
        return task_instance.can_view(self.request.user)

    def handle_no_permission(self):
        messages.error(self.request, _("У вас нет прав для просмотра этой задачи."))
        return redirect(reverse_lazy('tasks:task_list'))

    def get_queryset(self):
        return super().get_queryset().select_related(
            'project', 'category', 'subcategory', 'created_by', 'team', 'department'
        ).prefetch_related(
            'photos',
            Prefetch('comments', queryset=TaskComment.objects.select_related('author').order_by('created_at')),
            Prefetch('assignments', queryset=TaskAssignment.objects.select_related('user').order_by('role'))
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        task_instance = self.object
        context['page_title'] = _("Задача #%(number)s") % {'number': task_instance.task_number or task_instance.pk}
        context['page_subtitle'] = task_instance.title

        context['can_change_task'] = task_instance.can_change_properties(self.request.user)
        context['can_delete_task'] = task_instance.can_delete(self.request.user)
        context['can_change_status'] = task_instance.can_change_status(self.request.user)
        context['can_manage_assignments'] = task_instance.can_manage_assignments(self.request.user)
        context['can_add_comment'] = task_instance.can_add_comment(self.request.user)

        context['responsible_users'] = task_instance.get_responsible_users()
        context['executors'] = task_instance.get_executors()
        context['watchers'] = task_instance.get_watchers()
        context['all_participants'] = task_instance.get_all_participants()

        if context['can_add_comment']:
            context['comment_form'] = kwargs.get('comment_form', self.comment_form_class())

        context['task_detail_json_data'] = json.dumps({
            "taskId": task_instance.pk, "taskStatus": task_instance.status, "taskNumber": task_instance.task_number
        }, cls=DjangoJSONEncoder)
        context['status_choices_json'] = json.dumps(list(Task.StatusChoices.choices), cls=DjangoJSONEncoder)
        return context

    def post(self, request, *args, **kwargs):
        self.object = self.get_object()
        if not self.object.can_add_comment(request.user):
            messages.error(request, _("У вас нет прав для добавления комментария."))
            return HttpResponseForbidden(_("Действие запрещено."))

        form = self.comment_form_class(request.POST)
        if form.is_valid():
            try:
                comment = form.save(commit=False)
                comment.task = self.object; comment.author = request.user
                setattr(comment, '_initiator_user_id', request.user.id)
                comment.save()
                logger.info(f"Comment {comment.id} added to task {self.object.id} by {request.user.username}")
                messages.success(request, _("Комментарий добавлен."))
                return redirect(self.object.get_absolute_url() + '#comments_section')
            except Exception as e:
                logger.exception(f"Error saving comment for task {self.object.id}: {e}")
                messages.error(request, _("Ошибка сохранения комментария."))
            finally:
                if hasattr(comment, '_initiator_user_id'): delattr(comment, '_initiator_user_id')
        else:
            logger.warning(f"Invalid comment form for task {self.object.id}: {form.errors.as_json()}")
            messages.error(request, _("Исправьте ошибки в форме комментария."))
        return self.render_to_response(self.get_context_data(comment_form=form))


class TaskCreateView(LoginRequiredMixin, UserPassesTestMixin, SuccessMessageMixin, CreateView):
    model = Task; form_class = TaskForm; template_name = 'tasks/task_form.html'

    def test_func(self): return self.request.user.has_perm('tasks.add_task')
    def handle_no_permission(self):
        messages.error(self.request, _("У вас нет прав для создания задач."))
        return redirect(reverse_lazy('tasks:task_list'))

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs(); kwargs['user'] = self.request.user; return kwargs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['page_title_from_view'] = _('Создание новой задачи')
        context['page_title'] = _('Создание новой задачи')
        context['form_action_label'] = _('Создать задачу')
        context['tasks_list_url'] = reverse_lazy('tasks:task_list')
        if self.request.POST: context['photo_formset'] = TaskPhotoFormSet(self.request.POST, self.request.FILES, queryset=TaskPhoto.objects.none(), prefix='photos')
        else: context['photo_formset'] = TaskPhotoFormSet(queryset=TaskPhoto.objects.none(), prefix='photos')
        return context

    def form_valid(self, form):
        context = self.get_context_data(); photo_formset = context['photo_formset']
        if not photo_formset.is_valid():
            logger.warning(f"Task create failed (invalid photo formset): {photo_formset.errors}")
            for fs_form_errors in photo_formset.errors:
                for field, errors in fs_form_errors.items():
                    form.add_error(None, _("Фото (%(field)s): %(error)s") % {'field': field, 'error': ", ".join(errors)})
            return self.form_invalid(form)
        try:
            with transaction.atomic():
                self.object = form.save()
                photos = photo_formset.save(commit=False)
                for photo_instance in photos:
                    photo_instance.task = self.object
                    if not photo_instance.uploaded_by_id: photo_instance.uploaded_by = self.request.user
                    setattr(photo_instance, '_initiator_user_id', self.request.user.id)
                    photo_instance.save()
                photo_formset.save_m2m()
            logger.info(f"Task '{self.object.task_number}' created by {self.request.user.username}.")
        except Exception as e:
            logger.exception(f"Error during atomic transaction for task creation by {self.request.user.username}: {e}")
            messages.error(self.request, _("Произошла ошибка при создании задачи: %(detail)s") % {'detail': str(e)})
            return self.form_invalid(form)
        return super().form_valid(form)

    def form_invalid(self, form):
        logger.warning(f"Invalid task create form: {form.errors.as_json()}")
        context = self.get_context_data(form=form); return self.render_to_response(context)
    def get_success_message(self, cleaned_data):
        return _("Задача '#%(number)s: %(title)s' успешно создана.") % {'number': self.object.task_number or self.object.pk, 'title': self.object.title}
    def get_success_url(self): return reverse_lazy('tasks:task_detail', kwargs={'pk': self.object.pk})


class TaskUpdateView(LoginRequiredMixin, UserPassesTestMixin, SuccessMessageMixin, UpdateView):
    model = Task; form_class = TaskForm; template_name = 'tasks/task_form.html'; context_object_name = 'task_instance'

    def test_func(self): return self.get_object().can_change_properties(self.request.user)
    def handle_no_permission(self):
        messages.error(self.request, _("У вас нет прав для редактирования этой задачи."))
        return redirect(self.get_object().get_absolute_url())

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs(); kwargs['user'] = self.request.user; return kwargs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs); task_instance = self.object
        context['page_title_from_view'] = _("Редактирование задачи #%(number)s") % {'number': task_instance.task_number or task_instance.pk}
        context['page_title'] = context['page_title_from_view']
        context['page_subtitle'] = task_instance.title
        context['form_action_label'] = _('Сохранить изменения')
        context['tasks_list_url'] = reverse_lazy('tasks:task_list')
        if self.request.POST: context['photo_formset'] = TaskPhotoFormSet(self.request.POST, self.request.FILES, queryset=task_instance.photos.all(), prefix='photos')
        else: context['photo_formset'] = TaskPhotoFormSet(queryset=task_instance.photos.all(), prefix='photos')
        return context

    def form_valid(self, form):
        context = self.get_context_data(); photo_formset = context['photo_formset']
        if not photo_formset.is_valid():
            logger.warning(f"Task update {self.object.id} failed (invalid photo formset): {photo_formset.errors}")
            for fs_form_errors in photo_formset.errors:
                for field, errors in fs_form_errors.items():
                    form.add_error(None, _("Фото (%(field)s): %(error)s") % {'field': field, 'error': ", ".join(errors)})
            return self.form_invalid(form)
        try:
            with transaction.atomic():
                self.object = form.save()
                for photo_form_item in photo_formset.deleted_forms:
                    if photo_form_item.instance.pk: photo_form_item.instance.delete()
                new_photos = photo_formset.save(commit=False)
                for photo_instance in new_photos:
                    if not photo_instance.task_id: photo_instance.task = self.object
                    if not photo_instance.uploaded_by_id: photo_instance.uploaded_by = self.request.user
                    setattr(photo_instance, '_initiator_user_id', self.request.user.id)
                    photo_instance.save()
                photo_formset.save_m2m()
            logger.info(f"Task '{self.object.task_number}' updated by {self.request.user.username}.")
        except Exception as e:
            logger.exception(f"Error during atomic transaction for task update {self.object.id}: {e}")
            messages.error(self.request, _("Произошла ошибка при обновлении задачи: %(detail)s") % {'detail': str(e)})
            return self.form_invalid(form)
        return super().form_valid(form)

    def form_invalid(self, form):
        logger.warning(f"Invalid task update form {self.object.id}: {form.errors.as_json()}")
        context = self.get_context_data(form=form)
        if 'photo_formset' not in context:
            context['photo_formset'] = TaskPhotoFormSet(self.request.POST or None, self.request.FILES or None, queryset=self.object.photos.all(), prefix='photos')
        return self.render_to_response(context)
    def get_success_message(self, cleaned_data):
        return _("Задача '#%(number)s: %(title)s' успешно обновлена.") % {'number': self.object.task_number or self.object.pk, 'title': self.object.title}
    def get_success_url(self): return reverse_lazy('tasks:task_detail', kwargs={'pk': self.object.pk})


class TaskDeleteView(LoginRequiredMixin, UserPassesTestMixin, DeleteView):
    model = Task; template_name = 'tasks/task_confirm_delete.html'; success_url = reverse_lazy('tasks:task_list'); context_object_name = 'object'

    def test_func(self): return self.get_object().can_delete(self.request.user)
    def handle_no_permission(self):
        messages.error(self.request, _("У вас нет прав для удаления этой задачи."))
        try: return redirect(self.get_object().get_absolute_url())
        except Http404: return redirect(self.success_url)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs); task_instance = self.object
        display_name = f"#{task_instance.task_number or task_instance.pk}: {task_instance.title}"
        context['page_title'] = _("Удаление задачи: %(name)s") % {'name': display_name}
        context['confirm_delete_message'] = _("Вы уверены, что хотите удалить задачу '%(name)s'? Это действие необратимо.") % {'name': display_name}
        return context

    def form_valid(self, form):
        task_display = f"#{self.object.task_number or self.object.pk}: {self.object.title}"
        try:
            setattr(self.object, '_initiator_user_id', self.request.user.id)
            response = super().form_valid(form)
            logger.info(f"Task '{task_display}' deleted by {self.request.user.username}.")
            messages.success(self.request, _("Задача '%(name)s' успешно удалена.") % {'name': task_display})
            return response
        except Exception as e:
            logger.exception(f"Error deleting task '{task_display}': {e}")
            messages.error(self.request, _("Ошибка при удалении задачи."))
            return redirect(self.success_url)
        finally:
            if hasattr(self.object, '_initiator_user_id'): delattr(self.object, '_initiator_user_id')


class TaskPerformView(LoginRequiredMixin, UserPassesTestMixin, View):
    def setup(self, request, *args, **kwargs):
        super().setup(request, *args, **kwargs)
        self.task_instance = get_object_or_404(Task, pk=self.kwargs['pk'])

    def test_func(self): return self.task_instance.can_change_status(self.request.user)
    def handle_no_permission(self):
        messages.error(self.request, _("У вас нет прав для выполнения этого действия над задачей."))
        return redirect(self.task_instance.get_absolute_url())

    def get(self, request, *args, **kwargs):
        action = request.GET.get('action'); original_status = self.task_instance.status
        new_status_candidate = None; success_msg_template = None
        task_display_name = self.task_instance.task_number or self.task_instance.pk

        workflow_actions = {
            'start_progress': (Task.StatusChoices.IN_PROGRESS, _("Задача '#%(num)s' взята в работу."), [Task.StatusChoices.BACKLOG, Task.StatusChoices.NEW, Task.StatusChoices.ON_HOLD]),
            'put_on_hold': (Task.StatusChoices.ON_HOLD, _("Задача '#%(num)s' отложена."), [Task.StatusChoices.IN_PROGRESS]),
            # 'send_to_review': (Task.StatusChoices.IN_REVIEW, _("Задача '#%(num)s' отправлена на проверку."), [Task.StatusChoices.IN_PROGRESS]),
            'mark_done': (Task.StatusChoices.COMPLETED, _("Задача '#%(num)s' отмечена как выполненная."), [Task.StatusChoices.NEW, Task.StatusChoices.IN_PROGRESS, Task.StatusChoices.ON_HOLD]), # Removed IN_REVIEW for now
            'reopen_to_todo': (Task.StatusChoices.NEW, _("Задача '#%(num)s' переоткрыта и возвращена в 'Новая'."), [Task.StatusChoices.COMPLETED, Task.StatusChoices.CANCELLED, Task.StatusChoices.ON_HOLD]), # Removed CLOSED, IN_REVIEW
            # 'close_task': (Task.StatusChoices.CLOSED, _("Задача '#%(num)s' закрыта."), [Task.StatusChoices.COMPLETED]),
            'cancel_task': (Task.StatusChoices.CANCELLED, _("Задача '#%(num)s' отменена."), lambda t: not t.is_resolved)
        }
        if action in workflow_actions:
            action_config = workflow_actions[action]
            new_status_candidate = action_config[0]
            success_msg_template = action_config[1]
            allowed_current_statuses_or_condition = action_config[2]

            if isinstance(allowed_current_statuses_or_condition, list) and original_status not in allowed_current_statuses_or_condition:
                new_status_candidate = None # Prevent action
            elif callable(allowed_current_statuses_or_condition) and not allowed_current_statuses_or_condition(self.task_instance):
                new_status_candidate = None # Prevent action based on condition

        if not new_status_candidate:
            messages.warning(request, _("Действие '%(action)s' неприменимо для текущего статуса задачи '#%(num)s'.") % {'action': action, 'num': task_display_name})
            return redirect(request.META.get('HTTP_REFERER', self.task_instance.get_absolute_url()))

        if not self.task_instance.can_change_status(request.user, new_status_candidate):
            messages.error(request, _("У вас нет прав на перевод задачи '#%(num)s' в статус '%(status)s'.") % {'num': task_display_name, 'status': Task.StatusChoices(new_status_candidate).label})
            return redirect(request.META.get('HTTP_REFERER', self.task_instance.get_absolute_url()))

        self.task_instance.status = new_status_candidate
        try:
            setattr(self.task_instance, '_initiator_user_id', request.user.id)
            self.task_instance.save(update_fields=['status', 'updated_at', 'completion_date'])
            logger.info(f"User {request.user.username} action '{action}' on task {self.task_instance.id}. Status: {original_status} -> {self.task_instance.status}")
            if success_msg_template: messages.success(request, success_msg_template % {'num': task_display_name})
        except Exception as e:
            logger.exception(f"Error saving task {self.task_instance.id} after action '{action}': {e}")
            messages.error(request, _("Ошибка сохранения изменений в задаче."))
        finally:
            if hasattr(self.task_instance, '_initiator_user_id'): delattr(self.task_instance, '_initiator_user_id')
        return redirect(request.META.get('HTTP_REFERER', self.task_instance.get_absolute_url()))


@login_required
def add_comment_to_task(request, task_id):
    task_instance = get_object_or_404(Task, pk=task_id)
    if not task_instance.can_add_comment(request.user):
        messages.error(request, _("У вас нет прав для добавления комментария к этой задаче."))
        return redirect(task_instance.get_absolute_url())

    if request.method == 'POST':
        form = TaskCommentForm(request.POST)
        if form.is_valid():
            try:
                comment = form.save(commit=False)
                comment.task = task_instance; comment.author = request.user
                setattr(comment, '_initiator_user_id', request.user.id)
                comment.save()
                messages.success(request, _("Комментарий успешно добавлен."))
                return redirect(task_instance.get_absolute_url() + '#comments_section')
            except Exception as e:
                logger.exception(f"Error saving comment for task {task_instance.id}: {e}")
                messages.error(request, _("Ошибка при сохранении комментария."))
            finally:
                if hasattr(comment, '_initiator_user_id'): delattr(comment, '_initiator_user_id')
        else:
            logger.warning(f"Invalid comment form for task {task_instance.id}: {form.errors.as_json()}")
            messages.error(request, _("Пожалуйста, исправьте ошибки в форме комментария."))
            return redirect(task_instance.get_absolute_url() + '#comment-form')
    else: return HttpResponseForbidden(_("Метод GET не разрешен для этого URL, используйте POST для добавления комментария."))