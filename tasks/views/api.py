# tasks/views/api.py
from rest_framework import viewsets, permissions, status, filters
from rest_framework.views import APIView
from rest_framework.response import Response
from django_filters.rest_framework import DjangoFilterBackend
from django.db.models import Q, Count
from django.contrib.auth import get_user_model
from django.utils.translation import gettext_lazy as _
from django.urls import reverse

from ..models import (Project, TaskCategory, TaskSubcategory, Task, TaskPhoto)
from ..serializers import (
    ProjectSerializer, TaskCategorySerializer, TaskSubcategorySerializer,
    TaskSerializer, TaskPhotoSerializer
)
# user_profiles.models импортируются здесь для SearchSuggestionsView и UserAutocompleteView
# Убедитесь, что они доступны и User модель определена корректно.
from user_profiles.models import User, Team, Department # Assuming availability

# Optional imports, handled gracefully
try: from checklists.models import ChecklistTemplate, ChecklistRun
except ImportError: ChecklistTemplate, ChecklistRun = None, None
try: from room.models import Room
except ImportError: Room = None

User = get_user_model()

class ProjectViewSet(viewsets.ModelViewSet):
    queryset = Project.objects.annotate(task_count=Count('tasks')).order_by('name')
    serializer_class = ProjectSerializer
    permission_classes = [permissions.IsAuthenticated] # Заменить на более гранулярные права
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['start_date', 'end_date'] # Добавить другие поля по необходимости
    search_fields = ['name', 'description']
    ordering_fields = ['name', 'start_date', 'end_date', 'created_at', 'task_count']
    ordering = ['name']

class TaskCategoryViewSet(viewsets.ModelViewSet):
    queryset = TaskCategory.objects.annotate(
        task_count=Count('tasks'),
        subcategory_count=Count('subcategories')
    ).order_by('name')
    serializer_class = TaskCategorySerializer
    permission_classes = [permissions.IsAuthenticated]
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ['name', 'description']
    ordering_fields = ['name', 'created_at', 'task_count', 'subcategory_count']
    ordering = ['name']

class TaskSubcategoryViewSet(viewsets.ModelViewSet):
    queryset = TaskSubcategory.objects.select_related('category').annotate(
        task_count=Count('tasks')
    ).order_by('category__name', 'name')
    serializer_class = TaskSubcategorySerializer
    permission_classes = [permissions.IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    # Use 'category' (PK) for filtering from Task form's dependent dropdown AJAX
    filterset_fields = ['category', 'category__name']
    search_fields = ['name', 'description', 'category__name']
    ordering_fields = ['name', 'category__name', 'created_at', 'task_count']
    ordering = ['category__name', 'name']

    # Оставляем list метод для поддержки параметра 'select2', если он используется веб-фронтендом
    def list(self, request, *args, **kwargs):
        category_id = request.query_params.get('category') # Фильтрация по category_id
        select2_request = request.query_params.get('select2', 'false').lower() == 'true'

        queryset = self.filter_queryset(self.get_queryset())
        if category_id:
            queryset = queryset.filter(category_id=category_id)

        # Если это запрос для Select2, не используем пагинацию DRF, возвращаем плоский список
        if select2_request:
            serializer = self.get_serializer(queryset, many=True)
            return Response(serializer.data) # Возвращаем список напрямую

        # Стандартная пагинация для API
        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)

        serializer = self.get_serializer(queryset, many=True)
        return Response(serializer.data)


class TaskViewSet(viewsets.ModelViewSet):
    queryset = Task.objects.select_related(
        'project', 'category', 'subcategory', 'created_by'
    ).prefetch_related(
        'photos', 'user_roles__user' # user_roles - related_name из TaskUserRole
    ).order_by('-created_at')
    serializer_class = TaskSerializer
    permission_classes = [permissions.IsAuthenticated] # Заменить на кастомные права
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    # filterset_class = TaskAPIFilter # Можно создать отдельный класс фильтра для API
    filterset_fields = { # Более гибкая настройка фильтров
        'project': ['exact'],
        'category': ['exact'],
        'subcategory': ['exact'],
        'status': ['exact', 'in'],
        'priority': ['exact', 'in', 'gte', 'lte'],
        'created_by': ['exact'],
        'deadline': ['exact', 'gte', 'lte', 'isnull'],
        'start_date': ['exact', 'gte', 'lte'],
        'completion_date': ['exact', 'gte', 'lte', 'isnull'],
        # Для фильтрации по ролям пользователей (если TaskUserRole существует):
        # 'user_roles__user': ['exact'],
        # 'user_roles__role': ['exact'],
    }
    search_fields = ['task_number', 'title', 'description', 'project__name', 'created_by__username']
    ordering_fields = ['task_number', 'title', 'status', 'priority', 'deadline', 'start_date', 'completion_date', 'created_at', 'project__name']
    ordering = ['-created_at']

    # perform_create уже есть, устанавливает created_by
    # def perform_create(self, serializer):
    #     serializer.save(created_by=self.request.user)

    # Можно добавить кастомные actions, например, для изменения статуса
    # from rest_framework.decorators import action
    # @action(detail=True, methods=['post'], permission_classes=[IsTaskParticipantOrAdmin]) # Нужен кастомный permission
    # def set_status(self, request, pk=None):
    #     task = self.get_object()
    #     new_status = request.data.get('status')
    #     if not new_status or new_status not in dict(Task.StatusChoices.choices).keys():
    #         return Response({'error': 'Invalid status provided'}, status=status.HTTP_400_BAD_REQUEST)
    #     task.status = new_status
    #     task.save(update_fields=['status', 'updated_at']) # completion_date обновится в model.save()
    #     return Response(TaskSerializer(task, context={'request': request}).data)


