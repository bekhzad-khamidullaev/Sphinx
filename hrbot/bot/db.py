# hrbot/bot/db.py

import logging
from django.db import models, IntegrityError
from django.db.models import Q
from asgiref.sync import sync_to_async
from django.core.exceptions import FieldError, FieldDoesNotExist

# Импортируем модели из соседних модулей
try:
    from hrbot.models import TelegramUser, Evaluation, Question, Questionnaire
    from user_profiles.models import User, Department, Role
except ImportError as e:
    logging.critical(f"Failed to import models in db.py: {e}")
    raise

logger = logging.getLogger(__name__)

# Константы для связи User <-> Role
USER_ROLE_FIELD_NAME = None
USER_ROLES_M2M_NAME = 'roles' # Поле на модели User

# --- Основные ORM обертки ---

@sync_to_async
def get_or_create_tguser(tg_id: str) -> TelegramUser | None:
    """Асинхронно получает или создает TelegramUser и User."""
    try:
        user, user_created = User.objects.get_or_create(
            username=f"user_{tg_id}",
            defaults={'first_name': f'TG {tg_id}'}
        )
        if user_created: logger.info(f"Created Django User {user.id} for tg_id {tg_id}")

        tg, tg_created = TelegramUser.objects.select_related('user').get_or_create(
            telegram_id=tg_id,
            defaults={'user': user}
        )

        if not tg_created and tg.user_id != user.id:
             logger.warning(f"TelegramUser {tg_id} existed but linked to wrong User ({tg.user_id} != {user.id}). Relinking.")
             tg.user = user
             tg.save(update_fields=['user'])
             tg = TelegramUser.objects.select_related('user').get(telegram_id=tg_id)

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
def all_departments() -> list[Department]:
    """Асинхронно получает все департаменты."""
    try:
        return list(Department.objects.all().order_by('name')) # Добавим сортировку
    except Exception as e:
        logger.exception(f"Error fetching all departments: {e}")
        return []

@sync_to_async
def get_active_questionnaires() -> list[Questionnaire]:
    """Асинхронно получает активные опросники."""
    try:
        return list(Questionnaire.objects.filter(is_active=True).order_by('name'))
    except Exception as e:
        logger.exception(f"Error fetching active questionnaires: {e}")
        return []

@sync_to_async
def get_questionnaire_questions(questionnaire_id: int) -> list[Question]:
    """Асинхронно получает вопросы для конкретного опросника."""
    try:
        return list(Question.objects.filter(questionnaire_id=questionnaire_id).order_by("order"))
    except Question.DoesNotExist: # На случай если Question модель не найдена
        logger.warning(f"Question model not found or query failed for questionnaire_id {questionnaire_id}.")
        return []
    except Exception as e:
        logger.exception(f"Error fetching questions for questionnaire_id {questionnaire_id}: {e}")
        return []

# -- Вспомогательная функция для QuerySet User --
def _get_user_queryset():
    """Возвращает базовый QuerySet для User с нужными related полями."""
    qs = User.objects.all()
    select_fields = ['department']
    prefetch_fields = []

    # Добавляем поле роли, если задано
    if USER_ROLE_FIELD_NAME:
        try: User._meta.get_field(USER_ROLE_FIELD_NAME); select_fields.append(USER_ROLE_FIELD_NAME)
        except FieldDoesNotExist: logger.warning(f"Field '{USER_ROLE_FIELD_NAME}' not found on User model for select_related.")
    elif USER_ROLES_M2M_NAME:
        try: User._meta.get_field(USER_ROLES_M2M_NAME); prefetch_fields.append(USER_ROLES_M2M_NAME)
        except FieldDoesNotExist: logger.warning(f"Field '{USER_ROLES_M2M_NAME}' not found on User model for prefetch_related.")

    # Добавляем telegram_profile, если есть
    try: User._meta.get_field('telegram_profile'); select_fields.append('telegram_profile')
    except FieldDoesNotExist: logger.debug("Field 'telegram_profile' not found on User model, skipping select_related.")

    # Применяем related поля
    if select_fields:
        try: qs = qs.select_related(*select_fields)
        except FieldError as e: logger.error(f"Error applying select_related({select_fields}): {e}. Falling back."); qs = qs.select_related('department')
    if prefetch_fields:
        try: qs = qs.prefetch_related(*prefetch_fields)
        except (FieldError, ValueError) as e: logger.error(f"Error applying prefetch_related({prefetch_fields}): {e}. Skipping prefetch.")

    return qs


@sync_to_async
def users_in_dept(dept_id: int) -> list[User]:
    """Асинхронно получает пользователей в департаменте с предзагрузкой."""
    try:
        qs = _get_user_queryset()
        return list(qs.filter(department_id=dept_id).order_by('last_name', 'first_name')) # Добавим сортировку
    except FieldError as e:
         logger.error(f"FieldError in users_in_dept preloading: {e}. Check related field names.")
         try: return list(User.objects.select_related('department').filter(department_id=dept_id).order_by('last_name', 'first_name'))
         except Exception as fallback_e: logger.exception(f"Fallback DB error fetching users for dept_id {dept_id}: {fallback_e}"); return []
    except Exception as e: logger.exception(f"Error fetching users for dept_id {dept_id}: {e}"); return []

