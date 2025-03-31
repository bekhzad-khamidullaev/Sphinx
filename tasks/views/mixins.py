# tasks/views/mixins.py
import logging
from django.contrib import messages
from django.utils.translation import gettext_lazy as _
from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer

logger = logging.getLogger(__name__)
channel_layer = get_channel_layer()

class WebSocketNotificationMixin:
    """Миксин для отправки уведомлений через WebSocket."""
    ws_group_name = None
    ws_event_type = "updateData"

    def send_ws_notification(self, message_data):
        """Отправляет уведомление в группу WebSocket."""
        if self.ws_group_name:
            async_to_sync(channel_layer.group_send)(
                self.ws_group_name,
                {"type": self.ws_event_type, "message": message_data}
            )
        else:
            logger.warning(f"ws_group_name не определено для {self.__class__.__name__}")

class SuccessMessageMixin:
    """Миксин для добавления сообщений об успешном выполнении."""
    success_message = None

    def form_valid(self, form):
        # Сохраняем cleaned_data перед вызовом super, т.к. объект может измениться
        cleaned_data = getattr(form, 'cleaned_data', {})
        response = super().form_valid(form)
        if self.success_message:
            # Пытаемся форматировать сообщение, если есть данные
            try:
                message = self.success_message % cleaned_data
            except (TypeError, KeyError):
                 # Если форматирование не удалось (например, в DeleteView нет cleaned_data)
                 # Берем текст до первого знака форматирования или всё сообщение
                 message = self.success_message.split('%', 1)[0] if '%' in self.success_message else self.success_message
            messages.success(self.request, message)
        return response