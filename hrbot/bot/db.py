# hrbot/bot/db.py
# -*- coding: utf-8 -*-
import logging
from django.db import models, IntegrityError
from django.db.models import Q
from asgiref.sync import sync_to_async
from django.core.exceptions import FieldError, FieldDoesNotExist, ObjectDoesNotExist

# Импортируем модели из соседних модулей
try:
    # Убедитесь, что модель Questionnaire существует и импортируется
    from hrbot.models import TelegramUser, Evaluation, Question, Questionnaire
    from user_profiles.models import User, Department, Role
except ImportError as e:
    logging.critical(f"Failed to import models in db.py: {e}")
    raise

logger = logging.getLogger(__name__)

# --- Константы для связи User <-> Role ---
# Имя поля ForeignKey от User к Role (если оно есть и называется не 'role')
USER_ROLE_FIELD_NAME = None
# Имя ManyToMany поля от User к Role (в модели User)
USER_ROLES_M2M_NAME = 'roles' # ИСПОЛЬЗУЕМ ЭТО ИМЯ, Т.К. ОНО В МОДЕЛИ USER

# --- Основные ORM обертки ---

@sync_to_async
def get_or_create_tguser(tg_id: str) -> TelegramUser | None:
    """
    Асинхронно получает или создает TelegramUser и связанный с ним User.
    Корректно обрабатывает OneToOneField constraint.
    Предзагружает связанный User объект.
    """
    logger.debug(f"get_or_create_tguser called for tg_id: {tg_id}")
    try:
        # 1. Пытаемся найти существующий TelegramUser по telegram_id
        tg_user = TelegramUser.objects.select_related('user').filter(telegram_id=tg_id).first()

        if tg_user:
            logger.debug(f"Found existing TelegramUser {tg_user.id} by telegram_id {tg_id}.")
            # Убедимся, что связанный user существует
            # (поле OneToOne не может быть null=True по умолчанию,
            # но на всякий случай проверим, если user был удален некорректно)
            if not tg_user.user:
                logger.error(f"CRITICAL: Existing TelegramUser {tg_user.id} found, but has no linked user! This indicates data inconsistency.")
                # Попытка найти User по username (менее надежно)
                user = User.objects.filter(username=f"user_{tg_id}").first()
                if user:
                    logger.warning(f"Found User {user.id} separately. Attempting to relink.")
                    tg_user.user = user
                    tg_user.save(update_fields=['user'])
                    tg_user = TelegramUser.objects.select_related('user').get(pk=tg_user.pk) # Перезагружаем
                else:
                    logger.error(f"Could not find or create User for inconsistent TelegramUser {tg_user.id}")
                    return None # Не можем исправить ситуацию
            # Возвращаем найденный и проверенный/исправленный объект
            return tg_user

        # 2. Если TelegramUser по telegram_id не найден, ищем/создаем User
        logger.debug(f"TelegramUser for tg_id {tg_id} not found. Getting/creating Django User.")
        # Используем email=None при создании, если поле email допускает NULL
        user, user_created = User.objects.get_or_create(
            username=f"user_{tg_id}",
            defaults={'first_name': f'TG {tg_id}', 'email': None} # Явно указываем email=None
        )
        if user_created: logger.info(f"Created Django User {user.id} for tg_id {tg_id}")

        # 3. Пытаемся СОЗДАТЬ TelegramUser, связывая его с найденным/созданным User
        try:
            logger.debug(f"Attempting to create TelegramUser for telegram_id {tg_id} linked to User {user.id}")
            # Убеждаемся, что передаем user объект, а не user_id
            tg_user = TelegramUser.objects.create(telegram_id=tg_id, user=user)
            logger.info(f"Successfully created TelegramUser {tg_user.id} for tg_id {tg_id}")
            # Перезагрузим с select_related, чтобы user точно был в кеше
            tg_user = TelegramUser.objects.select_related('user').get(pk=tg_user.pk)
            return tg_user
        except IntegrityError as e:
            # Если создать не удалось (UNIQUE constraint на user_id),
            # значит, запись для этого User уже существует (возможно, с другим telegram_id!)
            # Это указывает на рассинхронизацию или попытку привязать одного User к разным TG ID
            logger.warning(f"IntegrityError (UNIQUE user_id) creating TelegramUser for tg_id {tg_id} / user {user.id}: {e}. Fetching existing by user.")
            tg_user = TelegramUser.objects.select_related('user').filter(user=user).first()
            if tg_user:
                 # Если найденная запись имеет другой telegram_id, обновляем его (опасно!)
                 if tg_user.telegram_id != tg_id:
                     logger.warning(f"Found existing TelegramUser {tg_user.id} linked to User {user.id}, but telegram_id is {tg_user.telegram_id}. Updating to {tg_id}.")
                     tg_user.telegram_id = tg_id
                     # Возможно, нужно удалить старую запись по tg_id, если она есть? Зависит от логики.
                     # TelegramUser.objects.filter(telegram_id=tg_id).exclude(pk=tg_user.pk).delete()
                     tg_user.save(update_fields=['telegram_id'])
                 return tg_user
            else:
                 # Очень странная ситуация
                 logger.error(f"CRITICAL: Failed to create TelegramUser for user {user.id} due to user_id IntegrityError, but couldn't find existing one by user.")
                 tg_user = TelegramUser.objects.select_related('user').filter(telegram_id=tg_id).first()
                 return tg_user # Возвращаем то, что нашли по telegram_id

    # Ловим IntegrityError связанный с email
    except IntegrityError as e:
        if 'user_profiles_user.email' in str(e):
            logger.error(f"IntegrityError (UNIQUE email) during get_or_create_tguser for tg_id {tg_id}: {e}. This likely means a User with a blank/duplicate email exists. Check if User.email allows NULL.")
            # Пытаемся найти пользователя по username, если создание не удалось из-за email
            user = User.objects.filter(username=f"user_{tg_id}").first()
            if user:
                logger.warning(f"Found user {user.id} by username after email constraint error. Trying to find/link TelegramUser.")
                # Пытаемся найти или создать TelegramUser для этого найденного User
                tg_user, created = TelegramUser.objects.select_related('user').get_or_create(
                    user=user,
                    defaults={'telegram_id': tg_id}
                )
                if created:
                    logger.info(f"Created TelegramUser {tg_user.id} for existing User {user.id} after email constraint error.")
                elif tg_user.telegram_id != tg_id:
                     logger.warning(f"Found TelegramUser {tg_user.id} linked to User {user.id}, updating telegram_id to {tg_id}.")
                     tg_user.telegram_id = tg_id
                     tg_user.save(update_fields=['telegram_id'])
                return tg_user
            else:
                logger.error(f"Could not find user by username {f'user_{tg_id}'} after email constraint error.")
                return None
        else:
            # Другая ошибка IntegrityError
            logger.exception(f"Unhandled IntegrityError in get_or_create_tguser for tg_id {tg_id}: {e}")
            return None
    except Exception as e:
        logger.exception(f"General DB error in get_or_create_tguser for tg_id {tg_id}: {e}")
        return None


