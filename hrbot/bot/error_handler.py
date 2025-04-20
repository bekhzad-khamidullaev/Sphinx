# hrbot/bot/error_handler.py

import logging
from django.utils.translation import gettext as _
from telegram import Update
from telegram.error import TelegramError
from telegram.ext import ContextTypes
from django.core.exceptions import SynchronousOnlyOperation, FieldError

# Импортируем хелперы
from .utils import reply_text, send_message

logger = logging.getLogger(__name__)

async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Логирует ошибки и сообщает пользователю."""
    logger.error("Exception while handling an update:", exc_info=context.error)

    if isinstance(context.error, SynchronousOnlyOperation):
         logger.critical("SynchronousOnlyOperation detected! Ensure DB access within async functions uses sync_to_async or preloading (e.g., select_related, prefetch_related).")
    elif isinstance(context.error, FieldError):
         logger.critical(f"FieldError detected: {context.error}. Check model field names used in select_related/prefetch_related.")
    elif isinstance(context.error, TelegramError):
         logger.warning(f"Telegram API Error: {context.error}")

    error_message = _("⚠️ Произошла внутренняя ошибка. Мы уже уведомлены и разбираемся. Пожалуйста, попробуйте позже или начните диалог заново с /start.")

    if isinstance(update, Update):
        try:
            if update.callback_query:
                 # Сначала отвечаем на callback, чтобы убрать "часики"
                 try: await update.callback_query.answer(_("Произошла ошибка!"), show_alert=True)
                 except Exception as answer_err: logger.warning(f"Could not answer callback query after error: {answer_err}")
                 # Затем отправляем сообщение в чат
                 if update.effective_chat and context: await send_message(context, update.effective_chat.id, error_message)
            elif update.effective_message: # Если есть сообщение (не callback)
                await reply_text(update, error_message)
            elif update.effective_chat and context: # Если нет сообщения, но есть чат
                await send_message(context, update.effective_chat.id, error_message)
            else: logger.error("Cannot send error message to user: No effective_message or effective_chat/context in Update object.")
        except Exception as e_reply: logger.exception(f"Failed to send error message to user after an error: {e_reply}")
    else: logger.warning(f"Cannot send error message to user for update of type {type(update)}")