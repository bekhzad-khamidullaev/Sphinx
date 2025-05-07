# tasks/views/task.py
import logging
import json
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.urls import reverse_lazy, reverse
from django.utils.translation import gettext_lazy as _
from django.views.generic import ListView, DetailView, CreateView, UpdateView, DeleteView, View
from django.shortcuts import get_object_or_404, redirect, render
from django.http import Http404, JsonResponse # JsonResponse для возможных AJAX в будущем
from django.db.models import Prefetch, Q
from django.forms import modelformset_factory
from django.contrib import messages
from django.core.serializers.json import DjangoJSONEncoder # Для сериализации в JSON для JS
from django.contrib.auth.decorators import login_required
from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
import logging

from ..models import Task, TaskPhoto, TaskComment
from ..forms import TaskForm, TaskPhotoForm, TaskCommentForm # TaskPhotoFormSet будет здесь
from ..filters import TaskFilter
from .mixins import SuccessMessageMixin, WebSocketNotificationMixin # WebSocket для деталей задачи

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Предполагается, что TaskUserRole импортируется из user_profiles
try:
    from user_profiles.models import TaskUserRole, User
except ImportError:
    TaskUserRole = None
    User = None # Если User не из django.contrib.auth.models
    logger.warning("TaskUserRole or User model not found. Task assignment features might be limited.")


logger = logging.getLogger(__name__)

# FormSet для загрузки нескольких фотографий
TaskPhotoFormSet = modelformset_factory(
    TaskPhoto,
    form=TaskPhotoForm, # Используем нашу кастомную TaskPhotoForm
    fields=('photo', 'description'), # Поля для редактирования в формсете
    extra=1, # Количество пустых форм для добавления
    can_delete=True # Позволяет удалять существующие фото через формсет
)

class TaskListView(LoginRequiredMixin, ListView):
    model = Task
    template_name = 'tasks/task_list.html' # Убедитесь, что шаблон существует
    context_object_name = 'tasks' # Имя для списка задач в шаблоне
    paginate_by = 10 # Или другое значение по умолчанию

    def get_queryset(self):
        # Оптимизированный запрос с предзагрузкой связанных данных
        queryset = Task.objects.select_related(
            'project', 'category', 'subcategory', 'created_by'
        ).prefetch_related(
            # Prefetch для ролей пользователей, если TaskUserRole используется
            Prefetch('user_roles', queryset=TaskUserRole.objects.select_related('user').order_by('role') if TaskUserRole else TaskUserRole.objects.none()),
            'photos' # Предзагрузка фото для возможного отображения миниатюр в списке
        ).order_by('-created_at') # Сортировка по умолчанию

        # Применение фильтров
        # Пользователь request передается в TaskFilter для возможной фильтрации "мои задачи"
        self.filterset = TaskFilter(self.request.GET, queryset=queryset, request=self.request)
        filtered_qs = self.filterset.qs.distinct() # distinct() важен при использовании Q-объектов или M2M в фильтрах

        # Обработка сортировки из GET-параметра
        sort_param = self.request.GET.get('sort', '-created_at') # По умолчанию сортируем по дате создания (новые сверху)
        allowed_sort_fields = [
            'task_number', 'title', 'project__name', 'status', 'priority',
            'deadline', 'start_date', 'completion_date', 'created_at', 'updated_at'
        ]
        # Проверка, чтобы избежать сортировки по неразрешенным полям
        sort_field_cleaned = sort_param.lstrip('-')
        if sort_field_cleaned in allowed_sort_fields:
            # self.active_queryset используется для Kanban и пагинации
            self.active_queryset = filtered_qs.order_by(sort_param)
        else:
            logger.warning(f"Attempted to sort by unallowed field: {sort_param}. Defaulting to '-created_at'.")
            self.active_queryset = filtered_qs.order_by('-created_at')
        
        return self.active_queryset # Возвращаем уже отсортированный queryset для пагинации ListView

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['filterset'] = self.filterset
        context['page_title'] = _('Задачи')
        context['current_sort'] = self.request.GET.get('sort', '-created_at') # Для отображения активной сортировки

        # Данные для Kanban-доски (все отфильтрованные задачи, не только текущая страница)
        # Используем self.active_queryset, который уже отфильтрован и отсортирован
        all_tasks_for_kanban = self.active_queryset # Это уже отфильтрованный и отсортированный queryset

        tasks_by_status = {code: [] for code, display_name in Task.StatusChoices.choices}
        for task in all_tasks_for_kanban: # Итерируемся по полному отфильтрованному списку
            tasks_by_status.setdefault(task.status, []).append(task)
        
        context['tasks_by_status'] = tasks_by_status
        context['status_mapping'] = dict(Task.StatusChoices.choices) # { 'new': 'Новая', ... }
        context['status_mapping_json'] = json.dumps(context['status_mapping'], cls=DjangoJSONEncoder) # Для JS
        context['status_choices_for_kanban'] = Task.StatusChoices.choices # Для итерации в шаблоне Kanban
        
        # `page_obj` уже содержит пагинированные задачи для табличного/списочного вида
        # context['tasks'] (из context_object_name) будет содержать пагинированный список
        # context['page_obj'] = context['page_obj'] # Уже есть от ListView

        context['ws_group_name'] = 'tasks_list' # Для real-time обновлений списка
        return context

