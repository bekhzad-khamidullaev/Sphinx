from celery import shared_task
from django.utils.timezone import now
from django.core.mail import send_mail
from django.conf import settings
from tasks.models import Task

@shared_task
def check_overdue_tasks():
    """Проверяет просроченные задачи и обновляет их статус на 'overdue'."""
    overdue_tasks = Task.objects.filter(deadline__lt=now(), status__in=["new", "in_progress", "on_hold"])

    for task in overdue_tasks:
        task.status = "overdue"
        task.save()

        recipients = set()
        if task.created_by:
            recipients.add(task.created_by.email)
        if task.assignee:
            recipients.add(task.assignee.email)

        # Отправка уведомлений
        if recipients:
            send_mail(
                subject=f"Задача {task.task_number} просрочена!",
                message=f"Задача '{task.description}' была автоматически помечена как просроченная.",
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=list(recipients),
                fail_silently=True,
            )

    return f"Обновлено {overdue_tasks.count()} задач"
