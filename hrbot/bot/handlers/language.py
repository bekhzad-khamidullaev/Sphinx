# hrbot/bot/handlers/language.py
import logging
from django.conf import settings
from django.utils.translation import gettext as _
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ParseMode
from telegram.error import BadRequest, NetworkError, TimedOut
from telegram.ext import ContextTypes, ConversationHandler

from ..constants import LANG_MENU, CB_LANG, CB_MAIN
from ..db import get_or_create_tguser, set_user_setting
from ..utils import reply_text, edit_message_text
from .common import start # Импортируем start для возврата в меню

logger = logging.getLogger(__name__)

async def lang_menu_cb(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Обрабатывает выбор языка интерфейса."""
    if not update.callback_query or not update.callback_query.data: return LANG_MENU
    cq = update.callback_query; user_id = str(update.effective_user.id)
    logger.info(f"LANG_MENU callback '{cq.data}' from user {user_id}")
    try:
        try: await cq.answer()
        except BadRequest: pass
        parts = cq.data.split(":", 1)
        if len(parts) != 2: raise ValueError("Invalid callback data format")
        code = parts[1]; supported_langs = dict(settings.LANGUAGES)
        if code not in supported_langs: logger.warning(f"User {user_id} selected unsupported language code: {code}"); await edit_message_text(cq.message, _("⚠️ Выбран неподдерживаемый язык.")); return LANG_MENU
        logger.debug(f"User {user_id} selected language '{code}'."); tg = await get_or_create_tguser(user_id)
        if not tg or not tg.user: logger.error(f"Cannot find user profile for {user_id} to save language setting."); await edit_message_text(cq.message, _("❌ Ошибка: не удалось найти ваш профиль для сохранения языка.")); return ConversationHandler.END
        if await set_user_setting(tg.user, "language_code", code): lang_name = supported_langs.get(code, code); await edit_message_text(cq.message, _("✅ Язык интерфейса изменён на *{lang}*.").format(lang=lang_name), parse_mode=ParseMode.MARKDOWN)
        else: await edit_message_text(cq.message, _("❌ Не удалось сохранить настройку языка (ошибка сервера)."))
        return await start(update, context)
    except (ValueError, IndexError) as e: logger.warning(f"Invalid callback data in lang_menu_cb: {cq.data} ({e})"); await edit_message_text(cq.message, _("⚠️ Некорректный выбор языка.")); return LANG_MENU
    except (BadRequest, NetworkError, TimedOut) as e: logger.warning(f"Network/API error in lang_menu_cb: {e}"); await reply_text(update, _("⚠️ Ошибка сети или API. Попробуйте выбрать язык снова.")); return LANG_MENU
    except Exception as e: logger.exception(f"Unexpected error in lang_menu_cb: {e}"); await reply_text(update, _("⚠️ Внутренняя ошибка. Попробуйте /start")); return ConversationHandler.END