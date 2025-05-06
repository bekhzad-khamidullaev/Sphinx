# tasks/views/ajax.py
import json
import logging
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.http import JsonResponse, HttpResponseBadRequest
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from django.views.decorators.csrf import csrf_protect
from django.views.decorators.http import require_POST, require_GET

from ..models import Task, TaskSubcategory, TaskCategory

logger = logging.getLogger(__name__)

@csrf_protect
@require_POST
@login_required
def update_task_status(request, task_id):
    logger.debug(f"AJAX update_task_status: task={task_id}, user={request.user.username}, content_type={request.content_type}")
    task = get_object_or_404(Task, id=task_id)
    user = request.user

    if not task.has_permission(user, 'change_status'):
        logger.warning(f"User {user.username} forbidden status change for task {task_id}")
        return JsonResponse({'error': 'Forbidden', 'message': _('Нет прав на изменение статуса.')}, status=403)

    if request.content_type != 'application/json':
        logger.warning(f"Invalid content type for task {task_id}: {request.content_type}")
        return JsonResponse({'error': 'Bad Request', 'message': _('Ожидается JSON.')}, status=400)

    try:
        data = json.loads(request.body)
        new_status = data.get('status')
        logger.debug(f"Task {task_id}: Received new status '{new_status}'")
    except (json.JSONDecodeError, TypeError) as e:
        logger.error(f"JSONDecodeError task {task_id}: {e}")
        return JsonResponse({'error': 'Bad Request', 'message': _('Неверный JSON.')}, status=400)

    valid_statuses = dict(Task.StatusChoices.choices).keys()
    if new_status not in valid_statuses:
        logger.warning(f"Invalid status '{new_status}' for task {task_id}. Valid: {valid_statuses}")
        return JsonResponse({'error': 'Bad Request', 'message': _('Недопустимый статус.')}, status=400)

    old_status = task.status
    if old_status == new_status:
        logger.info(f"Task {task_id} status unchanged ('{new_status}').")
        return JsonResponse({'success': True, 'message': _('Статус не изменился.')}, status=200)

    task.status = new_status
    updated_fields = {'status', 'updated_at'}

    try:
        task.clean()
        task.save(update_fields=list(updated_fields))
        logger.info(f"Task {task_id} status updated: '{old_status}' -> '{task.status}' by {user.username}.")
        return JsonResponse({
            'success': True,
            'task_id': task.id,
            'new_status_key': task.status,
            'new_status_display': task.get_status_display(),
            'message': _('Статус обновлен.')
        })
    except ValidationError as e:
        logger.error(f"ValidationError saving task {task_id}: {e.message_dict if hasattr(e, 'message_dict') else e.messages}")
        task.status = old_status
        return JsonResponse({'error': 'Validation Error', 'message': ". ".join(e.messages)}, status=400)
    except Exception as e:
        logger.exception(f"Error saving task {task_id} status update: {e}")
        return JsonResponse({'error': 'Server Error', 'message': _('Ошибка сохранения.')}, status=500)


@require_GET
@login_required
def load_subcategories(request):
    category_id = request.GET.get('category_id')
    if not category_id:
        return JsonResponse({'error': 'Missing category_id parameter'}, status=400)
    try:
        # No need to fetch the category object itself if we only need the ID for filtering
        subcategories = TaskSubcategory.objects.filter(category_id=category_id).order_by('name')
        # Return simple list of id/name pairs, suitable for Select2 or basic dropdowns
        data = list(subcategories.values('id', 'name'))
        return JsonResponse(data, safe=False)
    except ValueError: # Handle case where category_id is not a valid integer
         return JsonResponse({'error': 'Invalid category_id format'}, status=400)
    except Exception as e:
        logger.error(f"Error loading subcategories for category_id {category_id}: {e}")
        return JsonResponse({'error': 'Server error'}, status=500)