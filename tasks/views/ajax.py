from rest_framework import viewsets, permissions, status, filters
from rest_framework.views import APIView
from rest_framework.response import Response
from django_filters.rest_framework import DjangoFilterBackend
from django.db.models import Q, Count, Prefetch
from django.contrib.auth import get_user_model
from django.utils.translation import gettext_lazy as _
from django.urls import reverse
from django.db import transaction
from django.conf import settings
from django.shortcuts import get_object_or_404

import json
from django.core.serializers.json import DjangoJSONEncoder
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_protect
from django.views.decorators.http import require_POST
from django.core.exceptions import ValidationError

import logging
logging.getLogger('django.db.backends').setLevel(logging.INFO)
logger = logging.getLogger(__name__)

from django.db import models
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_GET

from ..models import (Project, TaskCategory, TaskSubcategory, Task, TaskPhoto, TaskAssignment, Team, Department)
from ..serializers import (
    ProjectSerializer, TaskCategorySerializer, TaskSubcategorySerializer,
    TaskSerializer, TaskPhotoSerializer, TaskAssignmentSerializer
)

User = get_user_model()
# Optional imports
try: from checklists.models import ChecklistTemplate, ChecklistRun
except ImportError: ChecklistTemplate, ChecklistRun = None, None
try: from room.models import Room
except ImportError: Room = None