@sync_to_async
def all_departments() -> list[Department]:
    """Асинхронно получает все департаменты."""
    try:
        return list(Department.objects.all().order_by('name'))
    except Exception as e:
        logger.exception(f"Error fetching all departments: {e}")
        return []

@sync_to_async
def get_active_questionnaires() -> list[Questionnaire]:
    """Асинхронно получает активные опросники."""
    try:
        # Убедимся, что модель Questionnaire существует
        return list(Questionnaire.objects.filter(is_active=True).order_by('name'))
    except NameError: # Если Questionnaire не импортирован
        logger.error("Model Questionnaire is not defined or imported.")
        return []
    except Exception as e:
        logger.exception(f"Error fetching active questionnaires: {e}")
        return []

@sync_to_async
def get_questionnaire_questions(questionnaire_id: int) -> list[Question]:
    """Асинхронно получает вопросы для конкретного опросника."""
    try:
        # Фильтруем также по is_active, чтобы не показывать неактивные вопросы
        return list(Question.objects.filter(questionnaire_id=questionnaire_id, is_active=True).order_by("order"))
    except Question.DoesNotExist:
        logger.warning(f"Question model query failed for questionnaire_id {questionnaire_id}.")
        return []
    except Exception as e:
        logger.exception(f"Error fetching questions for questionnaire_id {questionnaire_id}: {e}")
        return []