@sync_to_async
def all_users() -> list[User]:
    """Асинхронно получает всех пользователей с предзагрузкой."""
    try:
        qs = _get_user_queryset()
        return list(qs.order_by('last_name', 'first_name')) # Добавим сортировку
    except FieldError as e:
         logger.error(f"FieldError in all_users preloading: {e}. Check related field names.")
         try: return list(User.objects.select_related('department').all().order_by('last_name', 'first_name'))
         except Exception as fallback_e: logger.exception(f"Fallback DB error fetching all users: {fallback_e}"); return []
    except Exception as e: logger.exception(f"Error fetching all users: {e}"); return []


@sync_to_async
def save_eval(ev_data: dict) -> Evaluation | None:
    """Асинхронно сохраняет оценку и пытается отправить в Битрикс."""
    evaluation = None
    evaluator_id = ev_data.get('evaluator_id') # ID TelegramUser
    questionnaire_id = ev_data.get('questionnaire_id')
    employee_id = ev_data.get('employee_id') # ID User (optional)
    role_id = ev_data.get('role_id') # ID Role (optional)

    # Проверка существования внешних ключей
    try:
        evaluator_exists = TelegramUser.objects.filter(id=evaluator_id).exists()
        qset_exists = Questionnaire.objects.filter(id=questionnaire_id).exists()
        employee_exists = User.objects.filter(id=employee_id).exists() if employee_id else True
        role_exists = Role.objects.filter(id=role_id).exists() if role_id else True
        logger.info(f"Checking existence before create: TGUser ID {evaluator_id} exists: {evaluator_exists}, QSet ID {questionnaire_id} exists: {qset_exists}, Employee ID {employee_id} exists: {employee_exists}, Role ID {role_id} exists: {role_exists}")
        if not evaluator_exists: logger.error(f"Cannot save evaluation: TelegramUser (evaluator) with ID {evaluator_id} does not exist!"); return None
        if not qset_exists: logger.error(f"Cannot save evaluation: Questionnaire with ID {questionnaire_id} does not exist!"); return None
        if employee_id and not employee_exists: logger.error(f"Cannot save evaluation: Employee (User) with ID {employee_id} does not exist!"); return None
        if role_id and not role_exists: logger.error(f"Cannot save evaluation: Role with ID {role_id} does not exist!"); return None
    except Exception as check_e: logger.exception(f"Error checking FK existence before saving evaluation: {check_e}"); return None

    try:
        # Подготовка данных для создания объекта Evaluation
        data_to_create = {
            'evaluator_id': evaluator_id,
            'employee_name': ev_data.get('employee_name'),
            'questionnaire_id': questionnaire_id,
            'responses': ev_data.get('responses'),
            # Добавляем опциональные поля, только если они есть
            **({'employee_id': employee_id} if employee_id else {}),
            **({'role_id': role_id} if role_id else {}),
        }
        evaluation = Evaluation.objects.create(**data_to_create)
        logger.info(f"Evaluation {evaluation.id} created successfully for employee '{ev_data.get('employee_name')}'.")
        # Отправка в Bitrix
        try: send_evaluation_to_bitrix(evaluation); logger.info(f"Evaluation {evaluation.id} sent to Bitrix.")
        except Exception as e_bitrix: logger.exception(f"Error sending evaluation {evaluation.id} to Bitrix: {e_bitrix}")
        return evaluation
    except IntegrityError as e:
         logger.error(f"FOREIGN KEY constraint failed while saving evaluation data {ev_data}: {e}")
         logger.error(f"Data passed: evaluator_id={evaluator_id}, questionnaire_id={questionnaire_id}, employee_id={employee_id}, role_id={role_id}")
         return None
    except Exception as e: logger.exception(f"Error saving evaluation data {ev_data}: {e}"); return None

@sync_to_async
def search_users(q: str) -> list[User]:
    """Асинхронно ищет пользователей с предзагрузкой."""
    try:
        qs = _get_user_queryset()
        return list(
            qs.filter(
                Q(first_name__icontains=q)
                | Q(last_name__icontains=q)
                | Q(phone_number__icontains=q)
                | Q(email__icontains=q)
            ).order_by('last_name', 'first_name') # Добавим сортировку
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
                ).order_by('last_name', 'first_name')
            )
         except Exception as fallback_e: logger.exception(f"Fallback DB error searching users with query '{q}': {fallback_e}"); return []
    except Exception as e: logger.exception(f"Error searching users with query '{q}': {e}"); return []


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
    except FieldError as e:
         logger.error(f"FieldError in fetch_user_by_id preloading: {e}. Check related field names.")
         try: return User.objects.select_related('department').get(id=user_id)
         except User.DoesNotExist: logger.warning(f"User with id {user_id} not found (fallback)."); return None
         except Exception as fallback_e: logger.exception(f"Fallback DB error fetching user with id {user_id}: {fallback_e}"); return None
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