class TaskDetailView(LoginRequiredMixin, UserPassesTestMixin, DetailView):
    model = Task
    template_name = 'tasks/task_detail.html' # Убедитесь, что шаблон существует
    context_object_name = 'task'
    comment_form_class = TaskCommentForm # Форма для добавления комментариев

    def test_func(self):
        # Проверка прав доступа к просмотру задачи
        task = self.get_object() # Получаем объект задачи
        return task.has_permission(self.request.user, 'view')

    def handle_no_permission(self):
        messages.error(self.request, _("У вас нет прав для просмотра этой задачи."))
        return redirect(reverse_lazy('tasks:task_list')) # Или на другую страницу

    def get_queryset(self):
        # Оптимизированный запрос с предзагрузкой всех необходимых связанных данных
        return super().get_queryset().select_related(
            'project', 'category', 'subcategory', 'created_by', 'created_by__userprofile' if User else None
        ).prefetch_related(
            'photos',
            Prefetch('comments', queryset=TaskComment.objects.select_related('author__userprofile' if User else 'author').order_by('created_at')),
            # Предзагрузка ролей пользователей, если TaskUserRole используется
            Prefetch('user_roles', queryset=TaskUserRole.objects.select_related('user__userprofile' if User else 'user').order_by('role') if TaskUserRole else TaskUserRole.objects.none())
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        task = self.object # self.object уже установлен DetailView
        context['page_title'] = _('Задача #%(number)s: %(title)s') % {'number': task.task_number or task.pk, 'title': task.title}
        
        # Проверка прав для отображения кнопок действий
        context['can_change_task'] = task.has_permission(self.request.user, 'change')
        context['can_delete_task'] = task.has_permission(self.request.user, 'delete')
        context['can_add_comment'] = task.has_permission(self.request.user, 'add_comment')
        context['can_change_status'] = task.has_permission(self.request.user, 'change_status')


        # Получение пользователей по ролям (если TaskUserRole используется)
        if TaskUserRole:
            context['responsible_users_list'] = task.get_responsible_users()
            context['executors_list'] = task.get_executors()
            context['watchers_list'] = task.get_watchers()
        
        context['comments_list'] = task.comments.all() # Уже отсортированы в prefetch
        if context['can_add_comment']:
            # Передаем форму комментария, если она не была передана после неудачной отправки
            context['comment_form'] = kwargs.get('comment_form', self.comment_form_class())
        
        # Данные для JS на странице (например, для WebSocket или AJAX)
        context['task_detail_json_data'] = json.dumps({
            "taskId": task.pk,
            "taskStatus": task.status,
            "wsCommentGroup": f"task_comments_{task.pk}", # Группа для комментариев этой задачи
            "wsTaskUpdateGroup": f"task_{task.pk}",     # Группа для обновлений этой задачи
        }, cls=DjangoJSONEncoder)
        context['status_choices_json'] = json.dumps(dict(Task.StatusChoices.choices), cls=DjangoJSONEncoder)


        return context

    def post(self, request, *args, **kwargs):
        # Обработка POST-запроса для добавления комментария
        self.object = self.get_object() # Устанавливаем self.object
        if not self.object.has_permission(request.user, 'add_comment'):
            messages.error(request, _("У вас нет прав для добавления комментария к этой задаче."))
            return redirect(self.object.get_absolute_url())

        form = self.comment_form_class(request.POST)
        if form.is_valid():
            try:
                comment = form.save(commit=False)
                comment.task = self.object
                comment.author = request.user # Устанавливаем автора комментария
                comment.save()
                logger.info(f"Comment {comment.id} added to task {self.object.id} by {request.user.username}")
                messages.success(request, _("Ваш комментарий успешно добавлен."))
                # WebSocket уведомление о новом комментарии отправляется через сигнал post_save TaskComment
                return redirect(self.object.get_absolute_url() + '#comments-section') # Перенаправляем к секции комментариев
            except Exception as e:
                logger.exception(f"Error saving comment for task {self.object.id}: {e}")
                messages.error(request, _("Произошла ошибка при сохранении вашего комментария."))
        else:
            logger.warning(f"Invalid comment form for task {self.object.id}: {form.errors.as_json()}")
            messages.error(request, _("Пожалуйста, исправьте ошибки в форме комментария."))
        
        # Если форма невалидна, снова рендерим страницу с ошибками в форме
        return self.render_to_response(self.get_context_data(comment_form=form))


class TaskCreateView(LoginRequiredMixin, SuccessMessageMixin, WebSocketNotificationMixin, CreateView):
    model = Task
    form_class = TaskForm
    template_name = 'tasks/task_form.html' # Убедитесь, что шаблон существует
    success_message = _("Задача '#%(task_number)s: %(title)s' успешно создана.")
    
    # WebSocketNotificationMixin settings
    ws_group_name = "tasks_list" # Обновляем общий список задач
    ws_event_type = "list_update" # Тип события для консьюмера (должен совпадать с методом в TaskConsumer)

    def get_form_kwargs(self):
        # Передаем текущего пользователя в форму
        kwargs = super().get_form_kwargs()
        kwargs['user'] = self.request.user
        return kwargs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['page_title'] = _('Создание новой задачи')
        context['form_action_label'] = _('Создать задачу')
        if self.request.POST:
            context['photo_formset'] = TaskPhotoFormSet(self.request.POST, self.request.FILES, queryset=TaskPhoto.objects.none(), prefix='photos')
        else:
            context['photo_formset'] = TaskPhotoFormSet(queryset=TaskPhoto.objects.none(), prefix='photos')
        return context

    def form_valid(self, form):
        context = self.get_context_data()
        photo_formset = context['photo_formset']

        if photo_formset.is_valid():
            # `form.save()` вызовет TaskForm.save(), который создаст задачу и установит created_by
            self.object = form.save(commit=True) # `commit=True` здесь, т.к. TaskForm.save() делает это атомарно
            
            # Сохранение фотографий из формсета
            photos = photo_formset.save(commit=False)
            for photo in photos:
                if photo.photo: # Только если файл был выбран
                    photo.task = self.object
                    if not photo.uploaded_by_id: # Устанавливаем загрузчика, если не задан
                        photo.uploaded_by = self.request.user
                    photo.save()
            # photo_formset.save_m2m() # Если есть m2m в TaskPhotoForm

            logger.info(f"Task '{self.object.task_number}' created by {self.request.user.username}.")
            
            # Сообщение об успехе будет сформировано миксином
            # WebSocket уведомление
            self.send_ws_notification(action="create", instance=self.object)
            
            return redirect(self.get_success_url()) # Используем redirect вместо super().form_valid()
        else:
            logger.warning(f"Task creation failed due to invalid photo formset: {photo_formset.errors}")
            # Возвращаем форму с ошибками фото-формсета
            return self.render_to_response(self.get_context_data(form=form, photo_formset=photo_formset))

    def form_invalid(self, form):
        logger.warning(f"Invalid task creation form: {form.errors.as_json()}")
        # Если основная форма невалидна, фото-формсет также нужно передать обратно
        photo_formset = TaskPhotoFormSet(self.request.POST or None, self.request.FILES or None, queryset=TaskPhoto.objects.none(), prefix='photos')
        return self.render_to_response(self.get_context_data(form=form, photo_formset=photo_formset))

    def get_success_url(self):
        # Перенаправляем на детальную страницу созданной задачи
        return reverse('tasks:task_detail', kwargs={'pk': self.object.pk})

    def get_success_message(self, cleaned_data):
        # self.object уже доступен здесь
        return self.success_message % {
            'task_number': self.object.task_number or self.object.pk,
            'title': self.object.title
        }


class TaskUpdateView(LoginRequiredMixin, UserPassesTestMixin, SuccessMessageMixin, WebSocketNotificationMixin, UpdateView):
    model = Task
    form_class = TaskForm
    template_name = 'tasks/task_form.html'
    success_message = _("Задача '#%(task_number)s: %(title)s' успешно обновлена.")
    context_object_name = 'task' # Явно указываем имя объекта в контексте

    # WebSocketNotificationMixin settings
    ws_event_type = "list_update" # Обновляем задачу в общем списке
    # Для обновления деталей задачи, можно использовать другую группу/тип или отдельный вызов

    def get_ws_group_name(self):
        # return f"task_{self.object.id}" # Для деталей (если такой консьюмер есть)
        return "tasks_list" # Для списка

    def test_func(self):
        task = self.get_object()
        return task.has_permission(self.request.user, 'change')

    def handle_no_permission(self):
        messages.error(self.request, _("У вас нет прав для редактирования этой задачи."))
        return redirect(self.get_object().get_absolute_url())

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['user'] = self.request.user # Передаем пользователя в форму
        return kwargs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['page_title'] = _('Редактирование задачи #%(number)s') % {'number': self.object.task_number or self.object.pk}
        context['form_action_label'] = _('Сохранить изменения')
        if self.request.POST:
            context['photo_formset'] = TaskPhotoFormSet(self.request.POST, self.request.FILES, queryset=self.object.photos.all(), prefix='photos')
        else:
            context['photo_formset'] = TaskPhotoFormSet(queryset=self.object.photos.all(), prefix='photos')
        return context

    def form_valid(self, form):
        context = self.get_context_data()
        photo_formset = context['photo_formset']

        if photo_formset.is_valid():
            self.object = form.save(commit=True) # TaskForm.save() handles roles

            # Обработка удаленных фото
            for photoform in photo_formset.deleted_forms:
                 if photoform.instance.pk: # Убеждаемся, что это существующий объект
                      try:
                          photoform.instance.delete()
                          logger.info(f"Photo {photoform.instance.pk} deleted for task {self.object.id}")
                      except Exception as e:
                          logger.exception(f"Error deleting photo {photoform.instance.pk}: {e}")
            
            # Сохранение новых/измененных фото
            photos = photo_formset.save(commit=False)
            for photo in photos:
                if photo.photo: # Если файл был выбран или изменен
                    photo.task = self.object
                    if not photo.uploaded_by_id:
                        photo.uploaded_by = self.request.user
                    photo.save()
            # photo_formset.save_m2m() # Если есть m2m

            logger.info(f"Task '{self.object.task_number}' updated by {self.request.user.username}.")
            
            self.send_ws_notification(action="update", instance=self.object)
            # Дополнительное уведомление для страницы деталей задачи
            if hasattr(self, 'object') and self.object:
                detail_ws_mixin = WebSocketNotificationMixin()
                detail_ws_mixin.ws_group_name = f"task_{self.object.id}"
                detail_ws_mixin.ws_event_type = "task_update" # Другой тип события для деталей
                detail_ws_mixin.send_ws_notification(action="update", instance=self.object)


            return redirect(self.get_success_url())
        else:
            logger.warning(f"Task update {self.object.id} failed due to invalid photo formset: {photo_formset.errors}")
            return self.render_to_response(self.get_context_data(form=form, photo_formset=photo_formset))

    def form_invalid(self, form):
        logger.warning(f"Invalid task update form for {self.object.id if hasattr(self, 'object') else 'new task'}: {form.errors.as_json()}")
        photo_formset = TaskPhotoFormSet(self.request.POST or None, self.request.FILES or None, queryset=self.object.photos.all() if hasattr(self, 'object') else TaskPhoto.objects.none(), prefix='photos')
        return self.render_to_response(self.get_context_data(form=form, photo_formset=photo_formset))

    def get_success_url(self):
        return reverse('tasks:task_detail', kwargs={'pk': self.object.pk})

    def get_success_message(self, cleaned_data):
        return self.success_message % {
            'task_number': self.object.task_number or self.object.pk,
            'title': self.object.title
        }


class TaskDeleteView(LoginRequiredMixin, UserPassesTestMixin, DeleteView):
    model = Task
    template_name = 'tasks/task_confirm_delete.html' # Убедитесь, что шаблон существует
    success_url = reverse_lazy('tasks:task_list')
    context_object_name = 'task'

    # Параметры для ручной отправки WebSocket уведомления
    ws_group_name_on_delete = "tasks_list"
    ws_event_type_on_delete = "list_update" # Тип для TaskConsumer

    def test_func(self):
        task = self.get_object()
        return task.has_permission(self.request.user, 'delete')

    def handle_no_permission(self):
        messages.error(self.request, _("У вас нет прав для удаления этой задачи."))
        return redirect(self.get_object().get_absolute_url())

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['page_title'] = _('Удаление задачи #%(number)s') % {'number': self.object.task_number or self.object.pk}
        return context

    def form_valid(self, form):
        task_number = self.object.task_number or self.object.pk
        task_id = self.object.id # Сохраняем ID до удаления
        task_title = self.object.title

        try:
            response = super().form_valid(form) # Задача удаляется здесь
            logger.info(f"Task '{task_number}' deleted by {self.request.user.username}.")
            messages.success(self.request, _("Задача '#%(number)s: %(title)s' успешно удалена.") % {'number': task_number, 'title': task_title})
            
            # Ручная отправка WebSocket уведомления
            try:
                channel_layer = get_channel_layer()
                if channel_layer:
                    async_to_sync(channel_layer.group_send)(
                        self.ws_group_name_on_delete,
                        {
                            "type": self.ws_event_type_on_delete,
                            "message": {"action": "delete", "model": "task", "id": task_id}
                        }
                    )
                    logger.debug(f"WS delete notification sent for Task ID {task_id}")
            except Exception as e:
                logger.error(f"Failed sending WS delete notification for Task ID {task_id}: {e}")

            return response
        except Exception as e:
            logger.exception(f"Error deleting task '{task_number}': {e}")
            messages.error(self.request, _("Произошла ошибка при удалении задачи."))
            return redirect(self.success_url)


class TaskPerformView(LoginRequiredMixin, UserPassesTestMixin, View):
    """
    Представление для выполнения быстрых действий над задачей,
    например, "взять в работу", "завершить".
    Используется GET-запрос с параметром action.
    """
    def test_func(self):
        task = get_object_or_404(Task, pk=self.kwargs['pk'])
        # Проверяем общее право на изменение статуса
        return task.has_permission(self.request.user, 'change_status')

    def handle_no_permission(self):
        messages.error(self.request, _("У вас нет прав для выполнения этого действия над задачей."))
        # Пытаемся вернуть на предыдущую страницу или на страницу задачи
        task_pk = self.kwargs.get('pk')
        if task_pk:
            return redirect(reverse_lazy('tasks:task_detail', kwargs={'pk': task_pk}))
        return redirect(reverse_lazy('tasks:task_list'))

    def get(self, request, *args, **kwargs):
        task = get_object_or_404(Task, pk=kwargs['pk'])
        action = request.GET.get('action', None)
        original_status = task.status
        success_msg = ""

        if action == 'complete' and task.status != Task.StatusChoices.COMPLETED:
            task.status = Task.StatusChoices.COMPLETED
            success_msg = _("Задача '#%(num)s' отмечена как выполненная.")
        elif action == 'start_progress' and task.status not in [Task.StatusChoices.IN_PROGRESS, Task.StatusChoices.COMPLETED, Task.StatusChoices.CANCELLED]:
            task.status = Task.StatusChoices.IN_PROGRESS
            success_msg = _("Задача '#%(num)s' взята в работу.")
        elif action == 'put_on_hold' and task.status == Task.StatusChoices.IN_PROGRESS:
            task.status = Task.StatusChoices.ON_HOLD
            success_msg = _("Задача '#%(num)s' отложена.")
        elif action == 'resume_progress' and task.status == Task.StatusChoices.ON_HOLD:
            task.status = Task.StatusChoices.IN_PROGRESS
            success_msg = _("Работа над задачей '#%(num)s' возобновлена.")
        # Добавить другие действия по необходимости (например, 'cancel')
        else:
            messages.warning(request, _("Действие '%(action)s' не применимо к текущему статусу задачи или не распознано.") % {'action': action})
            return redirect(request.META.get('HTTP_REFERER', task.get_absolute_url()))

        if task.status != original_status:
            try:
                # Модель сама обработает completion_date и overdue status
                task.save(update_fields=['status', 'updated_at', 'completion_date']) # Указываем поля для сохранения
                logger.info(f"User {request.user.username} performed action '{action}' on task {task.id}. Status changed: {original_status} -> {task.status}")
                messages.success(request, success_msg % {'num': task.task_number or task.pk})
                # WebSocket уведомление отправляется через сигнал post_save Task
            except Exception as e:
                logger.exception(f"Error saving task {task.id} after action '{action}': {e}")
                messages.error(request, _("Произошла ошибка при сохранении изменений задачи."))
        else:
             messages.info(request, _("Статус задачи '#%(num)s' не изменен.") % {'num': task.task_number or task.pk})
        
        return redirect(request.META.get('HTTP_REFERER', task.get_absolute_url()))


# FBV для добавления комментариев, если используется отдельно от TaskDetailView.post
@login_required
def add_comment_to_task(request, task_id):
    task = get_object_or_404(Task, pk=task_id)
    if not task.has_permission(request.user, 'add_comment'):
        messages.error(request, _("У вас нет прав для добавления комментария к этой задаче."))
        return redirect(task.get_absolute_url())

    if request.method == 'POST':
        form = TaskCommentForm(request.POST)
        if form.is_valid():
            comment = form.save(commit=False)
            comment.task = task
            comment.author = request.user
            comment.save()
            messages.success(request, _("Комментарий успешно добавлен."))
            # WebSocket уведомление отправляется через сигнал post_save TaskComment
            return redirect(task.get_absolute_url() + '#comments-section')
        else:
            logger.warning(f"Invalid comment form (FBV) for task {task.id}: {form.errors.as_json()}")
            # В идеале, здесь нужно передать ошибки формы обратно в шаблон TaskDetailView
            # Это сложно сделать с простым redirect, поэтому CBV (TaskDetailView.post) предпочтительнее.
            # Можно сохранить ошибки в сессии и отобразить их на странице задачи.
            for field, errors in form.errors.items():
                for error in errors:
                    messages.error(request, f"{form.fields[field].label if field != '__all__' else ''}: {error}")
            return redirect(task.get_absolute_url() + '#comment-form-section') # Якорь к форме
    else: # GET-запрос на этот URL не должен ничего делать, кроме редиректа
        return redirect(task.get_absolute_url())