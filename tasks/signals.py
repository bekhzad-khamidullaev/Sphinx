from django.dispatch import Signal, receiver
from django.core.mail import send_mail
from django.conf import settings
from django.utils.translation import gettext as _
from django.urls import reverse
from django.utils import timezone
from datetime import timedelta
from django.db.models.signals import post_save
import logging

from .models import Task, TaskAssignment

logger = logging.getLogger(__name__)

task_completed_signal = Signal()

@receiver(task_completed_signal)
def send_task_completed_email_notification(sender, **kwargs):
    task = kwargs.get("task")
    if not task:
        logger.warning("send_task_completed_email_notification called without a task instance.")
        return

    recipients_emails = set()
    if task.created_by and task.created_by.email:
        recipients_emails.add(task.created_by.email)

    responsible_users = task.get_responsible_users()
    for user in responsible_users:
        if user.email:
            recipients_emails.add(user.email)

    if recipients_emails and hasattr(settings, "SITE_URL"):
        try:
            site_url = settings.SITE_URL.strip('/')
            task_detail_url = site_url + task.get_absolute_url()

            subject = _(f"Задача '{task.task_number or task.title}' выполнена")
            message_body = _(
                f"Задача '{task.task_number or task.title}' "
                f"(Проект: {task.project.name if task.project else 'N/A'}) была отмечена как *Выполнена*.\n\n"
                f"Статус: {task.get_status_display()}\n"
                f"Дата завершения: {task.completion_date.strftime('%d.%m.%Y %H:%M') if task.completion_date else '-'}\n\n"
                f"Подробности задачи: {task_detail_url}"
            )

            send_mail(
                subject, message_body, settings.DEFAULT_FROM_EMAIL,
                list(recipients_emails), fail_silently=False
            )
            logger.info(f"Email уведомление о выполнении задачи {task.id} отправлено: {recipients_emails}")
        except Exception as e:
            logger.error(f"Ошибка при отправке email уведомления о выполнении задачи {task.id}: {e}", exc_info=True)
    elif not recipients_emails:
        logger.info(f"Нет получателей email для уведомления о выполнении задачи {task.id}.")


@receiver(post_save, sender=Task)
def check_task_completion_for_email_signal(sender, instance: Task, created: bool, update_fields=None, **kwargs):
    is_completed = instance.status == Task.StatusChoices.COMPLETED
    status_was_changed = not update_fields or 'status'in update_fields

    just_completed_event = False
    if is_completed and status_was_changed:
        if created:
            just_completed_event = True
        elif instance.completion_date and (not update_fields or 'completion_date' in update_fields):
             if (timezone.now() - instance.completion_date) < timedelta(seconds=10):
                 just_completed_event = True

    if just_completed_event:
        logger.info(f"Task {instance.id} detected as 'just completed'. Sending task_completed_signal for email.")
        task_completed_signal.send(sender=instance.__class__, task=instance)