class ProjectViewSet(viewsets.ModelViewSet):
    queryset = Project.objects.annotate(task_count=Count('tasks')).order_by('name')
    serializer_class = ProjectSerializer
    permission_classes = [permissions.IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['start_date', 'end_date', 'is_active', 'owner']
    search_fields = ['name', 'description']
    ordering_fields = ['name', 'start_date', 'end_date', 'created_at', 'task_count']
    ordering = ['name']

class TaskCategoryViewSet(viewsets.ModelViewSet):
    queryset = TaskCategory.objects.all().order_by('name')
    serializer_class = TaskCategorySerializer
    permission_classes = [permissions.IsAuthenticated]
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ['name', 'description']
    ordering_fields = ['name', 'created_at']
    ordering = ['name']

class TaskSubcategoryViewSet(viewsets.ModelViewSet):
    queryset = TaskSubcategory.objects.select_related('category').order_by('category__name', 'name')
    serializer_class = TaskSubcategorySerializer
    permission_classes = [permissions.IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['category', 'category__name']
    search_fields = ['name', 'description', 'category__name']
    ordering_fields = ['name', 'category__name', 'created_at']
    ordering = ['category__name', 'name']

    def list(self, request, *args, **kwargs):
        category_id = request.query_params.get('category')
        queryset = self.filter_queryset(self.get_queryset())
        if category_id:
            queryset = queryset.filter(category_id=category_id)

        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            if request.accepted_renderer.format == 'json' and request.query_params.get('select2'):
                 return Response(serializer.data)
            return self.get_paginated_response(serializer.data)

        serializer = self.get_serializer(queryset, many=True)
        if request.accepted_renderer.format == 'json' and request.query_params.get('select2'):
             return Response(serializer.data)
        return Response(serializer.data)


class TaskViewSet(viewsets.ModelViewSet):
    queryset = Task.objects.select_related(
        'project', 'category', 'subcategory', 'created_by', 'team', 'department'
    ).prefetch_related(
        'photos',
        Prefetch('assignments', queryset=TaskAssignment.objects.select_related('user'))
    ).order_by('-created_at')
    serializer_class = TaskSerializer
    permission_classes = [permissions.IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = {
        'project': ['exact'], 'category': ['exact'], 'subcategory': ['exact'],
        'status': ['exact', 'in'], 'priority': ['exact', 'in'],
        'created_by': ['exact'], 'team': ['exact'], 'department': ['exact'],
        'due_date': ['exact', 'lte', 'gte', 'range'],
        'start_date': ['exact', 'lte', 'gte', 'range'],
        'completion_date': ['exact', 'lte', 'gte', 'range', 'isnull'],
        'assignments__user': ['exact'],
        'assignments__role': ['exact', 'in'],
    }
    search_fields = [
        'task_number', 'title', 'description',
        'project__name', 'created_by__username',
        'assignments__user__username'
    ]
    ordering_fields = [
        'task_number', 'title', 'status', 'priority', 'due_date',
        'start_date', 'completion_date', 'created_at', 'project__name',
        'team__name', 'department__name'
    ]
    ordering = ['-created_at']

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)

    def perform_update(self, serializer):
        serializer.save()

class TaskAssignmentViewSet(viewsets.ModelViewSet):
    queryset = TaskAssignment.objects.select_related('task', 'user', 'assigned_by').all()
    serializer_class = TaskAssignmentSerializer
    permission_classes = [permissions.IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.OrderingFilter]
    filterset_fields = ['task', 'user', 'role', 'assigned_by']
    ordering_fields = ['created_at', 'task__title', 'user__username', 'role']
    ordering = ['-created_at']

    def perform_create(self, serializer):
        assigned_by_user = self.request.user if self.request.user.is_authenticated else None
        serializer.save(assigned_by=assigned_by_user)

class TaskPhotoViewSet(viewsets.ModelViewSet):
    queryset = TaskPhoto.objects.select_related('task', 'uploaded_by').order_by('-created_at')
    serializer_class = TaskPhotoSerializer
    permission_classes = [permissions.IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.OrderingFilter]
    filterset_fields = ['task', 'uploaded_by']
    ordering_fields = ['created_at', 'task__task_number']
    ordering = ['-created_at']

    def perform_create(self, serializer):
        serializer.save(uploaded_by=self.request.user)


class SearchSuggestionsView(APIView):
    permission_classes = [permissions.IsAuthenticated]
    def get(self, request, *args, **kwargs):
        query = request.query_params.get('q', '').strip()
        suggestions = []
        limit = 5

        if len(query) >= 2:
            tasks_qs = Task.objects.filter(
                Q(title__icontains=query) | Q(task_number__icontains=query)
            ).select_related('project')[:limit]
            suggestions.extend([{
                'type': 'task', 'id': t.id, 'title': f"#{t.task_number}: {t.title}",
                'context': t.project.name if t.project else '',
                'url': t.get_absolute_url(), 'icon': 'tasks', 'color': 'blue'
            } for t in tasks_qs])

            projects_qs = Project.objects.filter(name__icontains=query)[:limit]
            suggestions.extend([{
                'type': 'project', 'id': p.id, 'title': p.name, 'context': _("Проект"),
                'url': p.get_absolute_url(), 'icon': 'project-diagram', 'color': 'purple'
            } for p in projects_qs])

            cats_qs = TaskCategory.objects.filter(name__icontains=query)[:limit]
            suggestions.extend([{
                'type': 'category', 'id': c.id, 'title': c.name, 'context': _("Категория"),
                'url': reverse('tasks:category_detail', kwargs={'pk': c.pk}),
                'icon': 'folder-open', 'color': 'teal'
            } for c in cats_qs])

            subcats_qs = TaskSubcategory.objects.filter(name__icontains=query).select_related('category')[:limit]
            suggestions.extend([{
                'type': 'subcategory', 'id': sc.id, 'title': f"{sc.category.name} / {sc.name}", 'context': _("Подкатегория"),
                'url': reverse('tasks:subcategory_detail', kwargs={'pk': sc.pk}),
                'icon': 'folder', 'color': 'cyan'
            } for sc in subcats_qs])

            users_qs = User.objects.filter(
                Q(username__icontains=query) | Q(first_name__icontains=query) | Q(last_name__icontains=query) | Q(email__icontains=query),
                is_active=True
            )[:limit]
            suggestions.extend([{
                'type': 'user', 'id': u.id, 'title': f"{u.display_name or u.username} (@{u.username})",
                'context': u.job_title or _('Пользователь'),
                'url': u.get_absolute_url() if hasattr(u, 'get_absolute_url') else '#',
                'icon': 'user', 'color': 'orange'
            } for u in users_qs])

            if hasattr(Team, 'objects') and not isinstance(Team, type(models.Model)):
                teams_qs = Team.objects.filter(name__icontains=query)[:limit]
                suggestions.extend([{
                    'type': 'team', 'id': t.id, 'title': t.name, 'context': _("Команда"),
                    'url': reverse('user_profiles:user_list') + f'?team={t.pk}' if 'user_profiles' in settings.INSTALLED_APPS else '#',
                    'icon': 'users-cog', 'color': 'pink'
                } for t in teams_qs])

            if hasattr(Department, 'objects') and not isinstance(Department, type(models.Model)):
                depts_qs = Department.objects.filter(name__icontains=query)[:limit]
                suggestions.extend([{
                    'type': 'department', 'id': d.id, 'title': d.name, 'context': _("Отдел"),
                    'url': reverse('user_profiles:user_list') + f'?department={d.pk}' if 'user_profiles' in settings.INSTALLED_APPS else '#',
                    'icon': 'building', 'color': 'sky'
                } for d in depts_qs])

            if ChecklistTemplate:
                 templates = ChecklistTemplate.objects.filter(name__icontains=query, is_archived=False)[:limit]
                 suggestions.extend([{'type': 'checklist_template', 'id': t.id, 'title': t.name, 'context': _("Шаблон"), 'url': t.get_absolute_url(), 'icon': 'clipboard-list', 'color': 'indigo'} for t in templates])
            if ChecklistRun:
                runs = ChecklistRun.objects.filter(Q(template__name__icontains=query) | Q(performed_by__username__icontains=query)).select_related('template', 'performed_by').order_by('-performed_at')[:limit]
                suggestions.extend([{'type': 'checklist_run', 'id': r.id, 'title': f"{r.template.name} ({r.performed_at:%d.%m.%y})", 'context': f"{_('Выполнен')}: {r.performed_by.display_name if r.performed_by else '-'}", 'url': r.get_absolute_url(), 'icon': 'history', 'color': 'gray'} for r in runs])

            if Room:
                rooms_qs = Room.objects.filter(name__icontains=query)[:limit]
                suggestions.extend([{'type': 'room', 'id': r.id, 'title': f"# {r.name}", 'context': _("Чат"), 'url': r.get_absolute_url(), 'icon': 'comments', 'color': 'green'} for r in rooms_qs])

        return Response({'results': suggestions[:15]})

class UserAutocompleteView(APIView):
    permission_classes = [permissions.IsAuthenticated]
    def get(self, request, *args, **kwargs):
        query = request.query_params.get('q', '').strip()
        project_id_str = request.query_params.get('project')
        page = int(request.query_params.get('page', 1))
        page_size = 20

        results = []
        more = False

        if len(query) >= 1:
            search_filter = (
                Q(username__icontains=query) |
                Q(first_name__icontains=query) |
                Q(last_name__icontains=query) |
                Q(email__icontains=query)
            )
            queryset = User.objects.filter(is_active=True).filter(search_filter)

            # Project-specific user filtering logic can be added here if needed.
            # For example, if Project has a Team, filter users by that Team.
            # if project_id_str and project_id_str.isdigit():
            #     project_id = int(project_id_str)
            #     try:
            #         project = Project.objects.get(pk=project_id)
            #         if project.team: # Assuming Project.team FK to Team
            #             queryset = queryset.filter(teams=project.team) # Assuming User.teams M2M to Team
            #     except Project.DoesNotExist:
            #         queryset = queryset.none()


            total_count = queryset.count()
            start_index = (page - 1) * page_size
            end_index = start_index + page_size

            if total_count > end_index:
                more = True

            users = queryset.order_by('username')[start_index:end_index]
            results = [{'id': user.pk, 'text': user.display_name or user.username} for user in users]

        return Response({'results': results, 'pagination': {'more': more}})
    

@require_GET # Важно: для загрузки данных лучше использовать GET
@login_required # Или другая проверка прав, если необходимо
def load_subcategories(request):
    category_id = request.GET.get('category_id')
    if not category_id:
        return JsonResponse({'error': 'Missing category_id parameter'}, status=400)
    try:
        # Преобразуем category_id в int для безопасности и корректной фильтрации
        category_id_int = int(category_id)
        subcategories = TaskSubcategory.objects.filter(category_id=category_id_int).order_by('name')
        # Возвращаем простой список id/name пар, подходящий для Select2 или базовых выпадающих списков
        data = list(subcategories.values('id', 'name'))
        return JsonResponse(data, safe=False)
    except ValueError: # Обработка случая, если category_id не является валидным числом
         return JsonResponse({'error': 'Invalid category_id format'}, status=400)
    except Exception as e:
        logger.error(f"Error loading subcategories for category_id {category_id}: {e}")
        return JsonResponse({'error': 'Server error'}, status=500)
# ---------------------------------------------
@csrf_protect # CSRF защита важна для POST запросов, изменяющих данные
@require_POST # Изменение статуса - это POST запрос
@login_required
def update_task_status(request, task_id):
    logger.debug(f"AJAX update_task_status: task={task_id}, user={request.user.username}, content_type={request.content_type}")
    task = get_object_or_404(Task, id=task_id)
    user = request.user

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

    # Проверка прав доступа к изменению статуса задачи
    if not task.can_change_status(user, new_status): # Используем метод модели Task
        logger.warning(f"User {user.username} forbidden status change for task {task_id} to {new_status}")
        return JsonResponse({'error': 'Forbidden', 'message': _('Нет прав на изменение статуса на "%(status)s".') % {'status': Task.StatusChoices(new_status).label}}, status=403)

    old_status = task.status
    if old_status == new_status:
        logger.info(f"Task {task_id} status unchanged ('{new_status}').")
        return JsonResponse({'success': True, 'message': _('Статус не изменился.')}, status=200)

    task.status = new_status
    # updated_fields = {'status', 'updated_at'} # clean() может изменить completion_date, так что лучше не ограничивать поля здесь
                                             # или убедиться, что clean() и save() в модели Task правильно обрабатывают update_fields

    try:
        setattr(task, '_initiator_user_id', user.id) # Для сигналов, если они нужны для отслеживания, кто изменил статус
        task.clean() # Вызываем clean для валидации и установки completion_date, если нужно
        task.save() # Сохраняем все изменения после clean
        if hasattr(task, '_initiator_user_id'):
            delattr(task, '_initiator_user_id')

        logger.info(f"Task {task_id} status updated: '{old_status}' -> '{task.status}' by {user.username}.")
        return JsonResponse({
            'success': True,
            'task_id': task.id,
            'new_status_key': task.status,
            'new_status_display': task.get_status_display(), # Убедитесь, что у модели Task есть get_status_display()
            'completion_date': task.completion_date.isoformat() if task.completion_date else None, # Отправляем обновленную дату завершения
            'updated_at': task.updated_at.isoformat(), # Отправляем обновленную дату обновления
            'message': _('Статус обновлен.')
        })
    except ValidationError as e:
        logger.error(f"ValidationError saving task {task_id}: {e.message_dict if hasattr(e, 'message_dict') else e.messages}")
        task.status = old_status # Откатываем статус, если сохранение не удалось
        return JsonResponse({'error': 'Validation Error', 'message': ". ".join(e.messages)}, status=400)
    except Exception as e:
        logger.exception(f"Error saving task {task_id} status update: {e}")
        task.status = old_status # Откатываем статус
        return JsonResponse({'error': 'Server Error', 'message': _('Ошибка сохранения.')}, status=500)
# ---------------------------------------------

@require_POST
@login_required
def delete_task_ajax(request, task_id):
    task = get_object_or_404(Task, pk=task_id)

    # Optional: Check permissions
    if not task.can_delete(request.user): # Assuming you have a can_delete method on your Task model
        logger.warning(f"User {request.user.username} forbidden to delete task {task_id}")
        return JsonResponse({'success': False, 'message': _('У вас нет прав на удаление этой задачи.')}, status=403)

    try:
        task_display_info = f"#{task.task_number or task.pk} '{task.title}'"
        # Set initiator_user_id if your model's delete signal or logic needs it
        # setattr(task, '_initiator_user_id', request.user.id)
        task.delete()
        logger.info(f"Task {task_display_info} AJAX deleted by {request.user.username}.")
        return JsonResponse({'success': True, 'message': _('Задача "%(name)s" успешно удалена.') % {'name': task_display_info}})
    except Exception as e:
        logger.error(f"Error AJAX deleting task {task_id} by user {request.user.username}: {e}", exc_info=True)
        return JsonResponse({'success': False, 'message': _('Произошла ошибка при удалении задачи.')}, status=500)