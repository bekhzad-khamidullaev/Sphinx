# hrbot/bot/handlers/profile.py
import logging
import os
from django.conf import settings
from django.utils.translation import gettext as _
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ParseMode
from telegram.error import BadRequest, NetworkError, TimedOut, TelegramError
from telegram.ext import ContextTypes, ConversationHandler

from ..constants import PROFILE_MENU, PROFILE_UPLOAD_PHOTO, PROFILE_SET_NAME, CB_MAIN, CB_PROFILE
from ..db import get_or_create_tguser, update_user_image, update_user_name
from ..utils import reply_text, edit_message_text
from .common import start # Импортируем start для возврата в меню

logger = logging.getLogger(__name__)

async def profile_menu_cb(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if not update.callback_query or not update.callback_query.data: return PROFILE_MENU
    cq = update.callback_query; user_id = str(update.effective_user.id)
    logger.info(f"PROFILE_MENU callback '{cq.data}' from user {user_id}")
    try:
        try: await cq.answer()
        except BadRequest: pass
        parts = cq.data.split(":", 1)
        if len(parts) != 2 or parts[0] != CB_PROFILE: raise ValueError(f"Invalid callback data format: {cq.data}")
        key = parts[1]
        if key == "photo": await edit_message_text(cq.message, _("📸 Отправьте фото, которое хотите установить как фото профиля (пожалуйста, *не* как документ)."), parse_mode=ParseMode.MARKDOWN); return PROFILE_UPLOAD_PHOTO
        elif key == "name": tg = await get_or_create_tguser(user_id); current_name = tg.user.first_name if tg and tg.user else _("ваше текущее имя"); await edit_message_text(cq.message, _("✍️ Введите ваше новое имя (например, '{name}'):").format(name=current_name)); return PROFILE_SET_NAME
        else: logger.warning(f"Unknown key '{key}' in profile_menu_cb."); await edit_message_text(cq.message, _("⚠️ Неизвестная опция.")); return PROFILE_MENU
    except (ValueError, IndexError) as e: logger.warning(f"Invalid callback data in profile_menu_cb: {cq.data} ({e})"); await edit_message_text(cq.message, _("⚠️ Некорректный запрос.")); return PROFILE_MENU
    except (BadRequest, NetworkError, TimedOut) as e: logger.warning(f"Network/API error in profile_menu_cb: {e}"); await reply_text(update, _("⚠️ Ошибка сети или API. Попробуйте снова.")); return PROFILE_MENU
    except Exception as e: logger.exception(f"Unexpected error in profile_menu_cb: {e}"); await reply_text(update, _("⚠️ Внутренняя ошибка. Попробуйте /start")); return ConversationHandler.END


async def profile_upload_photo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if not update.message or not update.message.photo: await reply_text(update, _("⚠️ Это не фото. Пожалуйста, отправьте изображение.")); return PROFILE_UPLOAD_PHOTO
    user_id = str(update.effective_user.id); logger.info(f"Received photo for profile update from user {user_id}.")
    photo = update.message.photo[-1]; tg = await get_or_create_tguser(user_id)
    if not tg or not tg.user: logger.error(f"Cannot find user profile for {user_id} during photo upload."); await reply_text(update, _("❌ Ошибка: не удалось найти ваш профиль.")); return ConversationHandler.END
    file = None; downloaded_path = None; file_operation_success = False
    try:
        logger.debug(f"Getting file for photo from user {user_id}"); file = await photo.get_file()
        logger.debug(f"File info: id={file.file_id}, size={file.file_size}, path={file.file_path}")
        media_dir = os.path.join(settings.MEDIA_ROOT, 'profile_pics'); os.makedirs(media_dir, exist_ok=True)
        file_ext = os.path.splitext(file.file_path)[1].lower() if file.file_path and '.' in file.file_path else '.jpg'; allowed_extensions = ['.jpg', '.jpeg', '.png']
        if file_ext not in allowed_extensions: logger.warning(f"User {user_id} uploaded file with unsupported extension: {file_ext}"); await reply_text(update, _("⚠️ Неподдерживаемый формат файла. Пожалуйста, отправьте JPG, JPEG или PNG.")); return PROFILE_UPLOAD_PHOTO
        file_name = f"user_{tg.user.id}_{file.file_unique_id}{file_ext}"; downloaded_path = os.path.join(media_dir, file_name)
        logger.debug(f"Downloading photo to: {downloaded_path}"); await file.download_to_drive(downloaded_path); logger.info(f"Photo downloaded successfully to {downloaded_path}")
        rel_path = os.path.join('profile_pics', file_name).replace("\\", "/"); logger.debug(f"Updating user image field with relative path: {rel_path}")
        if await update_user_image(tg.user, rel_path): await reply_text(update, _("✅ Фото профиля успешно обновлено!")); file_operation_success = True
        else:
            await reply_text(update, _("❌ Не удалось сохранить фото в вашем профиле (ошибка БД)."))
            if os.path.exists(downloaded_path):
                try: os.remove(downloaded_path); logger.info(f"Removed temporary file {downloaded_path} after DB save failure.")
                except OSError as remove_err: logger.error(f"Failed to remove temporary file {downloaded_path}: {remove_err}")
        if file_operation_success: return await start(update, context)
        else: await reply_text(update, _("Попробуйте отправить фото еще раз.")); return PROFILE_UPLOAD_PHOTO
    except (NetworkError, TimedOut) as e: logger.warning(f"Network error downloading/getting photo file for user {user_id}: {e}"); await reply_text(update, _("⚠️ Ошибка сети при загрузке фото. Пожалуйста, попробуйте еще раз.")); return PROFILE_UPLOAD_PHOTO
    except TelegramError as e: logger.exception(f"Telegram error with photo file processing for user {user_id}: {e}"); await reply_text(update, _("⚠️ Произошла ошибка на стороне Telegram при обработке фото. Попробуйте другое фото или позже.")); return PROFILE_UPLOAD_PHOTO
    except OSError as e:
        logger.exception(f"OS error saving photo to {downloaded_path} for user {user_id}: {e}"); await reply_text(update, _("❌ Ошибка сервера при сохранении файла изображения. Администраторы уведомлены."))
        buttons = [ [InlineKeyboardButton(_("📸 Загрузить/сменить фото"), callback_data=f"{CB_PROFILE}:photo")], [InlineKeyboardButton(_("✍️ Изменить имя"), callback_data=f"{CB_PROFILE}:name")], [InlineKeyboardButton(_("🔙 Назад"), callback_data=f"{CB_MAIN}:back_main")],]; await reply_text(update, _("⚙️ *Настройки профиля*"), reply_markup=InlineKeyboardMarkup(buttons), parse_mode=ParseMode.MARKDOWN); return PROFILE_MENU
    except Exception as e: logger.exception(f"Unexpected error in profile_upload_photo for user {user_id}: {e}"); await reply_text(update, _("⚠️ Непредвиденная ошибка при загрузке фото.")); return await start(update, context)


async def profile_set_name(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if not update.message or not update.message.text: await reply_text(update, _("⚠️ Пожалуйста, введите имя текстом.")); return PROFILE_SET_NAME
    user_id = str(update.effective_user.id); logger.info(f"Received new name input from user {user_id}.")
    new_name = update.message.text.strip()
    if not new_name: await reply_text(update, _("⚠️ Имя не может быть пустым. Введите ваше имя:")); return PROFILE_SET_NAME
    if len(new_name) > 50: await reply_text(update, _("⚠️ Имя слишком длинное (максимум 50 символов). Введите имя покороче:")); return PROFILE_SET_NAME
    tg = await get_or_create_tguser(user_id)
    if not tg or not tg.user: await reply_text(update, _("❌ Ошибка: не удалось найти ваш профиль для сохранения имени.")); logger.error(f"Profile not found or user not loaded for tg_id {user_id} in profile_set_name."); return ConversationHandler.END
    logger.debug(f"Attempting to update name for user {tg.user.id} to '{new_name}'.")
    try:
        if await update_user_name(tg.user, new_name): await reply_text(update, _("✅ Ваше имя успешно изменено на '{name}'!").format(name=new_name)); return await start(update, context)
        else: await reply_text(update, _("❌ Не удалось обновить имя из-за ошибки сохранения в базе данных.")); return PROFILE_SET_NAME
    except Exception as e: logger.exception(f"Unexpected error in profile_set_name saving for user {tg.user.id}: {e}"); await reply_text(update, _("⚠️ Внутренняя ошибка при сохранении имени.")); return await start(update, context)