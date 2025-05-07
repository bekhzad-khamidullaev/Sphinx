# tasks/views/project.py
from django.contrib.auth.mixins import LoginRequiredMixin
from django.urls import reverse_lazy
from django.utils.translation import gettext_lazy as _
from django.views.generic import ListView, CreateView, UpdateView, DeleteView, DetailView
from django.contrib import messages
from django.db.models import Count # Для аннотации
import logging

from ..models import Project
from ..forms import ProjectForm
from ..filters import ProjectFilter
from .mixins import SuccessMessageMixin, WebSocketNotificationMixin # Подключаем миксины


logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class ProjectListView(LoginRequiredMixin, ListView):
    model = Project
    template_name = 'tasks/project_list.html' # Убедитесь, что шаблон существует
    context_object_name = 'projects' # Более понятное имя контекста
    paginate_by = 15

    def get_queryset(self):
        # Аннотируем количество задач для каждого проекта
        queryset = super().get_queryset().annotate(task_count=Count('tasks')).prefetch_related('tasks')
        self.filterset = ProjectFilter(self.request.GET, queryset=queryset, request=self.request)
        return self.filterset.qs.distinct().order_by('-created_at') # Сортировка по умолчанию

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['filterset'] = self.filterset
        context['page_title'] = _('Проекты')
        # Для real-time обновлений списка через WebSocket
        context['ws_group_name'] = 'projects_list'
        return context

class ProjectDetailView(LoginRequiredMixin, DetailView):
    model = Project
    template_name = "tasks/project_detail.html" # Убедитесь, что шаблон существует
    context_object_name = "project"

    def get_queryset(self):
        # Оптимизируем запрос, подгружая связанные задачи
        return super().get_queryset().prefetch_related('tasks__category', 'tasks__subcategory', 'tasks__created_by')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        project = self.object
        context["page_title"] = _("Проект: %(name)s") % {'name': project.name}
        # Можно передать задачи проекта в контекст, если они нужны на детальной странице
        # context['tasks_in_project'] = project.tasks.all()[:20] # Пример: первые 20 задач
        
        # Для real-time обновлений деталей проекта через WebSocket
        context['ws_group_name'] = f'project_{project.id}' # Группа для конкретного проекта
        return context

class ProjectCreateView(LoginRequiredMixin, SuccessMessageMixin, WebSocketNotificationMixin, CreateView):
    model = Project
    form_class = ProjectForm
    template_name = 'tasks/project_form.html' # Убедитесь, что шаблон существует
    success_url = reverse_lazy('tasks:project_list')
    success_message = _("Проект '%(name)s' успешно создан.")
    
    # WebSocketNotificationMixin settings
    ws_group_name = "projects_list" # Обновляем общий список проектов
    ws_event_type = "project_update" # Тип события для консьюмера

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['page_title'] = _('Создание нового проекта')
        context['form_action_label'] = _('Создать проект')
        return context

    def form_valid(self, form):
        response = super().form_valid(form)
        # self.object здесь уже сохраненный экземпляр проекта
        self.send_ws_notification(action="create", instance=self.object)
        return response

class ProjectUpdateView(LoginRequiredMixin, SuccessMessageMixin, WebSocketNotificationMixin, UpdateView):
    model = Project
    form_class = ProjectForm
    template_name = 'tasks/project_form.html'
    success_url = reverse_lazy('tasks:project_list')
    success_message = _("Проект '%(name)s' успешно обновлен.")
    context_object_name = 'project'

    # WebSocketNotificationMixin settings
    ws_event_type = "project_update"

    def get_ws_group_name(self): # Динамическое имя группы
        # Обновляем и общий список, и конкретный проект (если кто-то его смотрит)
        # Это потребует от консьюмера обрабатывать сообщения в разных группах
        # или отправлять в несколько групп. Проще пока только общий список.
        # return f"project_{self.object.id}" # Для деталей
        return "projects_list" # Для списка

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['page_title'] = _('Редактирование проекта: %(name)s') % {'name': self.object.name}
        context['form_action_label'] = _('Сохранить изменения')
        return context

    def form_valid(self, form):
        response = super().form_valid(form)
        self.send_ws_notification(action="update", instance=self.object)
        # Если нужно отправлять и в группу деталей:
        # self.send_ws_notification(action="update", instance=self.object, group_name=f"project_{self.object.id}")
        return response

class ProjectDeleteView(LoginRequiredMixin, DeleteView): # WebSocketNotificationMixin обрабатывается вручную
    model = Project
    template_name = 'tasks/project_confirm_delete.html' # Убедитесь, что шаблон существует
    success_url = reverse_lazy('tasks:project_list')
    context_object_name = 'project'

    # ws_group_name и ws_event_type для ручной отправки
    ws_group_name_on_delete = "projects_list"
    ws_event_type_on_delete = "project_update"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['page_title'] = _('Удаление проекта: %(name)s') % {'name': self.object.name}
        return context

    def form_valid(self, form):
        project_name = self.object.name
        project_id = self.object.id # Сохраняем ID до удаления
        
        response = super().form_valid(form) # Проект удаляется здесь
        
        messages.success(self.request, _("Проект '%(name)s' был успешно удален.") % {'name': project_name})
        
        # Ручная отправка WebSocket уведомления
        # Создаем "фиктивный" объект или используем данные до удаления
        # Здесь мы не можем передать self.object, т.к. он уже удален
        # Вместо этого передадим словарь с необходимой информацией.
        deleted_instance_info = {"id": project_id, "name": project_name, "__class__": {"__name__": "Project"}}

        # Используем временный экземпляр миксина для отправки
        ws_mixin = WebSocketNotificationMixin()
        ws_mixin.ws_group_name = self.ws_group_name_on_delete
        ws_mixin.ws_event_type = self.ws_event_type_on_delete
        
        # Адаптируем get_ws_message_data, если он ожидает реальный instance
        # Проще передать словарь напрямую в `send_ws_notification` если он это поддерживает,
        # или создать кастомный метод в миксине для таких случаев.
        # В текущей реализации `get_ws_message_data` ожидает instance.
        # Можно передать словарь, который имитирует instance для get_ws_message_data:
        class DeletedProjectStub:
            def __init__(self, pk, name):
                self.pk = pk
                self.name = name
            def __str__(self): return self.name
            class _meta: model_name = "project" # Для get_ws_message_data


        # ws_mixin.send_ws_notification(action="delete", instance=DeletedProjectStub(project_id, project_name))
        # ИЛИ, если модель Project имеет `project_update` как consumer method:
        try:
            channel_layer = get_channel_layer()
            if channel_layer:
                async_to_sync(channel_layer.group_send)(
                    self.ws_group_name_on_delete,
                    {
                        "type": self.ws_event_type_on_delete, # e.g., "project_update"
                        "message": {"action": "delete", "model": "project", "id": project_id}
                    }
                )
                logger.debug(f"WS delete notification sent for Project ID {project_id}")
        except Exception as e:
            logger.error(f"Failed sending WS delete notification for Project ID {project_id}: {e}")

        return response