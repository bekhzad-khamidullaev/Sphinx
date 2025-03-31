# tasks/views/api.py
import logging
from django.db.models import Q
from django.urls import reverse, NoReverseMatch
from django.utils.translation import gettext_lazy as _
from django_filters.rest_framework import DjangoFilterBackend

from rest_framework import viewsets, permissions, filters as drf_filters
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated # Убраны лишние импорты

# Импортируем модели из правильных мест
from ..models import Project, TaskCategory, TaskSubcategory, Task, TaskPhoto
from user_profiles.models import Team, User # Импортируем User отсюда

from ..serializers import (
    ProjectSerializer, TaskCategorySerializer, TaskSubcategorySerializer,
    TaskSerializer, TaskPhotoSerializer
)
from ..filters import TaskFilter # Фильтр для TaskViewSet

logger = logging.getLogger(__name__)

# --- Existing ViewSets (без изменений) ---
class ProjectViewSet(viewsets.ModelViewSet):
    queryset = Project.objects.all().order_by('-created_at')
    serializer_class = ProjectSerializer
    permission_classes = [permissions.IsAuthenticatedOrReadOnly]

class TaskCategoryViewSet(viewsets.ModelViewSet):
    queryset = TaskCategory.objects.all().order_by('name')
    serializer_class = TaskCategorySerializer
    permission_classes = [permissions.IsAuthenticatedOrReadOnly]

class TaskSubcategoryViewSet(viewsets.ModelViewSet):
    queryset = TaskSubcategory.objects.select_related('category').order_by('category__name', 'name')
    serializer_class = TaskSubcategorySerializer
    permission_classes = [permissions.IsAuthenticatedOrReadOnly]

class TaskViewSet(viewsets.ModelViewSet):
    # --- ИСПРАВЛЕНИЕ: Убираем assignee/team из select_related ---
    queryset = Task.objects.select_related(
        "project", "category", "subcategory", "created_by" # Убраны assignee, team
    ).prefetch_related(
        'photos', 'user_roles__user' # Заменено task_roles на user_roles, добавлен prefetch user
    ).all().order_by('-created_at')
    # --- КОНЕЦ ИСПРАВЛЕНИЯ ---
    serializer_class = TaskSerializer
    # permission_classes = [IsAuthenticated, DjangoModelPermissions] # DjangoModelPermissions требует настройки
    permission_classes = [IsAuthenticated] # Оставляем пока только IsAuthenticated
    filter_backends = [DjangoFilterBackend, drf_filters.OrderingFilter, drf_filters.SearchFilter] # Добавляем Ordering и Search
    filterset_class = TaskFilter
    search_fields = ['task_number', 'title', 'description'] # Поля для SearchFilter
    ordering_fields = ['created_at', 'updated_at', 'deadline', 'priority', 'status', 'project__name'] # Поля для OrderingFilter
    ordering = ['-created_at'] # Сортировка по умолчанию

class TaskPhotoViewSet(viewsets.ModelViewSet):
    queryset = TaskPhoto.objects.select_related('task', 'uploaded_by').all() # Добавлен uploaded_by
    serializer_class = TaskPhotoSerializer
    permission_classes = [IsAuthenticated] # Только аутентифицированные могут видеть/управлять фото


