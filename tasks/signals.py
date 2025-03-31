from django.dispatch import Signal, receiver
from django.core.mail import send_mail
from django.conf import settings
from django.utils.translation import gettext as _
from django.urls import reverse
from .models import TaskComment
from django.utils.html import escape
from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
import logging


logger = logging.getLogger(__name__)
# ------------------ Сигнал завершения задачи ------------------
task_completed = Signal()

@receiver(task_completed)
def send_task_completed_notification(sender, **kwargs):
    """Отправляет уведомление по email, когда задача выполнена."""
    task = kwargs.get("task")
    
    if not task:
        return
    
    initiator = task.created_by
    team_leader = task.team.team_leader if task.team else None

    recipients_emails = {initiator.email} if initiator and initiator.email else set()
    if team_leader and team_leader.email and team_leader != initiator:
        recipients_emails.add(team_leader.email)

    if recipients_emails and hasattr(settings, "SITE_URL"):
        try:
            task_detail_url = settings.SITE_URL + reverse("crm_core:task_detail", kwargs={"pk": task.pk})

            subject = _(f"Задача '{task.task_number}': Выполнена")
            message = _(
                f"Задача '{task.task_number} ({task.project.name})' была отмечена как *Выполнена*.\n\n"
                f"Описание: {task.description[:200]}...\n\n"
                f"Статус: {task.get_status_display()}\n\n"
                f"Подробности задачи: {task_detail_url}"
            )

            send_mail(
                subject,
                message,
                settings.DEFAULT_FROM_EMAIL,
                list(recipients_emails),
                fail_silently=True,
            )

            print(f"✅ Email уведомление отправлено: {recipients_emails} для задачи {task.task_number}")

        except Exception as e:
            print(f"⚠ Ошибка при отправке email для задачи {task.task_number}: {e}")

    else:
        print(f"⚠ Нет получателей для уведомления о выполнении задачи {task.task_number}")


@receiver(post_save, sender=TaskComment)
def broadcast_new_comment(sender, instance: TaskComment, created: bool, **kwargs):
    """Отправляет новый комментарий через WebSocket при его создании."""
    if created:
        channel_layer = get_channel_layer()
        group_name = f'task_comments_{instance.task.id}'
        author = instance.author
        author_name = author.display_name if author else _("Аноним")
        author_avatar_url = author.image.url if author and author.image else None # Нужен путь к дефолтному аватару

        # Формируем данные для отправки (сериализуем вручную)
        comment_data = {
            'id': instance.id,
            'text': escape(instance.text), # Экранируем текст
            'created_at_iso': instance.created_at.isoformat(), # ISO формат для JS
            'created_at_display': instance.created_at.strftime('%d.%m.%Y %H:%M'), # Формат для отображения
            'author': {
                'id': author.id if author else None,
                'name': author_name,
                'avatar_url': author_avatar_url
            },
            'task_id': instance.task.id,
        }

        logger.debug(f"Broadcasting new comment {instance.id} to group {group_name}")
        try:
            async_to_sync(channel_layer.group_send)(
                group_name,
                {
                    'type': 'comment.message', # Указываем тип для обработчика в консьюмере
                    'message': comment_data
                }
            )
        except Exception as e:
             logger.error(f"Error sending comment {instance.id} to WebSocket group {group_name}: {e}")