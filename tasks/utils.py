from django.contrib import messages
from django.utils.timezone import now
from tasks.models import Task
from django.core.exceptions import PermissionDenied
from django.http import Http404

def has_task_access(user, task, edit=False):
    """ Проверяет доступ к задаче. """
    if user.is_superuser:
        return True
    if user.has_perm('tasks.view_task') or (edit and user.has_perm('tasks.change_task')):
        return True
    if task.assignee == user or task.created_by == user:
        return True
    if hasattr(user, 'user_profile') and task.team in user.user_profile.teams.all():
        return True
    if edit and task.team and task.team.team_leader == user:
        return True
    return False


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