# -- Вспомогательная функция для QuerySet User --
def _get_user_queryset():
    """Возвращает базовый QuerySet для User с нужными related полями."""
    qs = User.objects.filter(is_active=True) # Начинаем с активных пользователей
    select_fields = ['department']
    prefetch_fields = []

    # Добавляем поле роли
    if USER_ROLES_M2M_NAME:
        try:
            User._meta.get_field(USER_ROLES_M2M_NAME)
            prefetch_fields.append(USER_ROLES_M2M_NAME)
        except FieldDoesNotExist:
             logger.warning(f"Field '{USER_ROLES_M2M_NAME}' not found on User model for prefetch_related.")

    # Добавляем telegram_profile
    try:
        User._meta.get_field('telegram_profile')
        select_fields.append('telegram_profile')
    except FieldDoesNotExist:
        logger.debug("Field 'telegram_profile' not found on User model, skipping select_related.")

    # Применяем related поля
    if select_fields:
        try:
            qs = qs.select_related(*select_fields)
        except FieldError as e:
             logger.error(f"Error applying select_related({select_fields}): {e}. Falling back.")
             qs = qs.select_related('department') # Минимально необходимый fallback
    if prefetch_fields:
        try:
            qs = qs.prefetch_related(*prefetch_fields)
        except (FieldError, ValueError) as e:
             logger.error(f"Error applying prefetch_related({prefetch_fields}): {e}. Skipping prefetch.")

    return qs


@sync_to_async
def users_in_dept(dept_id: int) -> list[User]:
    """Асинхронно получает активных пользователей в департаменте с предзагрузкой."""
    try:
        qs = _get_user_queryset()
        return list(qs.filter(department_id=dept_id).order_by('last_name', 'first_name'))
    except Exception as e:
        logger.exception(f"Error fetching users for dept_id {dept_id}: {e}")
        return []

@sync_to_async
def all_users() -> list[User]:
    """Асинхронно получает всех активных пользователей с предзагрузкой."""
    try:
        qs = _get_user_queryset()
        return list(qs.order_by('last_name', 'first_name'))
    except Exception as e:
        logger.exception(f"Error fetching all users: {e}")
        return []


