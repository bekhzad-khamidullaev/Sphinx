# hrbot/bot/handlers.py

import os
import logging
# Убедитесь, что настройки логирования сконфигурированы для UTF-8,
# особенно если выводите в файл или консоль Windows.
# Пример настройки (может быть в settings.py или другом месте):
# logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', encoding='utf-8')

from django.conf import settings
from django.utils.translation import gettext as _
from django.db import models, IntegrityError
from django.db.models import Q
from asgiref.sync import sync_to_async
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, InputFile
from telegram.constants import ParseMode # Используем константу для ParseMode
from telegram.error import BadRequest, NetworkError, TelegramError, TimedOut
from telegram.ext import (
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    ConversationHandler,
    filters,
    ContextTypes,
)
# Защита от синхронных вызовов из асинхронного контекста
from django.core.exceptions import SynchronousOnlyOperation, FieldError, FieldDoesNotExist

# Импортируйте ваши модели и функции
# Убедитесь, что импорты user_profiles и hrbot корректны
try:
    from hrbot.models import TelegramUser, Evaluation, Question
    # Убедитесь, что эта функция существует и корректна, и обрабатывает свои ошибки
    from hrbot.bitrix import send_evaluation_to_bitrix
    from user_profiles.models import User, Department, Role
except ImportError as e:
    # Логируем ошибку импорта и выходим, так как бот не сможет работать
    logging.critical(f"Failed to import models or functions: {e}. Bot cannot start.")
    raise

logger = logging.getLogger(__name__)

# ===================================================================
#                         STATES DEFINITION
# ===================================================================
(
    MAIN_MENU,
    EVAL_DEPT, EVAL_ROLE, EVAL_EMP, EVAL_Q,
    DEPT_LIST, DEPT_EMP_LIST,
    EMP_LIST,
    PROFILE_MENU, PROFILE_UPLOAD_PHOTO, PROFILE_SET_NAME,
    LANG_MENU,
    SEARCH_INPUT, SEARCH_RESULTS
) = range(14)

# ===================================================================
#                         ASYNC ORM WRAPPERS with Error Handling
# ===================================================================

# Имя поля ForeignKey от User к Role (если оно есть и называется не 'role')
USER_ROLE_FIELD_NAME = None # У вас используется M2M, оставляем None
# Имя ManyToMany поля от User к Role
# В user_profiles.models.User: roles = ManyToManyField(..., related_name="users", ...)
# Значит, обратная связь на модели Role называется 'users'
USER_ROLES_M2M_NAME = 'roles'

@sync_to_async
def get_or_create_tguser(tg_id: str) -> TelegramUser | None:
    """
    Асинхронно получает или создает TelegramUser и связанный с ним User.
    Предзагружает связанный User объект для избежания SynchronousOnlyOperation.
    """
    try:
        user, user_created = User.objects.get_or_create(
            username=f"user_{tg_id}",
            defaults={'first_name': f'TG {tg_id}'}
        )
        if user_created:
            logger.info(f"Created Django User {user.id} for tg_id {tg_id}")

        # Используем select_related('user')
        tg, tg_created = TelegramUser.objects.select_related('user').get_or_create(
            telegram_id=tg_id,
            defaults={'user': user}
        )

        if not tg_created and tg.user_id != user.id:
             logger.warning(f"TelegramUser {tg_id} existed but linked to wrong User ({tg.user_id} != {user.id}). Relinking.")
             tg.user = user
             tg.save(update_fields=['user'])
             tg = TelegramUser.objects.select_related('user').get(telegram_id=tg_id)

        # Финальная проверка: есть ли связанный пользователь?
        if not tg.user_id or not hasattr(tg, 'user'):
             logger.error(f"CRITICAL: TelegramUser {tg.id} (tg_id: {tg_id}) has no associated user object after get_or_create/relink.")
             user_check = User.objects.filter(username=f"user_{tg_id}").first()
             logger.error(f"Does User object for username user_{tg_id} exist? {user_check is not None}")
             return None

        logger.debug(f"Successfully got/created TelegramUser {tg.id} linked to User {tg.user_id} for tg_id {tg_id}. User preloaded: {hasattr(tg, '_user_cache')}")
        return tg

    except Exception as e:
        logger.exception(f"DB error getting or creating TelegramUser for tg_id {tg_id}: {e}")
        return None

@sync_to_async
def all_departments():
    """Асинхронно получает все департаменты."""
    try:
        return list(Department.objects.all())
    except Exception as e:
        logger.exception(f"Error fetching all departments: {e}")
        return []

@sync_to_async
def roles_in_dept(dept_id: int):
    """
    Асинхронно возвращает список ролей, в которых есть хотя бы
    один пользователь из указанного отдела.
    Использует ManyToManyField 'users' на модели Role.
    """
    try:
        if not USER_ROLES_M2M_NAME: # Проверка на случай, если константа не задана
            logger.error("USER_ROLES_M2M_NAME is not set. Cannot filter roles by department via M2M.")
            return []
        # Фильтруем роли по ID департамента связанных пользователей
        return list(
            Role.objects
                .filter(users__department_id=dept_id)
                .distinct()
        )
    except Role.DoesNotExist:
         logger.warning("Role model not found or query failed.")
         return []
    except FieldError as e:
         logger.error(f"FieldError fetching roles via users/department: {e}. Check model relations ('{USER_ROLES_M2M_NAME}', 'department').")
         return []
    except Exception as e:
        logger.exception(f"Error fetching roles for dept_id {dept_id} via users: {e}")
        return []

# -- Вспомогательная функция для добавления prefetch/select related --
def _get_user_queryset():
    """Возвращает базовый QuerySet для User с нужными related полями."""
    qs = User.objects.all()
    # Обязательно загружаем 'department'
    select_fields = ['department']
    prefetch_fields = []

    # Проверяем и добавляем поле роли
    if USER_ROLE_FIELD_NAME:
        try:
            User._meta.get_field(USER_ROLE_FIELD_NAME)
            select_fields.append(USER_ROLE_FIELD_NAME)
        except FieldDoesNotExist:
            logger.warning(f"Field '{USER_ROLE_FIELD_NAME}' not found on User model for select_related.")
    elif USER_ROLES_M2M_NAME:
        try:
            User._meta.get_field(USER_ROLES_M2M_NAME)
            prefetch_fields.append(USER_ROLES_M2M_NAME)
        except FieldDoesNotExist:
             logger.warning(f"Field '{USER_ROLES_M2M_NAME}' not found on User model for prefetch_related.")

    # Проверяем и добавляем поле telegram_profile
    try:
        User._meta.get_field('telegram_profile')
        select_fields.append('telegram_profile')
    except models.FieldDoesNotExist:
        logger.debug("Field 'telegram_profile' not found on User model, skipping select_related.")

    # Применяем select_related и prefetch_related
    if select_fields:
        try:
            qs = qs.select_related(*select_fields)
        except FieldError as e:
             logger.error(f"Error applying select_related({select_fields}): {e}. Falling back.")
             qs = qs.select_related('department') # Фоллбэк на минимально необходимое
    if prefetch_fields:
        try:
            qs = qs.prefetch_related(*prefetch_fields)
        except (FieldError, ValueError) as e: # ValueError тоже возможен для prefetch
             logger.error(f"Error applying prefetch_related({prefetch_fields}): {e}. Skipping prefetch.")
             # Не падаем, просто не будет предзагрузки M2M

    return qs


@sync_to_async
def users_in_dept(dept_id: int):
    """Асинхронно получает пользователей в департаменте с предзагрузкой."""
    try:
        qs = _get_user_queryset()
        return list(qs.filter(department_id=dept_id))
    except FieldError as e: # На случай ошибки в _get_user_queryset (маловероятно с проверками)
         logger.error(f"FieldError in users_in_dept preloading: {e}. Check related field names.")
         try:
            return list(User.objects.select_related('department').filter(department_id=dept_id))
         except Exception as fallback_e:
            logger.exception(f"Fallback DB error fetching users for dept_id {dept_id}: {fallback_e}")
            return []
    except Exception as e:
        logger.exception(f"Error fetching users for dept_id {dept_id}: {e}")
        return []

@sync_to_async
def all_users():
    """Асинхронно получает всех пользователей с предзагрузкой."""
    try:
        qs = _get_user_queryset()
        return list(qs)
    except FieldError as e:
         logger.error(f"FieldError in all_users preloading: {e}. Check related field names.")
         try:
            return list(User.objects.select_related('department').all())
         except Exception as fallback_e:
            logger.exception(f"Fallback DB error fetching all users: {fallback_e}")
            return []
    except Exception as e:
        logger.exception(f"Error fetching all users: {e}")
        return []

@sync_to_async
def get_questions(role_id: int):
    """Асинхронно получает вопросы для роли."""
    try:
        return list(Question.objects.filter(role_id=role_id).order_by("order"))
    except Question.DoesNotExist: # Эта модель не имеет DoesNotExist как исключение менеджера
        logger.warning(f"No questions found for role_id {role_id}.")
        return []
    except Exception as e:
        logger.exception(f"Error fetching questions for role_id {role_id}: {e}")
        return []

