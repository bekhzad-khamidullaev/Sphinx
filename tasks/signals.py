#tasks/signals.py
# -*- coding: utf-8 -*-

from django.dispatch import Signal, receiver
from django.core.mail import send_mail
from django.conf import settings
from django.utils.translation import gettext as _
from django.urls import reverse
from .models import TaskComment, Task # Added Task for task_completed example
from django.db.models.signals import post_save
from django.utils.html import escape
from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
import logging

logger = logging.getLogger(__name__)

task_completed_signal = Signal() # Renamed for clarity, used 'task_completed_signal'

@receiver(task_completed_signal) # Connect to the renamed signal
def send_task_completed_notification(sender, **kwargs):
    task = kwargs.get("task")
    if not task: return

    # Assuming task.project, task.created_by, and potentially task.team exist
    # and have necessary attributes like 'email' and 'team_leader'.
    # This part requires careful checking of your actual model relations.
    # For example, if team is not directly on task, you'd fetch it differently.
    
    recipients_emails = set()
    if task.created_by and task.created_by.email:
        recipients_emails.add(task.created_by.email)
    
    # Example: Get responsible user(s) if defined via TaskUserRole
    responsible_users = task.get_responsible_users() # Assuming this method exists
    for user in responsible_users:
        if user.email:
            recipients_emails.add(user.email)

    # Example: Notify project manager if project has one
    # if task.project and hasattr(task.project, 'manager') and task.project.manager and task.project.manager.email:
    #     recipients_emails.add(task.project.manager.email)


    if recipients_emails and hasattr(settings, "SITE_URL"):
        try:
            task_detail_url = settings.SITE_URL.strip('/') + reverse("tasks:task_detail", kwargs={"pk": task.pk})
            subject = _(f"Задача '{task.task_number or task.title}': Выполнена")
            message = _(
                f"Задача '{task.task_number or task.title}' (Проект: {task.project.name if task.project else 'N/A'}) была отмечена как *Выполнена*.\n\n"
                f"Статус: {task.get_status_display()}\n\n"
                f"Подробности задачи: {task_detail_url}"
            )
            send_mail(subject, message, settings.DEFAULT_FROM_EMAIL, list(recipients_emails), fail_silently=False) # fail_silently=False for debugging
            logger.info(f"Email уведомление о выполнении задачи {task.id} отправлено: {recipients_emails}")
        except Exception as e:
            logger.error(f"Ошибка при отправке email для задачи {task.id}: {e}")
    elif not recipients_emails:
        logger.warning(f"Нет получателей для уведомления о выполнении задачи {task.id}")


@receiver(post_save, sender=TaskComment)
def broadcast_new_comment(sender, instance: TaskComment, created: bool, **kwargs):
    if created:
        channel_layer = get_channel_layer()
        group_name = f'task_comments_{instance.task.id}'
        author = instance.author
        author_name = author.display_name if author and hasattr(author, 'display_name') else (author.username if author else _("Аноним"))
        author_avatar_url = None
        if author and hasattr(author, 'image') and author.image: # Check for profile image
            author_avatar_url = author.image.url
        # else: provide a default avatar URL if needed

        comment_data = {
            'id': instance.id,
            'text': escape(instance.text),
            'created_at_iso': instance.created_at.isoformat(),
            'created_at_display': instance.created_at.strftime('%d.%m.%Y %H:%M'),
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
                    'type': 'comment_message', # Matches method in TaskCommentConsumer
                    'message': comment_data
                }
            )
        except Exception as e:
             logger.error(f"Error sending comment {instance.id} to WebSocket group {group_name}: {e}")

# Example of triggering task_completed_signal when a task status changes to COMPLETED
# This would typically be in the Task model's save method or another post_save signal for Task
@receiver(post_save, sender=Task)
def check_task_completion_for_signal(sender, instance: Task, created: bool, update_fields=None, **kwargs):
    if instance.status == Task.StatusChoices.COMPLETED:
        # Check if it was *just* completed (to avoid sending signal on every save of a completed task)
        # This is a simplified check. A more robust way involves checking the status *before* this save.
        just_completed = False
        if created: # If created as completed
            just_completed = True
        elif update_fields and 'status' in update_fields: # If status was explicitly updated
             # Ideally, you'd compare old_status != COMPLETED and new_status == COMPLETED
             just_completed = True # Simplified: assume if status in update_fields and it's COMPLETED, it's a new completion event
        
        if just_completed:
            logger.info(f"Task {instance.id} completed, sending task_completed_signal.")
            task_completed_signal.send(sender=instance.__class__, task=instance)