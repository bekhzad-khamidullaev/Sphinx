# hrbot/signals.py

import logging
import requests
import json

from django.conf import settings
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.utils.translation import gettext as _
# Убираем импорты клавиатур, они больше не нужны в этом файле
# from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ParseMode

# Импортируем ТОЛЬКО модель, чтобы избежать циклических зависимостей
from .models import TelegramUser

logger = logging.getLogger(__name__)

# --- Константа для URL API Telegram ---
TELEGRAM_API_BASE_URL = "https://api.telegram.org/bot"

def send_telegram_message_sync(chat_id, text, reply_markup=None, parse_mode=None):
    """
    Синхронно отправляет сообщение через Telegram Bot API с использованием requests.
    """
    token = getattr(settings, 'TELEGRAM_BOT_TOKEN', None)
    if not token:
        logger.error("TELEGRAM_BOT_TOKEN not found in settings. Cannot send message.")
        return False

    api_url = f"{TELEGRAM_API_BASE_URL}{token}/sendMessage"
    payload = {
        'chat_id': chat_id,
        'text': text,
    }
    # --- УДАЛЕНО: обработка reply_markup, т.к. мы его не передаем ---
    # if reply_markup:
    #     try:
    #         payload['reply_markup'] = reply_markup.to_dict()
    #     except Exception as e:
    #         logger.exception(f"Error converting reply_markup to dict for chat_id {chat_id}: {e}")
    # -----------------------------------------------------------------
    if parse_mode:
        payload['parse_mode'] = parse_mode

    headers = {'Content-Type': 'application/json'}
    try:
        response = requests.post(api_url, json=payload, headers=headers, timeout=15)
        response.raise_for_status()
        result = response.json()
        if result.get('ok'):
            logger.info(f"Successfully sent message to chat_id {chat_id}")
            return True
        else:
            error_code = result.get('error_code')
            description = result.get('description')
            logger.error(f"Telegram API error sending to {chat_id}: Code {error_code} - {description}")
            if error_code == 403 and 'bot was blocked by the user' in description:
                 logger.warning(f"Bot was blocked by user with chat_id {chat_id}.")
            return False
    except requests.exceptions.Timeout:
        logger.warning(f"Timeout sending Telegram message to {chat_id} after 15 seconds.")
        return False
    except requests.exceptions.RequestException as e:
        logger.error(f"HTTP request error sending message to {chat_id}: {e}")
        return False
    except json.JSONDecodeError as e:
         logger.error(f"Error decoding JSON response from Telegram API for chat_id {chat_id}: {e}")
         return False
    except Exception as e:
        logger.exception(f"Unexpected error sending message to {chat_id}: {e}")
        return False


@receiver(post_save, sender=TelegramUser)
def notify_user_on_approval(sender, instance: TelegramUser, created, **kwargs):
    """
    Отправляет уведомление пользователю при первом подтверждении его аккаунта.
    """
    logger.info(f"[SIGNAL] post_save received for TGUser {instance.pk} (ID: {instance.telegram_id}), created={created}, approved={instance.approved}, notified={instance.notified_on_approval}")

    if created or not instance.approved or instance.notified_on_approval:
        logger.debug(f"[SIGNAL] Skipping notification for TGUser {instance.pk}. Conditions not met: created={created}, approved={instance.approved}, notified={instance.notified_on_approval}")
        return

    logger.info(f"TelegramUser {instance.telegram_id} approved. Sending notification.")

    # 1) Сообщаем об одобрении
    approval_message = _("✅ Ваш аккаунт подтвержден! Теперь вам доступны все функции бота.")
    sent_approval = send_telegram_message_sync(
        chat_id=instance.telegram_id,
        text=approval_message
    )

    if not sent_approval:
        logger.error(f"Failed to send approval notification to {instance.telegram_id}. Will not update flag or send prompt.")
        return

    # 2) Отправляем ПРИГЛАШЕНИЕ нажать /start (без кнопок)
    start_prompt_text = _("Пожалуйста, отправьте команду /start, чтобы начать работу или увидеть главное меню.")
    sent_prompt = send_telegram_message_sync(
        chat_id=instance.telegram_id,
        text=start_prompt_text
        # reply_markup и parse_mode убраны
    )

    if not sent_prompt:
         logger.warning(f"Successfully sent approval message, but failed to send start prompt to {instance.telegram_id}.")
         # Все равно обновляем флаг

    # 3) Обновляем флаг
    try:
        updated_count = TelegramUser.objects.filter(
            pk=instance.pk,
            notified_on_approval=False
        ).update(notified_on_approval=True)

        if updated_count > 0:
            logger.info(f"Marked TelegramUser {instance.telegram_id} as notified.")
        else:
            logger.warning(f"TelegramUser {instance.telegram_id} was already marked as notified before update.")
    except Exception as e:
        logger.exception(f"Failed to update notified_on_approval flag for {instance.telegram_id}: {e}")