# tasks/signals.py
# -*- coding: utf-8 -*-

from django.dispatch import Signal, receiver
from django.db.models.signals import post_save, post_delete # Добавляем post_delete
from django.conf import settings # Для SITE_URL и DEFAULT_FROM_EMAIL
from django.urls import reverse # Для генерации URL
from django.utils.translation import gettext as _ # Используем gettext для форматирования строк
from django.utils.html import escape # Для экранирования текста комментария
from django.core.mail import send_mail # Для отправки email

from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
import logging

from .models import TaskComment, Task, Project, TaskCategory, TaskSubcategory # Импортируем все нужные модели

logger = logging.getLogger(__name__)

# --- Сигналы для уведомлений (можно оставить, если используется сложная логика) ---
task_completed_signal = Signal() # Сигнал о завершении задачи
# task_assigned_signal = Signal() # Пример: Сигнал о назначении задачи
# new_comment_signal = Signal() # Если не используется post_save TaskComment напрямую

# --- Обработчики сигналов моделей для WebSocket ---

def _send_ws_model_update(instance, action, group_name_base, event_type_base="model_update_event"):
    """
    Вспомогательная функция для отправки WebSocket уведомлений об обновлении модели.
    `action` может быть "create", "update", "delete".
    """
    channel_layer = get_channel_layer()
    if not channel_layer:
        logger.error("Channel layer not available for WebSocket notification.")
        return

    model_name = instance.__class__.__name__.lower()
    instance_id = instance.pk

    # Сообщение для списка (более общее)
    list_group_name = f"{group_name_base}_list"
    list_message = {
        "action": action,
        "model": model_name,
        "id": instance_id,
    }
    if action != "delete": # Для create/update добавляем больше данных
        # Сериализатор был бы здесь идеальным решением для консистентности данных с API
        # Для простоты, пока основные поля:
        list_message.update({
            "name": getattr(instance, 'name', str(instance)), # Если есть поле 'name'
            "title": getattr(instance, 'title', None),       # Если есть поле 'title'
            "status": getattr(instance, 'status', None),     # Для задач
            # Добавить другие поля, важные для отображения в списках
        })


    async_to_sync(channel_layer.group_send)(
        list_group_name,
        {"type": f"{event_type_base}", "message": list_message} # e.g., project_update, category_update
    )
    logger.debug(f"WS {action} notification sent to group '{list_group_name}' for {model_name} {instance_id}")

    # Сообщение для детальной страницы (если есть)
    if action != "delete": # Для delete детальная страница обычно не актуальна
        detail_group_name = f"{group_name_base}_{instance_id}"
        # Здесь данные должны быть более полными, как от сериализатора
        # Опять же, сериализатор был бы лучше.
        detail_message = list_message.copy() # Начинаем с того же, что и для списка
        # detail_message.update({ ... более детальные поля ... }) #

        async_to_sync(channel_layer.group_send)(
            detail_group_name,
            {"type": f"{event_type_base}", "message": detail_message}
        )
        logger.debug(f"WS {action} notification sent to group '{detail_group_name}' for {model_name} {instance_id}")


@receiver(post_save, sender=Project)
def project_post_save_handler(sender, instance: Project, created: bool, **kwargs):
    action = "create" if created else "update"
    _send_ws_model_update(instance, action, group_name_base="projects", event_type_base="project_update")

@receiver(post_delete, sender=Project)
def project_post_delete_handler(sender, instance: Project, **kwargs):
    _send_ws_model_update(instance, "delete", group_name_base="projects", event_type_base="project_update")


@receiver(post_save, sender=TaskCategory)
def category_post_save_handler(sender, instance: TaskCategory, created: bool, **kwargs):
    action = "create" if created else "update"
    _send_ws_model_update(instance, action, group_name_base="categories", event_type_base="category_update")

@receiver(post_delete, sender=TaskCategory)
def category_post_delete_handler(sender, instance: TaskCategory, **kwargs):
    _send_ws_model_update(instance, "delete", group_name_base="categories", event_type_base="category_update")


@receiver(post_save, sender=TaskSubcategory)
def subcategory_post_save_handler(sender, instance: TaskSubcategory, created: bool, **kwargs):
    action = "create" if created else "update"
    _send_ws_model_update(instance, action, group_name_base="subcategories", event_type_base="subcategory_update")

@receiver(post_delete, sender=TaskSubcategory)
def subcategory_post_delete_handler(sender, instance: TaskSubcategory, **kwargs):
    _send_ws_model_update(instance, "delete", group_name_base="subcategories", event_type_base="subcategory_update")


# Сигнал для Task уже определен в models.py (task_post_save_handler).
# Если он там, здесь его дублировать не нужно. Убедитесь, что он отправляет в нужные группы.
# Группы: "tasks_list" (для списка) и "tasks_<task_id>" (для деталей).
# Типы событий: "list_update" и "task_update" соответственно.

@receiver(post_delete, sender=Task)
def task_post_delete_handler(sender, instance: Task, **kwargs):
    # Отправка уведомления об удалении задачи
    channel_layer = get_channel_layer()
    if not channel_layer: return

    message_data = {"action": "delete", "model": "task", "id": instance.pk}
    # В группу списка
    async_to_sync(channel_layer.group_send)(
        "tasks_list",
        {"type": "list_update", "message": message_data}
    )
    # В группу деталей (если кто-то ее еще слушает)
    async_to_sync(channel_layer.group_send)(
        f"tasks_{instance.pk}",
        {"type": "task_update", "message": message_data} # Клиент на детальной стр. должен обработать удаление
    )
    logger.debug(f"WS delete notification sent for Task {instance.pk}")


