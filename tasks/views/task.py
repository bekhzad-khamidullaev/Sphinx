# tasks/views/task.py

import logging
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import Q
from django.forms.models import inlineformset_factory
from django.http import Http404, HttpResponseRedirect
from django.shortcuts import redirect, render
from django.urls import reverse_lazy
from django.utils.translation import gettext_lazy as _
from django.views.generic import DetailView, CreateView, UpdateView, DeleteView
from django_filters.views import FilterView
from django.contrib import messages
# Paginator импортируется базовым классом, но ошибки можно импортировать
from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger

# Локальные импорты
from ..models import Task, TaskPhoto
from user_profiles.models import TaskUserRole # Импорт из user_profiles
from ..forms import TaskForm, TaskPhotoForm, TaskCommentForm
from ..filters import TaskFilter
from .mixins import SuccessMessageMixin

logger = logging.getLogger(__name__)

# ==============================================================================
# Task List View (Kanban & List)
# ==============================================================================
class TaskListView(LoginRequiredMixin, FilterView):
    """
    Отображает список задач в виде Канбан-доски или таблицы.
    Поддерживает фильтрацию и пагинацию (для вида списка).
    """
    model = Task
    template_name = "tasks/task_list.html"
    # context_object_name определяет имя для списка объектов В ТЕКУЩЕЙ странице
    # page_obj будет содержать сам объект пагинатора
    context_object_name = "tasks_on_page" # Используем это имя для итерации в шаблоне списка
    paginate_by = 15
    filterset_class = TaskFilter

    def get_base_queryset(self):
        """
        Возвращает базовый QuerySet задач с необходимой оптимизацией.
        """
        return Task.objects.select_related(
            "project", "category", "subcategory", "created_by"
        ).prefetch_related(
            'photos',
            'user_roles__user' # Prefetch пользователей через роли для оптимизации
        ).order_by('priority', 'deadline', '-created_at') # Сортировка: приоритет -> срок -> дата создания

    def get_queryset(self):
        """
        Фильтрует базовый QuerySet на основе прав текущего пользователя.
        """
        user = self.request.user
        queryset = self.get_base_queryset()

        if user.is_superuser or user.has_perm('tasks.view_task'):
            return queryset # Возвращаем все задачи

        # Фильтруем для обычных пользователей
        queryset = queryset.filter(
            Q(created_by=user) | Q(user_roles__user=user)
        ).distinct() # distinct обязателен из-за M2M user_roles

        logger.debug(f"User {user.username} queryset count (filtered): {queryset.count()}")
        return queryset

    def get_context_data(self, **kwargs):
        """
        Подготавливает и добавляет данные в контекст шаблона для ОБОИХ видов.
        """
        # 1. Вызываем super() СНАЧАЛА. Он обработает фильтрацию и пагинацию,
        # установит self.object_list (отфильтрованный) и добавит в контекст:
        # 'filter' (filterset), 'paginator', 'page_obj', 'is_paginated',
        # и object_list под именем context_object_name ('tasks_on_page')
        context = super().get_context_data(**kwargs) # <<< ИСПРАВЛЕНО: убрана передача object_list

        # 2. Получаем отфильтрованные задачи (из context или self.object_list)
        # self.object_list содержит ВСЕ отфильтрованные задачи, не только текущую страницу
        # Используем context['filter'].qs, т.к. super() уже установил отфильтрованный queryset в filterset
        filterset = context.get('filter')
        if not filterset:
             logger.error("Filterset not found in context after super().get_context_data(). Check FilterView setup.")
             filtered_tasks_qs = self.model.objects.none() # Возвращаем пустой queryset в случае ошибки
        else:
             filtered_tasks_qs = filterset.qs.distinct() # Получаем отфильтрованный queryset из filterset


        # 3. Подготовка данных для Канбана
        status_mapping = dict(Task.StatusChoices.choices)
        tasks_by_status = {key: [] for key, _ in Task.StatusChoices.choices}
        for task in filtered_tasks_qs: # Итерируем по ПОЛНОМУ отфильтрованному списку
             if task.status in tasks_by_status:
                 tasks_by_status[task.status].append(task)
             else:
                 logger.warning(f"Task {task.id} has unknown status '{task.status}' for Kanban grouping.")

        # 4. Добавляем/обновляем элементы контекста
        context['filterset'] = filterset # Filterset для формы фильтров
        context['page_title'] = _("Задачи")
        # Определяем текущий вид для JS (приоритет: URL -> session -> default)
        view_type = self.request.GET.get('view', self.request.session.get('task_list_view', 'kanban'))
        self.request.session['task_list_view'] = view_type # Сохраняем в сессию для следующего раза
        context['view_type'] = view_type

        # Добавляем данные, нужные для ОБОИХ видов
        context['status_mapping'] = status_mapping # Для отображения названий статусов
        context['status_choices'] = Task.StatusChoices.choices # Для select'ов смены статуса
        context['tasks_by_status'] = tasks_by_status # Данные для рендеринга Канбана

        # Данные пагинации ('page_obj', 'paginator', 'is_paginated') уже в контексте от super()
        # Список задач для ТЕКУЩЕЙ страницы уже в контексте под именем 'tasks_on_page' (context_object_name)
        # Переименуем page_obj для ясности в шаблоне пагинации
        context['page_obj'] = context.get('page_obj') # Получаем из контекста, установленного super()

        # Логирование для отладки
        page_obj = context.get('page_obj')
        paginator = context.get('paginator')
        if page_obj and paginator:
             logger.debug(f"Context prepared. View: '{view_type}'. Page: {page_obj.number}/{paginator.num_pages}. Tasks on page: {len(context.get(self.context_object_name, []))}. Total filtered: {paginator.count}")
        else:
             logger.error("Pagination context ('page_obj', 'paginator') not found after super().get_context_data()")


        return context

