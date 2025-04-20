# hrbot/bot/utils.py

import logging
import os
from django.conf import settings
from django.utils.translation import gettext as _
from telegram import Update, InputFile
from telegram.constants import ParseMode
from telegram.error import BadRequest, NetworkError, TelegramError, TimedOut
from telegram.ext import ContextTypes
from asgiref.sync import sync_to_async # Импортируем для асинхронных вызовов внутри

# Импортируем модели для type hinting и проверки полей
try:
    from user_profiles.models import User
    from hrbot.bot.db import USER_ROLE_FIELD_NAME, USER_ROLES_M2M_NAME # Импортируем константы
except ImportError:
    User = None
    USER_ROLE_FIELD_NAME = None
    USER_ROLES_M2M_NAME = None

logger = logging.getLogger(__name__)

# --- Функции отправки/редактирования ---

async def send_message(context: ContextTypes.DEFAULT_TYPE, chat_id: int, text: str, **kwargs):
    """Безопасная отправка сообщения с обработкой ошибок."""
    try:
        await context.bot.send_message(chat_id=chat_id, text=text, **kwargs)
        return True
    except (NetworkError, TimedOut) as e: logger.warning(f"Network error sending message to {chat_id}: {e}")
    except BadRequest as e: logger.warning(f"Bad request sending message to {chat_id}: {e}")
    except TelegramError as e: logger.exception(f"Telegram error sending message to {chat_id}: {e}")
    except Exception as e: logger.exception(f"Unexpected error sending message to {chat_id}: {e}")
    return False

async def edit_message_text(message, text: str, **kwargs):
    """Безопасное редактирование сообщения с обработкой ошибок."""
    kwargs.pop('context', None)
    try:
        await message.edit_text(text=text, **kwargs)
        return True
    except BadRequest as e:
        if "Message is not modified" in str(e): logger.debug(f"Message {message.message_id} not modified."); return True
        logger.warning(f"Bad request editing message {message.message_id}: {e}")
    except (NetworkError, TimedOut) as e: logger.warning(f"Network error editing message {message.message_id}: {e}")
    except TelegramError as e: logger.exception(f"Telegram error editing message {message.message_id}: {e}")
    except Exception as e: logger.exception(f"Unexpected error editing message {message.message_id}: {e}")
    return False

async def reply_text(update: Update, text: str, **kwargs):
    """
    Безопасный ответ на сообщение.
    Принимает дополнительные именованные аргументы (kwargs).
    """
    if not update: logger.error("reply_text called with None update object."); return False
    target_message = update.message or (update.callback_query and update.callback_query.message)
    if target_message:
        try:
            await target_message.reply_text(text=text, **kwargs); return True
        except (NetworkError, TimedOut) as e: logger.warning(f"Network error replying to message {target_message.message_id}: {e}")
        except BadRequest as e: logger.warning(f"Bad request replying to message {target_message.message_id}: {e}")
        except TelegramError as e: logger.exception(f"Telegram error replying to message {target_message.message_id}: {e}")
        except TypeError as e: logger.exception(f"TypeError replying to message {target_message.message_id}: Invalid kwargs? {kwargs} - {e}")
        except Exception as e: logger.exception(f"Unexpected error replying to message {target_message.message_id}: {e}")
    elif update.effective_chat and hasattr(update, '_context'):
         logger.warning("Replying via send_message as target message is unavailable.")
         await send_message( context=update._context, chat_id=update.effective_chat.id, text=text, **kwargs); return True
    else: logger.error("Cannot reply: No message, or no effective_chat/context in update.")
    return False


# --- Функция отправки профиля ---

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
                logger.debug(f"Roles for user {user.id} prefetched: {len(roles_list)}")
                if roles_list:
                    job_title = ", ".join([r.name for r in roles_list])
            elif await sync_to_async(m2m_manager.exists)(): # Если не предзагружено, делаем доп. запрос (асинхронно!)
                 logger.warning(f"Roles for user {user.id} were not prefetched. Making extra DB query.")
                 roles_list = await sync_to_async(list)(m2m_manager.all())
                 job_title = ", ".join([r.name for r in roles_list])
            else:
                 logger.debug(f"No roles found for user {user.id} via M2M manager.")


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
                        await target_message.reply_photo(
                            photo=InputFile(f),
                            caption=text,
                            parse_mode=ParseMode.MARKDOWN
                        )
                        photo_sent = True
                else:
                     logger.warning(f"User image file not found at expected path: {image_full_path} for user {user.id}")
            except FileNotFoundError: logger.warning(f"FileNotFoundError on open: {image_full_path} for user {user.id}")
            except PermissionError: logger.error(f"Permission error reading image file: {image_full_path} for user {user.id}")
            except BadRequest as e: logger.warning(f"BadRequest sending photo for user {user.id}: {e}. Sending text instead."); photo_sent = False
            except (NetworkError, TimedOut) as e: logger.warning(f"Network error sending photo for user {user.id}: {e}. Sending text instead."); photo_sent = False
            except TelegramError as e: logger.exception(f"Telegram error sending photo for user {user.id}: {e}. Sending text instead."); photo_sent = False
            except Exception as e: logger.exception(f"Unexpected error sending photo for user {user.id}: {e}. Sending text instead."); photo_sent = False
        else:
            logger.debug(f"User {user.id} has no image or image path.")

        if not photo_sent:
            logger.debug(f"Sending text profile for user {user.id} as photo was not sent.")
            await target_message.reply_text(text, parse_mode=ParseMode.MARKDOWN)

    except Exception as e:
        logger.exception(f"Unexpected error in send_user_profile for user {user.id}: {e}")
        await target_message.reply_text(_("⚠️ Произошла ошибка при отображении профиля."))