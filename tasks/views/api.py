# tasks/views/api.py
from rest_framework import viewsets, permissions, status, filters
from rest_framework.views import APIView
from rest_framework.response import Response
from django_filters.rest_framework import DjangoFilterBackend
from django.db.models import Q, Count
from django.contrib.auth import get_user_model

from ..models import (
    Project,
    TaskCategory,
    TaskSubcategory,
    Task,
    TaskPhoto,
)
from ..serializers import (
    ProjectSerializer,
    TaskCategorySerializer,
    TaskSubcategorySerializer,
    TaskSerializer,
    TaskPhotoSerializer,
)
# Assuming you might want permission checks later
# from .permissions import IsOwnerOrReadOnly, IsTeamMemberOrReadOnly

User = get_user_model()


# --------------------------------------------------------------------------
# Model ViewSets for Standard CRUD Operations
# --------------------------------------------------------------------------

class ProjectViewSet(viewsets.ModelViewSet):
    """
    API endpoint that allows projects to be viewed or edited.
    """
    queryset = Project.objects.annotate(
        task_count=Count('tasks') # Add task count for potentially richer API responses
    ).order_by('name')
    serializer_class = ProjectSerializer
    permission_classes = [permissions.IsAuthenticated] # Example: Only logged-in users
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['start_date', 'end_date'] # Fields for exact filtering
    search_fields = ['name', 'description'] # Fields for full-text search
    ordering_fields = ['name', 'start_date', 'end_date', 'created_at', 'task_count']
    ordering = ['name'] # Default ordering


class TaskCategoryViewSet(viewsets.ModelViewSet):
    """
    API endpoint that allows task categories to be viewed or edited.
    """
    queryset = TaskCategory.objects.all().order_by('name')
    serializer_class = TaskCategorySerializer
    permission_classes = [permissions.IsAuthenticated]
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ['name', 'description']
    ordering_fields = ['name', 'created_at']
    ordering = ['name']


class TaskSubcategoryViewSet(viewsets.ModelViewSet):
    """
    API endpoint that allows task subcategories to be viewed or edited.
    """
    queryset = TaskSubcategory.objects.select_related('category').order_by('category__name', 'name')
    serializer_class = TaskSubcategorySerializer
    permission_classes = [permissions.IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['category', 'category__name'] # Filter by category ID or name
    search_fields = ['name', 'description', 'category__name']
    ordering_fields = ['name', 'category__name', 'created_at']
    ordering = ['category__name', 'name']

    # Example: Dynamic queryset based on category_id URL parameter
    # def get_queryset(self):
    #     queryset = super().get_queryset()
    #     category_id = self.request.query_params.get('category_id')
    #     if category_id:
    #         queryset = queryset.filter(category_id=category_id)
    #     return queryset


class TaskViewSet(viewsets.ModelViewSet):
    """
    API endpoint that allows tasks to be viewed or edited.
    Includes filtering, searching, and ordering.
    """
    # Optimize queryset by selecting/prefetching related fields frequently used
    queryset = Task.objects.select_related(
        'project', 'category', 'subcategory', 'created_by'#, 'assignee', 'team' # Uncomment if these fields exist
    ).prefetch_related(
        'photos', 'user_roles__user' # Prefetch photos and users involved
    ).order_by('-created_at')
    serializer_class = TaskSerializer
    permission_classes = [permissions.IsAuthenticated] # Add more specific permissions if needed
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    # Use TaskFilter for more complex filtering defined in filters.py
    # filterset_class = TaskFilter # Uncomment if using TaskFilter class
    # Or define simple fields here:
    filterset_fields = ['project', 'category', 'subcategory', 'status', 'priority', 'created_by', 'deadline', 'start_date', 'completion_date']
    search_fields = ['task_number', 'title', 'description', 'project__name', 'created_by__username'] # Add fields from related models
    ordering_fields = ['task_number', 'title', 'status', 'priority', 'deadline', 'start_date', 'completion_date', 'created_at', 'project__name']
    ordering = ['-created_at'] # Default ordering

    # Optionally override perform_create to set the creator automatically
    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)

    # Optionally override perform_update or perform_destroy for permission checks or logging


