# hrbot/bot/handlers/search.py
import logging
from django.utils.translation import gettext as _
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ParseMode
from telegram.error import BadRequest, NetworkError, TimedOut
from telegram.ext import ContextTypes, ConversationHandler

from ..constants import SEARCH_INPUT, SEARCH_RESULTS, CB_MAIN, CB_SEARCH_RES, CB_NOOP
from ..db import search_users, fetch_user_by_id
from ..utils import reply_text, edit_message_text, send_user_profile
from .common import start # Импортируем start для возврата в меню

logger = logging.getLogger(__name__)

async def search_input_msg(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Обрабатывает ввод текста для поиска сотрудника."""
    if not update.message or not update.message.text: await reply_text(update, _("⚠️ Пожалуйста, введите запрос для поиска текстом.")); return SEARCH_INPUT
    user_id = str(update.effective_user.id); q = update.message.text.strip()
    logger.info(f"User {user_id} submitted search query: '{q}'")
    if not q: await reply_text(update, _("⚠️ Запрос не может быть пустым. Введите имя, фамилию, телефон или email:")); return SEARCH_INPUT
    if len(q) < 3: await reply_text(update, _("⚠️ Запрос слишком короткий (минимум 3 символа).")); return SEARCH_INPUT
    try:
        users = await search_users(q)
        if not users: logger.info(f"No users found for query '{q}' by user {user_id}."); await reply_text(update, _("❌ По вашему запросу '{query}' совпадений не найдено.\nПопробуйте другой запрос или вернитесь в /start.").format(query=q)); return SEARCH_INPUT
        logger.info(f"Found {len(users)} user(s) for query '{q}' by user {user_id}.")
        context.user_data["search_res_names"] = {str(u.id): u.get_full_name() for u in users}
        context.user_data["search_res_users"] = {str(u.id): u for u in users}
        buttons = [ [InlineKeyboardButton(name, callback_data=f"{CB_SEARCH_RES}:{uid}")] for uid, name in list(context.user_data["search_res_names"].items())[:15] ] + [[InlineKeyboardButton(_("🔄 Новый поиск"), callback_data=f"{CB_MAIN}:search_emp")], [InlineKeyboardButton(_("🔙 Главное меню"), callback_data=f"{CB_MAIN}:back_main")]]
        if len(users) > 15: buttons.insert(-1, [InlineKeyboardButton(_("... (еще результаты)"), callback_data=CB_NOOP)])
        await reply_text(update, _("🔍 *Результаты поиска по запросу '{query}'* ({count} найдено):").format(query=q, count=len(users)), reply_markup=InlineKeyboardMarkup(buttons), parse_mode=ParseMode.MARKDOWN)
        return SEARCH_RESULTS
    except (NetworkError, TimedOut) as e: logger.warning(f"Network error during user search for user {user_id}: {e}"); await reply_text(update, _("⚠️ Ошибка сети во время поиска. Пожалуйста, попробуйте еще раз.")); return SEARCH_INPUT
    except Exception as e: logger.exception(f"Unexpected error during search_input_msg for query '{q}' by user {user_id}: {e}"); await reply_text(update, _("⚠️ Внутренняя ошибка сервера во время поиска. Попробуйте /start")); return ConversationHandler.END


async def search_results_cb(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Показывает профиль сотрудника, выбранного из результатов поиска."""
    if not update.callback_query or not update.callback_query.data: return SEARCH_RESULTS
    cq = update.callback_query; user_id = str(update.effective_user.id)
    logger.info(f"SEARCH_RESULTS callback '{cq.data}' from user {user_id}")
    try:
        try: await cq.answer()
        except BadRequest: pass
        parts = cq.data.split(":", 1)
        if len(parts) != 2 or not parts[1].isdigit(): raise ValueError(f"Invalid callback data format: {cq.data}")
        uid_str = parts[1]; search_res_users = context.user_data.get("search_res_users", {})
        user = search_res_users.get(uid_str)
        if not user:
            logger.error(f"User {uid_str} was in search results but not found in user_data cache for user {user_id}. Fetching from DB.")
            user = await fetch_user_by_id(int(uid_str))
            if not user: logger.error(f"Failed to fetch user {uid_str} from DB in search_results_cb."); await reply_text(update, _("❌ Ошибка: Не удалось загрузить данные выбранного сотрудника.")); return SEARCH_RESULTS
        logger.debug(f"User {user_id} selected user {uid_str} from search results.")
        await send_user_profile(cq.message, user)
        return SEARCH_RESULTS
    except (ValueError, IndexError, KeyError) as e: logger.warning(f"Invalid data or state in search_results_cb: {cq.data} ({e})"); await reply_text(update, _("⚠️ Ошибка данных при выборе результата поиска.")); return SEARCH_RESULTS
    except Exception as e: logger.exception(f"Unexpected error in search_results_cb: {e}"); await reply_text(update, _("⚠️ Внутренняя ошибка при показе профиля.")); return SEARCH_RESULTS