class TaskPhotoViewSet(viewsets.ModelViewSet):
    queryset = TaskPhoto.objects.select_related('task', 'uploaded_by').order_by('-created_at')
    serializer_class = TaskPhotoSerializer
    permission_classes = [permissions.IsAuthenticated] # Кастомные права: может ли пользователь добавлять/удалять фото к этой задаче
    filter_backends = [DjangoFilterBackend, filters.OrderingFilter]
    filterset_fields = ['task', 'uploaded_by']
    ordering_fields = ['created_at', 'task__task_number']
    ordering = ['-created_at']

    # perform_create уже есть, устанавливает uploaded_by
    # def perform_create(self, serializer):
    #     serializer.save(uploaded_by=self.request.user)

# Представление для глобального поиска (Search Bar)
class SearchSuggestionsView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, *args, **kwargs):
        query = request.query_params.get('q', '').strip()
        suggestions = []
        limit = 5 # Лимит на каждый тип результата

        if len(query) >= 2: # Минимальная длина запроса
            # Задачи
            tasks = Task.objects.filter(
                Q(title__icontains=query) | Q(task_number__icontains=query)
            ).select_related('project')[:limit]
            suggestions.extend([
                { 'type': 'task',
                  'title': f"#{t.task_number}: {t.title}",
                  'context': t.project.name if t.project else '',
                  'url': t.get_absolute_url(), # URL для веб-версии
                  'api_url': reverse('tasks:task-api-detail', kwargs={'pk': t.pk}, request=request), # URL для API
                  'icon': 'tasks', 'color': 'blue'} for t in tasks
            ])

            # Проекты
            projects = Project.objects.filter(name__icontains=query)[:limit]
            suggestions.extend([
                { 'type': 'project', 'title': p.name, 'context': _("Проект"),
                  'url': p.get_absolute_url(),
                  'api_url': reverse('tasks:project-api-detail', kwargs={'pk': p.pk}, request=request),
                  'icon': 'project-diagram', 'color': 'purple'} for p in projects
            ])

            # Категории
            cats = TaskCategory.objects.filter(name__icontains=query)[:limit]
            suggestions.extend([
                { 'type': 'category', 'title': c.name, 'context': _("Категория"),
                  'url': reverse('tasks:task_list') + f'?category={c.pk}',
                  'api_url': reverse('tasks:category-api-detail', kwargs={'pk': c.pk}, request=request),
                  'icon': 'folder-open', 'color': 'teal'} for c in cats
            ])
            
            # Пользователи (если user_profiles подключен)
            if User:
                users = User.objects.filter(
                    Q(username__icontains=query) | Q(first_name__icontains=query) |
                    Q(last_name__icontains=query) | Q(email__icontains=query),
                    is_active=True
                )[:limit]
                suggestions.extend([
                    {'type': 'user',
                     'title': f"{u.display_name} (@{u.username})",
                     'context': u.job_title or '',
                     # 'url': u.get_absolute_url(), # Если есть профиль пользователя
                     # 'api_url': reverse('user-api-detail', kwargs={'pk': u.pk}, request=request), # Если есть API для User
                     'icon': 'user', 'color': 'orange'} for u in users
                ])

            # Команды (если user_profiles.Team подключен)
            if Team:
                teams = Team.objects.filter(name__icontains=query)[:limit]
                suggestions.extend([
                    {'type': 'team', 'title': t.name, 'context': _("Команда"),
                    #  'url': reverse('user_profiles:user_list') + f'?team={t.pk}', # Пример URL
                    #  'api_url': reverse('team-api-detail', kwargs={'pk': t.pk}, request=request), # Если есть API для Team
                     'icon': 'users-cog', 'color': 'pink'} for t in teams
                ])
            
            # Отделы (если user_profiles.Department подключен)
            if Department:
                depts = Department.objects.filter(name__icontains=query)[:limit]
                suggestions.extend([
                    {'type': 'department', 'title': d.name, 'context': _("Отдел"),
                    #  'url': reverse('user_profiles:user_list') + f'?department={d.pk}', # Пример URL
                    #  'api_url': reverse('department-api-detail', kwargs={'pk': d.pk}, request=request), # Если есть API для Department
                     'icon': 'building', 'color': 'sky'} for d in depts
                ])

            # Чек-листы (если подключены)
            if ChecklistTemplate:
                 templates = ChecklistTemplate.objects.filter(name__icontains=query, is_archived=False)[:limit]
                 suggestions.extend([{'type': 'checklist_template', 'title': t.name, 'context': _("Шаблон чек-листа"),
                                    #   'url': t.get_absolute_url(),
                                    #   'api_url': reverse('checklist-template-api-detail', kwargs={'pk': t.pk}, request=request),
                                      'icon': 'clipboard-list', 'color': 'indigo'} for t in templates])

            if ChecklistRun:
                runs = ChecklistRun.objects.filter(
                    Q(template__name__icontains=query) | Q(performed_by__username__icontains=query)
                ).select_related('template', 'performed_by').order_by('-performed_at')[:limit]
                suggestions.extend([{'type': 'checklist_run',
                                     'title': f"{r.template.name} ({r.performed_at:%d.%m.%y})",
                                     'context': f"{_('Выполнен')}: {r.performed_by.display_name if r.performed_by else '-'}",
                                    #  'url': r.get_absolute_url(),
                                    #  'api_url': reverse('checklist-run-api-detail', kwargs={'pk': r.pk}, request=request),
                                     'icon': 'history', 'color': 'gray'} for r in runs])
            
            # Чаты/комнаты (если подключены)
            if Room:
                rooms = Room.objects.filter(name__icontains=query)[:limit]
                suggestions.extend([{'type': 'room', 'title': f"# {r.name}", 'context': _("Чат"),
                                    #  'url': r.get_absolute_url(),
                                    #  'api_url': reverse('room-api-detail', kwargs={'pk': r.pk}, request=request),
                                     'icon': 'comments', 'color': 'green'} for r in rooms])

        return Response({'results': suggestions[:10]}) # Ограничиваем общее количество результатов