class TaskPhotoViewSet(viewsets.ModelViewSet):
    """
    API endpoint that allows task photos to be viewed or edited.
    """
    queryset = TaskPhoto.objects.select_related('task', 'uploaded_by').order_by('-created_at')
    serializer_class = TaskPhotoSerializer
    permission_classes = [permissions.IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.OrderingFilter]
    filterset_fields = ['task', 'uploaded_by']
    ordering_fields = ['created_at', 'task__task_number']
    ordering = ['-created_at']

    # Override perform_create to set the uploader automatically
    def perform_create(self, serializer):
        serializer.save(uploaded_by=self.request.user)


# --------------------------------------------------------------------------
# Custom API Views (Example: Search Suggestions, User Autocomplete)
# --------------------------------------------------------------------------

class SearchSuggestionsView(APIView):
    """
    Provides search suggestions across multiple models (Tasks, Projects).
    """
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, *args, **kwargs):
        query = request.query_params.get('q', '').strip()
        suggestions = []
        limit = 10 # Limit the number of suggestions

        if len(query) >= 2: # Only search if query is long enough
            # Search Tasks
            tasks = Task.objects.filter(
                Q(title__icontains=query) | Q(task_number__icontains=query)
            ).select_related('project')[:limit]
            for task in tasks:
                suggestions.append({
                    'id': f'task-{task.pk}',
                    'type': 'task',
                    'value': f"#{task.task_number}: {task.title}",
                    'label': f"Задача #{task.task_number}: {task.title} ({task.project.name})", # More descriptive label
                    'url': task.get_absolute_url() # URL to the task detail page
                })

            # Search Projects (limit remaining suggestions)
            project_limit = limit - len(suggestions)
            if project_limit > 0:
                projects = Project.objects.filter(name__icontains=query)[:project_limit]
                for project in projects:
                    suggestions.append({
                        'id': f'project-{project.pk}',
                        'type': 'project',
                        'value': project.name,
                         'label': f"Проект: {project.name}",
                        'url': project.get_absolute_url() # URL to project tasks or detail
                    })

            # Add other models here if needed (Categories, Users etc.)

        return Response(suggestions)


class UserAutocompleteView(APIView):
    """
    Provides user suggestions for autocomplete widgets (like Select2).
    Matches the endpoint expected by 'tasks:user_autocomplete'.
    Supports optional filtering by project.
    """
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, *args, **kwargs):
        query = request.query_params.get('q', '').strip()
        project_id = request.query_params.get('project')  # <-- Добавлено для фильтрации по проекту
        page = int(request.query_params.get('page', 1))
        page_size = 20  # Number of results per page for Select2 pagination

        results = []
        more = False

        if len(query) >= 1:  # Minimum characters to trigger search
            # Build the filter dynamically
            search_filter = (
                Q(username__icontains=query) |
                Q(first_name__icontains=query) |
                Q(last_name__icontains=query) |
                Q(email__icontains=query)
            )
            # Query only active users
            queryset = User.objects.filter(is_active=True).filter(search_filter)

            # 🔥 Фильтрация по проекту если задан
            if project_id:
                # Если у юзеров есть прямая связь на проект — раскомментировать:
                # queryset = queryset.filter(project_id=project_id)

                # Или если через профиль или роли, надо написать свою логику
                # Пока оставлю как пример без изменений, тебе нужно здесь дописать
                pass

            # Calculate pagination offsets
            start_index = (page - 1) * page_size
            end_index = start_index + page_size

            # Get total count for pagination check
            total_count = queryset.count()
            if total_count > end_index:
                more = True  # Indicate there are more pages

            # Get the users for the current page
            users = queryset.order_by('username')[start_index:end_index]

            # Format results for Select2 AJAX
            results = [
                {
                    'id': user.pk,
                    'text': user.display_name or user.username,
                }
                for user in users
            ]

        # Select2 AJAX response format: { results: [...], pagination: { more: true/false } }
        return Response({
            'results': results,
            'pagination': {'more': more}
        })
# Note: Ensure that the URL patterns are set up to route to these views correctly.
# You may need to adjust the import paths based on your project structure.
# Also, consider adding error handling and logging as needed.
# This is a basic structure. You can expand upon it based on your specific requirements.
# --------------------------------------------------------------------------
# End of file
# tasks/views/api.py