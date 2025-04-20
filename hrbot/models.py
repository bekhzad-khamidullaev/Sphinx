# hrbot/models.py

from django.db import models
from django.utils.translation import gettext_lazy as _
from django.conf import settings # Используем settings.AUTH_USER_MODEL
import logging

# Импортируем User и Role из user_profiles (убедитесь, что путь верный)
try:
    from user_profiles.models import User, Role, Department
except ImportError:
     # Эта ошибка критична, бот не сможет работать без моделей User/Role/Department
     logging.critical("Could not import User, Role, Department from user_profiles.models. Check app dependencies and model definitions.")
     raise ImportError("Could not import User, Role, Department from user_profiles.models.")


logger = logging.getLogger(__name__)

# --- Questionnaire Model ---
class Questionnaire(models.Model):
    """Represents a set of questions for a specific type of evaluation."""
    name = models.CharField(max_length=150, unique=True, verbose_name=_("Название опросника"))
    description = models.TextField(blank=True, verbose_name=_("Описание"))
    is_active = models.BooleanField(default=True, verbose_name=_("Активен"), help_text=_("Активные опросники доступны для выбора при оценке."))
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = _("Опросник")
        verbose_name_plural = _("Опросники")
        ordering = ['name']

    def __str__(self):
        return self.name

# --- TelegramUser Model ---
class TelegramUser(models.Model):
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL, # Используем настройку Django
        on_delete=models.CASCADE,
        related_name='telegram_profile',
        verbose_name=_("Пользователь Django")
    )
    telegram_id = models.CharField(max_length=20, unique=True, db_index=True, verbose_name=_("Telegram ID"))
    approved = models.BooleanField(default=False, verbose_name=_("Подтвержден"))
    notified_on_approval = models.BooleanField(default=False, verbose_name=_("Уведомлен о подтверждении"))

    class Meta:
        verbose_name = _("Telegram Пользователь")
        verbose_name_plural = _("Telegram Пользователи")

    def __str__(self):
        approved_status = "✅" if self.approved else "⏳"
        notified_status = "📨" if self.notified_on_approval else ""
        # Пытаемся получить username безопасно
        username = "N/A"
        try:
             if self.user:
                 username = self.user.username
        except User.DoesNotExist: # Обработка случая, если user удален (хотя on_delete=CASCADE)
             logger.warning(f"User for TelegramUser {self.pk} not found.")
        except Exception as e:
             logger.error(f"Error accessing user for TelegramUser {self.pk}: {e}")

        return f"{username} ({self.telegram_id}) {approved_status}{notified_status}"

# --- Question Model ---
class Question(models.Model):
    questionnaire = models.ForeignKey(Questionnaire, on_delete=models.CASCADE, related_name='questions', verbose_name=_("Опросник"))
    text = models.CharField(max_length=255, verbose_name=_("Текст вопроса"))
    order = models.PositiveIntegerField(default=1, verbose_name=_("Порядок"))
    # Используем JSONField для хранения вариантов ответа
    # Это может быть список строк, например ["Да", "Нет", "Затрудняюсь ответить"]
    answer_options = models.JSONField(
        null=True,
        blank=True,
        verbose_name=_("Варианты ответа (JSON list)"),
        help_text=_('Список строк с вариантами ответа, например ["Да", "Нет", "Затрудняюсь ответить"] или ["1", "2", "3", "4", "5"]. Оставьте пустым для свободного ответа.')
    )

    class Meta:
        ordering = ['questionnaire', 'order']
        verbose_name = _("Вопрос")
        verbose_name_plural = _("Вопросы")
        indexes = [ models.Index(fields=['questionnaire', 'order']), ]

    def __str__(self):
        q_name = getattr(self.questionnaire, 'name', 'N/A')
        options_mark = "[Btn]" if self.answer_options else "[Txt]"
        return f"{q_name}: ({self.order}) {self.text[:60]}... {options_mark}"

