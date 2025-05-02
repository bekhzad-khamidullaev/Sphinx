# tasks/views/api.py
from rest_framework import viewsets, permissions, status, filters
from rest_framework.views import APIView
from rest_framework.response import Response
from django_filters.rest_framework import DjangoFilterBackend
from django.db.models import Q, Count
from django.contrib.auth import get_user_model
from django.utils.translation import gettext_lazy as _
from django.urls import reverse



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
from user_profiles.models import User, Team, Department

try:
    from checklists.models import ChecklistTemplate, ChecklistRun
except ImportError:
    ChecklistTemplate = None
    ChecklistRun = None
try:
    from room.models import Room
except ImportError:
    Room = None

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
    Provides search suggestions across multiple models.
    Returns results in the format expected by search.js.
    """
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, *args, **kwargs):
        query = request.query_params.get('q', '').strip()
        all_suggestions = []
        limit_per_model = 5 # Limit results per model type initially
        final_limit = 10 # Final number of suggestions to return

        if len(query) >= 2:
            # --- Search Tasks ---
            tasks = Task.objects.filter(
                Q(title__icontains=query) | Q(task_number__icontains=query)
            ).select_related('project')[:limit_per_model]
            for task in tasks:
                all_suggestions.append({
                    'type': 'task',
                    'title': f"#{task.task_number}: {task.title}",
                    'context': task.project.name if task.project else _("Без проекта"),
                    'url': task.get_absolute_url(),
                    'icon': 'tasks', # Font Awesome icon name
                    'color': 'blue', # Color hint
                })

            # --- Search Projects ---
            projects = Project.objects.filter(name__icontains=query)[:limit_per_model]
            for project in projects:
                all_suggestions.append({
                    'type': 'project',
                    'title': project.name,
                    'context': _("Проект"),
                    'url': project.get_absolute_url(), # Assumes get_absolute_url links to project's task list
                    'icon': 'project-diagram',
                    'color': 'purple',
                })

            # --- Search Categories ---
            categories = TaskCategory.objects.filter(name__icontains=query)[:limit_per_model]
            for category in categories:
                 # Link to task list filtered by this category
                 category_task_list_url = reverse('tasks:task_list') + f'?category={category.pk}'
                 all_suggestions.append({
                     'type': 'category',
                     'title': category.name,
                     'context': _("Категория задач"),
                     'url': category_task_list_url,
                     'icon': 'folder-open', # Changed icon
                     'color': 'teal',
                 })

            # --- Search Checklist Templates ---
            if ChecklistTemplate:
                templates = ChecklistTemplate.objects.filter(
                    name__icontains=query, is_archived=False
                )[:limit_per_model]
                for template in templates:
                    all_suggestions.append({
                        'type': 'checklist_template',
                        'title': template.name,
                        'context': _("Шаблон чеклиста"),
                        'url': template.get_absolute_url(),
                        'icon': 'clipboard-list',
                        'color': 'indigo',
                    })

            # --- Search Checklist Runs ---
            if ChecklistRun:
                # Search by template name or performing user
                runs = ChecklistRun.objects.filter(
                     Q(template__name__icontains=query) | Q(performed_by__username__icontains=query) | Q(performed_by__first_name__icontains=query) | Q(performed_by__last_name__icontains=query)
                 ).select_related('template', 'performed_by').order_by('-performed_at')[:limit_per_model]
                for run in runs:
                     all_suggestions.append({
                         'type': 'checklist_run',
                         'title': f"{_('Результаты')}: {run.template.name} ({run.performed_at.strftime('%d.%m.%y')})",
                         'context': f"{_('Выполнен')}: {run.performed_by.display_name if run.performed_by else '-'}",
                         'url': run.get_absolute_url(),
                         'icon': 'history', # Or 'check-double'
                         'color': 'gray',
                     })

            # --- Search Users ---
            users = User.objects.filter(
                 Q(username__icontains=query) | Q(first_name__icontains=query) | Q(last_name__icontains=query) | Q(email__icontains=query),
                 is_active=True
             ).select_related('department')[:limit_per_model]
            for user in users:
                 # Prefer profile view, fallback to update view if profile view doesn't exist
                 user_url = '#'
                 try:
                      user_url = reverse('user_profiles:profile_view') # Assuming profile view is for the logged-in user
                      # If you have a public profile view per user:
                      # user_url = reverse('user_profiles:public_profile', kwargs={'username': user.username})
                 except:
                      try: # Fallback to update view (might need permissions)
                          user_url = reverse('user_profiles:user_update', kwargs={'pk': user.pk})
                      except:
                           pass # No suitable URL found

                 all_suggestions.append({
                     'type': 'user',
                     'title': f"{user.display_name} (@{user.username})",
                     'context': user.job_title or _("Пользователь"),
                     'url': user_url,
                     'icon': 'user',
                     'color': 'orange',
                 })

            # --- Search Teams ---
            teams = Team.objects.filter(name__icontains=query).select_related('department')[:limit_per_model]
            for team in teams:
                 # Link to user list filtered by this team
                 team_user_list_url = reverse('user_profiles:user_list') + f'?team={team.pk}'
                 all_suggestions.append({
                    'type': 'team',
                    'title': team.name,
                    'context': f"{_('Команда')} ({team.department.name if team.department else '-'})",
                    'url': team_user_list_url, # Link to filtered user list
                    'icon': 'users-cog',
                    'color': 'pink',
                 })

            # --- Search Departments ---
            departments = Department.objects.filter(name__icontains=query)[:limit_per_model]
            for department in departments:
                 department_user_list_url = reverse('user_profiles:user_list') + f'?department={department.pk}'
                 all_suggestions.append({
                     'type': 'department',
                     'title': department.name,
                     'context': _("Отдел"),
                     'url': department_user_list_url, # Link to filtered user list
                     'icon': 'building',
                     'color': 'sky', # Using 'sky' as an alternative to 'cyan'
                 })

            # --- Search Chat Rooms ---
            if Room:
                rooms = Room.objects.filter(name__icontains=query)[:limit_per_model]
                for room in rooms:
                    all_suggestions.append({
                        'type': 'room',
                        'title': f"# {room.name}",
                        'context': _("Чат комната"),
                        'url': room.get_absolute_url(), # Assumes get_absolute_url is defined
                        'icon': 'comments',
                        'color': 'green',
                    })

        # Limit the final combined list
        suggestions = all_suggestions[:final_limit]

        # Return in the format expected by JS
        return Response({'results': suggestions})

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