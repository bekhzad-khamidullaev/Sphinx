import logging
from django.db.models import Q
from django.urls import reverse, NoReverseMatch
from django.contrib.auth import get_user_model
from django_filters.rest_framework import DjangoFilterBackend

from rest_framework import viewsets, permissions, filters as drf_filters
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated, DjangoModelPermissions

from ..models import Project, TaskCategory, TaskSubcategory, Task, TaskPhoto
from user_profiles.models import Team, User
from ..serializers import (
    ProjectSerializer, TaskCategorySerializer, TaskSubcategorySerializer,
    TaskSerializer, TaskPhotoSerializer
)
from ..filters import TaskFilter

# User = get_user_model()
logger = logging.getLogger(__name__)

# --- Existing ViewSets ---
class ProjectViewSet(viewsets.ModelViewSet):
    queryset = Project.objects.all().order_by('-created_at')
    serializer_class = ProjectSerializer
    permission_classes = [permissions.IsAuthenticatedOrReadOnly]

class TaskCategoryViewSet(viewsets.ModelViewSet):
    queryset = TaskCategory.objects.all().order_by('name')
    serializer_class = TaskCategorySerializer
    permission_classes = [permissions.IsAuthenticatedOrReadOnly]

class TaskSubcategoryViewSet(viewsets.ModelViewSet):
    queryset = TaskSubcategory.objects.select_related('category').all().order_by('category__name', 'name')
    serializer_class = TaskSubcategorySerializer
    permission_classes = [permissions.IsAuthenticatedOrReadOnly]

class TaskViewSet(viewsets.ModelViewSet):
    queryset = Task.objects.select_related(
        "project", "category", "subcategory", "assignee", "team", "created_by"
    ).prefetch_related('photos', 'task_roles').all().order_by('-created_at')
    serializer_class = TaskSerializer
    permission_classes = [IsAuthenticated, DjangoModelPermissions]
    filter_backends = [DjangoFilterBackend]
    filterset_class = TaskFilter

class TaskPhotoViewSet(viewsets.ModelViewSet):
    queryset = TaskPhoto.objects.select_related('task').all()
    serializer_class = TaskPhotoSerializer
    permission_classes = [IsAuthenticated]


# --- New View for Search Suggestions ---
class SearchSuggestionsView(APIView):
    """ API endpoint for universal search suggestions. """
    permission_classes = [permissions.IsAuthenticated]
    SUGGESTION_LIMIT = 5 # Max suggestions per model type

    def get(self, request, *args, **kwargs):
        query = request.query_params.get('q', '').strip()
        suggestions = []

        if len(query) < 2:
            return Response(suggestions)

        # Search Tasks
        try:
            tasks = Task.objects.filter(
                Q(task_number__icontains=query) | Q(title__icontains=query) | Q(description__icontains=query)
            ).select_related('project')[:self.SUGGESTION_LIMIT]
            for task in tasks:
                try:
                    url = reverse('tasks:task_detail', kwargs={'pk': task.pk})
                    suggestions.append({'id': f'task-{task.pk}', 'text': f"Задача: {task.task_number} - {task.title[:50]}...", 'url': url, 'type': 'Задача'})
                except NoReverseMatch: pass
        except Exception as e: logger.error(f"Error searching Tasks: {e}")

        # Search Projects
        try:
            projects = Project.objects.filter(name__icontains=query)[:self.SUGGESTION_LIMIT]
            for project in projects:
                try:
                    url = reverse('tasks:task_list') + f'?project={project.pk}'
                    suggestions.append({'id': f'project-{project.pk}', 'text': f"Проект: {project.name}", 'url': url, 'type': 'Проект'})
                except NoReverseMatch: pass
        except Exception as e: logger.error(f"Error searching Projects: {e}")

        # Search Categories
        try:
            categories = TaskCategory.objects.filter(name__icontains=query)[:self.SUGGESTION_LIMIT]
            for category in categories:
                try:
                    url = reverse('tasks:task_list') + f'?category={category.pk}'
                    suggestions.append({'id': f'category-{category.pk}', 'text': f"Категория: {category.name}", 'url': url, 'type': 'Категория'})
                except NoReverseMatch: pass
        except Exception as e: logger.error(f"Error searching Categories: {e}")

        # Search Users
        try:
            users = User.objects.filter(
                Q(username__icontains=query) | Q(first_name__icontains=query) | Q(last_name__icontains=query)
            ).filter(is_active=True)[:self.SUGGESTION_LIMIT]
            for user in users:
                try:
                    url = reverse('tasks:task_list') + f'?assignee={user.pk}'
                    suggestions.append({'id': f'user-{user.pk}', 'text': f"Пользователь: {user.get_full_name() or user.username}", 'url': url, 'type': 'Пользователь'})
                except NoReverseMatch: pass
        except Exception as e: logger.error(f"Error searching Users: {e}")

        # Search Teams
        try:
            teams = Team.objects.filter(name__icontains=query)[:self.SUGGESTION_LIMIT]
            for team in teams:
                try:
                    url = reverse('tasks:task_list') + f'?team={team.pk}'
                    suggestions.append({'id': f'team-{team.pk}', 'text': f"Команда: {team.name}", 'url': url, 'type': 'Команда'})
                except NoReverseMatch: pass
        except Exception as e: logger.error(f"Error searching Teams: {e}")

        # Add other models (e.g., Subcategories) here if needed

        return Response(suggestions)