@sync_to_async
def save_eval(ev_data: dict):
    """Асинхронно сохраняет оценку и пытается отправить в Битрикс."""
    evaluation = None
    evaluator_id = ev_data.get('evaluator_id') # Ожидается ID TelegramUser
    role_id = ev_data.get('role_id')

    # --- Проверка существования внешних ключей ---
    try:
        # Проверяем существование TelegramUser
        evaluator_exists = TelegramUser.objects.filter(id=evaluator_id).exists()
        role_exists = Role.objects.filter(id=role_id).exists()
        logger.info(f"Checking existence before create: TelegramUser ID {evaluator_id} exists: {evaluator_exists}, Role ID {role_id} exists: {role_exists}")
        if not evaluator_exists:
             logger.error(f"Cannot save evaluation: TelegramUser (evaluator) with ID {evaluator_id} does not exist!")
             return None
        if not role_exists:
             logger.error(f"Cannot save evaluation: Role with ID {role_id} does not exist!")
             return None
    except Exception as check_e:
         logger.exception(f"Error checking FK existence before saving evaluation: {check_e}")
         # Не продолжаем, если проверка не удалась
         return None
    # --- Конец проверки ---

    try:
        evaluation = Evaluation.objects.create(**ev_data)
        logger.info(f"Evaluation {evaluation.id} created successfully for employee '{ev_data.get('employee_name')}'.")
        # Отправка в Bitrix
        try:
            send_evaluation_to_bitrix(evaluation)
            logger.info(f"Evaluation {evaluation.id} sent to Bitrix.")
        except Exception as e_bitrix:
            logger.exception(f"Error sending evaluation {evaluation.id} to Bitrix: {e_bitrix}")
        return evaluation
    except IntegrityError as e: # Ловим конкретно IntegrityError
         logger.error(f"FOREIGN KEY constraint failed while saving evaluation data {ev_data}: {e}")
         logger.error(f"Data passed: evaluator_id={evaluator_id}, role_id={role_id}")
         return None
    except Exception as e:
        logger.exception(f"Error saving evaluation data {ev_data}: {e}")
        return None

@sync_to_async
def search_users(q: str):
    """Асинхронно ищет пользователей с предзагрузкой."""
    try:
        qs = _get_user_queryset()
        return list(
            qs.filter(
                Q(first_name__icontains=q)
                | Q(last_name__icontains=q)
                | Q(phone_number__icontains=q)
                | Q(email__icontains=q)
            )
        )
    except FieldError as e:
         logger.error(f"FieldError in search_users preloading: {e}. Check related field names.")
         try:
            return list(
                User.objects.select_related('department').filter(
                    Q(first_name__icontains=q)
                    | Q(last_name__icontains=q)
                    | Q(phone_number__icontains=q)
                    | Q(email__icontains=q)
                )
            )
         except Exception as fallback_e:
            logger.exception(f"Fallback DB error searching users with query '{q}': {fallback_e}")
            return []
    except Exception as e:
        logger.exception(f"Error searching users with query '{q}': {e}")
        return []

@sync_to_async
def update_user_name(user: User, name: str):
    """Асинхронно обновляет имя пользователя."""
    try:
        user.first_name = name
        user.save(update_fields=['first_name'])
        logger.info(f"Updated first_name for user {user.id} to '{name}'.")
        return True
    except Exception as e:
        logger.exception(f"Error updating name for user {user.id}: {e}")
        return False

@sync_to_async
def update_user_image(user: User, image_path: str):
    """Асинхронно обновляет фото пользователя."""
    try:
        user.image = image_path
        user.save(update_fields=['image'])
        logger.info(f"Updated image for user {user.id} to '{image_path}'.")
        return True
    except Exception as e:
        logger.exception(f"Error updating image for user {user.id}: {e}")
        return False

@sync_to_async
def fetch_user_by_id(user_id: int):
    """Асинхронно получает пользователя по ID с предзагрузкой."""
    try:
        qs = _get_user_queryset()
        return qs.get(id=user_id)
    except User.DoesNotExist:
        logger.warning(f"User with id {user_id} not found.")
        return None
    except FieldError as e:
         logger.error(f"FieldError in fetch_user_by_id preloading: {e}. Check related field names.")
         try:
             return User.objects.select_related('department').get(id=user_id)
         except User.DoesNotExist:
             logger.warning(f"User with id {user_id} not found (fallback).")
             return None
         except Exception as fallback_e:
             logger.exception(f"Fallback DB error fetching user with id {user_id}: {fallback_e}")
             return None
    except Exception as e:
        logger.exception(f"Error fetching user with id {user_id}: {e}")
        return None

@sync_to_async
def set_user_setting(user: User, key: str, value):
    """Асинхронно устанавливает настройку пользователя (пример с JSONField 'settings')."""
    try:
        # Проверяем, есть ли поле 'settings'
        if not hasattr(user, 'settings'):
             logger.error(f"User model {type(user)} has no 'settings' attribute.")
             return False
        # Убеждаемся, что это словарь
        if not isinstance(user.settings, dict):
             user.settings = {}
        user.settings[key] = value
        user.save(update_fields=['settings'])
        logger.info(f"Set setting '{key}'='{value}' for user {user.id}")
        return True
    except Exception as e:
        logger.exception(f"Error setting setting '{key}'='{value}' for user {user.id}: {e}")
        return False

# ===================================================================
#                         Helper Functions
# ===================================================================
async def send_message(context: ContextTypes.DEFAULT_TYPE, chat_id: int, text: str, **kwargs):
    """Безопасная отправка сообщения с обработкой ошибок."""
    try:
        await context.bot.send_message(chat_id=chat_id, text=text, **kwargs)
        return True
    except (NetworkError, TimedOut) as e:
        logger.warning(f"Network error sending message to {chat_id}: {e}")
    except BadRequest as e:
        logger.warning(f"Bad request sending message to {chat_id}: {e}")
    except TelegramError as e:
        logger.exception(f"Telegram error sending message to {chat_id}: {e}")
    except Exception as e:
        logger.exception(f"Unexpected error sending message to {chat_id}: {e}")
    return False

async def edit_message_text(message, text: str, **kwargs):
    """Безопасное редактирование сообщения с обработкой ошибок."""
    kwargs.pop('context', None) # Убираем context, если он там случайно
    try:
        await message.edit_text(text=text, **kwargs)
        return True
    except BadRequest as e:
        if "Message is not modified" in str(e):
             logger.debug(f"Message {message.message_id} not modified.")
             return True
        logger.warning(f"Bad request editing message {message.message_id}: {e}")
    except (NetworkError, TimedOut) as e:
        logger.warning(f"Network error editing message {message.message_id}: {e}")
    except TelegramError as e:
        logger.exception(f"Telegram error editing message {message.message_id}: {e}")
    except Exception as e:
        logger.exception(f"Unexpected error editing message {message.message_id}: {e}")
    return False

async def reply_text(update: Update, text: str, **kwargs):
    """
    Безопасный ответ на сообщение.
    Принимает дополнительные именованные аргументы (kwargs)
    и передает их в `target_message.reply_text()`.
    """
    if not update:
        logger.error("reply_text called with None update object.")
        return False

    target_message = update.message or (update.callback_query and update.callback_query.message)

    if target_message:
        try:
            await target_message.reply_text(text=text, **kwargs)
            return True
        except (NetworkError, TimedOut) as e:
            logger.warning(f"Network error replying to message {target_message.message_id}: {e}")
        except BadRequest as e:
            logger.warning(f"Bad request replying to message {target_message.message_id}: {e}")
        except TelegramError as e:
            logger.exception(f"Telegram error replying to message {target_message.message_id}: {e}")
        except TypeError as e: # Ловим TypeError на случай передачи невалидных kwargs
            logger.exception(f"TypeError replying to message {target_message.message_id}: Invalid kwargs? {kwargs} - {e}")
        except Exception as e:
            logger.exception(f"Unexpected error replying to message {target_message.message_id}: {e}")
    elif update.effective_chat and hasattr(update, '_context'):
         logger.warning("Replying via send_message as target message is unavailable.")
         await send_message(
             context=update._context,
             chat_id=update.effective_chat.id,
             text=text,
             **kwargs
         )
         return True
    else:
         logger.error("Cannot reply: No message, or no effective_chat/context in update.")

    return False


