# tasks/views/subcategory.py
from django.contrib.auth.mixins import LoginRequiredMixin
from django.urls import reverse_lazy
from django.utils.translation import gettext_lazy as _
from django.views.generic import CreateView, UpdateView, DeleteView, DetailView
from django_filters.views import FilterView # Используем FilterView для ListView с фильтрацией
from django.contrib import messages
from django.db.models import Count
from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
import logging


from ..models import TaskSubcategory
from ..forms import TaskSubcategoryForm
from ..filters import TaskSubcategoryFilter
from .mixins import SuccessMessageMixin, WebSocketNotificationMixin


logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class TaskSubcategoryListView(LoginRequiredMixin, FilterView): # Заменяем ListView на FilterView
    model = TaskSubcategory
    queryset = TaskSubcategory.objects.select_related('category').annotate(
        task_count=Count('tasks')
    ).order_by('category__name', 'name')
    template_name = "tasks/subcategory_list.html" # Убедитесь, что шаблон существует
    context_object_name = "subcategories" # Имя для списка в шаблоне
    paginate_by = 20
    filterset_class = TaskSubcategoryFilter # Указываем класс фильтра

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        # FilterView передает filterset в контекст под именем 'filter'
        # Мы можем переименовать его для консистентности, если хотим:
        # context['filterset'] = context.get('filter')
        context['page_title'] = _("Подкатегории Задач")
        context['ws_group_name'] = 'subcategories_list'
        return context

class TaskSubcategoryDetailView(LoginRequiredMixin, DetailView):
    model = TaskSubcategory
    template_name = "tasks/subcategory_detail.html" # Убедитесь, что шаблон существует
    context_object_name = "subcategory"

    def get_queryset(self):
        return super().get_queryset().select_related('category').prefetch_related('tasks')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        subcategory = self.object
        context["page_title"] = _("Подкатегория: %(name)s (Категория: %(cat_name)s)") % {
            'name': subcategory.name,
            'cat_name': subcategory.category.name
        }
        context['tasks_in_subcategory_count'] = subcategory.tasks.count()
        context['ws_group_name'] = f'subcategory_{subcategory.id}'
        return context

class TaskSubcategoryCreateView(LoginRequiredMixin, SuccessMessageMixin, WebSocketNotificationMixin, CreateView):
    model = TaskSubcategory
    form_class = TaskSubcategoryForm
    template_name = "tasks/subcategory_form.html" # Убедитесь, что шаблон существует
    success_url = reverse_lazy("tasks:subcategory_list")
    success_message = _("Подкатегория '%(name)s' (категория: '%(category)s') успешно создана!")
    
    ws_group_name = "subcategories_list"
    ws_event_type = "subcategory_update"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['page_title'] = _("Создать Подкатегорию")
        context['form_action_label'] = _("Создать")
        return context

    def form_valid(self, form):
        # `self.object` будет установлен после `super().form_valid(form)`
        # Для `success_message` нужно, чтобы `self.object.category` было доступно.
        # Важно, чтобы `ForeignKey` `category` был уже установлен.
        response = super().form_valid(form)
        self.send_ws_notification(action="create", instance=self.object)
        return response
    
    def get_success_message(self, cleaned_data):
        # Переопределяем, чтобы включить имя категории в сообщение
        return self.success_message % {
            'name': self.object.name,
            'category': self.object.category.name
        }


class TaskSubcategoryUpdateView(LoginRequiredMixin, SuccessMessageMixin, WebSocketNotificationMixin, UpdateView):
    model = TaskSubcategory
    form_class = TaskSubcategoryForm
    template_name = "tasks/subcategory_form.html"
    success_url = reverse_lazy("tasks:subcategory_list")
    success_message = _("Подкатегория '%(name)s' (категория: '%(category)s') успешно обновлена!")
    context_object_name = 'subcategory'

    ws_event_type = "subcategory_update"
    
    def get_ws_group_name(self):
        return "subcategories_list"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['page_title'] = _("Редактировать Подкатегорию: %(name)s") % {'name': self.object.name}
        context['form_action_label'] = _("Сохранить")
        return context

    def form_valid(self, form):
        response = super().form_valid(form)
        self.send_ws_notification(action="update", instance=self.object)
        return response

    def get_success_message(self, cleaned_data):
        return self.success_message % {
            'name': self.object.name,
            'category': self.object.category.name
        }

class TaskSubcategoryDeleteView(LoginRequiredMixin, DeleteView):
    model = TaskSubcategory
    template_name = "tasks/subcategory_confirm_delete.html" # Убедитесь, что шаблон существует
    success_url = reverse_lazy("tasks:subcategory_list")
    context_object_name = 'subcategory'

    ws_group_name_on_delete = "subcategories_list"
    ws_event_type_on_delete = "subcategory_update"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['page_title'] = _("Удалить Подкатегорию: %(name)s") % {'name': self.object.name}
        return context

    def form_valid(self, form):
        subcategory_name = self.object.name
        subcategory_id = self.object.id
        category_name = self.object.category.name # Сохраняем для сообщения

        response = super().form_valid(form)
        messages.success(self.request, _("Подкатегория '%(name)s' (из категории '%(cat_name)s') удалена!") % {
            'name': subcategory_name, 'cat_name': category_name
        })
        
        try:
            channel_layer = get_channel_layer()
            if channel_layer:
                async_to_sync(channel_layer.group_send)(
                    self.ws_group_name_on_delete,
                    {"type": self.ws_event_type_on_delete,
                     "message": {"action": "delete", "model": "tasksubcategory", "id": subcategory_id}}
                )
        except Exception as e:
            logger.error(f"Failed sending WS delete notification for TaskSubcategory ID {subcategory_id}: {e}")
        return response