from django.contrib import messages
from django.utils.timezone import now
from tasks.models import Task

def send_notification(request, task):
    """Функция отправки уведомлений через Django Messages"""
    users = {task.created_by, task.assignee}
    users.discard(None)  # Убираем None-значения

    for user in users:
        if user and user.is_authenticated:
            messages.add_message(
                request,
                messages.WARNING,
                f"Задача '{task.task_number}' просрочена! Срочно примите меры."
            )

def update_overdue_tasks(request):
    """Функция обновления просроченных задач + уведомления"""
    overdue_tasks = Task.objects.filter(deadline__lt=now(), status__in=["new", "in_progress"])

    for task in overdue_tasks:
        task.status = "overdue"
        task.save()
        send_notification(request, task)