# ==============================================================================
# Task Detail View
# ==============================================================================
class TaskDetailView(LoginRequiredMixin, DetailView):
    """Отображает детальную информацию о конкретной задаче."""
    model = Task
    template_name = "tasks/task_detail.html"
    context_object_name = "task"

    def get_queryset(self):
        return super().get_queryset().select_related(
            "project", "category", "subcategory", "created_by"
        ).prefetch_related(
            'photos',
            'comments__author', # Предзагружаем комментарии и их авторов
            'user_roles__user'
        )

    def get_object(self, queryset=None):
        """Проверяет права доступа перед возвратом объекта."""
        obj = super().get_object(queryset=queryset)
        if not obj.has_permission(self.request.user, 'view'):
            logger.warning(f"User {self.request.user.username} forbidden to view task {obj.id}")
            raise Http404(_("Вы не имеете доступа к этой задаче."))
        return obj

    def get_context_data(self, **kwargs):
        """Добавляет данные в контекст для шаблона деталей."""
        context = super().get_context_data(**kwargs)
        task = self.object
        context['page_title'] = f"{_('Задача')}: {task.title}"
        context['responsible_users'] = task.get_responsible_users()
        context['executors'] = task.get_executors()
        context['watchers'] = task.get_watchers()
        TaskPhotoInlineFormSet = inlineformset_factory(Task, TaskPhoto, form=TaskPhotoForm, extra=0, can_delete=False)
        context['photo_formset'] = TaskPhotoInlineFormSet(instance=task)
        if 'comment_form' not in context: context['comment_form'] = TaskCommentForm()
        context['can_change_task'] = task.has_permission(self.request.user, 'change')
        context['can_delete_task'] = task.has_permission(self.request.user, 'delete')
        context['can_change_status'] = task.has_permission(self.request.user, 'change_status')
        context['can_assign_users'] = task.has_permission(self.request.user, 'assign_users')
        context['can_add_comment'] = task.has_permission(self.request.user, 'add_comment')
        context['comments'] = task.comments.select_related('author').all() # Оптимизация
        return context

    def post(self, request, *args, **kwargs):
        """Обрабатывает отправку формы комментария (AJAX или стандартный POST)."""
        self.object = self.get_object()
        user = request.user
        is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest'

        if not self.object.has_permission(user, 'add_comment'):
             error_message = _("У вас нет прав для добавления комментария к этой задаче.")
             if is_ajax:
                 return JsonResponse({'success': False, 'error': error_message}, status=403)
             else:
                 messages.error(request, error_message)
                 return redirect(self.object.get_absolute_url())

        form = TaskCommentForm(request.POST)

        if form.is_valid():
            comment = form.save(commit=False)
            comment.task = self.object
            comment.author = user
            comment.save()
            logger.info(f"User {user.username} added comment {comment.id} to task {self.object.id}")

            # --- Возвращаем JSON для AJAX запроса ---
            if is_ajax:
                # Возвращаем данные нового комментария для добавления в DOM через JS
                author_avatar_url = user.image.url if user.image else static('img/user.svg') # Получаем URL аватара
                comment_data = {
                    'id': comment.id,
                    'text': comment.text, # JS должен будет экранировать
                    'created_at_iso': comment.created_at.isoformat(),
                    'author': {
                        'id': user.id,
                        'name': user.display_name,
                        'avatar_url': author_avatar_url
                    },
                }
                return JsonResponse({'success': True, 'comment': comment_data})
            # --- Для стандартного POST - редирект ---
            else:
                messages.success(request, _("Ваш комментарий успешно добавлен."))
                return HttpResponseRedirect(self.object.get_absolute_url() + '#comments') # Используем HttpResponseRedirect
        else:
            # --- Ошибки валидации ---
            error_message = _("Ошибка при добавлении комментария. Проверьте текст.")
            logger.warning(f"Invalid comment submitted by user {user.username} for task {self.object.id}. Errors: {form.errors.as_json()}")
            if is_ajax:
                # Возвращаем ошибки формы в JSON
                 return JsonResponse({'success': False, 'errors': form.errors.get_json_data()}, status=400)
            else:
                # Показываем страницу снова с ошибками
                messages.error(request, error_message)
                context = self.get_context_data(comment_form=form) # Передаем невалидную форму
                return self.render_to_response(context)

