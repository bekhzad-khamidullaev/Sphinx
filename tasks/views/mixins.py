# tasks/views/mixins.py
import logging
from django.contrib import messages
from django.utils.translation import gettext_lazy as _
from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from django.contrib.messages.views import SuccessMessageMixin as DjangoSuccessMessageMixin
from django.views.generic.edit import DeleteView # Для примера в комментарии

logger = logging.getLogger(__name__)

class WebSocketNotificationMixin:
    """
    Миксин для отправки WebSocket уведомлений.
    Требует определения `ws_group_name` (имя группы) и
    `ws_event_type` (тип события для consumer) в классе представления.
    """
    ws_group_name = None  # e.g., "tasks_list", f"task_{self.object.id}"
    ws_event_type = "model_update_event"  # e.g., "task_update", "list_update"

    def get_ws_group_name(self):
        """Позволяет динамически определять имя группы, например, на основе объекта."""
        if callable(self.ws_group_name):
            return self.ws_group_name()
        return self.ws_group_name

    def get_ws_event_type(self):
        """Позволяет динамически определять тип события."""
        if callable(self.ws_event_type):
            return self.ws_event_type()
        return self.ws_event_type
    
    def get_ws_message_data(self, action, instance):
        """
        Формирует стандартное сообщение для WebSocket.
        Может быть переопределен в дочерних классах для специфичных данных.
        `action` может быть "create", "update", "delete".
        `instance` - это сохраненный или удаляемый объект.
        """
        return {
            "action": action,
            "model": instance.__class__.__name__.lower(),
            "id": instance.pk,
            # Можно добавить другие общие поля, например, 'name' или 'title', если они есть у большинства моделей
            "display_name": str(instance)
        }

    def send_ws_notification(self, action, instance):
        group_name = self.get_ws_group_name()
        event_type = self.get_ws_event_type()
        
        if group_name and event_type:
            message_data = self.get_ws_message_data(action, instance)
            try:
                channel_layer = get_channel_layer()
                if channel_layer is not None:
                    async_to_sync(channel_layer.group_send)(
                        group_name,
                        {"type": event_type, "message": message_data}
                    )
                    logger.debug(f"WS notification sent to group '{group_name}' (type: '{event_type}'): {message_data}")
                else:
                    logger.error("Channel layer is not configured or available for WebSocket notifications.")
            except Exception as e:
                 logger.error(f"Failed sending WS notification to group '{group_name}': {e}")
        else:
            logger.warning(f"ws_group_name ('{group_name}') or ws_event_type ('{event_type}') not defined for {self.__class__.__name__}")

class SuccessMessageMixin(DjangoSuccessMessageMixin):
    """
    Кастомизированный SuccessMessageMixin.
    Для DeleteView рекомендуется устанавливать success_message вручную в form_valid,
    так как cleaned_data отсутствует, а self.object удаляется до вызова get_success_message.
    """
    success_message = "" # Должно быть установлено в классе представления

    def get_success_message(self, cleaned_data):
        message_template = self.success_message
        if not message_template:
            logger.warning(f"SuccessMessageMixin used in {self.__class__.__name__} but 'success_message' attribute is empty.")
            return _("Действие выполнено успешно.") # Общее сообщение по умолчанию

        # Для CreateView и UpdateView, self.object доступен после super().form_valid()
        # и может использоваться для форматирования сообщения.
        context = cleaned_data.copy() # Начинаем с cleaned_data
        if hasattr(self, 'object') and self.object:
            # Добавляем атрибуты объекта в контекст для форматирования,
            # это позволяет использовать %(name)s, %(id)s и т.д. из объекта.
            for field in self.object._meta.fields:
                if field.name not in context: # Не перезаписываем ключи из cleaned_data
                    try:
                        context[field.name] = getattr(self.object, field.name)
                    except AttributeError:
                        pass # Поле может не иметь значения или быть связью

            # Добавляем PK отдельно, если он не является частью fields (например, для auto-полей)
            if 'pk' not in context and hasattr(self.object, 'pk'): context['pk'] = self.object.pk
            if 'id' not in context and hasattr(self.object, 'id'): context['id'] = self.object.id
            # Добавляем строковое представление объекта
            if 'object_str' not in context: context['object_str'] = str(self.object)


        try:
            message = message_template % context
            return message
        except (KeyError, ValueError, TypeError) as e:
            logger.warning(
                f"Could not fully format success_message '{message_template}' "
                f"in view {self.__class__.__name__} using context derived from cleaned_data and object. "
                f"Error: {e}. Keys available: {list(context.keys())}. Falling back to unformatted or partially formatted message."
            )
            # Попытка отформатировать только с тем, что доступно, или вернуть шаблон
            try:
                # Попытка частичного форматирования с доступными ключами, если '%(' есть в строке
                # Это сложная задача, проще вернуть шаблон или общее сообщение
                return message_template # Возвращаем исходный шаблон, если форматирование не удалось
            except:
                return _("Действие выполнено успешно.") # Крайний случай
        except Exception as e:
            logger.exception(f"Unexpected error formatting success_message in {self.__class__.__name__}: {e}")
            return _("Действие выполнено успешно.")

    # Важное примечание для DeleteView остается актуальным:
    # Для DeleteView:
    # 1. Получите нужную информацию из self.object ПЕРЕД вызовом super().form_valid().
    # 2. Вызовите super().form_valid() для выполнения удаления.
    # 3. Используйте django.contrib.messages.success() ПОСЛЕ super(), используя сохраненную информацию.
    #
    # class MyModelDeleteView(LoginRequiredMixin, DeleteView): # НЕ наследуем SuccessMessageMixin
    #     # ...
    #     def form_valid(self, form):
    #         object_repr = str(self.object)
    #         response = super().form_valid(form)
    #         messages.success(self.request, _("Объект '%(name)s' был успешно удален.") % {'name': object_repr})
    #         return response