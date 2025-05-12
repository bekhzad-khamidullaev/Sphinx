from celery import shared_task
from django.utils import timezone
from django.core.mail import send_mail
from django.conf import settings
from .models import Task
import logging

logger = logging.getLogger(__name__)

@shared_task
def check_overdue_tasks():
    now_tz = timezone.now()
    tasks_to_check = Task.objects.filter(
        due_date__lt=now_tz.date(), # Compare with date part of now_tz
        status__in=[Task.StatusChoices.NEW, Task.StatusChoices.IN_PROGRESS, Task.StatusChoices.ON_HOLD]
    )

    updated_count = 0
    for task in tasks_to_check:
        if task.status != Task.StatusChoices.OVERDUE:
            task.status = Task.StatusChoices.OVERDUE
            try:
                task.save(update_fields=['status', 'updated_at'])
                updated_count += 1
                logger.info(f"Task {task.id} ({task.title}) marked as overdue.")

                recipients = set()
                if task.created_by and task.created_by.email:
                    recipients.add(task.created_by.email)

                responsible_users = task.get_responsible_users()
                for user in responsible_users:
                    if user.email:
                        recipients.add(user.email)

                if recipients:
                    try:
                        send_mail(
                            subject=f"Задача {task.task_number or task.title} просрочена!",
                            message=f"Задача '{task.title}' (Номер: {task.task_number}) была автоматически помечена как просроченная.\nСрок: {task.due_date.strftime('%Y-%m-%d') if task.due_date else 'N/A'}",
                            from_email=settings.DEFAULT_FROM_EMAIL,
                            recipient_list=list(recipients),
                            fail_silently=False,
                        )
                        logger.info(f"Overdue notification sent for task {task.id} to {recipients}")
                    except Exception as e:
                        logger.error(f"Failed to send overdue notification for task {task.id}: {e}")
            except Exception as e:
                logger.error(f"Error updating task {task.id} to overdue: {e}")

    if updated_count > 0:
        return f"Marked {updated_count} tasks as overdue."
    return "No tasks newly marked as overdue."