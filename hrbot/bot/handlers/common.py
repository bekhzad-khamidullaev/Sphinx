# hrbot/bot/handlers/common.py

import logging
from django.conf import settings
from django.utils.translation import gettext as _
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ParseMode
from telegram.error import BadRequest, NetworkError, TimedOut
from telegram.ext import ContextTypes, ConversationHandler

# Импортируем состояния и префиксы
from ..constants import (
    MAIN_MENU, EVAL_SELECT_QSET, DEPT_LIST, EMP_LIST, PROFILE_MENU, LANG_MENU, SEARCH_INPUT,
    CB_MAIN, CB_EVAL_QSET, CB_DEPT, CB_USER, CB_PROFILE, CB_LANG, CB_NOOP
)
# Импортируем ORM врапперы и хелперы
from ..db import get_or_create_tguser, all_departments, all_users, get_active_questionnaires
from ..utils import reply_text, edit_message_text
from telegram.constants import ParseMode 
logger = logging.getLogger(__name__)

# --- /start Handler ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Обрабатывает команду /start и показывает главное меню."""
    target_message = update.message or (update.callback_query and update.callback_query.message)
    if not target_message:
        logger.warning("start called without message or usable callback.")
        if update.effective_chat and hasattr(update, '_context'):
            # Импортируем здесь, чтобы избежать циклического импорта
            from ..utils import send_message
            await send_message(update._context, update.effective_chat.id, _("Ошибка: Не удалось определить сообщение для ответа. Попробуйте ввести /start снова."))
        return ConversationHandler.END

    user_id = str(update.effective_user.id)
    logger.info(f"Processing /start command for user_id: {user_id}")
    tg = await get_or_create_tguser(user_id)

    if tg is None:
        logger.error(f"Failed to get/create TelegramUser or linked User for {user_id} (returned None).")
        await target_message.reply_text(_("❌ Произошла ошибка при доступе к вашему профилю. Попробуйте позже."))
        return ConversationHandler.END

    if not tg.approved:
        logger.info(f"User {user_id} is not approved.")
        await target_message.reply_text(_("⏳ Ваш аккаунт еще не подтвержден HR-отделом. Пожалуйста, ожидайте."))
        return ConversationHandler.END

    context.user_data.clear()
    logger.debug(f"User data cleared for user {user_id}")

    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton(_("📝 Новая оценка"), callback_data=f"{CB_MAIN}:new_eval")],
        [InlineKeyboardButton(_("🏢 Список отделов"), callback_data=f"{CB_MAIN}:show_depts"), InlineKeyboardButton(_("👥 Список сотрудников"), callback_data=f"{CB_MAIN}:show_all_users")],
        [InlineKeyboardButton(_("⚙️ Настройки профиля"), callback_data=f"{CB_MAIN}:profile_settings"), InlineKeyboardButton(_("🌐 Выбор языка"), callback_data=f"{CB_MAIN}:choose_lang")],
        [InlineKeyboardButton(_("🔍 Поиск сотрудника"), callback_data=f"{CB_MAIN}:search_emp")],
        [InlineKeyboardButton(_("⏹️ Завершить /stop"), callback_data=f"{CB_MAIN}:stop")],
    ])
    message_text = _("👋 *Главное меню*\nВыберите действие:")

    if update.message: # Если это была команда /start
        await reply_text(update, message_text, reply_markup=kb, parse_mode=ParseMode.MARKDOWN)
    elif update.callback_query: # Если это возврат из другого меню
        await edit_message_text(target_message, message_text, reply_markup=kb, parse_mode=ParseMode.MARKDOWN)

    return MAIN_MENU

