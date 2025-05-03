# tasks/views/task.py
import logging
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.contrib.messages.views import SuccessMessageMixin
from django.urls import reverse_lazy, reverse
from django.utils.translation import gettext_lazy as _
from django.views.generic import ListView, DetailView, CreateView, UpdateView, DeleteView, View
from django.shortcuts import get_object_or_404, redirect, render
from django.http import Http404, JsonResponse
from django.db.models import Prefetch, Q
from django.forms import modelformset_factory # For photo formset
from django.contrib import messages # For manual messages

from ..models import Task, TaskPhoto, TaskComment
from ..forms import TaskForm, TaskPhotoForm, TaskCommentForm
from ..filters import TaskFilter
# Safely import user-related models
try:
    from user_profiles.models import TaskUserRole, User
except ImportError:
    TaskUserRole = None
    User = None

logger = logging.getLogger(__name__)

# --- Helper for Task Photo Formset ---
TaskPhotoFormSet = modelformset_factory(
    TaskPhoto,
    form=TaskPhotoForm,
    fields=('photo', 'description'), # Fields editable in the formset
    extra=1, # Start with one extra empty form
    can_delete=True # Allow deleting existing photos
)

# --- Task Views ---
class TaskListView(LoginRequiredMixin, ListView):
    model = Task
    template_name = 'tasks/task_list.html'
    context_object_name = 'tasks_list' # Use this for the paginated list
    paginate_by = 10

    def get_queryset(self):
        # Start with base queryset, optimize with select/prefetch
        queryset = Task.objects.select_related(
            'project', 'category', 'subcategory', 'created_by'
        ).prefetch_related(
            # Prefetch users through TaskUserRole for participant display
            Prefetch('user_roles', queryset=TaskUserRole.objects.select_related('user').order_by('role'))
        ).order_by('-created_at') # Default ordering

        # --- Permission Filtering (Example: show only tasks user is involved in or created) ---
        # if not self.request.user.is_staff: # Example condition
        #     queryset = queryset.filter(
        #         Q(created_by=self.request.user) |
        #         Q(user_roles__user=self.request.user)
        #     ).distinct()

        # Apply filtering from URL parameters
        self.filterset = TaskFilter(self.request.GET, queryset=queryset, request=self.request)
        filtered_qs = self.filterset.qs.distinct()

        # --- Sorting Logic ---
        sort_param = self.request.GET.get('sort', '-created_at') # Default sort by newest
        allowed_sort_fields = ['task_number', 'title', 'project__name', 'status', 'priority', 'deadline', 'created_at', 'created_by__username']

        # Validate sort_param
        sort_field = sort_param.lstrip('-')
        if sort_field in allowed_sort_fields:
            self.active_queryset = filtered_qs.order_by(sort_param) # Apply requested sorting
        else:
            logger.warning(f"Attempted to sort by disallowed field: {sort_param}")
            self.active_queryset = filtered_qs.order_by('-created_at') # Fallback to default sorting

        return self.active_queryset # Return the final sorted & filtered queryset for pagination

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs) # Gets paginated object_list as 'tasks_list'
        context['filterset'] = self.filterset
        context['page_title'] = _('Задачи')
        context['current_sort'] = self.request.GET.get('sort', '-created_at')

        # --- Kanban/List View specific data ---
        # Pass the *unpaginated* but filtered/sorted queryset for Kanban
        all_tasks_for_kanban = self.active_queryset

        # Group tasks by status for Kanban
        tasks_by_status = {}
        status_mapping = dict(Task.StatusChoices.choices)
        context['status_mapping'] = status_mapping # Pass mapping to template

        # Initialize all statuses from choices to ensure columns render even if empty
        for status_code, _status_name in Task.StatusChoices.choices:
            tasks_by_status[status_code] = []

        for task in all_tasks_for_kanban:
            tasks_by_status.setdefault(task.status, []).append(task)

        context['tasks_by_status'] = tasks_by_status

        # Add status choices for the dropdown in list view
        context['status_choices'] = Task.StatusChoices.choices

        # Pass the paginated list under the correct name if different from default 'object_list'
        context['page_obj'] = context['page_obj'] # Already contains the paginated tasks

        return context


