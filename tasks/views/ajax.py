# tasks/views/ajax.py
import json
import logging
from django.contrib.auth.decorators import login_required, permission_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from django.views.decorators.csrf import csrf_protect
from django.views.decorators.http import require_POST

from ..models import Task

logger = logging.getLogger(__name__)

@csrf_protect
@require_POST
@login_required
# @permission_required('tasks.change_task', raise_exception=True) # Basic permission check
def update_task_status(request, task_id):
    """
    Обновляет статус задачи через AJAX POST запрос (например, из Kanban).
    Handles permission checking and potential validation errors during save.
    """
    logger.info(f"AJAX update_task_status called for task {task_id} by user {request.user.username}")
    task = get_object_or_404(Task, id=task_id)
    user = request.user

    # Use the refined permission check from the Task model
    if not task.has_permission(user, 'change_status'):
        logger.warning(f"User {user.username} forbidden to change status for task {task_id}")
        return JsonResponse({'error': 'Forbidden', 'message': _('У вас нет прав на изменение статуса этой задачи.')}, status=403)

    if request.content_type != 'application/json':
        logger.warning(f"Invalid content type for task {task_id} status update: {request.content_type}")
        return JsonResponse({'error': 'Bad Request', 'message': _('Ожидается JSON (application/json)')}, status=400)

    try:
        data = json.loads(request.body)
        new_status = data.get('status')
        logger.debug(f"Received new status '{new_status}' for task {task_id}")
    except (json.JSONDecodeError, TypeError) as e:
        logger.error(f"JSONDecodeError for task {task_id} status update by {user.username}: {e}")
        return JsonResponse({'error': 'Bad Request', 'message': _('Неверный формат JSON')}, status=400)

    # Validate against the choices defined in the model
    valid_statuses = {choice[0] for choice in Task.StatusChoices.choices}
    if new_status not in valid_statuses:
        logger.warning(f"Invalid status '{new_status}' received for task {task_id}. Valid: {valid_statuses}")
        return JsonResponse({'error': 'Bad Request', 'message': _('Недопустимый статус: %s') % new_status}, status=400)

    old_status = task.status
    if old_status == new_status:
        logger.info(f"Task {task_id} status unchanged ('{new_status}'). No update needed.")
        return JsonResponse({'success': True, 'message': _('Статус не изменился.')}, status=200)

    # Prepare fields to update
    task.status = new_status
    updated_fields = {'status', 'updated_at'} # Always update 'updated_at'

    # Handle completion_date logic based on status change
    if new_status == Task.StatusChoices.COMPLETED and not task.completion_date:
        task.completion_date = timezone.now()
        updated_fields.add('completion_date')
        logger.debug(f"Setting completion_date for task {task_id}")
    elif old_status == Task.StatusChoices.COMPLETED and new_status != Task.StatusChoices.COMPLETED and task.completion_date:
        task.completion_date = None
        updated_fields.add('completion_date')
        logger.debug(f"Clearing completion_date for task {task_id}")

    # Handle overdue status update automatically via clean() before save
    if task.is_overdue and new_status not in [Task.StatusChoices.COMPLETED, Task.StatusChoices.CANCELLED, Task.StatusChoices.OVERDUE]:
        task.status = Task.StatusChoices.OVERDUE
        updated_fields.add('status') # Ensure status is in updated_fields if changed here
        logger.debug(f"Setting status to OVERDUE for task {task_id}")


    try:
        # Explicitly call clean() for the fields being updated if necessary,
        # or rely on full_clean() if saving without update_fields.
        # Using update_fields avoids calling full_clean unnecessarily, but might miss some validations.
        # If complex cross-field validation is needed even for status updates, remove update_fields.
        task.clean() # Call clean manually before saving with update_fields
        task.save(update_fields=list(updated_fields))
        logger.info(f"Task {task_id} status updated from '{old_status}' to '{task.status}' by {user.username}.")

        # Return updated status information
        return JsonResponse({
            'success': True,
            'task_id': task.id,
            'new_status_key': task.status,
            'new_status_display': task.get_status_display(),
            'message': _('Статус задачи успешно обновлен')
        })

    except ValidationError as e:
        # This catches validation errors raised by task.clean() or during save
        error_messages = e.messages
        logger.error(f"ValidationError saving task {task_id} status update by {user.username}: {error_messages}")
        # Return the specific validation error message
        return JsonResponse({'error': 'Validation Error', 'message': ". ".join(error_messages)}, status=400)
    except Exception as e:
        # Catch unexpected errors during save
        logger.exception(f"Unexpected error saving task {task_id} status update by {user.username}: {e}")
        return JsonResponse({'error': 'Server Error', 'message': _('Ошибка при сохранении задачи.')}, status=500)