async def send_user_profile(target_message, user: User):
    """
    Отправляет фото (если есть и доступно) и информацию о пользователе.
    Отправляет как ответ на target_message.
    """
    if not user:
        logger.error("send_user_profile called with None user.")
        await target_message.reply_text(_("❌ Ошибка: данные пользователя не найдены."))
        return

    try:
        full_name = user.get_full_name() or _("Имя не указано")
        job_title = '-'
        # Получаем должность в зависимости от структуры модели
        if USER_ROLE_FIELD_NAME and hasattr(user, USER_ROLE_FIELD_NAME):
            role_obj = getattr(user, USER_ROLE_FIELD_NAME)
            if role_obj: job_title = role_obj.name
        elif USER_ROLES_M2M_NAME and hasattr(user, USER_ROLES_M2M_NAME):
            m2m_manager = getattr(user, USER_ROLES_M2M_NAME)
            # Проверка предзагрузки
            if hasattr(m2m_manager, '_prefetch_cache_name') and hasattr(user, m2m_manager._prefetch_cache_name):
                roles_list = getattr(user, m2m_manager._prefetch_cache_name)
                if roles_list:
                    job_title = ", ".join([r.name for r in roles_list])
            elif await sync_to_async(m2m_manager.exists)(): # Если не предзагружено, делаем доп. запрос (асинхронно!)
                 logger.warning(f"Roles for user {user.id} were not prefetched. Making extra DB query.")
                 roles_list = await sync_to_async(list)(m2m_manager.all())
                 job_title = ", ".join([r.name for r in roles_list])

        # Fallback на поле job_title, если оно есть
        if job_title == '-' and hasattr(user, 'job_title') and user.job_title:
             job_title = user.job_title

        phone = user.phone_number or '-'
        email = user.email or '-'
        dept_name = (user.department and user.department.name) or _("Отдел не указан")

        text = (
            f"👤 *{full_name}*\n"
            f"🏢 Отдел: {dept_name}\n"
            f"👔 Должность: {job_title}\n"
            f"📞 Телефон: {phone}\n"
            f"✉️ Email: {email}"
        )

        photo_sent = False
        if user.image and hasattr(user.image, 'name') and user.image.name:
            image_full_path = os.path.join(settings.MEDIA_ROOT, user.image.name)
            try:
                if os.path.exists(image_full_path):
                     logger.debug(f"Attempting to send photo: {image_full_path}")
                     with open(image_full_path, "rb") as f:
                        # Используем метод reply_photo сообщения, на которое отвечаем
                        await target_message.reply_photo(
                            photo=InputFile(f),
                            caption=text,
                            parse_mode=ParseMode.MARKDOWN # Используем константу
                        )
                        photo_sent = True
                else:
                     logger.warning(f"User image file not found at expected path: {image_full_path} for user {user.id}")
            except FileNotFoundError:
                logger.warning(f"FileNotFoundError on open: {image_full_path} for user {user.id}")
            except PermissionError:
                logger.error(f"Permission error reading image file: {image_full_path} for user {user.id}")
            except BadRequest as e:
                logger.warning(f"BadRequest sending photo for user {user.id}: {e}. Sending text instead.")
                photo_sent = False
            except (NetworkError, TimedOut) as e:
                logger.warning(f"Network error sending photo for user {user.id}: {e}. Sending text instead.")
                photo_sent = False
            except TelegramError as e:
                logger.exception(f"Telegram error sending photo for user {user.id}: {e}. Sending text instead.")
                photo_sent = False
            except Exception as e:
                logger.exception(f"Unexpected error sending photo for user {user.id}: {e}. Sending text instead.")
                photo_sent = False
        else:
            logger.debug(f"User {user.id} has no image or image path.")

        if not photo_sent:
            logger.debug(f"Sending text profile for user {user.id} as photo was not sent.")
            # Используем метод reply_text сообщения, на которое отвечаем
            await target_message.reply_text(text, parse_mode=ParseMode.MARKDOWN)

    except Exception as e:
        logger.exception(f"Unexpected error in send_user_profile for user {user.id}: {e}")
        await target_message.reply_text(_("⚠️ Произошла ошибка при отображении профиля."))


# ===================================================================
#                         /start and MAIN MENU
# ===================================================================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Обрабатывает команду /start и показывает главное меню."""
    target_message = update.message or (update.callback_query and update.callback_query.message)
    if not target_message:
        logger.warning("start called without message or usable callback.")
        if update.effective_chat and hasattr(update, '_context'):
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
        [InlineKeyboardButton(_("📝 Новая оценка"), callback_data="main:new_eval")],
        [
            InlineKeyboardButton(_("🏢 Список отделов"), callback_data="main:show_depts"),
            InlineKeyboardButton(_("👥 Список сотрудников"), callback_data="main:show_all_users"),
        ],
        [
            InlineKeyboardButton(_("⚙️ Настройки профиля"), callback_data="main:profile_settings"),
            InlineKeyboardButton(_("🌐 Выбор языка"), callback_data="main:choose_lang"),
        ],
        [InlineKeyboardButton(_("🔍 Поиск сотрудника"), callback_data="main:search_emp")],
        [InlineKeyboardButton(_("⏹️ Завершить /stop"), callback_data="main:stop")],
    ])
    message_text = _("👋 *Главное меню*\nВыберите действие:")

    if update.message: # Если это была команда /start
        # Используем хелпер reply_text
        await reply_text(update, message_text, reply_markup=kb, parse_mode=ParseMode.MARKDOWN)
    elif update.callback_query: # Если это возврат из другого меню
        await edit_message_text(target_message, message_text, reply_markup=kb, parse_mode=ParseMode.MARKDOWN)

    return MAIN_MENU

