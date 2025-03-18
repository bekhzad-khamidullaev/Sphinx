from django.dispatch import Signal, receiver
from django.core.mail import send_mail
from django.conf import settings
from django.utils.translation import gettext as _
from django.urls import reverse

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
                f"Задача '{task.task_number} ({task.campaign.name})' была отмечена как *Выполнена*.\n\n"
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