# --- Evaluation Model ---
class Evaluation(models.Model):
    evaluator = models.ForeignKey(
        TelegramUser,
        on_delete=models.CASCADE, # Если удаляется ТГ-юзер, его оценки удаляются
        related_name='evaluations_given',
        verbose_name=_("Оценщик (TG User)")
    )
    # Сохраняем имя на момент оценки
    employee_name = models.CharField(max_length=100, verbose_name=_("Имя оцениваемого (текст)"))
    # Опциональная ссылка на объект User оцениваемого
    employee = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL, # Сохраняем оценку, даже если юзер удален
        null=True,
        blank=True,
        related_name='evaluated_in',
        verbose_name=_("Сотрудник (объект User)")
    )
    # Ссылка на использованный опросник
    questionnaire = models.ForeignKey(
        Questionnaire,
        on_delete=models.PROTECT, # Защищаем от удаления опросники, по которым есть оценки
        related_name='evaluations',
        verbose_name=_("Использованный опросник")
    )
    # Сохраняем роль для контекста/отчетности
    role = models.ForeignKey(
        Role,
        on_delete=models.SET_NULL, # Сохраняем оценку, даже если роль удалена
        null=True,
        blank=True, # Роль может быть не всегда применима
        related_name='evaluations_in_role',
        verbose_name=_("Роль (контекст)")
    )
    # Ответы в формате JSON: {'question_id_str': 'answer_text', ...}
    responses = models.JSONField(verbose_name=_("Ответы (ID вопроса -> ответ)"))
    timestamp = models.DateTimeField(auto_now_add=True, verbose_name=_("Время оценки"))

    class Meta:
        ordering = ['-timestamp']
        verbose_name = _("Оценка")
        verbose_name_plural = _("Оценки")
        indexes = [
            models.Index(fields=['-timestamp']),
            models.Index(fields=['evaluator']),
            models.Index(fields=['employee']),
            models.Index(fields=['questionnaire']),
            models.Index(fields=['role']),
        ]

    def __str__(self):
        evaluator_name = self.get_evaluator_name() or f"TG User {self.evaluator_id}"
        q_name = self.questionnaire.name if self.questionnaire else "N/A"
        role_name = f" ({self.role.name})" if self.role else ""
        return f"Оценка {self.employee_name}{role_name} ({q_name}) от {evaluator_name}"

    # --- Вспомогательные методы ---
    def get_evaluator_name(self):
        """Безопасно получает полное имя оценщика."""
        try:
            if self.evaluator and self.evaluator.user:
                return self.evaluator.user.get_full_name()
        except User.DoesNotExist:
            logger.warning(f"User for evaluator (TelegramUser {self.evaluator_id}) not found in Evaluation {self.pk}")
        except Exception as e:
            logger.error(f"Error getting evaluator name for Evaluation {self.pk}: {e}")
        return None

    def get_evaluator_telegram_id(self):
        """Возвращает Telegram ID оценщика."""
        return self.evaluator.telegram_id if self.evaluator else None

    def get_questionnaire_name(self):
        """Возвращает название опросника."""
        return self.questionnaire.name if self.questionnaire else None

    def get_role_name(self):
        """Возвращает название роли (если есть)."""
        return self.role.name if self.role else None

    def get_formatted_responses(self) -> dict | None:
        """Возвращает ответы с текстами вопросов (требует доп. запроса)."""
        if not isinstance(self.responses, dict):
            return None
        try:
            question_ids = [int(qid) for qid in self.responses.keys() if qid.isdigit()]
            questions = Question.objects.in_bulk(question_ids)
            formatted = {}
            for qid_str, answer in self.responses.items():
                qid = int(qid_str) if qid_str.isdigit() else None
                question_obj = questions.get(qid)
                question_text = question_obj.text if question_obj else f"Вопрос ID {qid_str} (не найден)"
                formatted[question_text] = answer
            return formatted
        except Exception as e:
            logger.exception(f"Error formatting responses for Evaluation {self.pk}: {e}")
            return self.responses # Возвращаем сырые данные при ошибке