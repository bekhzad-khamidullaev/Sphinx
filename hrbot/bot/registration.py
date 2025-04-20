# hrbot/bot/registration.py

import logging
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler, MessageHandler,
    ConversationHandler, filters
)
from .utils import reply_text

from django.utils.translation import gettext_lazy as _

# Импортируем состояния и паттерны
from .constants import (
    MAIN_MENU, EVAL_SELECT_QSET, EVAL_SELECT_DEPT, EVAL_SELECT_EMP, EVAL_Q,
    DEPT_LIST, DEPT_EMP_LIST, EMP_LIST, PROFILE_MENU, PROFILE_UPLOAD_PHOTO,
    PROFILE_SET_NAME, LANG_MENU, SEARCH_INPUT, SEARCH_RESULTS,
    MAIN_CALLBACK, EVAL_QSET_CALLBACK, EVAL_DEPT_CALLBACK, EVAL_EMP_CALLBACK,
    DEPT_CALLBACK, DEPT_EMP_CALLBACK, USER_CALLBACK, PROFILE_CALLBACK,
    LANG_CALLBACK, SEARCH_RES_CALLBACK, STOP_CALLBACK, NOOP_CALLBACK
)

# Импортируем обработчики из подпакетов
from .handlers.common import start, main_menu_cb, stop_conversation, unexpected_input_handler
from .handlers.evaluation import (
    eval_select_qset_cb, eval_select_dept_cb, eval_select_emp_cb,
    eval_answer_cb # ИЗМЕНЕНО: импортируем новый обработчик
)
from .handlers.profile import profile_menu_cb, profile_upload_photo, profile_set_name
from .handlers.language import lang_menu_cb
from .handlers.search import search_input_msg, search_results_cb
from .handlers.directory import dept_cb, dept_emp_cb, all_users_cb
from .error_handler import error_handler # Используем error_handler из корня bot

logger = logging.getLogger(__name__)

def setup_handlers(application: Application):
    """Настраивает и добавляет обработчики в приложение PTB."""

    # --- Паттерн для callback'ов ответов на вопросы ---
    EVAL_ANSWER_CALLBACK = r"^eval_answer:(\d+):(-?\d+)$" # Вопрос PK: Индекс опции (-1 для пропуска)

    # --- Conversation Handler ---
    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            MAIN_MENU: [
                CallbackQueryHandler(main_menu_cb, pattern=MAIN_CALLBACK),
                CallbackQueryHandler(lambda u, c: None, pattern=NOOP_CALLBACK),
            ],
            # --- Новый поток Оценки ---
            EVAL_SELECT_QSET: [
                CallbackQueryHandler(eval_select_qset_cb, pattern=EVAL_QSET_CALLBACK),
                CallbackQueryHandler(start, pattern=r"^main:back_main$"),
                CallbackQueryHandler(main_menu_cb, pattern=r"^main:new_eval$"),
                CallbackQueryHandler(lambda u, c: None, pattern=NOOP_CALLBACK),
            ],
            EVAL_SELECT_DEPT: [
                CallbackQueryHandler(eval_select_dept_cb, pattern=EVAL_DEPT_CALLBACK),
                # Назад к выбору опросника (main:new_eval вызывает main_menu_cb, который покажет опросники)
                CallbackQueryHandler(main_menu_cb, pattern=r"^main:new_eval$"),
                CallbackQueryHandler(lambda u, c: None, pattern=NOOP_CALLBACK),
            ],
            EVAL_SELECT_EMP: [
                CallbackQueryHandler(eval_select_emp_cb,  pattern=EVAL_EMP_CALLBACK),
                 # Назад к выбору отдела (передаем ID опросника)
                CallbackQueryHandler(eval_select_qset_cb, pattern=EVAL_QSET_CALLBACK),
                CallbackQueryHandler(lambda u, c: None, pattern=NOOP_CALLBACK),
            ],
            # --- ИЗМЕНЕНО: Обрабатываем нажатия кнопок ---
            EVAL_Q: [
                CallbackQueryHandler(eval_answer_cb, pattern=EVAL_ANSWER_CALLBACK),
            ],
            # --- Остальные потоки ---
            DEPT_LIST:    [
                CallbackQueryHandler(dept_cb, pattern=DEPT_CALLBACK),
                CallbackQueryHandler(start, pattern=r"^main:back_main$"),
                CallbackQueryHandler(lambda u, c: None, pattern=NOOP_CALLBACK),
            ],
            DEPT_EMP_LIST:[
                CallbackQueryHandler(dept_emp_cb, pattern=DEPT_EMP_CALLBACK),
                CallbackQueryHandler(main_menu_cb, pattern=r"^main:show_depts$"),
                CallbackQueryHandler(lambda u, c: None, pattern=NOOP_CALLBACK),
            ],
            EMP_LIST:     [
                CallbackQueryHandler(all_users_cb, pattern=USER_CALLBACK),
                CallbackQueryHandler(start, pattern=r"^main:back_main$"),
                CallbackQueryHandler(lambda u, c: None, pattern=NOOP_CALLBACK),
            ],
            PROFILE_MENU: [
                CallbackQueryHandler(profile_menu_cb, pattern=PROFILE_CALLBACK),
                CallbackQueryHandler(start, pattern=r"^main:back_main$"),
            ],
            PROFILE_UPLOAD_PHOTO: [
                MessageHandler(filters.PHOTO, profile_upload_photo),
                MessageHandler(filters.TEXT & ~filters.COMMAND, lambda u, c: reply_text(u, _("Пожалуйста, отправьте фото, а не текст."))),
            ],
            PROFILE_SET_NAME:     [
                MessageHandler(filters.TEXT & ~filters.COMMAND, profile_set_name),
            ],
            LANG_MENU:    [
                CallbackQueryHandler(lang_menu_cb, pattern=LANG_CALLBACK),
                CallbackQueryHandler(start, pattern=r"^main:back_main$"),
            ],
            SEARCH_INPUT: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, search_input_msg),
            ],
            SEARCH_RESULTS:[
                CallbackQueryHandler(search_results_cb, pattern=SEARCH_RES_CALLBACK),
                CallbackQueryHandler(main_menu_cb, pattern=r"^main:search_emp$"),
                CallbackQueryHandler(start, pattern=r"^main:back_main$"),
                CallbackQueryHandler(lambda u, c: None, pattern=NOOP_CALLBACK),
            ],
        },
        fallbacks=[
             CommandHandler("stop", stop_conversation),
             CallbackQueryHandler(stop_conversation, pattern=STOP_CALLBACK),
             # Ловим все остальное внутри диалога
             MessageHandler(filters.ALL, unexpected_input_handler),
        ],
        allow_reentry=True,
        per_message=False,
    )

    application.add_handler(conv_handler)
    # Регистрируем обработчик ошибок последним
    application.add_error_handler(error_handler)

    logger.info("All handlers set up successfully for the application.")