# Представление для автокомплита пользователей (для Select2 в формах)
class UserAutocompleteView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, *args, **kwargs):
        query = request.query_params.get('q', '').strip()
        project_id = request.query_params.get('project') # Для фильтрации по участникам проекта
        page = int(request.query_params.get('page', 1))
        page_size = 20 # Стандартный размер страницы для Select2

        results = []
        more = False # Флаг для Select2, есть ли еще страницы

        if len(query) >= 1: # Минимальная длина запроса для автокомплита
            search_filter = (
                Q(username__icontains=query) |
                Q(first_name__icontains=query) |
                Q(last_name__icontains=query) |
                Q(email__icontains=query)
            )
            queryset = User.objects.filter(is_active=True).filter(search_filter)

            # Пример фильтрации по участникам проекта (требует модели связи Project <-> User/Team)
            if project_id:
                try:
                    project = Project.objects.get(pk=project_id)
                    # Это пример, адаптируйте под вашу структуру связи проекта с пользователями/командами
                    # Например, если проект связан с командами, а команды с пользователями:
                    # team_ids = project.teams.values_list('id', flat=True)
                    # queryset = queryset.filter(teams__id__in=team_ids).distinct()
                    # Или если у задач есть TaskUserRole:
                    # user_ids_in_project_tasks = TaskUserRole.objects.filter(task__project_id=project_id).values_list('user_id', flat=True).distinct()
                    # queryset = queryset.filter(id__in=user_ids_in_project_tasks)
                    pass # Замените на вашу логику фильтрации по проекту
                except Project.DoesNotExist:
                    queryset = queryset.none() # Проект не найден, возвращаем пустой результат


            # Пагинация для Select2
            start_index = (page - 1) * page_size
            end_index = start_index + page_size
            
            total_count = queryset.count()
            if total_count > end_index:
                more = True

            users = queryset.order_by('username')[start_index:end_index]
            results = [{'id': user.pk, 'text': user.display_name or user.username} for user in users]

        return Response({
            'results': results,
            'pagination': {'more': more}
        })