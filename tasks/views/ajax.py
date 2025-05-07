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

from ..models import Task, TaskSubcategory, TaskCategory # TaskCategory для полноты

logger = logging.getLogger(__name__)

@csrf_protect
@require_POST
@login_required
def update_task_status(request, task_id):
    logger.debug(f"AJAX update_task_status: task_id={task_id}, user={request.user.username}, content_type={request.content_type}")
    task = get_object_or_404(Task, id=task_id)
    user = request.user

    # Используем метод has_permission из модели Task
    if not task.has_permission(user, 'change_status'):
        logger.warning(f"User {user.username} forbidden status change for task {task_id}")
        return JsonResponse({'error': 'Forbidden', 'message': _('Нет прав на изменение статуса этой задачи.')}, status=403)

    if request.content_type != 'application/json':
        logger.warning(f"Invalid content type for task {task_id} status update: {request.content_type}")
        return JsonResponse({'error': 'Bad Request', 'message': _('Ожидается JSON в теле запроса.')}, status=400)

    try:
        data = json.loads(request.body)
        new_status = data.get('status')
        logger.debug(f"Task {task_id}: Received new status '{new_status}' from AJAX request.")
    except (json.JSONDecodeError, TypeError) as e:
        logger.error(f"JSONDecodeError or TypeError decoding status for task {task_id}: {e}")
        return JsonResponse({'error': 'Bad Request', 'message': _('Неверный формат JSON.')}, status=400)

    valid_statuses = dict(Task.StatusChoices.choices).keys()
    if new_status not in valid_statuses:
        logger.warning(f"Invalid status '{new_status}' for task {task_id}. Valid statuses: {valid_statuses}")
        return JsonResponse({'error': 'Bad Request', 'message': _('Недопустимый статус задачи.')}, status=400)

    old_status = task.status
    if old_status == new_status:
        logger.info(f"Task {task_id} status unchanged ('{new_status}'). No action taken.")
        return JsonResponse({'success': True, 'message': _('Статус задачи не изменился.')}, status=200)

    task.status = new_status
    # Модель Task сама обработает completion_date и overdue status в методе clean/save.
    # `updated_at` обновится автоматически.
    updated_fields_to_save = {'status', 'updated_at'}
    if new_status == Task.StatusChoices.COMPLETED and not task.completion_date:
        updated_fields_to_save.add('completion_date')
    elif old_status == Task.StatusChoices.COMPLETED and new_status != Task.StatusChoices.COMPLETED:
        updated_fields_to_save.add('completion_date') # для сброса

    try:
        task.full_clean(exclude=['task_number']) # task_number не меняется, project тоже. Иначе full_clean может его требовать.
        task.save(update_fields=list(updated_fields_to_save))
        logger.info(f"Task {task_id} status successfully updated via AJAX: '{old_status}' -> '{task.status}' by {user.username}.")
        return JsonResponse({
            'success': True,
            'task_id': task.id,
            'new_status_key': task.status,
            'new_status_display': task.get_status_display(),
            'is_completed': task.status == Task.StatusChoices.COMPLETED,
            'is_overdue': task.is_overdue,
            'completion_date': task.completion_date.isoformat() if task.completion_date else None,
            'message': _('Статус задачи успешно обновлен.')
        })
    except ValidationError as e:
        logger.error(f"ValidationError saving task {task_id} status update via AJAX: {e.message_dict if hasattr(e, 'message_dict') else e.messages}")
        task.status = old_status # Откатываем статус в объекте, если сохранение не удалось
        error_message = ". ".join(e.messages) if hasattr(e, 'messages') else str(e)
        return JsonResponse({'error': 'Validation Error', 'message': error_message}, status=400)
    except Exception as e:
        logger.exception(f"Unexpected error saving task {task_id} status update via AJAX: {e}")
        return JsonResponse({'error': 'Server Error', 'message': _('Произошла внутренняя ошибка сервера при сохранении статуса.')}, status=500)


@require_GET
@login_required # Доступ к подкатегориям обычно для аутентифицированных пользователей
def load_subcategories(request):
    category_id_str = request.GET.get('category_id')
    if not category_id_str:
        return JsonResponse({'error': 'Missing category_id parameter'}, status=400)

    try:
        category_id = int(category_id_str)
        # Проверяем, существует ли такая категория (опционально, но полезно)
        if not TaskCategory.objects.filter(id=category_id).exists():
            return JsonResponse({'error': 'Invalid category_id. Category does not exist.'}, status=404)

        subcategories = TaskSubcategory.objects.filter(category_id=category_id).order_by('name')
        # Возвращаем простой список id/name, подходящий для Select2 или обычных dropdown
        data = list(subcategories.values('id', 'name')) # Используем values для эффективности
        return JsonResponse(data, safe=False) # safe=False для списка в корне JSON
    except ValueError: # Если category_id не является целым числом
         logger.warning(f"Invalid category_id format in load_subcategories: {category_id_str}")
         return JsonResponse({'error': 'Invalid category_id format. Must be an integer.'}, status=400)
    except Exception as e:
        logger.error(f"Error loading subcategories for category_id {category_id_str}: {e}")
        return JsonResponse({'error': 'Server error while loading subcategories.'}, status=500)