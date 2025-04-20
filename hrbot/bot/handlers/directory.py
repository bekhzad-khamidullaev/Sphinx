# hrbot/bot/handlers/directory.py
import logging
from django.utils.translation import gettext as _
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ParseMode
from telegram.error import BadRequest, NetworkError, TimedOut
from telegram.ext import ContextTypes, ConversationHandler

from ..constants import DEPT_LIST, DEPT_EMP_LIST, EMP_LIST, CB_MAIN, CB_DEPT, CB_DEPT_EMP, CB_USER, CB_NOOP
from ..db import all_departments, users_in_dept, fetch_user_by_id
from ..utils import reply_text, edit_message_text, send_user_profile
from .common import start # Импортируем start для возврата в меню

logger = logging.getLogger(__name__)

async def dept_cb(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Обрабатывает выбор отдела для просмотра сотрудников."""
    if not update.callback_query or not update.callback_query.data: return DEPT_LIST
    cq = update.callback_query; user_id = str(update.effective_user.id)
    logger.info(f"DEPT_LIST callback '{cq.data}' from user {user_id}")
    try:
        try: await cq.answer()
        except BadRequest: pass
        parts = cq.data.split(":", 1)
        if len(parts) != 2 or not parts[1].isdigit(): raise ValueError(f"Invalid callback data format: {cq.data}")
        did = int(parts[1]); context.user_data["current_dept_id"] = did
        dept_name = context.user_data.get("dept_list", {}).get(str(did), f"ID {did}")
        logger.debug(f"User {user_id} selected department {did} ('{dept_name}') for viewing.")
        users = await users_in_dept(did)
        if not users:
            logger.warning(f"No users found in department {did}.")
            await edit_message_text(cq.message, _("❌ В этом отделе нет сотрудников."))
            deps = await all_departments()
            if deps:
                 context.user_data["dept_list"] = {str(d.id): d.name for d in deps}
                 buttons = [ [InlineKeyboardButton(name, callback_data=f"{CB_DEPT}:{d_id}")] for d_id, name in list(context.user_data["dept_list"].items())[:15]] + [[InlineKeyboardButton(_("🔙 Назад"), callback_data=f"{CB_MAIN}:back_main")]]
                 if len(deps) > 15: buttons.insert(-1, [InlineKeyboardButton(_("... (еще отделы)"), callback_data=CB_NOOP)])
                 await edit_message_text(cq.message, _("📋 *Отделы компании*"), reply_markup=InlineKeyboardMarkup(buttons), parse_mode=ParseMode.MARKDOWN); return DEPT_LIST
            else: return await start(update, context)
        context.user_data["dept_emps"] = {str(u.id): u for u in users}
        buttons = [ [InlineKeyboardButton(u.get_full_name(), callback_data=f"{CB_DEPT_EMP}:{uid}")] for uid, u in list(context.user_data["dept_emps"].items())[:15] ] + [[InlineKeyboardButton(_("🔙 Назад к отделам"), callback_data=f"{CB_MAIN}:show_depts")]]
        if len(users) > 15: buttons.insert(-1, [InlineKeyboardButton(_("... (еще сотрудники)"), callback_data=CB_NOOP)])
        await edit_message_text(cq.message, _("👥 *Сотрудники отдела '{dept}'*").format(dept=dept_name), reply_markup=InlineKeyboardMarkup(buttons), parse_mode=ParseMode.MARKDOWN)
        return DEPT_EMP_LIST
    except (ValueError, IndexError) as e: logger.warning(f"Invalid callback data in dept_cb: {cq.data} ({e})"); await edit_message_text(cq.message, _("⚠️ Некорректный выбор отдела.")); return DEPT_LIST
    except (BadRequest, NetworkError, TimedOut) as e: logger.warning(f"Network/API error in dept_cb: {e}"); await reply_text(update, _("⚠️ Ошибка сети или API. Попробуйте выбрать отдел снова.")); return DEPT_LIST
    except Exception as e: logger.exception(f"Unexpected error in dept_cb: {e}"); await reply_text(update, _("⚠️ Внутренняя ошибка. Попробуйте /start")); return ConversationHandler.END


async def dept_emp_cb(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Показывает профиль сотрудника, выбранного из списка отдела."""
    if not update.callback_query or not update.callback_query.data: return DEPT_EMP_LIST
    cq = update.callback_query; user_id = str(update.effective_user.id)
    logger.info(f"DEPT_EMP_LIST callback '{cq.data}' from user {user_id}")
    try:
        try: await cq.answer()
        except BadRequest: pass
        parts = cq.data.split(":", 1)
        if len(parts) != 2 or not parts[1].isdigit(): raise ValueError(f"Invalid callback data format: {cq.data}")
        uid_str = parts[1]; dept_emps = context.user_data.get("dept_emps", {})
        user = dept_emps.get(uid_str)
        if not user:
            logger.warning(f"User {uid_str} not found in dept_emps cache for user {user_id}. Fetching from DB.")
            user = await fetch_user_by_id(int(uid_str))
            if not user: logger.error(f"Failed to fetch user {uid_str} from DB in dept_emp_cb."); await reply_text(update, _("❌ Не удалось найти информацию о сотруднике.")); return DEPT_EMP_LIST
        await send_user_profile(cq.message, user)
        return DEPT_EMP_LIST
    except (ValueError, IndexError, KeyError) as e: logger.warning(f"Invalid data or state in dept_emp_cb: {cq.data} ({e})"); await reply_text(update, _("⚠️ Ошибка данных при выборе сотрудника.")); return DEPT_EMP_LIST
    except Exception as e: logger.exception(f"Unexpected error in dept_emp_cb: {e}"); await reply_text(update, _("⚠️ Внутренняя ошибка при показе профиля.")); return DEPT_EMP_LIST


async def all_users_cb(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Показывает профиль сотрудника, выбранного из общего списка."""
    if not update.callback_query or not update.callback_query.data: return EMP_LIST
    cq = update.callback_query; user_id = str(update.effective_user.id)
    logger.info(f"EMP_LIST callback '{cq.data}' from user {user_id}")
    try:
        try: await cq.answer()
        except BadRequest: pass
        parts = cq.data.split(":", 1)
        if len(parts) != 2 or not parts[1].isdigit(): raise ValueError(f"Invalid callback data format: {cq.data}")
        uid = int(parts[1])
        logger.debug(f"User {user_id} requested profile for user {uid} from all users list.")
        user = await fetch_user_by_id(uid)
        if not user: logger.error(f"Failed to fetch user {uid} from DB in all_users_cb."); await reply_text(update, _("❌ Не удалось найти информацию об этом сотруднике.")); return EMP_LIST
        await send_user_profile(cq.message, user)
        return EMP_LIST
    except (ValueError, IndexError) as e: logger.warning(f"Invalid callback data in all_users_cb: {cq.data} ({e})"); await reply_text(update, _("⚠️ Некорректный выбор сотрудника.")); return EMP_LIST
    except Exception as e: logger.exception(f"Unexpected error in all_users_cb: {e}"); await reply_text(update, _("⚠️ Внутренняя ошибка при показе профиля.")); return EMP_LIST