class TaskDetailView(LoginRequiredMixin, UserPassesTestMixin, DetailView):
    model = Task
    template_name = 'tasks/task_detail.html'
    context_object_name = 'task'

    comment_form_class = TaskCommentForm

    def test_func(self):
        task = self.get_object()
        return task.has_permission(self.request.user, 'view')

    def handle_no_permission(self):
        messages.error(self.request, _("У вас нет прав для просмотра этой задачи."))
        # Redirect to task list or dashboard
        return redirect(reverse_lazy('tasks:task_list'))

    def get_queryset(self):
        # Optimize query for detail view
        return super().get_queryset().select_related(
            'project', 'category', 'subcategory', 'created_by'
        ).prefetch_related(
            'photos',
            Prefetch('comments', queryset=TaskComment.objects.select_related('author').order_by('created_at')), # Order comments
            Prefetch('user_roles', queryset=TaskUserRole.objects.select_related('user').order_by('role')) # Order roles
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        task = self.object
        context['page_title'] = _('Задача') + f" #{task.task_number}"

        # Permissions for template rendering
        context['can_change_task'] = task.has_permission(self.request.user, 'change')
        context['can_delete_task'] = task.has_permission(self.request.user, 'delete')
        context['can_add_comment'] = task.has_permission(self.request.user, 'add_comment')

        # Separate users by role for easier template access
        context['responsible_users'] = task.get_responsible_users()
        context['executors'] = task.get_executors()
        context['watchers'] = task.get_watchers()
        context['comments'] = task.comments.all() # Already prefetched

        # Add comment form to context
        if context['can_add_comment']:
            # Check if form exists from a failed POST, otherwise create new
             context['comment_form'] = kwargs.get('comment_form', self.comment_form_class())

        return context

    def post(self, request, *args, **kwargs):
        """Handles POST requests for adding comments."""
        self.object = self.get_object() # Get the task instance

        # Check permission again for POST
        if not self.object.has_permission(request.user, 'add_comment'):
             messages.error(request, _("У вас нет прав для добавления комментария."))
             if request.headers.get('x-requested-with') == 'XMLHttpRequest':
                  return JsonResponse({'success': False, 'error': _("Нет прав.")}, status=403)
             return redirect(self.object.get_absolute_url())

        form = self.comment_form_class(request.POST)

        if form.is_valid():
            try:
                comment = form.save(commit=False)
                comment.task = self.object
                comment.author = request.user
                comment.save()
                logger.info(f"User {request.user.username} added comment {comment.id} to task {self.object.id}")

                # AJAX success response
                if request.headers.get('x-requested-with') == 'XMLHttpRequest':
                     author_name = comment.author.display_name if comment.author else _("Аноним")
                     author_avatar_url = comment.author.image.url if comment.author and comment.author.image else None # TODO: Add default avatar URL path
                     comment_data = {
                         'id': comment.id,
                         'text': comment.text, # Sending raw text, template should escape
                         'created_at_iso': comment.created_at.isoformat(),
                         'author': {
                             'id': comment.author.id if comment.author else None,
                             'name': author_name,
                             'avatar_url': author_avatar_url
                         },
                         'task_id': comment.task.id,
                     }
                     return JsonResponse({'success': True, 'comment': comment_data})

                # Standard success response (non-AJAX)
                messages.success(request, _("Комментарий успешно добавлен."))
                return redirect(self.object.get_absolute_url() + '#comments') # Redirect to comments anchor

            except Exception as e:
                 logger.exception(f"Error saving comment for task {self.object.id} by user {request.user.username}: {e}")
                 error_message = _("Произошла ошибка при сохранении комментария.")
                 if request.headers.get('x-requested-with') == 'XMLHttpRequest':
                     return JsonResponse({'success': False, 'error': error_message, 'errors': {'__all__': [error_message]}}, status=500)
                 messages.error(request, error_message)
                 # Re-render page with the form containing errors
                 return render(request, self.template_name, self.get_context_data(comment_form=form))

        else: # Form is invalid
            logger.warning(f"Invalid comment form submission for task {self.object.id} by user {request.user.username}: {form.errors.as_json()}")
            error_message = _("Пожалуйста, исправьте ошибки в форме комментария.")
            if request.headers.get('x-requested-with') == 'XMLHttpRequest':
                 return JsonResponse({'success': False, 'error': error_message, 'errors': form.errors}, status=400)
            messages.error(request, error_message)
             # Re-render page with the form containing errors
            return render(request, self.template_name, self.get_context_data(comment_form=form))


class TaskCreateView(LoginRequiredMixin, SuccessMessageMixin, CreateView):
    model = Task
    form_class = TaskForm
    template_name = 'tasks/task_form.html'
    # success_url is determined in form_valid

    def get_form_kwargs(self):
        """Pass the current user to the form."""
        kwargs = super().get_form_kwargs()
        kwargs['user'] = self.request.user
        return kwargs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['page_title'] = _('Создание новой задачи')
        context['form_action'] = _('Создать задачу')
        # Initialize photo formset for the template
        if self.request.method == 'POST':
            context['photo_formset'] = TaskPhotoFormSet(self.request.POST, self.request.FILES, queryset=TaskPhoto.objects.none(), prefix='photos')
        else:
            context['photo_formset'] = TaskPhotoFormSet(queryset=TaskPhoto.objects.none(), prefix='photos') # Empty queryset for create
        return context

    def form_valid(self, form):
        """Process a valid main task form and the photo formset."""
        context = self.get_context_data()
        photo_formset = context['photo_formset'] # Get formset from context (already initialized with POST data)

        if photo_formset.is_valid():
            # The form's save method now handles setting the creator via __init__ kwarg
            self.object = form.save() # commit=True by default

            # Save the photo formset instances, associating them with the newly created task
            instances = photo_formset.save(commit=False)
            for instance in instances:
                instance.task = self.object
                # Set uploaded_by if the model requires it and form doesn't handle it
                if hasattr(instance, 'uploaded_by') and not instance.uploaded_by_id:
                     instance.uploaded_by = self.request.user
                instance.save()
            photo_formset.save_m2m() # Save any m2m relationships if needed

            logger.info(f"Task '{self.object.task_number}' created successfully by user {self.request.user.username}.")
            messages.success(self.request, _("Задача '%(number)s' успешно создана.") % {'number': self.object.task_number})
            return redirect(self.get_success_url()) # Redirect to task detail
        else:
            # If photo formset is invalid, re-render the form with errors
            logger.warning(f"Task creation failed due to invalid photo formset for user {self.request.user.username}. Errors: {photo_formset.errors}")
            # Pass invalid formset back to template via context
            return self.render_to_response(self.get_context_data(form=form)) # form_valid isn't called if main form invalid

    def form_invalid(self, form):
        """Handle invalid main task form."""
        logger.warning(f"Invalid task creation form submission by user {self.request.user.username}. Errors: {form.errors.as_json()}")
        # Pass back the main form with errors and the photo formset (populated from POST)
        return self.render_to_response(self.get_context_data(form=form))
    

    def get_success_url(self):
        """Redirect to the detail view of the created task."""
        return reverse('tasks:task_detail', kwargs={'pk': self.object.pk})

    # Optional: Add permission checks
    # def dispatch(self, request, *args, **kwargs):
    #     if not request.user.has_perm('tasks.add_task'):
    #         messages.error(request, _("У вас нет прав для создания задач."))
    #         return self.handle_no_permission()
    #     return super().dispatch(request, *args, **kwargs)


class TaskUpdateView(LoginRequiredMixin, UserPassesTestMixin, SuccessMessageMixin, UpdateView):
    model = Task
    form_class = TaskForm
    template_name = 'tasks/task_form.html'
    # success_url depends on the object, set in get_success_url

    def test_func(self):
        task = self.get_object()
        return task.has_permission(self.request.user, 'change')

    def handle_no_permission(self):
        messages.error(self.request, _("У вас нет прав для редактирования этой задачи."))
        return redirect(self.get_object().get_absolute_url()) # Redirect back to detail

    def get_form_kwargs(self):
        """Pass the current user to the form."""
        kwargs = super().get_form_kwargs()
        kwargs['user'] = self.request.user # Pass user for potential logic within the form
        return kwargs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['page_title'] = _('Редактирование задачи') + f": #{self.object.task_number}"
        context['form_action'] = _('Сохранить изменения')
        if self.request.method == 'POST':
            context['photo_formset'] = TaskPhotoFormSet(self.request.POST, self.request.FILES, queryset=TaskPhoto.objects.filter(task=self.object), prefix='photos')
        else:
             # Query existing photos for this task for the formset
             context['photo_formset'] = TaskPhotoFormSet(queryset=TaskPhoto.objects.filter(task=self.object), prefix='photos')
        return context

    def form_valid(self, form):
        """Process valid task form and photo formset."""
        context = self.get_context_data()
        photo_formset = context['photo_formset'] # Get formset from context

        if photo_formset.is_valid():
            self.object = form.save() # Save main task changes

            # Handle photo deletions marked in the formset
            for photo_form in photo_formset.deleted_forms:
                 if photo_form.instance.pk:
                      try:
                           # Ensure the photo actually belongs to this task before deleting
                           if photo_form.instance.task == self.object:
                                photo_form.instance.delete()
                                logger.info(f"Photo {photo_form.instance.pk} deleted for task {self.object.id}")
                           else:
                               logger.warning(f"Attempt to delete photo {photo_form.instance.pk} not belonging to task {self.object.id}")
                      except Exception as e:
                           logger.exception(f"Error deleting photo {photo_form.instance.pk}: {e}")
                           messages.error(self.request, _("Ошибка при удалении фото %(id)s.") % {'id': photo_form.instance.pk})

            # Save new/updated photos
            instances = photo_formset.save(commit=False)
            for instance in instances:
                 instance.task = self.object # Ensure association
                 if hasattr(instance, 'uploaded_by') and not instance.uploaded_by_id: # Set uploader for new photos
                      instance.uploaded_by = self.request.user
                 instance.save()
            photo_formset.save_m2m()

            logger.info(f"Task '{self.object.task_number}' updated successfully by user {self.request.user.username}.")
            messages.success(self.request, _("Задача '%(number)s' успешно обновлена.") % {'number': self.object.task_number})
            return redirect(self.get_success_url())
        else:
            logger.warning(f"Task update failed due to invalid photo formset for task {self.object.id}. Errors: {photo_formset.errors}")
            # Pass invalid formset back to template via context
            return self.render_to_response(self.get_context_data(form=form)) # form_valid not called if main invalid

    def form_invalid(self, form):
        """Handle invalid main task form during update."""
        logger.warning(f"Invalid task update form submission for task {self.object.id} by user {self.request.user.username}. Errors: {form.errors.as_json()}")
        # Pass back the main form with errors and the photo formset (populated from POST)
        return self.render_to_response(self.get_context_data(form=form))

    def get_success_url(self):
        """Redirect back to the detail view of the updated task."""
        return reverse('tasks:task_detail', kwargs={'pk': self.object.pk})


class TaskDeleteView(LoginRequiredMixin, UserPassesTestMixin, DeleteView): # No SuccessMessageMixin
    model = Task
    template_name = 'tasks/task_confirm_delete.html'
    success_url = reverse_lazy('tasks:task_list')
    context_object_name = 'task' # Use 'task' for clarity in template

    def test_func(self):
        task = self.get_object()
        return task.has_permission(self.request.user, 'delete')

    def handle_no_permission(self):
        messages.error(self.request, _("У вас нет прав для удаления этой задачи."))
        return redirect(self.get_object().get_absolute_url())

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['page_title'] = _('Удаление задачи') + f": #{self.object.task_number}"
        return context

    def form_valid(self, form):
        task_number = self.object.task_number # Get info before deletion
        try:
             response = super().form_valid(form)
             logger.info(f"Task '{task_number}' deleted successfully by user {self.request.user.username}.")
             messages.success(self.request, _("Задача '%(number)s' успешно удалена.") % {'number': task_number})
             return response # Use response from super() which handles redirect
        except Exception as e:
             logger.exception(f"Error deleting task '{task_number}' by user {self.request.user.username}: {e}")
             messages.error(self.request, _("Произошла ошибка при удалении задачи."))
             # Attempt to redirect back to detail, might fail if object is partially deleted
             try:
                 return redirect(reverse('tasks:task_detail', kwargs={'pk': self.object.pk}))
             except:
                 return redirect(self.success_url) # Fallback to list view

# --- TaskPerformView (Kept as is) ---
class TaskPerformView(LoginRequiredMixin, UserPassesTestMixin, View):

     def test_func(self):
         task = get_object_or_404(Task, pk=self.kwargs['pk'])
         # Example: Only executors or responsible users can perform actions
         return task.has_permission(self.request.user, 'change_status') # Or a more specific permission

     def handle_no_permission(self):
         messages.error(self.request, _("У вас нет прав для выполнения этого действия над задачей."))
         task = get_object_or_404(Task, pk=self.kwargs['pk'])
         return redirect(task.get_absolute_url())

     def get(self, request, *args, **kwargs):
         task = get_object_or_404(Task, pk=kwargs['pk'])
         action = request.GET.get('action', 'toggle') # Allow specific actions via query param

         if action == 'complete':
             if task.status != Task.StatusChoices.COMPLETED:
                 task.status = Task.StatusChoices.COMPLETED
                 messages.success(request, _("Задача '%(num)s' отмечена как выполненная.") % {'num': task.task_number})
             else:
                 messages.info(request, _("Задача '%(num)s' уже была выполнена.") % {'num': task.task_number})
         elif action == 'start':
              if task.status not in [Task.StatusChoices.IN_PROGRESS, Task.StatusChoices.COMPLETED, Task.StatusChoices.CANCELLED]:
                  task.status = Task.StatusChoices.IN_PROGRESS
                  messages.success(request, _("Задача '%(num)s' взята в работу.") % {'num': task.task_number})
              else:
                   messages.info(request, _("Невозможно начать выполнение задачи '%(num)s' в текущем статусе.") % {'num': task.task_number})
         else: # Default 'toggle' or unrecognized action
             if task.status == Task.StatusChoices.IN_PROGRESS:
                 task.status = Task.StatusChoices.COMPLETED
                 messages.success(request, _("Задача '%(num)s' отмечена как выполненная.") % {'num': task.task_number})
             elif task.status == Task.StatusChoices.COMPLETED:
                 task.status = Task.StatusChoices.IN_PROGRESS
                 messages.info(request, _("Задача '%(num)s' возвращена в работу.") % {'num': task.task_number})
             else:
                 task.status = Task.StatusChoices.IN_PROGRESS
                 messages.info(request, _("Задача '%(num)s' взята в работу.") % {'num': task.task_number})

         try:
             task.save() # clean() method handles completion_date etc.
             logger.info(f"User {request.user.username} performed action '{action}' on task {task.id}, new status: {task.status}")
         except Exception as e:
             logger.exception(f"Error saving task {task.id} after action '{action}' by user {request.user.username}: {e}")
             messages.error(request, _("Ошибка при сохранении изменений задачи."))

         # Redirect back to the previous page or detail view
         return redirect(request.META.get('HTTP_REFERER', task.get_absolute_url()))