@receiver(post_save, sender=TaskComment)
def broadcast_new_comment_ws(sender, instance: TaskComment, created: bool, **kwargs):
    if created:
        channel_layer = get_channel_layer()
        if not channel_layer:
            logger.error("Channel layer not available for TaskComment WebSocket notification.")
            return

        group_name = f'task_comments_{instance.task.id}' # Группа для комментариев конкретной задачи
        author = instance.author
        author_name = author.display_name if author and hasattr(author, 'display_name') else (author.username if author else _("Аноним"))
        
        author_avatar_url = None
        # Предполагаем, что у User есть поле 'userprofile' и у профиля 'image'
        if author and hasattr(author, 'userprofile') and hasattr(author.userprofile, 'image') and author.userprofile.image:
            author_avatar_url = author.userprofile.image.url
        # else: можно указать URL для дефолтного аватара

        comment_data = {
            'id': instance.id,
            'text': escape(instance.text), # Экранируем HTML
            'created_at_iso': instance.created_at.isoformat(), # Для JS удобно
            'created_at_display': instance.created_at.strftime('%d.%m.%Y %H:%M'), # Для отображения
            'author': {
                'id': author.id if author else None,
                'name': author_name,
                'avatar_url': author_avatar_url
            },
            'task_id': instance.task.id,
        }
        logger.debug(f"Broadcasting new comment {instance.id} to WS group {group_name}")
        try:
            async_to_sync(channel_layer.group_send)(
                group_name,
                {
                    'type': 'comment_message', # Должен совпадать с методом в TaskCommentConsumer
                    'message': comment_data
                }
            )
        except Exception as e:
             logger.error(f"Error sending TaskComment {instance.id} to WebSocket group {group_name}: {e}")


# --- Обработчики для email-уведомлений ---

@receiver(task_completed_signal)
def send_task_completed_email_notification(sender, task: Task, **kwargs):
    if not task: return

    recipients_emails = set()
    if task.created_by and task.created_by.email:
        recipients_emails.add(task.created_by.email)
    
    if hasattr(task, 'get_responsible_users'): # Проверка наличия метода
        for user in task.get_responsible_users():
            if user.email: recipients_emails.add(user.email)
    
    if hasattr(task, 'get_watchers'):
        for user in task.get_watchers():
            if user.email: recipients_emails.add(user.email)


    if recipients_emails and hasattr(settings, "SITE_URL"):
        try:
            # Используем request=None, если SITE_URL уже полный (https://domain.com)
            # Если SITE_URL это просто домен, то нужен request для схемы.
            # Для простоты считаем, что SITE_URL - это полный базовый URL.
            task_url_path = reverse("tasks:task_detail", kwargs={"pk": task.pk})
            full_task_url = f"{settings.SITE_URL.strip('/')}{task_url_path}"

            subject = _("Задача '%(task_number)s' выполнена") % {'task_number': task.task_number or task.pk}
            message_body = _(
                "Здравствуйте,\n\n"
                "Задача \"%(title)s\" (номер: %(task_number)s) в проекте \"%(project_name)s\" была отмечена как выполненная.\n\n"
                "Статус: %(status)s\n"
                "Дата завершения: %(completion_date)s\n\n"
                "Подробности по ссылке: %(task_url)s\n\n"
                "С уважением,\nВаша система управления задачами."
            ) % {
                'title': task.title,
                'task_number': task.task_number or task.pk,
                'project_name': task.project.name if task.project else _('N/A'),
                'status': task.get_status_display(),
                'completion_date': task.completion_date.strftime('%d.%m.%Y %H:%M') if task.completion_date else _('N/A'),
                'task_url': full_task_url
            }
            
            send_mail(
                subject,
                message_body,
                settings.DEFAULT_FROM_EMAIL,
                list(recipients_emails),
                fail_silently=False # Установить в True для продакшена, если ошибки email не критичны
            )
            logger.info(f"Email уведомление о выполнении задачи {task.id} отправлено: {recipients_emails}")
        except Exception as e:
            logger.exception(f"Ошибка при отправке email-уведомления о выполнении задачи {task.id}: {e}")
    elif not recipients_emails:
        logger.warning(f"Нет получателей для email-уведомления о выполнении задачи {task.id}")


# Пример подключения обработчика к сигналу post_save Task для вызова task_completed_signal
# Этот код должен быть здесь, если task_post_save_handler в models.py не вызывает task_completed_signal.
# Если вызывает, то этот блок не нужен.
# @receiver(post_save, sender=Task)
# def trigger_task_completed_signal_on_status_change(sender, instance: Task, created: bool, update_fields=None, **kwargs):
#     if instance.status == Task.StatusChoices.COMPLETED:
#         just_completed = False
#         if created:
#             just_completed = True
#         elif update_fields and 'status' in update_fields:
#             # Здесь нужна более сложная логика для определения, что статус *только что* изменился на COMPLETED
#             # Например, сравнить с предыдущим значением (если доступно)
#             # Пока что упрощенно: если статус в update_fields и он COMPLETED, считаем "только что"
#             just_completed = True
#
#         if just_completed:
#             logger.info(f"Task {instance.id} status changed to COMPLETED, sending task_completed_signal.")
#             task_completed_signal.send(sender=instance.__class__, task=instance)

# Примечание: Логика вызова task_completed_signal уже есть в models.Task.task_post_save_handler.
# Убедитесь, что она там корректно работает и не дублируется.