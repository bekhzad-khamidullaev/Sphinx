# hrbot/management/commands/runbot.py

import os
import django
import logging
import asyncio
from django.core.management.base import BaseCommand
from django.conf import settings
from django.utils.translation import gettext as _
from django.db import models
from telegram import (
    Bot, Update, ReplyKeyboardMarkup, KeyboardButton, InputFile
)
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    ConversationHandler,
    filters,
    ContextTypes,
)
from asgiref.sync import sync_to_async

from hrbot.models import TelegramUser, Evaluation, Question
from hrbot.bitrix import send_evaluation_to_bitrix
from user_profiles.models import User, Department, Role

# Инициализация Django
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
django.setup()

logger = logging.getLogger(__name__)

# Состояния (0–14)
(
    MAIN_MENU,
    EVAL_DEPT, EVAL_ROLE, EVAL_EMP, EVAL_Q,
    DEPT_LIST, DEPT_EMP_LIST,
    EMP_LIST, EMP_CARD,
    PROFILE_MENU, PROFILE_UPLOAD_PHOTO, PROFILE_SET_NAME,
    LANG_MENU,
    SEARCH_INPUT, SEARCH_RESULTS
) = range(15)

# Асинхронные обёртки ORM
@sync_to_async
def get_or_create_tguser(tg_id: str) -> TelegramUser:
    user, _ = User.objects.get_or_create(username=f"user_{tg_id}")
    tg, _ = TelegramUser.objects.get_or_create(user=user, telegram_id=tg_id)
    return tg

@sync_to_async
def all_departments():
    return list(Department.objects.all())

@sync_to_async
def all_roles():
    return list(Role.objects.all())

@sync_to_async
def users_in_dept(dept_id):
    return list(User.objects.filter(department_id=dept_id))

@sync_to_async
def all_users():
    return list(User.objects.all())

@sync_to_async
def get_questions(role_id):
    return list(Question.objects.filter(role_id=role_id).order_by("order"))

@sync_to_async
def save_eval(ev_data):
    ev = Evaluation.objects.create(**ev_data)
    send_evaluation_to_bitrix(ev)

@sync_to_async
def search_users(q):
    return list(
        User.objects.filter(
            models.Q(first_name__icontains=q)
            | models.Q(last_name__icontains=q)
            | models.Q(phone_number__icontains=q)
            | models.Q(email__icontains=q)
        )
    )

@sync_to_async
def update_user_name(user, name):
    user.first_name = name
    user.save()

@sync_to_async
def update_user_image(user, image_path):
    user.image = image_path
    user.save()

@sync_to_async
def fetch_user_by_id(user_id):
    return User.objects.get(id=user_id)

@sync_to_async
def set_user_setting(user, key, value):
    user.set_setting(key, value)

# /start и главное меню
async def start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    tg = await get_or_create_tguser(str(update.effective_user.id))
    if not tg.approved:
        return await update.message.reply_text(_("⏳ Ожидайте подтверждения HR"))
    kb = [
        [KeyboardButton(_("Новая оценка"))],
        [KeyboardButton(_("Список отделов")), KeyboardButton(_("Список сотрудников"))],
        [KeyboardButton(_("Настройки профиля")), KeyboardButton(_("Выбор языка"))],
        [KeyboardButton(_("Поиск сотрудника"))],
        [KeyboardButton("/stop")],
    ]
    await update.message.reply_text(
        _("👋 Главное меню"),
        reply_markup=ReplyKeyboardMarkup(kb, resize_keyboard=True),
    )
    return MAIN_MENU

