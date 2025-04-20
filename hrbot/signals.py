# hrbot/signals.py

import logging
import requests
import json

from django.conf import settings
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.utils.translation import gettext as _  # уже возвращает str
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ParseMode

from .models import TelegramUser

logger = logging.getLogger(__name__)


def send_telegram_message_sync(chat_id, text, reply_markup=None, parse_mode=None):
    """
    Синхронно отправляет сообщение через Telegram Bot API с использованием requests.
    """
    token = getattr(settings, 'TELEGRAM_BOT_TOKEN', None)
    if not token:
        logger.error("TELEGRAM_BOT_TOKEN not found in settings. Cannot send message.")
        return False

    api_url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {
        'chat_id': chat_id,
        'text': text,
    }
    if reply_markup:
        # Здесь передаем уже готовый словарь, requests сам сделает JSON-encode
        payload['reply_markup'] = reply_markup.to_dict()
    if parse_mode:
        payload['parse_mode'] = parse_mode

    headers = {'Content-Type': 'application/json; charset=utf-8'}
    try:
        # Преобразуем в JSON-строку, чтобы гарантировать utf-8
        data = json.dumps(payload, ensure_ascii=False).encode('utf-8')
        response = requests.post(api_url, data=data, headers=headers, timeout=10)
        response.raise_for_status()
        result = response.json()
        if result.get('ok'):
            logger.info(f"Successfully sent message to chat_id {chat_id}")
            return True
        else:
            logger.error(f"Telegram API error sending to {chat_id}: {result.get('description')}")
            return False
    except requests.Timeout:
        logger.warning(f"Timeout sending Telegram message to {chat_id}")
        return False
    except requests.RequestException as e:
        logger.error(f"HTTP request error sending message to {chat_id}: {e}")
        return False
    except Exception as e:
        logger.exception(f"Unexpected error sending message to {chat_id}: {e}")
        return False


@receiver(post_save, sender=TelegramUser)
def notify_user_on_approval(sender, instance, created, **kwargs):
    """
    Отправляет уведомление пользователю при первом подтверждении его аккаунта.
    """
    # Если только создан, или не approved, или уже уведомляли — пропускаем
    if created or not instance.approved or instance.notified_on_approval:
        return

    logger.info(f"TelegramUser {instance.telegram_id} approved. Sending notification.")

    # 1) Сообщаем об одобрении
    approval_text = _("✅ Ваш аккаунт подтвержден! Теперь доступны все функции бота. Нажмите для продолжения /start")
    if not send_telegram_message_sync(
        chat_id=instance.telegram_id,
        text=approval_text
    ):
        logger.error(f"Failed to send approval notification to {instance.telegram_id}.")
        return

    # 2) Отправляем главное меню
    kb_data = [
        [InlineKeyboardButton(_("Начать"), callback_data="/start")],
    ]

    # Собираем InlineKeyboardButton
    buttons = [
        [InlineKeyboardButton(item["text"], callback_data=item["callback_data"]) for item in row]
        for row in kb_data
    ]
    menu_text = _("👋 *Главное меню*\nВыберите действие:")

    if not send_telegram_message_sync(
        chat_id=instance.telegram_id,
        text=menu_text,
        reply_markup=InlineKeyboardMarkup(buttons),
        parse_mode=ParseMode.MARKDOWN
    ):
        logger.warning(f"Failed to send main menu to {instance.telegram_id} after approval.")

    # 3) Отмечаем, что уведомление отправлено
    try:
        TelegramUser.objects.filter(pk=instance.pk).update(notified_on_approval=True)
        logger.info(f"Marked TelegramUser {instance.telegram_id} as notified.")
    except Exception as e:
        logger.exception(f"Failed to update notified_on_approval for {instance.telegram_id}: {e}")