# --- Main Menu Callback ---
async def main_menu_cb(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Обрабатывает нажатия кнопок главного меню."""
    if not update.callback_query or not update.callback_query.data:
        logger.warning("main_menu_cb called without callback_query or data.")
        return MAIN_MENU

    cq = update.callback_query
    user_id = str(update.effective_user.id)
    logger.info(f"MAIN_MENU callback '{cq.data}' from user {user_id}")

    try:
        try: await cq.answer()
        except BadRequest: pass

        parts = cq.data.split(":", 1)
        if len(parts) != 2 or parts[0] != CB_MAIN:
             logger.warning(f"Invalid callback data format received in MAIN_MENU: {cq.data}")
             await edit_message_text(cq.message, _("⚠️ Некорректный запрос."))
             return MAIN_MENU
        cmd = parts[1]

        # --- Обработка команд меню ---
        if cmd == "new_eval":
            questionnaires = await get_active_questionnaires()
            if not questionnaires:
                 await edit_message_text(cq.message, _("❌ Нет доступных опросников для проведения оценки."))
                 return MAIN_MENU
            context.user_data["eval_qsets"] = {str(q.id): q.name for q in questionnaires}
            buttons = [ [InlineKeyboardButton(name, callback_data=f"{CB_EVAL_QSET}:{qid}")] for qid, name in context.user_data["eval_qsets"].items() ] + [[InlineKeyboardButton(_("🔙 Назад"), callback_data=f"{CB_MAIN}:back_main")]]
            await edit_message_text(cq.message, _("📊 *Новая оценка*\nВыберите тип опросника:"), reply_markup=InlineKeyboardMarkup(buttons), parse_mode=ParseMode.MARKDOWN)
            return EVAL_SELECT_QSET

        elif cmd == "show_depts":
            deps = await all_departments()
            if not deps: await edit_message_text(cq.message, _("❌ Не удалось загрузить список отделов или отделы отсутствуют.")); return MAIN_MENU
            context.user_data["dept_list"] = {str(d.id): d.name for d in deps}; buttons = [ [InlineKeyboardButton(name, callback_data=f"{CB_DEPT}:{did}")] for did, name in list(context.user_data["dept_list"].items())[:15]] + [[InlineKeyboardButton(_("🔙 Назад"), callback_data=f"{CB_MAIN}:back_main")]]
            if len(deps) > 15: buttons.insert(-1, [InlineKeyboardButton(_("... (еще отделы)"), callback_data=CB_NOOP)])
            await edit_message_text(cq.message, _("📋 *Отделы компании*"), reply_markup=InlineKeyboardMarkup(buttons), parse_mode=ParseMode.MARKDOWN); return DEPT_LIST

        elif cmd == "show_all_users":
            users = await all_users()
            if not users: await edit_message_text(cq.message, _("❌ Не удалось загрузить список сотрудников или сотрудники отсутствуют.")); return MAIN_MENU
            context.user_data["all_users"] = {str(u.id): u.get_full_name() for u in users}; buttons = [ [InlineKeyboardButton(name, callback_data=f"{CB_USER}:{uid}")] for uid, name in list(context.user_data["all_users"].items())[:15]] + [[InlineKeyboardButton(_("🔙 Назад"), callback_data=f"{CB_MAIN}:back_main")]]
            if len(users) > 15: buttons.insert(-1, [InlineKeyboardButton(_("... (еще сотрудники)"), callback_data=CB_NOOP)])
            await edit_message_text(cq.message, _("👥 *Все сотрудники*"), reply_markup=InlineKeyboardMarkup(buttons), parse_mode=ParseMode.MARKDOWN); return EMP_LIST

        elif cmd == "profile_settings":
            buttons = [ [InlineKeyboardButton(_("📸 Загрузить/сменить фото"), callback_data=f"{CB_PROFILE}:photo")], [InlineKeyboardButton(_("✍️ Изменить имя"), callback_data=f"{CB_PROFILE}:name")], [InlineKeyboardButton(_("🔙 Назад"), callback_data=f"{CB_MAIN}:back_main")]]
            await edit_message_text(cq.message, _("⚙️ *Настройки профиля*"), reply_markup=InlineKeyboardMarkup(buttons), parse_mode=ParseMode.MARKDOWN); return PROFILE_MENU

        elif cmd == "choose_lang":
            lang_buttons = []
            # --- ИСПРАВЛЕНО: Добавлен except сразу после try ---
            try:
                # current_lang = context.user_data.get('user_lang', settings.LANGUAGE_CODE) # Пока не используем current_lang
                for code, name in settings.LANGUAGES:
                     lang_buttons.append(InlineKeyboardButton(name, callback_data=f"{CB_LANG}:{code}"))
            except Exception as lang_e: # Перехватываем ошибку здесь
                logger.error(f"Error getting LANGUAGES from settings: {lang_e}")
                await edit_message_text(cq.message, _("❌ Ошибка загрузки доступных языков."))
                return MAIN_MENU
            # ----------------------------------------------------

            buttons = [[btn] for btn in lang_buttons]
            buttons.append([InlineKeyboardButton(_("🔙 Назад"), callback_data=f"{CB_MAIN}:back_main")])

            await edit_message_text(cq.message, _("🌐 *Выберите язык интерфейса*"), reply_markup=InlineKeyboardMarkup(buttons), parse_mode=ParseMode.MARKDOWN)
            return LANG_MENU

        elif cmd == "search_emp": await edit_message_text(cq.message, _("🔎 Введите часть имени, фамилии, телефона или email для поиска сотрудника:"), reply_markup=None); return SEARCH_INPUT
        elif cmd == "stop": await edit_message_text(cq.message, _("✋ Диалог завершен.")); context.user_data.clear(); return ConversationHandler.END
        elif cmd == "back_main": return await start(update, context)
        else: logger.warning(f"Unknown command '{cmd}' received in MAIN_MENU."); await edit_message_text(cq.message, _("⚠️ Неизвестная команда.")); return MAIN_MENU

    except (BadRequest, NetworkError, TimedOut) as e: logger.warning(f"Network/API error in main_menu_cb: {e}"); await reply_text(update, _("⚠️ Ошибка сети или API. Попробуйте еще раз.")); return MAIN_MENU
    except Exception as e: logger.exception(f"Unexpected error in main_menu_cb: {e}"); await reply_text(update, _("⚠️ Произошла внутренняя ошибка. Попробуйте /start")); return ConversationHandler.END


# --- /stop and Fallback Handlers ---
async def stop_conversation(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Завершает текущий диалог ConversationHandler."""
    user_id = update.effective_user.id if update.effective_user else "Unknown"; logger.info(f"Stopping conversation for user {user_id}")
    context.user_data.clear(); message_text = _("✋ Операция прервана."); next_state = ConversationHandler.END
    if update.message: await reply_text(update, message_text)
    elif update.callback_query:
        try: await update.callback_query.answer(); await edit_message_text(update.callback_query.message, message_text)
        except BadRequest: pass
    else: logger.warning("stop_conversation called without message or callback_query.")
    return next_state

async def unexpected_input_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обрабатывает любое сообщение/callback, не пойманное другими хендлерами в ConversationHandler."""
    user_id = update.effective_user.id if update.effective_user else "Unknown"; current_state = context.user_data.get(ConversationHandler.CURRENT_STATE)
    text = _("Неожиданный ввод.")
    if update.message: logger.debug(f"Unhandled message received from user {user_id} in state {current_state}: '{update.message.text}'"); text = _("Неожиданный ввод. Пожалуйста, используйте кнопки или команду /stop."); await reply_text(update, text)
    elif update.callback_query:
         logger.debug(f"Unhandled callback_query received from user {user_id} in state {current_state}: '{update.callback_query.data}'")
         try: await update.callback_query.answer(_("Действие недоступно."), show_alert=True)
         except BadRequest: pass
         return
    else: logger.warning(f"unexpected_input_handler triggered by unknown update type from user {user_id} in state {current_state}")