# ==============================================================================
# Base View for Task Forms (Create & Update)
# ==============================================================================
class BaseTaskFormView:
    """Общая логика для Create и Update Task представлений."""
    model = Task
    form_class = TaskForm
    template_name = "tasks/task_form.html" # Убедитесь, что шаблон существует

    def get_form_kwargs(self):
        """Передает пользователя в форму, если форма его ожидает."""
        kwargs = super().get_form_kwargs()
        # Если TaskForm требует пользователя (например, для фильтрации):
        # kwargs['user'] = self.request.user
        return kwargs

    def get_context_data(self, **kwargs):
        """Добавляет формсет для фото в контекст."""
        context = super().get_context_data(**kwargs)
        num_photos = 10 # Максимальное количество фото
        extra_photos = 1 # Количество пустых форм для добавления

        TaskPhotoFormSet = inlineformset_factory(
            Task, TaskPhoto, form=TaskPhotoForm,
            extra=extra_photos, max_num=num_photos,
            can_delete=True # Разрешаем удаление в UpdateView
        )

        if self.request.POST:
            # Если POST запрос, связываем формсет с данными POST и файлами
            context['photo_formset'] = TaskPhotoFormSet(
                self.request.POST, self.request.FILES,
                instance=self.object if hasattr(self, 'object') else None, # Передаем instance для UpdateView
                prefix='photos' # Важный префикс для полей формсета
            )
        else:
            # Если GET запрос, создаем несвязанный формсет
            context['photo_formset'] = TaskPhotoFormSet(
                instance=self.object if hasattr(self, 'object') else None, # Передаем instance для UpdateView
                prefix='photos'
            )
        return context

    def form_valid(self, form):
        """Обрабатывает валидную основную форму и формсет фото."""
        context = self.get_context_data()
        photo_formset = context['photo_formset']

        if not photo_formset.is_valid():
            logger.warning(f"Photo formset invalid. Errors: {photo_formset.errors}")
            # Возвращаем форму с ошибками, включая ошибки формсета
            return self.form_invalid(form)

        # Устанавливаем создателя для новых задач
        # Проверяем, является ли это CreateView, проверив наличие self.object до вызова super().form_valid()
        is_new_task = not hasattr(self, 'object') or not self.object
        if is_new_task:
            form.instance.created_by = self.request.user
            # Статус по умолчанию устанавливается в модели

        # Сохраняем основную форму - TaskForm.save() теперь обрабатывает назначение ролей
        # commit=True сохраняет задачу и роли
        self.object = form.save(commit=True)
        logger.info(f"Task {self.object.id} {'created' if is_new_task else 'updated'} by user {self.request.user.username}.")


        # Сохраняем формсет фото, связанный с задачей
        photo_formset.instance = self.object
        photos = photo_formset.save(commit=False) # Получаем фото без сохранения в БД
        for photo in photos:
             # Устанавливаем загрузившего пользователя, если не установлен
             if not photo.uploaded_by_id:
                 photo.uploaded_by = self.request.user
             photo.save() # Сохраняем каждое фото

        # Обработка удаления фото, отмеченных в формсете
        for form_in_set in photo_formset.deleted_forms:
             if form_in_set.instance.pk: # Проверяем, что экземпляр существует (не был пустой доп. формой)
                 photo_pk = form_in_set.instance.pk
                 form_in_set.instance.delete()
                 logger.info(f"Deleted photo {photo_pk} for task {self.object.id}")

        # Вызов form_valid() из SuccessMessageMixin и затем из Create/UpdateView
        # SuccessMessageMixin покажет сообщение об успехе
        # Create/UpdateView обработают редирект
        return super().form_valid(form)

    def form_invalid(self, form):
        """Обрабатывает невалидную основную форму."""
        context = self.get_context_data() # Получаем контекст снова, чтобы включить возможно невалидный формсет
        photo_formset = context['photo_formset']
        logger.warning(f"Task form invalid. Form Errors: {form.errors}")
        # Если формсет фото также невалиден, убеждаемся, что он передан обратно в шаблон
        if not photo_formset.is_valid():
             context['photo_formset'] = photo_formset
             logger.warning(f"Photo formset invalid. Formset Errors: {photo_formset.errors}")

        # Базовый класс обработает рендеринг ответа с невалидной формой
        return super().form_invalid(form)

