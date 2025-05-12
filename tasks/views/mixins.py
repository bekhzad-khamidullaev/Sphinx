import logging
from django.contrib import messages
from django.utils.translation import gettext_lazy as _
from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from django.contrib.messages.views import SuccessMessageMixin as DjangoSuccessMessageMixin

logger = logging.getLogger(__name__)

class WebSocketNotificationMixin:
    ws_group_name = None
    ws_event_type = "model_update_event"

    def send_ws_notification(self, message_data):
        if self.ws_group_name:
            try:
                channel_layer = get_channel_layer()
                if channel_layer is not None:
                    async_to_sync(channel_layer.group_send)(
                        self.ws_group_name,
                        {"type": self.ws_event_type, "message": message_data}
                    )
                    logger.debug(f"WS notification sent to {self.ws_group_name} (type: {self.ws_event_type}): {message_data}")
                else:
                    logger.error("Channel layer is not configured or available.")
            except Exception as e:
                 logger.error(f"Failed sending WS notification to {self.ws_group_name}: {e}")
        else:
            logger.warning(f"ws_group_name not defined for {self.__class__.__name__}")

class SuccessMessageMixin(DjangoSuccessMessageMixin):
    success_message = ""

    def get_success_message(self, cleaned_data):
        message_template = self.success_message
        if not message_template:
            logger.warning(f"SuccessMessageMixin used in {self.__class__.__name__} but 'success_message' attribute is empty.")
            return _("Действие выполнено успешно.")
        try:
            message = message_template % cleaned_data
            return message
        except (KeyError, ValueError, TypeError) as e:
            logger.warning(
                f"Could not format success_message '{message_template}' "
                f"in view {self.__class__.__name__} using cleaned_data keys {list(cleaned_data.keys())}. "
                f"Error: {e}. Falling back to unformatted message."
            )
            return message_template
        except Exception as e:
            logger.exception(f"Unexpected error formatting success_message in {self.__class__.__name__}: {e}")
            return _("Действие выполнено успешно.")