# --- Refactored View for Search Suggestions ---
class SearchSuggestionsView(APIView):
    """
    API endpoint for universal search suggestions.
    Returns results in the format: {"results": [item, ...]}.
    Each item contains: id, title, url, context, type, icon, color.
    """
    permission_classes = [permissions.IsAuthenticated]
    SUGGESTION_LIMIT = 5 # Макс. подсказок на тип

    def get(self, request, *args, **kwargs):
        query = request.query_params.get('q', '').strip()
        suggestions = []
        user = request.user # Получаем текущего пользователя для возможной фильтрации

        if len(query) < 2:
            logger.debug("Search query too short, returning empty results.")
            # Возвращаем ПРАВИЛЬНЫЙ формат
            return Response({'results': suggestions})

        logger.debug(f"Searching suggestions for query: '{query}'")

        # --- Search Tasks ---
        try:
            # Добавляем фильтрацию по правам доступа пользователя (аналогично TaskListView)
            task_qs = Task.objects.filter(
                Q(created_by=user) | Q(user_roles__user=user)
            ).distinct()

            tasks = task_qs.filter(
                Q(task_number__icontains=query) | Q(title__icontains=query) | Q(description__icontains=query)
            ).select_related('project')[:self.SUGGESTION_LIMIT]

            for task in tasks:
                try:
                    url = reverse('tasks:task_detail', kwargs={'pk': task.pk})
                    suggestions.append({
                        'id': f'task-{task.pk}',
                        'title': f"{task.task_number} - {task.title}", # Используем title
                        'url': url,
                        'context': task.project.name if task.project else _('Без проекта'), # Контекст - проект
                        'type': _('Задача'), # Тип
                        'icon': 'tasks',       # Иконка Font Awesome (без fa-)
                        'color': 'blue'       # Цвет Tailwind/iOS
                        })
                except NoReverseMatch:
                     logger.warning(f"NoReverseMatch for task detail URL, pk={task.pk}")
                except Exception as e:
                     logger.error(f"Error processing suggestion for task {task.pk}: {e}")
        except Exception as e:
            logger.exception(f"Error during Task search for suggestions: {e}")

        # --- Search Projects ---
        try:
            # Можно добавить фильтрацию проектов, доступных пользователю, если нужно
            projects = Project.objects.filter(name__icontains=query)[:self.SUGGESTION_LIMIT]
            for project in projects:
                try:
                    # URL ведет на список задач с фильтром по проекту
                    url = reverse('tasks:task_list') + f'?project={project.pk}'
                    suggestions.append({
                        'id': f'project-{project.pk}',
                        'title': project.name, # Используем title
                        'url': url,
                        'context': _('Проект'), # Контекст - тип
                        'type': _('Проект'),
                        'icon': 'project-diagram',
                        'color': 'purple'
                        })
                except NoReverseMatch: pass
                except Exception as e: logger.error(f"Error processing suggestion for project {project.pk}: {e}")
        except Exception as e:
            logger.exception(f"Error during Project search for suggestions: {e}")

        # --- Search Categories ---
        try:
            categories = TaskCategory.objects.filter(name__icontains=query)[:self.SUGGESTION_LIMIT]
            for category in categories:
                try:
                    url = reverse('tasks:task_list') + f'?category={category.pk}'
                    suggestions.append({
                        'id': f'category-{category.pk}',
                        'title': category.name, # Используем title
                        'url': url,
                        'context': _('Категория задач'),
                        'type': _('Категория'),
                        'icon': 'folder',
                        'color': 'teal'
                        })
                except NoReverseMatch: pass
                except Exception as e: logger.error(f"Error processing suggestion for category {category.pk}: {e}")
        except Exception as e:
             logger.exception(f"Error during TaskCategory search for suggestions: {e}")

        # --- Search Users ---
        try:
            # Ищем активных пользователей по имени или username
            users = User.objects.filter(
                Q(username__icontains=query) | Q(first_name__icontains=query) | Q(last_name__icontains=query)
            ).filter(is_active=True)[:self.SUGGESTION_LIMIT]
            for found_user in users:
                try:
                    # Ссылка на список задач, где этот пользователь - УЧАСТНИК
                    url = reverse('tasks:task_list') + f'?participant={found_user.pk}' # Используем фильтр participant
                    suggestions.append({
                        'id': f'user-{found_user.pk}',
                        'title': found_user.display_name, # Используем title
                        'url': url,
                        'context': found_user.job_title or _('Пользователь'), # Контекст - должность
                        'type': _('Пользователь'),
                        'icon': 'user',
                        'color': 'gray' # Или другой цвет
                        })
                except NoReverseMatch: pass
                except Exception as e: logger.error(f"Error processing suggestion for user {found_user.pk}: {e}")
        except Exception as e:
            logger.exception(f"Error during User search for suggestions: {e}")

        # --- Search Teams ---
        try:
            teams = Team.objects.filter(name__icontains=query)[:self.SUGGESTION_LIMIT]
            for team in teams:
                try:
                    # Ссылки на команды пока нет, можно сделать заглушку или ссылку на список задач
                    # url = reverse('user_profiles:team_detail', kwargs={'pk': team.pk}) # Если есть страница команды
                    url = '#' # Заглушка
                    suggestions.append({
                        'id': f'team-{team.pk}',
                        'title': team.name, # Используем title
                        'url': url,
                        'context': _('Рабочая группа'),
                        'type': _('Команда'),
                        'icon': 'users',
                        'color': 'indigo'
                        })
                except NoReverseMatch: pass
                except Exception as e: logger.error(f"Error processing suggestion for team {team.pk}: {e}")
        except Exception as e:
             logger.exception(f"Error during Team search for suggestions: {e}")

        # --- Возвращаем результат в формате {"results": [...]} ---
        logger.debug(f"Found {len(suggestions)} suggestions for query '{query}'.")
        return Response({'results': suggestions})