# ==============================================================================
# Task Create View
# ==============================================================================
class TaskCreateView(LoginRequiredMixin, SuccessMessageMixin, BaseTaskFormView, CreateView):
    """Представление для создания новой задачи."""
    success_url = reverse_lazy("tasks:task_list") # Куда перенаправить после успеха
    success_message = _("Задача '%(title)s' успешно создана!") # Сообщение для пользователя
    # permission_required = 'tasks.add_task' # Раскомментировать если используется PermissionRequiredMixin

    def get_context_data(self, **kwargs):
        """Добавляет заголовок и текст кнопки в контекст."""
        context = super().get_context_data(**kwargs)
        context['page_title'] = _("Создать Задачу")
        context['form_action'] = _("Создать") # Текст кнопки submit
        return context

    # form_valid и form_invalid обрабатываются в BaseTaskFormView и базовых классах

# ==============================================================================
# Task Update View
# ==============================================================================
class TaskUpdateView(LoginRequiredMixin, SuccessMessageMixin, BaseTaskFormView, UpdateView):
    """Представление для редактирования существующей задачи."""
    success_message = _("Задача '%(title)s' обновлена!")
    # permission_required = 'tasks.change_task'

    def get_success_url(self):
        """Возвращает на страницу деталей задачи после обновления."""
        return reverse_lazy('tasks:task_detail', kwargs={'pk': self.object.pk})

    def get_queryset(self):
        """Оптимизированный queryset для выбора задачи для редактирования."""
        return Task.objects.select_related(
            "project", "category", "subcategory", "created_by"
        ).prefetch_related('photos', 'user_roles__user')

    def get_object(self, queryset=None):
        """Проверяет права на редактирование перед возвратом объекта."""
        obj = super().get_object(queryset=queryset)
        if not obj.has_permission(self.request.user, 'change'):
            logger.warning(f"User {self.request.user.username} forbidden to change task {obj.id}")
            raise Http404(_("У вас нет прав на редактирование этой задачи."))
        return obj

    def get_context_data(self, **kwargs):
        """Добавляет заголовок и текст кнопки в контекст."""
        context = super().get_context_data(**kwargs)
        context['page_title'] = _("Редактировать Задачу: %s") % self.object.title
        context['form_action'] = _("Сохранить") # Текст кнопки submit
        return context

    # form_valid и form_invalid обрабатываются в BaseTaskFormView и базовых классах

