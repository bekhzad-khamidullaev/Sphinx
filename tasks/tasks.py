# tasks/tasks.py (для Celery)
# -*- coding: utf-8 -*-

from celery import shared_task
from django.utils import timezone
from django.core.mail import send_mail
from django.conf import settings
from django.urls import reverse
from django.utils.translation import gettext as _

from .models import Task
# from user_profiles.models import User # Если нужно получать User объекты для уведомлений
import logging

logger = logging.getLogger(__name__)

@shared_task(name="tasks.check_overdue_tasks_and_notify") # Явное имя задачи
def check_overdue_tasks_and_notify():
    """
    Проверяет задачи, у которых истек срок выполнения,
    обновляет их статус на 'Просрочена' (если еще не установлен),
    и отправляет уведомления ответственным и создателю.
    """
    now = timezone.now()
    logger.info(f"Celery task 'check_overdue_tasks_and_notify' started at {now.strftime('%Y-%m-%d %H:%M:%S')}")

    # Ищем задачи, которые:
    # 1. Имеют дедлайн в прошлом.
    # 2. Не находятся в конечном статусе (Выполнена, Отменена).
    # 3. Еще не помечены как Просрочена (чтобы не отправлять уведомления повторно каждый раз).
    tasks_to_become_overdue = Task.objects.filter(
        deadline__lt=now,
        status__in=[Task.StatusChoices.NEW, Task.StatusChoices.IN_PROGRESS, Task.StatusChoices.ON_HOLD]
    )

    updated_count = 0
    notified_tasks_count = 0

    for task in tasks_to_become_overdue:
        try:
            task.status = Task.StatusChoices.OVERDUE
            # Модель Task.save() должна обновить updated_at.
            # completion_date здесь не трогаем.
            task.save(update_fields=['status', 'updated_at'])
            updated_count += 1
            logger.info(f"Task {task.task_number or task.id} ('{task.title}') marked as OVERDUE.")

            # Отправка уведомлений
            recipients_emails = set()
            if task.created_by and task.created_by.email:
                recipients_emails.add(task.created_by.email)
            
            if hasattr(task, 'get_responsible_users'):
                for user in task.get_responsible_users(): # Предполагается, что метод возвращает queryset User'ов
                    if user.email:
                        recipients_emails.add(user.email)
            
            if recipients_emails and hasattr(settings, "SITE_URL"):
                try:
                    task_url_path = reverse("tasks:task_detail", kwargs={"pk": task.pk})
                    full_task_url = f"{settings.SITE_URL.strip('/')}{task_url_path}"

                    subject = _("Задача '%(task_number)s' просрочена!") % {'task_number': task.task_number or task.pk}
                    message_body = _(
                        "Здравствуйте,\n\n"
                        "Задача \"%(title)s\" (номер: %(task_number)s) в проекте \"%(project_name)s\" была автоматически отмечена как просроченная.\n\n"
                        "Срок выполнения был: %(deadline)s\n"
                        "Текущий статус: %(status)s\n\n"
                        "Пожалуйста, обратите внимание на эту задачу: %(task_url)s\n\n"
                        "С уважением,\nВаша система управления задачами."
                    ) % {
                        'title': task.title,
                        'task_number': task.task_number or task.pk,
                        'project_name': task.project.name if task.project else _('N/A'),
                        'deadline': task.deadline.strftime('%d.%m.%Y %H:%M') if task.deadline else _('N/A'),
                        'status': task.get_status_display(),
                        'task_url': full_task_url
                    }
                    
                    send_mail(
                        subject, message_body, settings.DEFAULT_FROM_EMAIL,
                        list(recipients_emails), fail_silently=False
                    )
                    notified_tasks_count +=1
                    logger.info(f"Overdue notification sent for task {task.id} to {recipients_emails}")
                except Exception as mail_exc:
                    logger.error(f"Failed to send overdue email notification for task {task.id}: {mail_exc}")
            elif not recipients_emails:
                logger.warning(f"No recipients for overdue notification for task {task.id}")

        except Exception as e:
            logger.error(f"Error processing task {task.task_number or task.id} for overdue status: {e}")

    result_message = f"Checked for overdue tasks. Updated {updated_count} tasks to OVERDUE. Sent notifications for {notified_tasks_count} tasks."
    logger.info(result_message)
    return result_message

# @shared_task(name="tasks.send_daily_digest")
# def send_daily_digest():
# """Пример задачи для отправки ежедневной сводки по задачам."""
# # Логика сбора данных для дайджеста
# # Отправка email пользователям
# logger.info("Daily digest task executed.")
# return "Daily digest sent."