# ===================================================================
#                       MAIN MENU CALLBACK HANDLER
# ===================================================================
async def main_menu_cb(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Обрабатывает нажатия кнопок главного меню."""
    if not update.callback_query or not update.callback_query.data:
        logger.warning("main_menu_cb called without callback_query or data.")
        return MAIN_MENU # Остаемся в главном меню

    cq = update.callback_query
    user_id = str(update.effective_user.id)
    logger.info(f"MAIN_MENU callback '{cq.data}' from user {user_id}")

    try:
        try: await cq.answer()
        except BadRequest: pass

        parts = cq.data.split(":", 1)
        if len(parts) != 2 or parts[0] != "main":
             logger.warning(f"Invalid callback data format received in MAIN_MENU: {cq.data}")
             await edit_message_text(cq.message, _("⚠️ Некорректный запрос."))
             return MAIN_MENU
        cmd = parts[1]

        # --- Обработка команд меню ---
        if cmd == "new_eval":
            deps = await all_departments()
            if not deps:
                 await edit_message_text(cq.message, _("❌ Не удалось загрузить список отделов или отделы отсутствуют."))
                 return MAIN_MENU
            context.user_data["eval_deps"] = {str(d.id): d.name for d in deps}
            buttons = [
                [InlineKeyboardButton(name, callback_data=f"eval_dept:{did}")]
                for did, name in context.user_data["eval_deps"].items()
            ] + [[InlineKeyboardButton(_("🔙 Назад"), callback_data="main:back_main")]]
            await edit_message_text(cq.message, _("🏢 *Новая оценка*\nВыберите отдел:"), reply_markup=InlineKeyboardMarkup(buttons), parse_mode=ParseMode.MARKDOWN)
            return EVAL_DEPT

        elif cmd == "show_depts":
            deps = await all_departments()
            if not deps:
                 await edit_message_text(cq.message, _("❌ Не удалось загрузить список отделов или отделы отсутствуют."))
                 return MAIN_MENU
            context.user_data["dept_list"] = {str(d.id): d.name for d in deps}
            buttons = [
                [InlineKeyboardButton(name, callback_data=f"dept:{did}")]
                for did, name in list(context.user_data["dept_list"].items())[:15]
            ] + [[InlineKeyboardButton(_("🔙 Назад"), callback_data="main:back_main")]]
            if len(deps) > 15:
                 buttons.insert(-1, [InlineKeyboardButton(_("... (еще отделы)"), callback_data="noop")])
            await edit_message_text(cq.message, _("📋 *Отделы компании*"), reply_markup=InlineKeyboardMarkup(buttons), parse_mode=ParseMode.MARKDOWN)
            return DEPT_LIST

        elif cmd == "show_all_users":
            users = await all_users() # Использует _get_user_queryset
            if not users:
                await edit_message_text(cq.message, _("❌ Не удалось загрузить список сотрудников или сотрудники отсутствуют."))
                return MAIN_MENU
            context.user_data["all_users"] = {str(u.id): u.get_full_name() for u in users}
            buttons = [
                [InlineKeyboardButton(name, callback_data=f"user:{uid}")]
                for uid, name in list(context.user_data["all_users"].items())[:15]
            ] + [[InlineKeyboardButton(_("🔙 Назад"), callback_data="main:back_main")]]
            if len(users) > 15:
                 buttons.insert(-1, [InlineKeyboardButton(_("... (еще сотрудники)"), callback_data="noop")])
            await edit_message_text(cq.message, _("👥 *Все сотрудники*"), reply_markup=InlineKeyboardMarkup(buttons), parse_mode=ParseMode.MARKDOWN)
            return EMP_LIST

        elif cmd == "profile_settings":
            buttons = [
                [InlineKeyboardButton(_("📸 Загрузить/сменить фото"), callback_data="profile:photo")],
                [InlineKeyboardButton(_("✍️ Изменить имя"), callback_data="profile:name")],
                [InlineKeyboardButton(_("🔙 Назад"), callback_data="main:back_main")],
            ]
            await edit_message_text(cq.message, _("⚙️ *Настройки профиля*"), reply_markup=InlineKeyboardMarkup(buttons), parse_mode=ParseMode.MARKDOWN)
            return PROFILE_MENU

        elif cmd == "choose_lang":
            lang_buttons = []
            try:
                current_lang = context.user_data.get('user_lang', settings.LANGUAGE_CODE)
                for code, name in settings.LANGUAGES:
                     lang_buttons.append(InlineKeyboardButton(name, callback_data=f"lang:{code}"))
            except Exception as lang_e:
                logger.error(f"Error getting LANGUAGES from settings: {lang_e}")
                await edit_message_text(cq.message, _("❌ Ошибка загрузки доступных языков."))
                return MAIN_MENU

            buttons = [[btn] for btn in lang_buttons]
            buttons.append([InlineKeyboardButton(_("🔙 Назад"), callback_data="main:back_main")])

            await edit_message_text(cq.message, _("🌐 *Выберите язык интерфейса*"), reply_markup=InlineKeyboardMarkup(buttons), parse_mode=ParseMode.MARKDOWN)
            return LANG_MENU

        elif cmd == "search_emp":
            await edit_message_text(cq.message, _("🔎 Введите часть имени, фамилии, телефона или email для поиска сотрудника:"), reply_markup=None)
            return SEARCH_INPUT

        elif cmd == "stop":
            await edit_message_text(cq.message, _("✋ Диалог завершен."))
            context.user_data.clear()
            return ConversationHandler.END

        elif cmd == "back_main":
            return await start(update, context)

        else:
            logger.warning(f"Unknown command '{cmd}' received in MAIN_MENU.")
            await edit_message_text(cq.message, _("⚠️ Неизвестная команда."))
            return MAIN_MENU

    except (BadRequest, NetworkError, TimedOut) as e:
        logger.warning(f"Network/API error in main_menu_cb: {e}")
        await reply_text(update, _("⚠️ Ошибка сети или API. Попробуйте еще раз."))
        return MAIN_MENU
    except Exception as e:
        logger.exception(f"Unexpected error in main_menu_cb: {e}")
        await reply_text(update, _("⚠️ Произошла внутренняя ошибка. Попробуйте /start"))
        return ConversationHandler.END

# ===================================================================
#                         EVALUATION FLOW
# ===================================================================
async def eval_dept_cb(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Обрабатывает выбор отдела для оценки."""
    if not update.callback_query or not update.callback_query.data: return EVAL_DEPT
    cq = update.callback_query
    user_id = str(update.effective_user.id)
    logger.info(f"EVAL_DEPT callback '{cq.data}' from user {user_id}")
    try:
        try: await cq.answer()
        except BadRequest: pass

        parts = cq.data.split(":", 1)
        if len(parts) != 2 or not parts[1].isdigit():
             raise ValueError(f"Invalid callback data format: {cq.data}")
        did = int(parts[1])
        context.user_data["eval_dept_id"] = did
        logger.debug(f"User {user_id} selected department {did} for evaluation.")

        roles = await roles_in_dept(did) # Использует исправленную функцию
        if not roles:
            logger.warning(f"No roles found associated with users in department {did} for evaluation.")
            await edit_message_text(cq.message, _("❌ В выбранном отделе нет сотрудников с должностями, для которых настроена оценка. Выберите другой отдел."))
            return EVAL_DEPT

        context.user_data["eval_roles"] = {str(r.id): r.name for r in roles}
        buttons = [
            [InlineKeyboardButton(name, callback_data=f"eval_role:{rid}")]
            for rid, name in context.user_data["eval_roles"].items()
        ] + [[InlineKeyboardButton(_("🔙 Назад к отделам"), callback_data="main:new_eval")]]
        await edit_message_text(cq.message, _("👔 *Оценка:* Выберите должность"), reply_markup=InlineKeyboardMarkup(buttons), parse_mode=ParseMode.MARKDOWN)
        return EVAL_ROLE

    except (ValueError, IndexError) as e:
         logger.warning(f"Invalid callback data in eval_dept_cb: {cq.data} ({e})")
         await edit_message_text(cq.message, _("⚠️ Некорректный выбор отдела."))
         return EVAL_DEPT
    except (BadRequest, NetworkError, TimedOut) as e:
        logger.warning(f"Network/API error in eval_dept_cb: {e}")
        await reply_text(update, _("⚠️ Ошибка сети или API. Попробуйте выбрать отдел снова."))
        return EVAL_DEPT
    except Exception as e:
        logger.exception(f"Unexpected error in eval_dept_cb: {e}")
        await reply_text(update, _("⚠️ Внутренняя ошибка. Попробуйте /start"))
        return ConversationHandler.END

async def eval_role_cb(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Обрабатывает выбор должности для оценки."""
    if not update.callback_query or not update.callback_query.data: return EVAL_ROLE
    cq = update.callback_query
    user_id = str(update.effective_user.id)
    logger.info(f"EVAL_ROLE callback '{cq.data}' from user {user_id}")
    try:
        try: await cq.answer()
        except BadRequest: pass

        parts = cq.data.split(":", 1)
        if len(parts) != 2 or not parts[1].isdigit():
             raise ValueError(f"Invalid callback data format: {cq.data}")
        rid = int(parts[1])
        context.user_data["eval_role_id"] = rid
        logger.debug(f"User {user_id} selected role {rid} for evaluation.")

        dept_id = context.user_data.get("eval_dept_id")
        if not dept_id:
             logger.error(f"eval_dept_id not found in user_data for eval_role_cb. User: {user_id}")
             await edit_message_text(cq.message, _("❌ Ошибка: отдел не был выбран. Начните оценку заново с /start."))
             return ConversationHandler.END

        # Находим пользователей в ДАННОМ отделе с ДАННОЙ ролью
        # Используем USER_ROLES_M2M_NAME для фильтрации
        if not USER_ROLES_M2M_NAME:
            logger.error("USER_ROLES_M2M_NAME is not set. Cannot filter users by role.")
            await edit_message_text(cq.message, _("❌ Ошибка конфигурации: не удается отфильтровать сотрудников по роли."))
            return await start(update, context) # Возврат в главное меню

        users = await sync_to_async(list)(
            _get_user_queryset().filter(department_id=dept_id, roles__id=rid) # <--- ИЗМЕНЕНИЕ ЗДЕСЬ
        )
        
        if not users:
             logger.warning(f"No users found with role {rid} in department {dept_id} for evaluation.")
             # Сообщаем об отсутствии сотрудников с ЭТОЙ ролью в ЭТОМ отделе
             role_name = context.user_data.get("eval_roles", {}).get(str(rid), f"ID {rid}")
             dept_name = context.user_data.get("eval_deps", {}).get(str(dept_id), f"ID {dept_id}")
             await edit_message_text(cq.message, _("❌ В отделе '{dept}' нет сотрудников с должностью '{role}'. Выберите другую должность или отдел.").format(dept=dept_name, role=role_name))
             # Возвращаемся к выбору должности в этом же отделе
             roles = await roles_in_dept(dept_id)
             if roles:
                 context.user_data["eval_roles"] = {str(r.id): r.name for r in roles}
                 buttons = [ [InlineKeyboardButton(name, callback_data=f"eval_role:{r_id}")] for r_id, name in context.user_data["eval_roles"].items() ] + [[InlineKeyboardButton(_("🔙 Назад к отделам"), callback_data="main:new_eval")]]
                 await edit_message_text(cq.message, _("👔 *Оценка:* Выберите должность"), reply_markup=InlineKeyboardMarkup(buttons), parse_mode=ParseMode.MARKDOWN)
                 return EVAL_ROLE
             else: # Если ролей в отделе нет (странно, т.к. мы сюда попали)
                 return await start(update, context)


        context.user_data["eval_emps"] = {str(u.id): u.get_full_name() for u in users}
        buttons = [
            [InlineKeyboardButton(name, callback_data=f"eval_emp:{uid}")]
            for uid, name in context.user_data["eval_emps"].items()
        ] + [[InlineKeyboardButton(_("🔙 Назад к должностям"), callback_data=f"eval_dept:{dept_id}")]]
        await edit_message_text(cq.message, _("👤 *Оценка:* Выберите сотрудника"), reply_markup=InlineKeyboardMarkup(buttons), parse_mode=ParseMode.MARKDOWN)
        return EVAL_EMP

    except (ValueError, IndexError, KeyError) as e:
         logger.warning(f"Invalid data or state in eval_role_cb: {cq.data} ({e})")
         await edit_message_text(cq.message, _("⚠️ Ошибка данных. Попробуйте выбрать должность снова."))
         dept_id = context.user_data.get("eval_dept_id")
         if dept_id:
             roles = await roles_in_dept(dept_id)
             if roles:
                 context.user_data["eval_roles"] = {str(r.id): r.name for r in roles}
                 buttons = [ [InlineKeyboardButton(name, callback_data=f"eval_role:{r_id}")] for r_id, name in context.user_data["eval_roles"].items() ] + [[InlineKeyboardButton(_("🔙 Назад к отделам"), callback_data="main:new_eval")]]
                 await edit_message_text(cq.message, _("👔 *Оценка:* Выберите должность"), reply_markup=InlineKeyboardMarkup(buttons), parse_mode=ParseMode.MARKDOWN)
                 return EVAL_ROLE
         return await start(update, context)
    except (BadRequest, NetworkError, TimedOut) as e:
        logger.warning(f"Network/API error in eval_role_cb: {e}")
        await reply_text(update, _("⚠️ Ошибка сети или API. Попробуйте выбрать должность снова."))
        return EVAL_ROLE
    except Exception as e:
        logger.exception(f"Unexpected error in eval_role_cb: {e}")
        await reply_text(update, _("⚠️ Внутренняя ошибка. Попробуйте /start"))
        return ConversationHandler.END

async def eval_emp_cb(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Обрабатывает выбор сотрудника для оценки."""
    if not update.callback_query or not update.callback_query.data: return EVAL_EMP
    cq = update.callback_query
    user_id = str(update.effective_user.id)
    logger.info(f"EVAL_EMP callback '{cq.data}' from user {user_id}")
    try:
        try: await cq.answer()
        except BadRequest: pass

        parts = cq.data.split(":", 1)
        if len(parts) != 2 or not parts[1].isdigit():
             raise ValueError(f"Invalid callback data format: {cq.data}")
        uid_str = parts[1]
        uid = int(uid_str)

        role_id = context.user_data.get("eval_role_id")
        eval_emps = context.user_data.get("eval_emps", {})
        dept_id = context.user_data.get("eval_dept_id") # Для кнопки назад

        if not role_id or not eval_emps or uid_str not in eval_emps or not dept_id:
             logger.error(f"State error in eval_emp_cb for user {user_id}: role_id={role_id}, uid={uid_str} in eval_emps={uid_str in eval_emps}, dept_id={dept_id}")
             await edit_message_text(cq.message, _("❌ Ошибка: данные сессии оценки потеряны. Начните оценку заново с /start."))
             return ConversationHandler.END

        context.user_data["eval_emp_id"]   = uid
        context.user_data["eval_emp_name"] = eval_emps[uid_str]
        logger.debug(f"User {user_id} selected employee {uid} ('{eval_emps[uid_str]}') for evaluation.")

        qs = await get_questions(role_id)
        if not qs:
            logger.warning(f"No questions found for role {role_id}. Cannot start evaluation.")
            await edit_message_text(cq.message, _("❌ Для этой должности не настроены вопросы. Оценка невозможна."))
            # Возвращаемся к выбору сотрудника
            buttons = [ [InlineKeyboardButton(name, callback_data=f"eval_emp:{e_uid}")] for e_uid, name in eval_emps.items() ] + [[InlineKeyboardButton(_("🔙 Назад к должностям"), callback_data=f"eval_dept:{dept_id}")]]
            await edit_message_text(cq.message, _("👤 *Оценка:* Выберите сотрудника"), reply_markup=InlineKeyboardMarkup(buttons), parse_mode=ParseMode.MARKDOWN)
            return EVAL_EMP

        context.user_data["eval_qs"]      = qs
        context.user_data["eval_answers"] = []
        context.user_data["eval_idx"]     = 0
        logger.debug(f"Starting evaluation with {len(qs)} questions for user {user_id}.")

        question_text = f"❓ *Вопрос 1/{len(qs)}*\n\n{qs[0].text}"
        await edit_message_text(cq.message, question_text, parse_mode=ParseMode.MARKDOWN)
        return EVAL_Q

    except (ValueError, IndexError, KeyError) as e:
         logger.warning(f"Invalid data or state in eval_emp_cb: {cq.data} ({e})")
         await edit_message_text(cq.message, _("⚠️ Ошибка данных. Попробуйте выбрать сотрудника снова."))
         dept_id = context.user_data.get("eval_dept_id")
         eval_emps = context.user_data.get("eval_emps", {})
         if dept_id and eval_emps:
             buttons = [ [InlineKeyboardButton(name, callback_data=f"eval_emp:{e_uid}")] for e_uid, name in eval_emps.items()] + [[InlineKeyboardButton(_("🔙 Назад к должностям"), callback_data=f"eval_dept:{dept_id}")]]
             await edit_message_text(cq.message, _("👤 *Оценка:* Выберите сотрудника"), reply_markup=InlineKeyboardMarkup(buttons), parse_mode=ParseMode.MARKDOWN)
             return EVAL_EMP
         else:
             return await start(update, context)
    except (BadRequest, NetworkError, TimedOut) as e:
        logger.warning(f"Network/API error in eval_emp_cb: {e}")
        await reply_text(update, _("⚠️ Ошибка сети или API. Попробуйте выбрать сотрудника снова."))
        return EVAL_EMP
    except Exception as e:
        logger.exception(f"Unexpected error in eval_emp_cb: {e}")
        await reply_text(update, _("⚠️ Внутренняя ошибка. Попробуйте /start"))
        return ConversationHandler.END

async def eval_q_msg(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Обрабатывает текстовый ответ на вопрос оценки."""
    if not update.message or not update.message.text:
        logger.warning("eval_q_msg received non-text message.")
        await reply_text(update, _("⚠️ Пожалуйста, введите ответ текстом."))
        return EVAL_Q

    user_id = str(update.effective_user.id)
    logger.debug(f"Received answer from user {user_id} in EVAL_Q state.")
    try:
        txt = update.message.text.strip()
        idx = context.user_data.get("eval_idx")
        qs = context.user_data.get("eval_qs")
        answers = context.user_data.get("eval_answers")
        role_id = context.user_data.get("eval_role_id")
        emp_name = context.user_data.get("eval_emp_name")

        if idx is None or qs is None or answers is None or role_id is None or emp_name is None:
            logger.error(f"State error in eval_q_msg for user {user_id}: idx={idx}, qs is None={qs is None}, answers is None={answers is None}, role_id={role_id}, emp_name={emp_name}")
            await reply_text(update, _("❌ Ошибка: данные опроса потеряны. Начните оценку заново с /start."))
            context.user_data.clear()
            return ConversationHandler.END

        if idx >= len(qs):
             logger.warning(f"Received answer for idx {idx} but only {len(qs)} questions exist. Ignoring.")
             return EVAL_Q

        logger.debug(f"User {user_id} answered question {idx+1}: '{txt[:50]}...'")
        answers.append(None if txt == _("Пропустить") else txt)
        context.user_data["eval_idx"] += 1
        next_idx = context.user_data["eval_idx"]

        if next_idx < len(qs):
            question_text = f"❓ *Вопрос {next_idx + 1}/{len(qs)}*\n\n{qs[next_idx].text}"
            await reply_text(update, question_text, parse_mode=ParseMode.MARKDOWN)
            return EVAL_Q
        else:
            logger.info(f"Evaluation finished by user {user_id} for employee '{emp_name}'. Saving results.")
            tg_user = await get_or_create_tguser(user_id) # Получаем TelegramUser
            if not tg_user: # Проверяем только tg_user
                await reply_text(update, _("❌ Не удалось идентифицировать вас для сохранения оценки."))
                logger.error(f"Could not get tg_user for {user_id} at evaluation save.")
                return ConversationHandler.END

            responses_dict = {str(q.id): a for q, a in zip(qs, answers)}

            # ---- ИЗМЕНЕНИЕ ЗДЕСЬ ----
            data = {
                "evaluator_id": tg_user.id, # Передаем ID объекта TelegramUser
                "employee_name": emp_name,
                "role_id":       role_id,
                "responses":     responses_dict
            }
            # -------------------------

            # Проверка role_id (оставляем, т.к. он все еще нужен)
            if data["role_id"] is None:
                 logger.error(f"Cannot save evaluation, role_id is missing. User: {user_id}")
                 await reply_text(update, _("❌ Ошибка: Не удалось определить должность. Оценка не сохранена."))
                 return ConversationHandler.END # Или возврат в start

            logger.debug(f"Attempting to save evaluation with data: {data}") # Лог перед сохранением
            saved_eval = await save_eval(data) # Вызов save_eval
            if not saved_eval:
                await reply_text(update, _("❌ Произошла ошибка при сохранении оценки в базу данных. Администраторы уведомлены."))
                # Не переходим в start, даем шанс админам разобраться
                # TODO: Добавить уведомление администраторам о сбое сохранения
                return ConversationHandler.END

            # --- Отправка отчета HR (без изменений, но проверим получение имени) ---
            hr_chat_id = getattr(settings, 'HR_TELEGRAM_CHAT_ID', None)
            if hr_chat_id:
                 # Получаем имя оценщика через tg_user.user (предполагая, что user был предзагружен в get_or_create_tguser)
                 evaluator_name = tg_user.user.get_full_name() if hasattr(tg_user, 'user') and tg_user.user else f"TG User {tg_user.id}"
                 evaluator_tg_info = f"@{update.effective_user.username}" if update.effective_user.username else f"ID: {user_id}"
                 q_texts = {str(q.id): q.text for q in qs}
                 summary = (
                     f"📝 *Новая оценка сотрудника (ID: {saved_eval.id})*\n\n"
                     f"👤 Сотрудник: *{emp_name}*\n"
                     f"👨‍💻 Оценщик: {evaluator_name} ({evaluator_tg_info})\n"
                     f"\n*Ответы:*\n"
                 )
                 for q_id_str, answer_text in responses_dict.items():
                     question_text = q_texts.get(q_id_str, f"Вопрос ID {q_id_str}")
                     summary += f"  • _{question_text}_: {answer_text or '-'}\n"
                 await send_message(context, chat_id=hr_chat_id, text=summary, parse_mode=ParseMode.MARKDOWN)
                 logger.info(f"Evaluation summary sent to HR chat {hr_chat_id}.")
            else:
                 logger.warning("HR_TELEGRAM_CHAT_ID is not set in settings. Cannot send summary.")

            await reply_text(update, _("✅ Оценка успешно сохранена! Спасибо."))
            # ... (очистка user_data и возврат в start) ...
            keys_to_remove = ["eval_dept_id", "eval_roles", "eval_role_id", "eval_emps", "eval_emp_id", "eval_emp_name", "eval_qs", "eval_answers", "eval_idx"]
            for key in keys_to_remove:
                context.user_data.pop(key, None)
            logger.debug(f"Evaluation context data cleared for user {user_id}.")
            return await start(update, context)

    except (NetworkError, TimedOut) as e:
        logger.warning(f"Network error in eval_q_msg for user {user_id}: {e}")
        await reply_text(update, _("⚠️ Ошибка сети при обработке ответа. Попробуйте отправить ответ еще раз."))
        return EVAL_Q
    except KeyError as e:
         logger.exception(f"Missing key in user_data during eval_q_msg for user {user_id}: {e}")
         await reply_text(update, _("❌ Ошибка состояния опроса. Пожалуйста, начните заново с /start."))
         context.user_data.clear()
         return ConversationHandler.END
    except Exception as e:
        logger.exception(f"Unexpected error in eval_q_msg for user {user_id}: {e}")
        await reply_text(update, _("⚠️ Внутренняя ошибка при обработке ответа. Попробуйте /start"))
        context.user_data.clear()
        return ConversationHandler.END

# ===================================================================
#                         DEPARTMENTS & USERS
# ===================================================================
async def dept_cb(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Обрабатывает выбор отдела для просмотра сотрудников."""
    if not update.callback_query or not update.callback_query.data: return DEPT_LIST
    cq = update.callback_query
    user_id = str(update.effective_user.id)
    logger.info(f"DEPT_LIST callback '{cq.data}' from user {user_id}")
    try:
        try: await cq.answer()
        except BadRequest: pass

        parts = cq.data.split(":", 1)
        if len(parts) != 2 or not parts[1].isdigit():
             raise ValueError(f"Invalid callback data format: {cq.data}")
        did = int(parts[1])
        context.user_data["current_dept_id"] = did
        dept_name = context.user_data.get("dept_list", {}).get(str(did), f"ID {did}")
        logger.debug(f"User {user_id} selected department {did} ('{dept_name}') for viewing.")

        users = await users_in_dept(did) # Использует _get_user_queryset
        if not users:
            logger.warning(f"No users found in department {did}.")
            await edit_message_text(cq.message, _("❌ В этом отделе нет сотрудников."))
            deps = await all_departments()
            if deps:
                 context.user_data["dept_list"] = {str(d.id): d.name for d in deps}
                 buttons = [ [InlineKeyboardButton(name, callback_data=f"dept:{d_id}")] for d_id, name in list(context.user_data["dept_list"].items())[:15]] + [[InlineKeyboardButton(_("🔙 Назад"), callback_data="main:back_main")]]
                 if len(deps) > 15: buttons.insert(-1, [InlineKeyboardButton(_("... (еще отделы)"), callback_data="noop")])
                 await edit_message_text(cq.message, _("📋 *Отделы компании*"), reply_markup=InlineKeyboardMarkup(buttons), parse_mode=ParseMode.MARKDOWN)
                 return DEPT_LIST
            else:
                 return await start(update, context)

        context.user_data["dept_emps"] = {str(u.id): u for u in users}
        buttons = [
            [InlineKeyboardButton(u.get_full_name(), callback_data=f"dept_emp:{uid}")]
            for uid, u in list(context.user_data["dept_emps"].items())[:15]
        ] + [[InlineKeyboardButton(_("🔙 Назад к отделам"), callback_data="main:show_depts")]]
        if len(users) > 15:
             buttons.insert(-1, [InlineKeyboardButton(_("... (еще сотрудники)"), callback_data="noop")])

        await edit_message_text(cq.message, _("👥 *Сотрудники отдела '{dept}'*").format(dept=dept_name), reply_markup=InlineKeyboardMarkup(buttons), parse_mode=ParseMode.MARKDOWN)
        return DEPT_EMP_LIST

    except (ValueError, IndexError) as e:
         logger.warning(f"Invalid callback data in dept_cb: {cq.data} ({e})")
         await edit_message_text(cq.message, _("⚠️ Некорректный выбор отдела."))
         return DEPT_LIST
    except (BadRequest, NetworkError, TimedOut) as e:
        logger.warning(f"Network/API error in dept_cb: {e}")
        await reply_text(update, _("⚠️ Ошибка сети или API. Попробуйте выбрать отдел снова."))
        return DEPT_LIST
    except Exception as e:
        logger.exception(f"Unexpected error in dept_cb: {e}")
        await reply_text(update, _("⚠️ Внутренняя ошибка. Попробуйте /start"))
        return ConversationHandler.END

async def dept_emp_cb(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Показывает профиль сотрудника, выбранного из списка отдела."""
    if not update.callback_query or not update.callback_query.data: return DEPT_EMP_LIST
    cq = update.callback_query
    user_id = str(update.effective_user.id)
    logger.info(f"DEPT_EMP_LIST callback '{cq.data}' from user {user_id}")
    try:
        try: await cq.answer()
        except BadRequest: pass

        parts = cq.data.split(":", 1)
        if len(parts) != 2 or not parts[1].isdigit():
             raise ValueError(f"Invalid callback data format: {cq.data}")
        uid_str = parts[1]
        dept_emps = context.user_data.get("dept_emps", {})
        user = dept_emps.get(uid_str)

        if not user:
            logger.warning(f"User {uid_str} not found in dept_emps cache for user {user_id}. Fetching from DB.")
            user = await fetch_user_by_id(int(uid_str)) # Использует _get_user_queryset
            if not user:
                logger.error(f"Failed to fetch user {uid_str} from DB in dept_emp_cb.")
                await reply_text(update, _("❌ Не удалось найти информацию о сотруднике."))
                return DEPT_EMP_LIST

        await send_user_profile(cq.message, user)
        return DEPT_EMP_LIST

    except (ValueError, IndexError, KeyError) as e:
         logger.warning(f"Invalid data or state in dept_emp_cb: {cq.data} ({e})")
         await reply_text(update, _("⚠️ Ошибка данных при выборе сотрудника."))
         return DEPT_EMP_LIST
    except Exception as e:
        logger.exception(f"Unexpected error in dept_emp_cb: {e}")
        await reply_text(update, _("⚠️ Внутренняя ошибка при показе профиля."))
        return DEPT_EMP_LIST

async def all_users_cb(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Показывает профиль сотрудника, выбранного из общего списка."""
    if not update.callback_query or not update.callback_query.data: return EMP_LIST
    cq = update.callback_query
    user_id = str(update.effective_user.id)
    logger.info(f"EMP_LIST callback '{cq.data}' from user {user_id}")
    try:
        try: await cq.answer()
        except BadRequest: pass

        parts = cq.data.split(":", 1)
        if len(parts) != 2 or not parts[1].isdigit():
             raise ValueError(f"Invalid callback data format: {cq.data}")
        uid = int(parts[1])
        logger.debug(f"User {user_id} requested profile for user {uid} from all users list.")

        user = await fetch_user_by_id(uid) # Использует _get_user_queryset

        if not user:
            logger.error(f"Failed to fetch user {uid} from DB in all_users_cb.")
            await reply_text(update, _("❌ Не удалось найти информацию об этом сотруднике."))
            return EMP_LIST

        await send_user_profile(cq.message, user)
        return EMP_LIST

    except (ValueError, IndexError) as e:
         logger.warning(f"Invalid callback data in all_users_cb: {cq.data} ({e})")
         await reply_text(update, _("⚠️ Некорректный выбор сотрудника."))
         return EMP_LIST
    except Exception as e:
        logger.exception(f"Unexpected error in all_users_cb: {e}")
        await reply_text(update, _("⚠️ Внутренняя ошибка при показе профиля."))
        return EMP_LIST

# ===================================================================
#                         PROFILE MANAGEMENT
# ===================================================================
async def profile_menu_cb(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Обрабатывает нажатия кнопок в меню настроек профиля."""
    if not update.callback_query or not update.callback_query.data: return PROFILE_MENU
    cq = update.callback_query
    user_id = str(update.effective_user.id)
    logger.info(f"PROFILE_MENU callback '{cq.data}' from user {user_id}")
    try:
        try: await cq.answer()
        except BadRequest: pass

        parts = cq.data.split(":", 1)
        if len(parts) != 2 or parts[0] != "profile":
            raise ValueError(f"Invalid callback data format: {cq.data}")
        key = parts[1]

        if key == "photo":
            await edit_message_text(cq.message, _("📸 Отправьте фото, которое хотите установить как фото профиля (пожалуйста, *не* как документ)."), parse_mode=ParseMode.MARKDOWN)
            return PROFILE_UPLOAD_PHOTO
        elif key == "name":
            tg = await get_or_create_tguser(user_id)
            current_name = tg.user.first_name if tg and tg.user else _("ваше текущее имя")
            await edit_message_text(cq.message, _("✍️ Введите ваше новое имя (например, '{name}'):").format(name=current_name))
            return PROFILE_SET_NAME
        else:
             logger.warning(f"Unknown key '{key}' in profile_menu_cb.")
             await edit_message_text(cq.message, _("⚠️ Неизвестная опция."))
             return PROFILE_MENU

    except (ValueError, IndexError) as e:
         logger.warning(f"Invalid callback data in profile_menu_cb: {cq.data} ({e})")
         await edit_message_text(cq.message, _("⚠️ Некорректный запрос."))
         return PROFILE_MENU
    except (BadRequest, NetworkError, TimedOut) as e:
        logger.warning(f"Network/API error in profile_menu_cb: {e}")
        await reply_text(update, _("⚠️ Ошибка сети или API. Попробуйте снова."))
        return PROFILE_MENU
    except Exception as e:
        logger.exception(f"Unexpected error in profile_menu_cb: {e}")
        await reply_text(update, _("⚠️ Внутренняя ошибка. Попробуйте /start"))
        return ConversationHandler.END

async def profile_upload_photo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Обрабатывает получение фото для профиля."""
    if not update.message or not update.message.photo:
        await reply_text(update, _("⚠️ Это не фото. Пожалуйста, отправьте изображение."))
        return PROFILE_UPLOAD_PHOTO

    user_id = str(update.effective_user.id)
    logger.info(f"Received photo for profile update from user {user_id}.")
    photo = update.message.photo[-1]
    tg = await get_or_create_tguser(user_id)
    if not tg or not tg.user:
        logger.error(f"Cannot find user profile for {user_id} during photo upload.")
        await reply_text(update, _("❌ Ошибка: не удалось найти ваш профиль."))
        return ConversationHandler.END

    file = None
    downloaded_path = None
    file_operation_success = False
    try:
        logger.debug(f"Getting file for photo from user {user_id}")
        file = await photo.get_file()
        logger.debug(f"File info: id={file.file_id}, size={file.file_size}, path={file.file_path}")

        media_dir = os.path.join(settings.MEDIA_ROOT, 'profile_pics')
        os.makedirs(media_dir, exist_ok=True)

        file_ext = os.path.splitext(file.file_path)[1].lower() if file.file_path and '.' in file.file_path else '.jpg'
        allowed_extensions = ['.jpg', '.jpeg', '.png']
        if file_ext not in allowed_extensions:
             logger.warning(f"User {user_id} uploaded file with unsupported extension: {file_ext}")
             await reply_text(update, _("⚠️ Неподдерживаемый формат файла. Пожалуйста, отправьте JPG, JPEG или PNG."))
             return PROFILE_UPLOAD_PHOTO

        file_name = f"user_{tg.user.id}_{file.file_unique_id}{file_ext}"
        downloaded_path = os.path.join(media_dir, file_name)
        logger.debug(f"Downloading photo to: {downloaded_path}")

        await file.download_to_drive(downloaded_path)
        logger.info(f"Photo downloaded successfully to {downloaded_path}")

        rel_path = os.path.join('profile_pics', file_name).replace("\\", "/")
        logger.debug(f"Updating user image field with relative path: {rel_path}")

        if await update_user_image(tg.user, rel_path):
            await reply_text(update, _("✅ Фото профиля успешно обновлено!"))
            file_operation_success = True
        else:
            await reply_text(update, _("❌ Не удалось сохранить фото в вашем профиле (ошибка БД)."))
            if os.path.exists(downloaded_path):
                try:
                     os.remove(downloaded_path)
                     logger.info(f"Removed temporary file {downloaded_path} after DB save failure.")
                except OSError as remove_err:
                     logger.error(f"Failed to remove temporary file {downloaded_path}: {remove_err}")

        if file_operation_success:
            return await start(update, context)
        else:
             await reply_text(update, _("Попробуйте отправить фото еще раз."))
             return PROFILE_UPLOAD_PHOTO

    except (NetworkError, TimedOut) as e:
        logger.warning(f"Network error downloading/getting photo file for user {user_id}: {e}")
        await reply_text(update, _("⚠️ Ошибка сети при загрузке фото. Пожалуйста, попробуйте еще раз."))
        return PROFILE_UPLOAD_PHOTO
    except TelegramError as e:
        logger.exception(f"Telegram error with photo file processing for user {user_id}: {e}")
        await reply_text(update, _("⚠️ Произошла ошибка на стороне Telegram при обработке фото. Попробуйте другое фото или позже."))
        return PROFILE_UPLOAD_PHOTO
    except OSError as e:
        logger.exception(f"OS error saving photo to {downloaded_path} for user {user_id}: {e}")
        await reply_text(update, _("❌ Ошибка сервера при сохранении файла изображения. Администраторы уведомлены."))
        buttons = [ [InlineKeyboardButton(_("📸 Загрузить/сменить фото"), callback_data="profile:photo")], [InlineKeyboardButton(_("✍️ Изменить имя"), callback_data="profile:name")], [InlineKeyboardButton(_("🔙 Назад"), callback_data="main:back_main")],]
        await reply_text(update, _("⚙️ *Настройки профиля*"), reply_markup=InlineKeyboardMarkup(buttons), parse_mode=ParseMode.MARKDOWN)
        return PROFILE_MENU
    except Exception as e:
        logger.exception(f"Unexpected error in profile_upload_photo for user {user_id}: {e}")
        await reply_text(update, _("⚠️ Непредвиденная ошибка при загрузке фото."))
        return await start(update, context)

async def profile_set_name(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Обрабатывает ввод нового имени пользователя."""
    if not update.message or not update.message.text:
        await reply_text(update, _("⚠️ Пожалуйста, введите имя текстом."))
        return PROFILE_SET_NAME

    user_id = str(update.effective_user.id)
    logger.info(f"Received new name input from user {user_id}.")

    new_name = update.message.text.strip()
    if not new_name:
        await reply_text(update, _("⚠️ Имя не может быть пустым. Введите ваше имя:"))
        return PROFILE_SET_NAME
    if len(new_name) > 50:
        await reply_text(update, _("⚠️ Имя слишком длинное (максимум 50 символов). Введите имя покороче:"))
        return PROFILE_SET_NAME

    tg = await get_or_create_tguser(user_id)
    if not tg or not tg.user:
        await reply_text(update, _("❌ Ошибка: не удалось найти ваш профиль для сохранения имени."))
        logger.error(f"Profile not found or user not loaded for tg_id {user_id} in profile_set_name.")
        return ConversationHandler.END

    logger.debug(f"Attempting to update name for user {tg.user.id} to '{new_name}'.")
    try:
        if await update_user_name(tg.user, new_name):
            await reply_text(update, _("✅ Ваше имя успешно изменено на '{name}'!").format(name=new_name))
            return await start(update, context)
        else:
            await reply_text(update, _("❌ Не удалось обновить имя из-за ошибки сохранения в базе данных."))
            return PROFILE_SET_NAME
    except Exception as e:
        logger.exception(f"Unexpected error in profile_set_name saving for user {tg.user.id}: {e}")
        await reply_text(update, _("⚠️ Внутренняя ошибка при сохранении имени."))
        return await start(update, context)

# ===================================================================
#                         LANGUAGE SELECTION
# ===================================================================
async def lang_menu_cb(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Обрабатывает выбор языка интерфейса."""
    if not update.callback_query or not update.callback_query.data: return LANG_MENU
    cq = update.callback_query
    user_id = str(update.effective_user.id)
    logger.info(f"LANG_MENU callback '{cq.data}' from user {user_id}")
    try:
        try: await cq.answer()
        except BadRequest: pass

        parts = cq.data.split(":", 1)
        if len(parts) != 2: raise ValueError("Invalid callback data format")
        code = parts[1]

        supported_langs = dict(settings.LANGUAGES)
        if code not in supported_langs:
            logger.warning(f"User {user_id} selected unsupported language code: {code}")
            await edit_message_text(cq.message, _("⚠️ Выбран неподдерживаемый язык."))
            return LANG_MENU

        logger.debug(f"User {user_id} selected language '{code}'.")
        tg = await get_or_create_tguser(user_id)
        if not tg or not tg.user:
            logger.error(f"Cannot find user profile for {user_id} to save language setting.")
            await edit_message_text(cq.message, _("❌ Ошибка: не удалось найти ваш профиль для сохранения языка."))
            return ConversationHandler.END

        if await set_user_setting(tg.user, "language_code", code):
             lang_name = supported_langs.get(code, code)
             await edit_message_text(cq.message, _("✅ Язык интерфейса изменён на *{lang}*.").format(lang=lang_name), parse_mode=ParseMode.MARKDOWN)
        else:
            await edit_message_text(cq.message, _("❌ Не удалось сохранить настройку языка (ошибка сервера)."))

        return await start(update, context)

    except (ValueError, IndexError) as e:
         logger.warning(f"Invalid callback data in lang_menu_cb: {cq.data} ({e})")
         await edit_message_text(cq.message, _("⚠️ Некорректный выбор языка."))
         return LANG_MENU
    except (BadRequest, NetworkError, TimedOut) as e:
        logger.warning(f"Network/API error in lang_menu_cb: {e}")
        await reply_text(update, _("⚠️ Ошибка сети или API. Попробуйте выбрать язык снова."))
        return LANG_MENU
    except Exception as e:
        logger.exception(f"Unexpected error in lang_menu_cb: {e}")
        await reply_text(update, _("⚠️ Внутренняя ошибка. Попробуйте /start"))
        return ConversationHandler.END

# ===================================================================
#                         SEARCH FLOW
# ===================================================================
async def search_input_msg(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Обрабатывает ввод текста для поиска сотрудника."""
    if not update.message or not update.message.text:
        await reply_text(update, _("⚠️ Пожалуйста, введите запрос для поиска текстом."))
        return SEARCH_INPUT

    user_id = str(update.effective_user.id)
    q = update.message.text.strip()
    logger.info(f"User {user_id} submitted search query: '{q}'")

    if not q:
        await reply_text(update, _("⚠️ Запрос не может быть пустым. Введите имя, фамилию, телефон или email:"))
        return SEARCH_INPUT
    if len(q) < 3:
         await reply_text(update, _("⚠️ Запрос слишком короткий (минимум 3 символа)."))
         return SEARCH_INPUT

    try:
        users = await search_users(q) # Использует _get_user_queryset
        if not users:
            logger.info(f"No users found for query '{q}' by user {user_id}.")
            await reply_text(update, _("❌ По вашему запросу '{query}' совпадений не найдено.\nПопробуйте другой запрос или вернитесь в /start.").format(query=q))
            return SEARCH_INPUT

        logger.info(f"Found {len(users)} user(s) for query '{q}' by user {user_id}.")
        context.user_data["search_res_names"] = {str(u.id): u.get_full_name() for u in users}
        context.user_data["search_res_users"] = {str(u.id): u for u in users}

        buttons = [
            [InlineKeyboardButton(name, callback_data=f"search_res:{uid}")]
            for uid, name in list(context.user_data["search_res_names"].items())[:15]
        ] + [[InlineKeyboardButton(_("🔄 Новый поиск"), callback_data="main:search_emp")],
             [InlineKeyboardButton(_("🔙 Главное меню"), callback_data="main:back_main")]]
        if len(users) > 15:
             buttons.insert(-1, [InlineKeyboardButton(_("... (еще результаты)"), callback_data="noop")])

        await reply_text(
            update,
            _("🔍 *Результаты поиска по запросу '{query}'* ({count} найдено):").format(query=q, count=len(users)),
            reply_markup=InlineKeyboardMarkup(buttons),
            parse_mode=ParseMode.MARKDOWN
        )
        return SEARCH_RESULTS

    except (NetworkError, TimedOut) as e:
        logger.warning(f"Network error during user search for user {user_id}: {e}")
        await reply_text(update, _("⚠️ Ошибка сети во время поиска. Пожалуйста, попробуйте еще раз."))
        return SEARCH_INPUT
    except Exception as e:
        logger.exception(f"Unexpected error during search_input_msg for query '{q}' by user {user_id}: {e}")
        await reply_text(update, _("⚠️ Внутренняя ошибка сервера во время поиска. Попробуйте /start"))
        return ConversationHandler.END

async def search_results_cb(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Показывает профиль сотрудника, выбранного из результатов поиска."""
    if not update.callback_query or not update.callback_query.data: return SEARCH_RESULTS
    cq = update.callback_query
    user_id = str(update.effective_user.id)
    logger.info(f"SEARCH_RESULTS callback '{cq.data}' from user {user_id}")
    try:
        try: await cq.answer()
        except BadRequest: pass

        parts = cq.data.split(":", 1)
        if len(parts) != 2 or not parts[1].isdigit():
             raise ValueError(f"Invalid callback data format: {cq.data}")
        uid_str = parts[1]
        search_res_users = context.user_data.get("search_res_users", {})
        user = search_res_users.get(uid_str)

        if not user:
            logger.error(f"User {uid_str} was in search results but not found in user_data cache for user {user_id}. Fetching from DB.")
            user = await fetch_user_by_id(int(uid_str)) # Использует _get_user_queryset
            if not user:
                logger.error(f"Failed to fetch user {uid_str} from DB in search_results_cb.")
                await reply_text(update, _("❌ Ошибка: Не удалось загрузить данные выбранного сотрудника."))
                return SEARCH_RESULTS

        logger.debug(f"User {user_id} selected user {uid_str} from search results.")
        await send_user_profile(cq.message, user)
        return SEARCH_RESULTS

    except (ValueError, IndexError, KeyError) as e:
         logger.warning(f"Invalid data or state in search_results_cb: {cq.data} ({e})")
         await reply_text(update, _("⚠️ Ошибка данных при выборе результата поиска."))
         return SEARCH_RESULTS
    except Exception as e:
        logger.exception(f"Unexpected error in search_results_cb: {e}")
        await reply_text(update, _("⚠️ Внутренняя ошибка при показе профиля."))
        return SEARCH_RESULTS

# ===================================================================
#                         /stop and FALLBACKS
# ===================================================================
async def stop_conversation(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Завершает текущий диалог ConversationHandler."""
    user_id = update.effective_user.id if update.effective_user else "Unknown"
    logger.info(f"Stopping conversation for user {user_id}")
    context.user_data.clear()
    message_text = _("✋ Операция прервана.")
    next_state = ConversationHandler.END

    if update.message:
        await reply_text(update, message_text)
    elif update.callback_query:
        try:
           await update.callback_query.answer()
           await edit_message_text(update.callback_query.message, message_text)
        except BadRequest: pass
    else:
         logger.warning("stop_conversation called without message or callback_query.")

    return next_state

async def unexpected_input_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обрабатывает любое сообщение/callback, не пойманное другими хендлерами в ConversationHandler."""
    user_id = update.effective_user.id if update.effective_user else "Unknown"
    current_state = context.user_data.get(ConversationHandler.CURRENT_STATE) # Получаем текущее состояние
    text = _("Неожиданный ввод.")
    if update.message:
        logger.debug(f"Unhandled message received from user {user_id} in state {current_state}: '{update.message.text}'")
        text = _("Неожиданный ввод. Пожалуйста, используйте кнопки или команду /stop.")
        await reply_text(update, text) # Отвечаем на сообщение
    elif update.callback_query:
         logger.debug(f"Unhandled callback_query received from user {user_id} in state {current_state}: '{update.callback_query.data}'")
         # Отвечаем на callback, чтобы убрать "часики"
         try:
             # Не показываем alert, просто отвечаем
             await update.callback_query.answer(_("Неожиданное действие"))
         except BadRequest: pass
         # Можно отправить доп. сообщение, если нужно, но обычно не стоит спамить
         # await reply_text(update, _("Неожиданное нажатие кнопки."))
    else:
         logger.warning(f"unexpected_input_handler triggered by unknown update type from user {user_id} in state {current_state}")


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
            # Пытаемся ответить наиболее подходящим способом
            if update.callback_query:
                 await update.callback_query.answer(_("Произошла ошибка!"), show_alert=True)
                 # После alert можно попробовать отправить сообщение в чат
                 if update.effective_chat and hasattr(update, '_context'):
                     await send_message(update._context, update.effective_chat.id, error_message)
            elif update.effective_message: # Если есть сообщение (не callback)
                await reply_text(update, error_message)
            elif update.effective_chat and hasattr(update, '_context'): # Если нет сообщения, но есть чат
                await send_message(update._context, update.effective_chat.id, error_message)
            else:
                 logger.error("Cannot send error message to user: No effective_message or effective_chat/context in Update object.")
        except Exception as e_reply:
             logger.exception(f"Failed to send error message to user after an error: {e_reply}")
    else:
        logger.warning(f"Cannot send error message to user for update of type {type(update)}")


# ===================================================================
#                         HANDLERS REGISTRATION
# ===================================================================
def setup_handlers(application):
    """Настраивает и добавляет обработчики в приложение."""

    # Регулярные выражения для callback_data
    MAIN_CALLBACK = r"^main:(new_eval|show_depts|show_all_users|profile_settings|choose_lang|search_emp|stop|back_main)$"
    EVAL_DEPT_CALLBACK = r"^eval_dept:(\d+)$"
    EVAL_ROLE_CALLBACK = r"^eval_role:(\d+)$"
    EVAL_EMP_CALLBACK = r"^eval_emp:(\d+)$"
    DEPT_CALLBACK = r"^dept:(\d+)$"
    DEPT_EMP_CALLBACK = r"^dept_emp:(\d+)$"
    USER_CALLBACK = r"^user:(\d+)$"
    PROFILE_CALLBACK = r"^profile:(photo|name)$"
    LANG_CALLBACK = r"^lang:([a-zA-Z]{2}(?:-[a-zA-Z]{2})?)$"
    SEARCH_RES_CALLBACK = r"^search_res:(\d+)$"
    STOP_CALLBACK = r"^main:stop$"
    NOOP_CALLBACK = r"^noop$"

    # --- Conversation Handler ---
    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            MAIN_MENU: [
                CallbackQueryHandler(main_menu_cb, pattern=MAIN_CALLBACK),
                CallbackQueryHandler(lambda u, c: None, pattern=NOOP_CALLBACK),
            ],
            EVAL_DEPT:    [
                CallbackQueryHandler(eval_dept_cb, pattern=EVAL_DEPT_CALLBACK),
                CallbackQueryHandler(main_menu_cb, pattern=r"^main:new_eval$"), # Back button from eval_role_cb
                CallbackQueryHandler(start, pattern=r"^main:back_main$"), # Back button from this state
                CallbackQueryHandler(lambda u, c: None, pattern=NOOP_CALLBACK),
            ],
            EVAL_ROLE:    [
                CallbackQueryHandler(eval_role_cb, pattern=EVAL_ROLE_CALLBACK),
                CallbackQueryHandler(eval_dept_cb, pattern=EVAL_DEPT_CALLBACK), # Back button from eval_emp_cb
                CallbackQueryHandler(main_menu_cb, pattern=r"^main:new_eval$"), # Back button from this state
                CallbackQueryHandler(lambda u, c: None, pattern=NOOP_CALLBACK),
            ],
            EVAL_EMP:     [
                CallbackQueryHandler(eval_emp_cb,  pattern=EVAL_EMP_CALLBACK),
                # Back button from this state should go back to role selection for the *same* department
                CallbackQueryHandler(eval_role_cb, pattern=EVAL_ROLE_CALLBACK), # This might need adjustment based on how you get the role ID
                CallbackQueryHandler(eval_dept_cb, pattern=EVAL_DEPT_CALLBACK), # Or back to department selection? Check eval_emp_cb back button logic
                CallbackQueryHandler(lambda u, c: None, pattern=NOOP_CALLBACK),
            ],
            EVAL_Q:       [
                MessageHandler(filters.TEXT & ~filters.COMMAND, eval_q_msg),
                # Add explicit /stop handler? Fallback should catch it.
            ],
            DEPT_LIST:    [
                CallbackQueryHandler(dept_cb, pattern=DEPT_CALLBACK),
                CallbackQueryHandler(start, pattern=r"^main:back_main$"),
                CallbackQueryHandler(lambda u, c: None, pattern=NOOP_CALLBACK),
            ],
            DEPT_EMP_LIST:[
                CallbackQueryHandler(dept_emp_cb, pattern=DEPT_EMP_CALLBACK),
                CallbackQueryHandler(main_menu_cb, pattern=r"^main:show_depts$"), # Back button to department list
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
                 # Fallback handles /stop
            ],
            PROFILE_SET_NAME:     [
                MessageHandler(filters.TEXT & ~filters.COMMAND, profile_set_name),
                 # Fallback handles /stop
            ],
            LANG_MENU:    [
                CallbackQueryHandler(lang_menu_cb, pattern=LANG_CALLBACK),
                CallbackQueryHandler(start, pattern=r"^main:back_main$"),
            ],
            SEARCH_INPUT: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, search_input_msg),
                 # Fallback handles /stop
            ],
            SEARCH_RESULTS:[
                CallbackQueryHandler(search_results_cb, pattern=SEARCH_RES_CALLBACK),
                CallbackQueryHandler(main_menu_cb, pattern=r"^main:search_emp$"), # New search
                CallbackQueryHandler(start, pattern=r"^main:back_main$"), # Back to main menu
                CallbackQueryHandler(lambda u, c: None, pattern=NOOP_CALLBACK),
            ],
        },
        fallbacks=[
             CommandHandler("stop", stop_conversation),
             CallbackQueryHandler(stop_conversation, pattern=STOP_CALLBACK),
             # Catch any other message or callback inside the conversation
             MessageHandler(filters.ALL, unexpected_input_handler),
        ],
        allow_reentry=True,
        per_message=False,
    )

    application.add_handler(conv_handler)
    # Add the error handler last
    application.add_error_handler(error_handler)
    logger.info("All handlers set up successfully.")