# ==============================================================================
# Task Delete View
# ==============================================================================
class TaskDeleteView(LoginRequiredMixin, SuccessMessageMixin, DeleteView):
    """Представление для подтверждения и удаления задачи."""
    model = Task
    template_name = "tasks/task_confirm_delete.html" # Убедитесь, что шаблон существует
    success_url = reverse_lazy("tasks:task_list")
    success_message = _("Задача удалена!")
    # permission_required = 'tasks.delete_task'

    def get_object(self, queryset=None):
        """Проверяет права на удаление перед возвратом объекта."""
        obj = super().get_object(queryset=queryset)
        if not obj.has_permission(self.request.user, 'delete'):
            logger.warning(f"User {self.request.user.username} forbidden to delete task {obj.id}")
            raise Http404(_("У вас нет прав на удаление этой задачи."))
        return obj

    def get_context_data(self, **kwargs):
        """Добавляет заголовок в контекст."""
        context = super().get_context_data(**kwargs)
        context['page_title'] = _("Удалить Задачу: %s") % self.object.title
        return context

    # form_valid используется из SuccessMessageMixin и DeleteView для обработки POST и редиректа

# ==============================================================================
# Task Perform View (Example)
# ==============================================================================
class TaskPerformView(LoginRequiredMixin, DetailView):
    """
    Представление для 'выполнения' задачи (просмотр деталей в специфичном контексте).
    Может включать опции быстрой смены статуса.
    """
    model = Task
    template_name = "tasks/task_perform.html" # Нужен этот шаблон
    context_object_name = "task"

    def get_queryset(self):
        """Использует тот же оптимизированный queryset, что и TaskDetailView."""
        return Task.objects.select_related(
            "project", "category", "subcategory", "created_by"
        ).prefetch_related('photos', 'user_roles__user')

    def get_object(self, queryset=None):
        """Проверяет права на 'выполнение' (просмотр + смена статуса)."""
        obj = super().get_object(queryset=queryset)
        # Определяем, что значит "выполнять" с точки зрения прав
        can_view = obj.has_permission(self.request.user, 'view')
        can_change_status = obj.has_permission(self.request.user, 'change_status')

        if not (can_view and can_change_status): # Пример: нужно право и на просмотр, и на смену статуса
             logger.warning(f"User {self.request.user.username} forbidden to 'perform' task {obj.id} (view={can_view}, change_status={can_change_status})")
             raise Http404(_("Вы не имеете доступа к выполнению этой задачи."))
        return obj

    def get_context_data(self, **kwargs):
        """Добавляет специфичный контекст для выполнения."""
        context = super().get_context_data(**kwargs)
        context['page_title'] = f"{_('Выполнение задачи')}: {self.object.title}"
        # Добавляем контекст, специфичный для выполнения, например, доступные статусы
        context['allowed_statuses'] = [
             (key, label) for key, label in Task.StatusChoices.choices
             if key in [Task.StatusChoices.IN_PROGRESS, Task.StatusChoices.ON_HOLD, Task.StatusChoices.COMPLETED] # Пример доступных статусов для кнопок
        ]
        return context

