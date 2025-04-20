# hrbot/bot/handlers/evaluation.py

import logging
from django.utils.translation import gettext as _
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ParseMode
from telegram.error import BadRequest, NetworkError, TimedOut
from telegram.ext import ContextTypes, ConversationHandler
from asgiref.sync import sync_to_async
from django.conf import settings
# Импортируем состояния и префиксы
from ..constants import ( # Добавляем EVAL_Q в импорты состояний
    EVAL_SELECT_QSET, EVAL_SELECT_DEPT, EVAL_SELECT_EMP, EVAL_Q, MAIN_MENU,
    CB_MAIN, CB_EVAL_QSET, CB_EVAL_DEPT, CB_EVAL_EMP, CB_NOOP
)
# Импортируем ORM врапперы и хелперы
from ..db import (
    get_active_questionnaires, all_departments, users_in_dept,
    get_questionnaire_questions, save_eval, get_or_create_tguser
)
from ..utils import reply_text, edit_message_text, send_message

# Импортируем модели для проверки типов и доступа к полям
from hrbot.models import Questionnaire, Question, Evaluation
from user_profiles.models import User, Role, Department

logger = logging.getLogger(__name__)

# --- Шаг 1: Выбор Опросника (без изменений) ---
async def eval_select_qset_cb(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if not update.callback_query or not update.callback_query.data: return EVAL_SELECT_QSET
    cq = update.callback_query; user_id = str(update.effective_user.id)
    logger.info(f"EVAL_SELECT_QSET callback '{cq.data}' from user {user_id}")
    try:
        try: await cq.answer()
        except BadRequest: pass
        parts = cq.data.split(":", 1)
        if len(parts) != 2 or not parts[1].isdigit(): raise ValueError(f"Invalid callback data format: {cq.data}")
        qset_id = int(parts[1]); context.user_data["eval_qset_id"] = qset_id
        qset_name = context.user_data.get("eval_qsets", {}).get(str(qset_id), f"ID {qset_id}")
        logger.debug(f"User {user_id} selected questionnaire {qset_id} ('{qset_name}') for evaluation.")
        deps = await all_departments()
        if not deps:
             await edit_message_text(cq.message, _("❌ Не удалось загрузить список отделов для выбора сотрудника."))
             questionnaires = await get_active_questionnaires()
             if questionnaires:
                 context.user_data["eval_qsets"] = {str(q.id): q.name for q in questionnaires}
                 buttons = [ [InlineKeyboardButton(name, callback_data=f"{CB_EVAL_QSET}:{qid}")] for qid, name in context.user_data["eval_qsets"].items() ] + [[InlineKeyboardButton(_("🔙 Назад"), callback_data=f"{CB_MAIN}:back_main")]]
                 await edit_message_text(cq.message, _("📊 *Новая оценка*\nВыберите тип опросника:"), reply_markup=InlineKeyboardMarkup(buttons), parse_mode=ParseMode.MARKDOWN); return EVAL_SELECT_QSET
             else: from .common import start; return await start(update, context) # Импорт и вызов start
        context.user_data["eval_deps"] = {str(d.id): d.name for d in deps}
        buttons = [ [InlineKeyboardButton(name, callback_data=f"{CB_EVAL_DEPT}:{did}")] for did, name in context.user_data["eval_deps"].items()] + [[InlineKeyboardButton(_("🔙 Назад к опросникам"), callback_data=f"{CB_MAIN}:new_eval")]]
        await edit_message_text(cq.message, _("🏢 *Оценка (Опросник: {qset})*\nВыберите отдел сотрудника:").format(qset=qset_name), reply_markup=InlineKeyboardMarkup(buttons), parse_mode=ParseMode.MARKDOWN)
        return EVAL_SELECT_DEPT
    except (ValueError, IndexError) as e: logger.warning(f"Invalid callback data in eval_select_qset_cb: {cq.data} ({e})"); await edit_message_text(cq.message, _("⚠️ Некорректный выбор опросника.")); return EVAL_SELECT_QSET
    except (BadRequest, NetworkError, TimedOut) as e: logger.warning(f"Network/API error in eval_select_qset_cb: {e}"); await reply_text(update, _("⚠️ Ошибка сети или API. Попробуйте выбрать опросник снова.")); return EVAL_SELECT_QSET
    except Exception as e: logger.exception(f"Unexpected error in eval_select_qset_cb: {e}"); await reply_text(update, _("⚠️ Внутренняя ошибка. Попробуйте /start")); return ConversationHandler.END

async def eval_select_dept_cb(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    # ... (код без изменений) ...
    if not update.callback_query or not update.callback_query.data: return EVAL_SELECT_DEPT
    cq = update.callback_query; user_id = str(update.effective_user.id)
    logger.info(f"EVAL_SELECT_DEPT callback '{cq.data}' from user {user_id}")
    try:
        try: await cq.answer()
        except BadRequest: pass
        parts = cq.data.split(":", 1)
        if len(parts) != 2 or not parts[1].isdigit(): raise ValueError(f"Invalid callback data format: {cq.data}")
        did = int(parts[1]); context.user_data["eval_dept_id"] = did
        dept_name = context.user_data.get("eval_deps", {}).get(str(did), f"ID {did}")
        qset_id = context.user_data.get("eval_qset_id")
        qset_name = context.user_data.get("eval_qsets", {}).get(str(qset_id), f"ID {qset_id}")
        logger.debug(f"User {user_id} selected department {did} ('{dept_name}') for evaluation using qset {qset_id}.")
        if not qset_id: logger.error(f"eval_qset_id not found in user_data for eval_select_dept_cb. User: {user_id}"); await edit_message_text(cq.message, _("❌ Ошибка: опросник не был выбран. Начните оценку заново с /start.")); return ConversationHandler.END
        users = await users_in_dept(did)
        if not users:
             logger.warning(f"No users found in department {did} for evaluation.")
             await edit_message_text(cq.message, _("❌ В отделе '{dept}' нет сотрудников. Выберите другой отдел.").format(dept=dept_name))
             deps = await all_departments()
             if deps:
                 context.user_data["eval_deps"] = {str(d.id): d.name for d in deps}
                 buttons = [ [InlineKeyboardButton(name, callback_data=f"{CB_EVAL_DEPT}:{dep_id}")] for dep_id, name in context.user_data["eval_deps"].items() ] + [[InlineKeyboardButton(_("🔙 Назад к опросникам"), callback_data=f"{CB_MAIN}:new_eval")]]
                 await edit_message_text(cq.message, _("🏢 *Оценка (Опросник: {qset})*\nВыберите отдел сотрудника:").format(qset=qset_name), reply_markup=InlineKeyboardMarkup(buttons), parse_mode=ParseMode.MARKDOWN)
                 return EVAL_SELECT_DEPT
             else: from .common import start; return await start(update, context)
        context.user_data["eval_emps"] = {str(u.id): u.get_full_name() for u in users}
        context.user_data["eval_emp_objects"] = {str(u.id): u for u in users}
        buttons = [ [InlineKeyboardButton(name, callback_data=f"{CB_EVAL_EMP}:{uid}")] for uid, name in context.user_data["eval_emps"].items()] + [[InlineKeyboardButton(_("🔙 Назад к отделам"), callback_data=f"{CB_EVAL_QSET}:{qset_id}")]] # Назад к выбору отдела
        await edit_message_text(cq.message, _("👤 *Оценка (Отдел: {dept})*\nВыберите сотрудника:").format(dept=dept_name), reply_markup=InlineKeyboardMarkup(buttons), parse_mode=ParseMode.MARKDOWN)
        return EVAL_SELECT_EMP
    except (ValueError, IndexError, KeyError) as e: logger.warning(f"Invalid data or state in eval_select_dept_cb: {cq.data} ({e})"); await edit_message_text(cq.message, _("⚠️ Ошибка данных. Попробуйте выбрать отдел снова.")); return EVAL_SELECT_DEPT
    except (BadRequest, NetworkError, TimedOut) as e: logger.warning(f"Network/API error in eval_select_dept_cb: {e}"); await reply_text(update, _("⚠️ Ошибка сети или API. Попробуйте выбрать отдел снова.")); return EVAL_SELECT_DEPT
    except Exception as e: logger.exception(f"Unexpected error in eval_select_dept_cb: {e}"); await reply_text(update, _("⚠️ Внутренняя ошибка. Попробуйте /start")); return ConversationHandler.END


# --- Шаг 3: Выбор Сотрудника и показ ПЕРВОГО вопроса ---
async def eval_select_emp_cb(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Обрабатывает выбор сотрудника для оценки и начинает опрос."""
    if not update.callback_query or not update.callback_query.data: return EVAL_SELECT_EMP
    cq = update.callback_query; user_id = str(update.effective_user.id)
    logger.info(f"EVAL_SELECT_EMP callback '{cq.data}' from user {user_id}")
    try:
        try: await cq.answer()
        except BadRequest: pass
        parts = cq.data.split(":", 1)
        if len(parts) != 2 or not parts[1].isdigit(): raise ValueError(f"Invalid callback data format: {cq.data}")
        uid_str = parts[1]; uid = int(uid_str)
        qset_id = context.user_data.get("eval_qset_id"); eval_emps = context.user_data.get("eval_emps", {}); dept_id = context.user_data.get("eval_dept_id"); emp_objects = context.user_data.get("eval_emp_objects", {})
        if not qset_id or not eval_emps or uid_str not in eval_emps or not dept_id or not emp_objects: logger.error(f"State error in eval_select_emp_cb for user {user_id}: qset_id={qset_id}, uid={uid_str} in eval_emps={uid_str in eval_emps}, dept_id={dept_id}, emp_objects exists={bool(emp_objects)}"); await edit_message_text(cq.message, _("❌ Ошибка: данные сессии оценки потеряны. Начните оценку заново с /start.")); return ConversationHandler.END
        context.user_data["eval_emp_id"] = uid; context.user_data["eval_emp_name"] = eval_emps[uid_str]
        selected_user_obj = emp_objects.get(uid_str); context.user_data["eval_role_id"] = None
        if selected_user_obj:
             user_roles = await sync_to_async(list)(selected_user_obj.roles.all()[:1])
             if user_roles: context.user_data["eval_role_id"] = user_roles[0].id; logger.debug(f"Found role ID {user_roles[0].id} for evaluated employee {uid}")
             else: logger.debug(f"No roles found for evaluated employee {uid}")
        else: logger.warning(f"Could not find User object for employee ID {uid} in cache.")
        logger.debug(f"User {user_id} selected employee {uid} ('{eval_emps[uid_str]}') for evaluation using qset {qset_id}.")
        qs = await get_questionnaire_questions(qset_id)
        if not qs:
            logger.warning(f"No questions found for questionnaire {qset_id}. Cannot start evaluation.")
            await edit_message_text(cq.message, _("❌ Для выбранного опросника не настроены вопросы. Оценка невозможна."))
            buttons = [ [InlineKeyboardButton(name, callback_data=f"{CB_EVAL_EMP}:{e_uid}")] for e_uid, name in eval_emps.items() ] + [[InlineKeyboardButton(_("🔙 Назад к отделам"), callback_data=f"{CB_EVAL_QSET}:{qset_id}")]]
            await edit_message_text(cq.message, _("👤 *Оценка*\nВыберите сотрудника:"), reply_markup=InlineKeyboardMarkup(buttons), parse_mode=ParseMode.MARKDOWN); return EVAL_SELECT_EMP
        context.user_data["eval_qs"] = qs; context.user_data["eval_answers"] = []; context.user_data["eval_idx"] = 0; logger.debug(f"Starting evaluation with {len(qs)} questions for user {user_id}.")

        # --- Показ первого вопроса (с кнопками или кнопкой пропуска) ---
        current_q = qs[0]
        question_text = f"❓ *Вопрос 1/{len(qs)}*\n\n{current_q.text}"
        keyboard = None
        # Проверяем, что answer_options это непустой список
        if current_q.answer_options and isinstance(current_q.answer_options, list):
            buttons = []
            for idx, option in enumerate(current_q.answer_options):
                 callback_data = f"eval_answer:{current_q.pk}:{idx}"
                 buttons.append(InlineKeyboardButton(str(option), callback_data=callback_data))
            keyboard = InlineKeyboardMarkup([buttons[i:i + 2] for i in range(0, len(buttons), 2)])
        else:
             # Если опций нет или они пустые, предлагаем пропустить
             logger.warning(f"Question {current_q.pk} has no valid answer options list. Offering skip.")
             keyboard = InlineKeyboardMarkup([[InlineKeyboardButton(_("Пропустить вопрос"), callback_data=f"eval_answer:{current_q.pk}:-1")]]) # -1 как индекс пропуска

        await edit_message_text(cq.message, question_text, reply_markup=keyboard, parse_mode=ParseMode.MARKDOWN)
        return EVAL_Q

    except (ValueError, IndexError, KeyError) as e:
         logger.warning(f"Invalid data or state in eval_select_emp_cb: {cq.data} ({e})")
         await edit_message_text(cq.message, _("⚠️ Ошибка данных. Попробуйте выбрать сотрудника снова."))
         dept_id = context.user_data.get("eval_dept_id"); eval_emps = context.user_data.get("eval_emps", {}); qset_id = context.user_data.get("eval_qset_id")
         if dept_id and eval_emps and qset_id:
             buttons = [ [InlineKeyboardButton(name, callback_data=f"{CB_EVAL_EMP}:{e_uid}")] for e_uid, name in eval_emps.items()] + [[InlineKeyboardButton(_("🔙 Назад к отделам"), callback_data=f"{CB_EVAL_QSET}:{qset_id}")]]
             await edit_message_text(cq.message, _("👤 *Оценка*\nВыберите сотрудника:"), reply_markup=InlineKeyboardMarkup(buttons), parse_mode=ParseMode.MARKDOWN); return EVAL_SELECT_EMP
         else: from .common import start; return await start(update, context)
    except (BadRequest, NetworkError, TimedOut) as e: logger.warning(f"Network/API error in eval_select_emp_cb: {e}"); await reply_text(update, _("⚠️ Ошибка сети или API. Попробуйте выбрать сотрудника снова.")); return EVAL_SELECT_EMP
    except Exception as e: logger.exception(f"Unexpected error in eval_select_emp_cb: {e}"); await reply_text(update, _("⚠️ Внутренняя ошибка. Попробуйте /start")); return ConversationHandler.END

# --- Шаг 4: Обработка Нажатия Кнопки Ответа ---
async def eval_answer_cb(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Обрабатывает нажатие кнопки с вариантом ответа."""
    # ... (код функции eval_answer_cb из предыдущего ответа) ...
    # ... (с корректной обработкой option_index == -1) ...
    if not update.callback_query or not update.callback_query.data: logger.warning("eval_answer_cb called without callback_query or data."); return EVAL_Q
    cq = update.callback_query; user_id = str(update.effective_user.id)
    logger.info(f"EVAL_Q callback '{cq.data}' from user {user_id}")
    try:
        try: await cq.answer()
        except BadRequest: pass
        parts = cq.data.split(":");
        if len(parts) != 3 or parts[0] != "eval_answer" or not parts[1].isdigit() or not parts[2].lstrip('-').isdigit(): raise ValueError(f"Invalid callback data format: {cq.data}")
        callback_q_pk = int(parts[1]); option_index = int(parts[2])
        current_idx = context.user_data.get("eval_idx"); questions = context.user_data.get("eval_qs"); answers = context.user_data.get("eval_answers"); qset_id = context.user_data.get("eval_qset_id"); emp_name = context.user_data.get("eval_emp_name"); emp_id = context.user_data.get("eval_emp_id"); role_id = context.user_data.get("eval_role_id")
        if current_idx is None or questions is None or answers is None or qset_id is None or emp_name is None: logger.error(f"State error in eval_answer_cb for user {user_id}. Missing context data."); await edit_message_text(cq.message, _("❌ Ошибка: данные опроса потеряны. Начните оценку заново с /start.")); context.user_data.clear(); return ConversationHandler.END
        if current_idx >= len(questions): logger.warning(f"Received answer callback when evaluation should be finished. Idx: {current_idx}, TotalQs: {len(questions)}"); await edit_message_text(cq.message, _("Оценка уже завершена.")); from .common import start; return await start(update, context)
        current_q = questions[current_idx]
        if current_q.pk != callback_q_pk: logger.warning(f"Callback question PK ({callback_q_pk}) doesn't match current question PK ({current_q.pk}) at index {current_idx}. User might have clicked an old button."); return EVAL_Q
        selected_answer = None
        if option_index == -1: logger.debug(f"User {user_id} skipped question {current_idx+1} (PK: {current_q.pk})")
        elif current_q.answer_options and isinstance(current_q.answer_options, list) and 0 <= option_index < len(current_q.answer_options): selected_answer = current_q.answer_options[option_index]; logger.debug(f"User {user_id} answered question {current_idx+1} (PK: {current_q.pk}) with option {option_index}: '{selected_answer}'")
        else: logger.error(f"Invalid option index {option_index} or missing options for question {current_q.pk}."); await edit_message_text(cq.message, _("⚠️ Ошибка: Некорректный вариант ответа. Попробуйте снова.")); return EVAL_Q
        answers.append(selected_answer); context.user_data["eval_idx"] += 1; next_idx = context.user_data["eval_idx"]
        if next_idx < len(questions):
            next_q = questions[next_idx]; question_text = f"❓ *Вопрос {next_idx + 1}/{len(questions)}*\n\n{next_q.text}"; keyboard = None
            if next_q.answer_options and isinstance(next_q.answer_options, list):
                buttons = [];
                for idx, option in enumerate(next_q.answer_options): callback_data = f"eval_answer:{next_q.pk}:{idx}"; buttons.append(InlineKeyboardButton(str(option), callback_data=callback_data))
                keyboard = InlineKeyboardMarkup([buttons[i:i + 2] for i in range(0, len(buttons), 2)])
            else: logger.warning(f"Question {next_q.pk} has no valid answer options list! Offering skip."); keyboard = InlineKeyboardMarkup([[InlineKeyboardButton(_("Пропустить вопрос"), callback_data=f"eval_answer:{next_q.pk}:-1")]])
            await edit_message_text(cq.message, question_text, reply_markup=keyboard, parse_mode=ParseMode.MARKDOWN); return EVAL_Q
        else:
            logger.info(f"Evaluation finished by user {user_id} for employee '{emp_name}' (ID: {emp_id}) using qset {qset_id}.")
            tg_user = await get_or_create_tguser(user_id)
            if not tg_user: await reply_text(update, _("❌ Не удалось идентифицировать вас для сохранения оценки.")); logger.error(f"Could not get tg_user for {user_id} at evaluation save."); return ConversationHandler.END
            responses_dict = {str(q.id): a for q, a in zip(questions, answers)}
            data = { "evaluator_id": tg_user.id, "employee_name": emp_name, "employee_id": emp_id, "questionnaire_id": qset_id, "role_id": role_id, "responses": responses_dict }
            logger.debug(f"Attempting to save evaluation with data: {data}")
            saved_eval = await save_eval(data)
            if not saved_eval: await reply_text(update, _("❌ Произошла ошибка при сохранении оценки в базу данных. Администраторы уведомлены.")); return ConversationHandler.END
            hr_chat_id = getattr(settings, 'HR_TELEGRAM_CHAT_ID', None)
            if hr_chat_id:
                 evaluator_name = tg_user.user.get_full_name() if hasattr(tg_user, 'user') and tg_user.user else f"TG User {tg_user.id}"; evaluator_tg_info = f"@{update.effective_user.username}" if update.effective_user.username else f"ID: {user_id}"; q_texts = {str(q.id): q.text for q in questions}; qset_name = context.user_data.get("eval_qsets", {}).get(str(qset_id), f"ID {qset_id}")
                 summary = (f"📝 *Новая оценка сотрудника (ID: {saved_eval.id})*\n\n👤 Сотрудник: *{emp_name}* (ID: {emp_id or 'N/A'})\n📊 Опросник: {qset_name}\n👨‍💻 Оценщик: {evaluator_name} ({evaluator_tg_info})\n\n*Ответы:*\n")
                 for q_id_str, answer_text in responses_dict.items(): summary += f"  • _{q_texts.get(q_id_str, f'Вопрос ID {q_id_str}')}_: {answer_text or '-'}\n"
                 await send_message(context, chat_id=hr_chat_id, text=summary, parse_mode=ParseMode.MARKDOWN); logger.info(f"Evaluation summary sent to HR chat {hr_chat_id}.")
            else: logger.warning("HR_TELEGRAM_CHAT_ID is not set in settings. Cannot send summary.")
            await edit_message_text(cq.message, _("✅ Оценка успешно сохранена! Спасибо."))
            keys_to_remove = [ "eval_qsets", "eval_qset_id", "eval_deps", "eval_dept_id", "eval_emps", "eval_emp_objects", "eval_emp_id", "eval_emp_name", "eval_role_id", "eval_qs", "eval_answers", "eval_idx"]
            for key in keys_to_remove: context.user_data.pop(key, None)
            logger.debug(f"Evaluation context data cleared for user {user_id}.")
            return ConversationHandler.END # Завершаем диалог после оценки
    except (ValueError, IndexError) as e: logger.warning(f"Invalid callback data or state in eval_answer_cb: {cq.data} ({e})"); await edit_message_text(cq.message, _("⚠️ Ошибка данных при обработке ответа.")); return EVAL_Q
    except (BadRequest, NetworkError, TimedOut) as e: logger.warning(f"Network/API error in eval_answer_cb: {e}"); await reply_text(update, _("⚠️ Ошибка сети или API. Попробуйте нажать кнопку снова.")); return EVAL_Q
    except Exception as e: logger.exception(f"Unexpected error in eval_answer_cb: {e}"); await reply_text(update, _("⚠️ Внутренняя ошибка при обработке ответа. Попробуйте /start")); context.user_data.clear(); return ConversationHandler.END