# tasks/views/ajax.py
import json
import logging
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from django.views.decorators.csrf import csrf_protect
from django.views.decorators.http import require_POST

# Убедитесь, что импорт Task корректен
from ..models import Task
# Убедитесь, что TaskUserRole импортирован, если используете его в проверке прав
# from user_profiles.models import TaskUserRole

logger = logging.getLogger(__name__)

@csrf_protect
@require_POST
@login_required
def update_task_status(request, task_id):
    """Обновляет статус задачи через AJAX POST запрос (например, из Kanban)."""
    logger.info(f"AJAX update_task_status called for task {task_id}")
    user = request.user

    if not user.is_authenticated:
        return JsonResponse({'error': 'Unauthorized', 'message': _('Необходимо войти в систему.')}, status=401)

    task = get_object_or_404(Task, id=task_id)

    if not task.has_permission_to_change(user):
        logger.warning(f"User {user.username} forbidden to change status for task {task_id}")
        return JsonResponse({'error': 'Forbidden', 'message': _('У вас нет прав на изменение статуса этой задачи.')}, status=403)

    if request.content_type != 'application/json':
        return JsonResponse({'error': 'Bad Request', 'message': _('Ожидается JSON (application/json)')}, status=400)

    try:
        data = json.loads(request.body)
        new_status = data.get('status')
    except (json.JSONDecodeError, TypeError) as e:
        logger.error(f"JSONDecodeError for task {task_id} status update: {e}")
        return JsonResponse({'error': 'Bad Request', 'message': _('Неверный формат JSON')}, status=400)

    valid_statuses = {choice[0] for choice in Task.TASK_STATUS_CHOICES}
    if new_status not in valid_statuses:
        logger.warning(f"Invalid status '{new_status}' received for task {task_id}. Valid: {valid_statuses}")
        return JsonResponse({'error': 'Bad Request', 'message': _('Недопустимый статус: %s') % new_status}, status=400)

    old_status = task.status
    updated_fields = {'updated_at'}  # Всегда обновляем

    if old_status != new_status:
        task.status = new_status
        updated_fields.add('status')

        if new_status == "completed" and not task.completion_date:
            task.completion_date = timezone.now()
            updated_fields.add('completion_date')
        elif old_status == "completed" and task.completion_date:
            task.completion_date = None
            updated_fields.add('completion_date')

    if len(updated_fields) > 1:
        try:
            logger.debug(f"Task before save: Assignee = {task.assignee}, Team = {task.team}, Status = {task.status}")
            task.save(update_fields=updated_fields)
            logger.info(f"Task {task_id} updated fields {updated_fields} by user {user.username}.")
        except Exception as e:
            logger.error(f"Error saving task {task_id}: {e}")
            return JsonResponse({'error': 'Save Error', 'message': _('Ошибка при сохранении задачи.')}, status=500)

        return JsonResponse({'success': True, 'new_status_key': task.status, 'new_status_display': task.get_status_display(), 'message': _('Статус задачи обновлен')})
    
    return JsonResponse({'success': True, 'message': _('Изменений не было')}, status=200)