@sync_to_async
def save_eval(ev_data: dict) -> Evaluation | None:
    """Асинхронно сохраняет оценку."""
    evaluation = None
    evaluator_id = ev_data.get('evaluator_id') # ID TelegramUser! (Согласно модели Evaluation)
    questionnaire_id = ev_data.get('questionnaire_id')
    employee_id = ev_data.get('employee_id') # ID User (optional)
    role_id = ev_data.get('role_id') # ID Role (optional)

    # --- Проверка существования внешних ключей ---
    try:
        # Проверяем существование TelegramUser (evaluator)
        evaluator_exists = TelegramUser.objects.filter(id=evaluator_id).exists()
        qset_exists = Questionnaire.objects.filter(id=questionnaire_id).exists()
        employee_exists = User.objects.filter(id=employee_id).exists() if employee_id else True
        role_exists = Role.objects.filter(id=role_id).exists() if role_id else True

        logger.info(f"Checking existence before create: TGUser ID {evaluator_id} exists={evaluator_exists}, QSet ID {questionnaire_id} exists={qset_exists}, Employee ID {employee_id} exists={employee_exists}, Role ID {role_id} exists={role_exists}")

        if not evaluator_exists: logger.error(f"Cannot save evaluation: TelegramUser (evaluator) with ID {evaluator_id} does not exist!"); return None
        if not qset_exists: logger.error(f"Cannot save evaluation: Questionnaire with ID {questionnaire_id} does not exist!"); return None
        if employee_id and not employee_exists: logger.error(f"Cannot save evaluation: Employee (User) with ID {employee_id} does not exist!"); return None
        if role_id and not role_exists: logger.error(f"Cannot save evaluation: Role with ID {role_id} does not exist!"); return None
    except Exception as check_e:
         logger.exception(f"Error checking FK existence before saving evaluation: {check_e}")
         return None
    # --- Конец проверки ---

    try:
        # Подготовка данных для создания объекта Evaluation
        data_to_create = {
            'evaluator_id': evaluator_id,
            'employee_name': ev_data.get('employee_name'),
            'questionnaire_id': questionnaire_id,
            'responses': ev_data.get('responses'),
            **({'employee_id': employee_id} if employee_id else {}),
            **({'role_id': role_id} if role_id else {}),
            **({'title': ev_data['title']} if 'title' in ev_data else {}) # Добавляем title, если есть
        }
        evaluation = Evaluation.objects.create(**data_to_create)
        logger.info(f"Evaluation {evaluation.id} created successfully for employee '{ev_data.get('employee_name')}'.")
        # Отправка в Bitrix
        try:
            # send_evaluation_to_bitrix(evaluation)
            logger.info(f"Evaluation {evaluation.id} sent to Bitrix.")
        except Exception as e_bitrix:
            logger.exception(f"Error sending evaluation {evaluation.id} to Bitrix: {e_bitrix}")
        return evaluation
    except IntegrityError as e:
         logger.error(f"IntegrityError while saving evaluation data {ev_data}: {e}")
         logger.error(f"Data passed: {data_to_create}") # Логируем точные данные
         return None
    except Exception as e:
        logger.exception(f"Error saving evaluation data {ev_data}: {e}")
        return None

@sync_to_async
def search_users(q: str) -> list[User]:
    """Асинхронно ищет активных пользователей с предзагрузкой."""
    try:
        qs = _get_user_queryset() # Уже фильтрует по is_active=True
        return list(
            qs.filter(
                Q(first_name__icontains=q)
                | Q(last_name__icontains=q)
                | Q(phone_number__icontains=q)
                | Q(email__icontains=q)
            ).order_by('last_name', 'first_name')
        )
    except Exception as e:
        logger.exception(f"Error searching users with query '{q}': {e}")
        return []


@sync_to_async
def update_user_name(user: User, name: str) -> bool:
    """Асинхронно обновляет имя пользователя."""
    try:
        user.first_name = name; user.save(update_fields=['first_name'])
        logger.info(f"Updated first_name for user {user.id} to '{name}'."); return True
    except Exception as e: logger.exception(f"Error updating name for user {user.id}: {e}"); return False

@sync_to_async
def update_user_image(user: User, image_path: str) -> bool:
    """Асинхронно обновляет фото пользователя."""
    try:
        user.image = image_path; user.save(update_fields=['image'])
        logger.info(f"Updated image for user {user.id} to '{image_path}'."); return True
    except Exception as e: logger.exception(f"Error updating image for user {user.id}: {e}"); return False


@sync_to_async
def fetch_user_by_id(user_id: int) -> User | None:
    """Асинхронно получает пользователя по ID с предзагрузкой."""
    try:
        qs = _get_user_queryset(); return qs.get(id=user_id)
    except User.DoesNotExist: logger.warning(f"User with id {user_id} not found."); return None
    except Exception as e: logger.exception(f"Error fetching user with id {user_id}: {e}"); return None


@sync_to_async
def set_user_setting(user: User, key: str, value) -> bool:
    """Асинхронно устанавливает настройку пользователя (JSONField 'settings')."""
    try:
        if not hasattr(user, 'settings'): logger.error(f"User model {type(user)} has no 'settings' attribute."); return False
        if not isinstance(user.settings, dict): user.settings = {}
        user.settings[key] = value; user.save(update_fields=['settings'])
        logger.info(f"Set setting '{key}'='{value}' for user {user.id}"); return True
    except Exception as e: logger.exception(f"Error setting setting '{key}'='{value}' for user {user.id}: {e}"); return False