# Главное меню
async def main_menu(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    if text == _("Новая оценка"):
        deps = await all_departments()
        ctx.user_data["eval_deps"] = {d.name: d.id for d in deps}
        kb = [[KeyboardButton(d)] for d in ctx.user_data["eval_deps"]] + [[KeyboardButton(_("Назад"))]]
        await update.message.reply_text(
            _("🏢 Выберите отдел для оценки:"),
            reply_markup=ReplyKeyboardMarkup(kb, resize_keyboard=True),
        )
        return EVAL_DEPT

    if text == _("Список отделов"):
        deps = await all_departments()
        ctx.user_data["dept_list"] = {d.name: d.id for d in deps}
        kb = [[KeyboardButton(d)] for d in ctx.user_data["dept_list"]] + [[KeyboardButton(_("Назад"))]]
        await update.message.reply_text(
            _("📋 Отделы компании:"),
            reply_markup=ReplyKeyboardMarkup(kb, resize_keyboard=True),
        )
        return DEPT_LIST

    if text == _("Список сотрудников"):
        users = await all_users()
        ctx.user_data["all_users"] = {u.get_full_name(): u.id for u in users}
        kb = [[KeyboardButton(n)] for n in ctx.user_data["all_users"]] + [[KeyboardButton(_("Назад"))]]
        await update.message.reply_text(
            _("👥 Сотрудники:"),
            reply_markup=ReplyKeyboardMarkup(kb, resize_keyboard=True),
        )
        return EMP_LIST

    if text == _("Настройки профиля"):
        kb = [
            [KeyboardButton(_("Загрузить фото"))],
            [KeyboardButton(_("Изменить имя"))],
            [KeyboardButton(_("Назад"))],
        ]
        await update.message.reply_text(
            _("⚙️ Настройки профиля:"),
            reply_markup=ReplyKeyboardMarkup(kb, resize_keyboard=True),
        )
        return PROFILE_MENU

    if text == _("Выбор языка"):
        kb = [
            [KeyboardButton("Русский"), KeyboardButton("English"), KeyboardButton("O'zbek")],
            [KeyboardButton(_("Назад"))],
        ]
        await update.message.reply_text(
            _("🌐 Выберите язык:"),
            reply_markup=ReplyKeyboardMarkup(kb, resize_keyboard=True),
        )
        return LANG_MENU

    if text == _("Поиск сотрудника"):
        await update.message.reply_text(
            _("🔎 Введите имя, фамилию или телефон:"),
            reply_markup=ReplyKeyboardMarkup([[KeyboardButton(_("Назад"))]], resize_keyboard=True),
        )
        return SEARCH_INPUT

    if text == "/stop":
        await update.message.reply_text(_("✋ Операция прервана"))
        return ConversationHandler.END

    await update.message.reply_text(_("❌ Не знаю такой команды, выберите из меню"))
    return MAIN_MENU

# ======== НОВАЯ ОЦЕНКА ========
async def eval_dept(update: Update, ctx):
    if update.message.text == _("Назад"):
        return await start(update, ctx)
    sel = update.message.text
    if sel not in ctx.user_data.get("eval_deps", {}):
        return await update.message.reply_text(_("❌ Выберите отдел из списка"))
    ctx.user_data["eval_dept_id"] = ctx.user_data["eval_deps"][sel]

    roles = await all_roles()
    ctx.user_data["eval_roles"] = {r.name: r.id for r in roles}
    kb = [[KeyboardButton(r)] for r in ctx.user_data["eval_roles"]] + [[KeyboardButton(_("Назад"))]]
    await update.message.reply_text(
        _("👔 Выберите должность:"),
        reply_markup=ReplyKeyboardMarkup(kb, resize_keyboard=True),
    )
    return EVAL_ROLE

async def eval_role(update: Update, ctx):
    if update.message.text == _("Назад"):
        return await start(update, ctx)
    sel = update.message.text
    if sel not in ctx.user_data.get("eval_roles", {}):
        return await update.message.reply_text(_("❌ Выберите должность из списка"))
    ctx.user_data["eval_role_id"] = ctx.user_data["eval_roles"][sel]

    users = await users_in_dept(ctx.user_data["eval_dept_id"])
    ctx.user_data["eval_emps"] = {u.get_full_name(): u.id for u in users}
    kb = [[KeyboardButton(n)] for n in ctx.user_data["eval_emps"]] + [[KeyboardButton(_("Назад"))]]
    await update.message.reply_text(
        _("👤 Выберите сотрудника:"),
        reply_markup=ReplyKeyboardMarkup(kb, resize_keyboard=True),
    )
    return EVAL_EMP

async def eval_emp(update: Update, ctx):
    if update.message.text == _("Назад"):
        return await eval_dept(update, ctx)
    sel = update.message.text
    if sel not in ctx.user_data.get("eval_emps", {}):
        return await update.message.reply_text(_("❌ Выберите сотрудника из списка"))
    ctx.user_data["eval_emp_name"] = sel

    qs = await get_questions(ctx.user_data["eval_role_id"])
    ctx.user_data["eval_qs"] = qs
    ctx.user_data["eval_answers"] = []
    ctx.user_data["eval_idx"] = 0

    await update.message.reply_text(
        qs[0].text,
        reply_markup=ReplyKeyboardMarkup(
            [[KeyboardButton(_("Пропустить"))], [KeyboardButton(_("Назад"))]],
            resize_keyboard=True,
        ),
    )
    return EVAL_Q

async def eval_q(update: Update, ctx):
    txt = update.message.text
    idx = ctx.user_data["eval_idx"]
    qs = ctx.user_data["eval_qs"]

    if txt == _("Назад"):
        if idx > 0:
            ctx.user_data["eval_idx"] -= 1
        return await update.message.reply_text(qs[ctx.user_data["eval_idx"]].text)

    if txt != _("Пропустить"):
        ctx.user_data["eval_answers"].append(txt)
    else:
        ctx.user_data["eval_answers"].append(None)

    ctx.user_data["eval_idx"] += 1
    if ctx.user_data["eval_idx"] < len(qs):
        return await update.message.reply_text(
            qs[ctx.user_data["eval_idx"]].text,
            reply_markup=ReplyKeyboardMarkup(
                [[KeyboardButton(_("Пропустить"))], [KeyboardButton(_("Назад"))]],
                resize_keyboard=True,
            ),
        )

    data = {
        "evaluator_id": (await get_or_create_tguser(str(update.effective_user.id))).id,
        "employee_name": ctx.user_data["eval_emp_name"],
        "role_id": ctx.user_data["eval_role_id"],
        "responses": {q.text: a for q, a in zip(qs, ctx.user_data["eval_answers"])},
    }
    await save_eval(data)

    hr = settings.HR_TELEGRAM_CHAT_ID
    summary = _("📝 Оценка") + f": {ctx.user_data['eval_emp_name']}\n"
    for q, a in zip(qs, ctx.user_data["eval_answers"]):
        summary += f"• {q.text}: {a or '-'}\n"
    Bot(settings.TELEGRAM_BOT_TOKEN).send_message(chat_id=hr, text=summary)

    await update.message.reply_text(_("✅ Оценка сохранена"))
    return await start(update, ctx)

# ======== СПИСОК ОТДЕЛОВ ========
async def dept_list(update: Update, ctx):
    if update.message.text == _("Назад"):
        return await start(update, ctx)
    depts = ctx.user_data["dept_list"]
    sel = update.message.text
    if sel not in depts:
        return await update.message.reply_text(_("❌ Выберите отдел из списка"))
    dept_id = depts[sel]
    users = await users_in_dept(dept_id)
    ctx.user_data["dept_emps"] = {u.get_full_name(): u for u in users}
    kb = [[KeyboardButton(u.get_full_name())] for u in users] + [[KeyboardButton(_("Назад"))]]
    await update.message.reply_text(
        _("👥 Сотрудники отдела: ") + sel,
        reply_markup=ReplyKeyboardMarkup(kb, resize_keyboard=True),
    )
    return DEPT_EMP_LIST

async def dept_emp_list(update: Update, ctx):
    if update.message.text == _("Назад"):
        return await dept_list(update, ctx)
    name = update.message.text
    emps = ctx.user_data["dept_emps"]
    if name not in emps:
        return await update.message.reply_text(_("❌ Выберите сотрудника"))
    u = emps[name]
    text = (
        f"{u.get_full_name()}\n"
        f"{u.job_title or ''}\n"
        f"📞 {u.phone_number or '-'}\n"
        f"✉️ {u.email or '-'}"
    )
    if u.image:
        with open(u.image.path, "rb") as f:
            await update.message.reply_photo(photo=f, caption=text)
    else:
        await update.message.reply_text(text)
    return DEPT_EMP_LIST

# ======== СПИСОК ВСЕХ СОТРУДНИКОВ ========
async def emp_list(update: Update, ctx):
    if update.message.text == _("Назад"):
        return await start(update, ctx)
    name = update.message.text
    all_u = ctx.user_data["all_users"]
    if name not in all_u:
        return await update.message.reply_text(_("❌ Выберите сотрудника"))
    u = await fetch_user_by_id(all_u[name])
    text = (
        f"{u.get_full_name()}\n"
        f"{u.job_title or ''}\n"
        f"📞 {u.phone_number or '-'}\n"
        f"✉️ {u.email or '-'}"
    )
    if u.image:
        with open(u.image.path, "rb") as f:
            await update.message.reply_photo(photo=f, caption=text)
    else:
        await update.message.reply_text(text)
    return EMP_LIST

# ======== НАСТРОЙКИ ПРОФИЛЯ ========
async def profile_menu(update: Update, ctx):
    text = update.message.text
    if text == _("Загрузить фото"):
        await update.message.reply_text(_("📸 Отправьте своё фото"))
        return PROFILE_UPLOAD_PHOTO
    if text == _("Изменить имя"):
        await update.message.reply_text(_("✍️ Введите новое имя"))
        return PROFILE_SET_NAME
    if text == _("Назад"):
        return await start(update, ctx)
    return PROFILE_MENU

async def profile_upload_photo(update: Update, ctx):
    photo = update.message.photo[-1]
    tg = await get_or_create_tguser(str(update.effective_user.id))
    file = await photo.get_file()
    path = os.path.join(settings.MEDIA_ROOT, f"profile_{tg.id}.jpg")
    await file.download_to_drive(path)
    image_path = f"profile_pics/{os.path.basename(path)}"
    await update_user_image(tg.user, image_path)
    await update.message.reply_text(_("✅ Фото обновлено"))
    return PROFILE_MENU

async def profile_set_name(update: Update, ctx):
    new_name = update.message.text.strip()
    tg = await get_or_create_tguser(str(update.effective_user.id))
    await update_user_name(tg.user, new_name)
    await update.message.reply_text(_("✅ Имя обновлено"))
    return PROFILE_MENU

# ======== ВЫБОР ЯЗЫКА ========
async def lang_menu(update: Update, ctx):
    text = update.message.text
    code_map = {"Русский": "ru", "English": "en", "O'zbek": "uz"}
    code = code_map.get(text)
    if code:
        tg = await get_or_create_tguser(str(update.effective_user.id))
        await set_user_setting(tg.user, "lang", code)
        await update.message.reply_text(_("✅ Язык изменён"))
    return await start(update, ctx)

# ======== ПОИСК СОТРУДНИКОВ ========
async def search_input(update: Update, ctx):
    if update.message.text == _("Назад"):
        return await start(update, ctx)
    users = await search_users(update.message.text.strip())
    if not users:
        return await update.message.reply_text(_("❌ Никого не найдено"))
    ctx.user_data["search_res"] = {u.get_full_name(): u.id for u in users}
    kb = [[KeyboardButton(n)] for n in ctx.user_data["search_res"]] + [[KeyboardButton(_("Назад"))]]
    await update.message.reply_text(
        _("🔍 Результаты поиска:"),
        reply_markup=ReplyKeyboardMarkup(kb, resize_keyboard=True),
    )
    return SEARCH_RESULTS

async def search_results(update: Update, ctx):
    if update.message.text == _("Назад"):
        return await start(update, ctx)
    name = update.message.text
    res = ctx.user_data["search_res"]
    if name not in res:
        return await update.message.reply_text(_("❌ Выберите сотрудника"))
    u = await fetch_user_by_id(res[name])
    text = (
        f"{u.get_full_name()}\n"
        f"{u.job_title or ''}\n"
        f"📞 {u.phone_number or '-'}\n"
        f"✉️ {u.email or '-'}"
    )
    if u.image:
        with open(u.image.path, "rb") as f:
            await update.message.reply_photo(photo=f, caption=text)
    else:
        await update.message.reply_text(text)
    return SEARCH_RESULTS

# /stop
async def stop(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(_("✋ Операция прервана"))
    return ConversationHandler.END

# Команда запуска
class Command(BaseCommand):
    help = "Запускает HR-бота"

    def handle(self, *args, **opts):
        # удаляем webhook перед polling
        asyncio.run(Bot(settings.TELEGRAM_BOT_TOKEN).delete_webhook(drop_pending_updates=True))

        app = ApplicationBuilder().token(settings.TELEGRAM_BOT_TOKEN).build()

        conv = ConversationHandler(
            entry_points=[CommandHandler("start", start)],
            states={
                MAIN_MENU:      [MessageHandler(filters.TEXT & ~filters.COMMAND, main_menu)],
                EVAL_DEPT:      [MessageHandler(filters.TEXT & ~filters.COMMAND, eval_dept)],
                EVAL_ROLE:      [MessageHandler(filters.TEXT & ~filters.COMMAND, eval_role)],
                EVAL_EMP:       [MessageHandler(filters.TEXT & ~filters.COMMAND, eval_emp)],
                EVAL_Q:         [MessageHandler(filters.TEXT & ~filters.COMMAND, eval_q)],
                DEPT_LIST:      [MessageHandler(filters.TEXT & ~filters.COMMAND, dept_list)],
                DEPT_EMP_LIST:  [MessageHandler(filters.TEXT & ~filters.COMMAND, dept_emp_list)],
                EMP_LIST:       [MessageHandler(filters.TEXT & ~filters.COMMAND, emp_list)],
                PROFILE_MENU:         [MessageHandler(filters.TEXT & ~filters.COMMAND, profile_menu)],
                PROFILE_UPLOAD_PHOTO: [MessageHandler(filters.PHOTO, profile_upload_photo)],
                PROFILE_SET_NAME:     [MessageHandler(filters.TEXT & ~filters.COMMAND, profile_set_name)],
                LANG_MENU:            [MessageHandler(filters.TEXT & ~filters.COMMAND, lang_menu)],
                SEARCH_INPUT:         [MessageHandler(filters.TEXT & ~filters.COMMAND, search_input)],
                SEARCH_RESULTS:       [MessageHandler(filters.TEXT & ~filters.COMMAND, search_results)],
            },
            fallbacks=[CommandHandler("stop", stop)],
            allow_reentry=True,
        )

        app.add_handler(conv)
        print("🚀 Бот запущен")
        app.run_polling()
        print("🛑 Бот остановлен")