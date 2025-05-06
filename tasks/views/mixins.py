# tasks/views/mixins.py
import logging
from django.contrib import messages
from django.utils.translation import gettext_lazy as _
from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from django.contrib.messages.views import SuccessMessageMixin as DjangoSuccessMessageMixin
from django.views.generic.edit import DeleteView

logger = logging.getLogger(__name__)

# --- WebSocket Mixin (Remains the same) ---
class WebSocketNotificationMixin:
    """Mixin for sending WebSocket notifications."""
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

# --- Customized Success Message Mixin ---
class SuccessMessageMixin(DjangoSuccessMessageMixin):
    """
    A customized SuccessMessageMixin that attempts default formatting
    but provides a fallback if a KeyError or other formatting error occurs.

    For DeleteView, it's strongly recommended to set the success message manually
    in the view's form_valid method AFTER calling super().form_valid(form),
    as cleaned_data is not applicable and self.object is deleted during super().
    """
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

    # --- REFINED Important Note on DeleteView ---
    # This mixin's `get_success_message` method relies on `cleaned_data`, which `DeleteView` lacks.
    # Furthermore, `DeleteView.form_valid` calls `self.object.delete()`.
    #
    # THEREFORE, for DeleteView:
    # 1. Capture necessary object info BEFORE calling super().form_valid().
    # 2. Call super().form_valid() to perform the deletion.
    # 3. Use django.contrib.messages.success() AFTER super() returns, using the captured info.
    #
    # Example DeleteView Implementation:
    #
    # from django.contrib import messages
    # from django.views.generic.edit import DeleteView
    # # No need to inherit SuccessMessageMixin for DeleteView
    #
    # class MyModelDeleteView(LoginRequiredMixin, DeleteView):
    #     model = MyModel
    #     template_name = 'confirm_delete.html'
    #     success_url = reverse_lazy('my_list_view')
    #
    #     def form_valid(self, form):
    #         # --- Step 1: Capture info BEFORE deletion ---
    #         object_repr = str(self.object) # Or self.object.name, self.object.pk etc.
    #
    #         # --- Step 2: Perform the deletion ---
    #         # This calls self.object.delete() internally
    #         response = super().form_valid(form)
    #
    #         # --- Step 3: Add success message AFTER deletion, using captured info ---
    #         messages.success(
    #              self.request,
    #              _("Объект '%(name)s' был успешно удален.") % {'name': object_repr}
    #         )
    #         return response
    #