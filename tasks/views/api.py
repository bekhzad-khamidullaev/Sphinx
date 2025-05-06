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
    permission_classes = [permissions.IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['start_date', 'end_date']
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
    # Use 'category' (PK) for filtering from Task form's dependent dropdown AJAX
    filterset_fields = ['category', 'category__name']
    search_fields = ['name', 'description', 'category__name']
    ordering_fields = ['name', 'category__name', 'created_at']
    ordering = ['category__name', 'name']

    # Added list method override to handle 'category' param for AJAX dropdowns
    def list(self, request, *args, **kwargs):
        category_id = request.query_params.get('category')
        if category_id:
            queryset = self.filter_queryset(self.get_queryset().filter(category_id=category_id))
        else:
            queryset = self.filter_queryset(self.get_queryset())

        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            # For Select2 AJAX, return flat list if requested, else paginated response
            if request.accepted_renderer.format == 'json' and request.query_params.get('select2'):
                 return Response(serializer.data) # Return list directly
            return self.get_paginated_response(serializer.data)

        serializer = self.get_serializer(queryset, many=True)
        # For Select2 AJAX, return flat list if requested
        if request.accepted_renderer.format == 'json' and request.query_params.get('select2'):
             return Response(serializer.data) # Return list directly
        return Response(serializer.data)

class TaskViewSet(viewsets.ModelViewSet):
    queryset = Task.objects.select_related(
        'project', 'category', 'subcategory', 'created_by'
    ).prefetch_related(
        'photos', 'user_roles__user'
    ).order_by('-created_at')
    serializer_class = TaskSerializer
    permission_classes = [permissions.IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['project', 'category', 'subcategory', 'status', 'priority', 'created_by', 'deadline', 'start_date', 'completion_date']
    search_fields = ['task_number', 'title', 'description', 'project__name', 'created_by__username']
    ordering_fields = ['task_number', 'title', 'status', 'priority', 'deadline', 'start_date', 'completion_date', 'created_at', 'project__name']
    ordering = ['-created_at']

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)

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
        limit = 5 # Limit per type

        if len(query) >= 2:
            tasks = Task.objects.filter(Q(title__icontains=query) | Q(task_number__icontains=query)).select_related('project')[:limit]
            suggestions.extend([{ 'type': 'task', 'title': f"#{t.task_number}: {t.title}", 'context': t.project.name if t.project else '', 'url': t.get_absolute_url(), 'icon': 'tasks', 'color': 'blue'} for t in tasks])

            projects = Project.objects.filter(name__icontains=query)[:limit]
            suggestions.extend([{ 'type': 'project', 'title': p.name, 'context': _("Проект"), 'url': p.get_absolute_url(), 'icon': 'project-diagram', 'color': 'purple'} for p in projects])

            cats = TaskCategory.objects.filter(name__icontains=query)[:limit]
            suggestions.extend([{ 'type': 'category', 'title': c.name, 'context': _("Категория"), 'url': reverse('tasks:task_list') + f'?category={c.pk}', 'icon': 'folder-open', 'color': 'teal'} for c in cats])

            if ChecklistTemplate:
                 templates = ChecklistTemplate.objects.filter(name__icontains=query, is_archived=False)[:limit]
                 suggestions.extend([{'type': 'checklist_template', 'title': t.name, 'context': _("Шаблон"), 'url': t.get_absolute_url(), 'icon': 'clipboard-list', 'color': 'indigo'} for t in templates])

            if ChecklistRun:
                runs = ChecklistRun.objects.filter(Q(template__name__icontains=query) | Q(performed_by__username__icontains=query)).select_related('template', 'performed_by').order_by('-performed_at')[:limit]
                suggestions.extend([{'type': 'checklist_run', 'title': f"{r.template.name} ({r.performed_at:%d.%m.%y})", 'context': f"{_('Выполнен')}: {r.performed_by.display_name if r.performed_by else '-'}", 'url': r.get_absolute_url(), 'icon': 'history', 'color': 'gray'} for r in runs])

            users = User.objects.filter(Q(username__icontains=query) | Q(first_name__icontains=query) | Q(last_name__icontains=query) | Q(email__icontains=query), is_active=True)[:limit]
            suggestions.extend([{'type': 'user', 'title': f"{u.display_name} (@{u.username})", 'context': u.job_title or '', 'url': '#', 'icon': 'user', 'color': 'orange'} for u in users]) # Add user URL logic if needed

            teams = Team.objects.filter(name__icontains=query)[:limit]
            suggestions.extend([{'type': 'team', 'title': t.name, 'context': _("Команда"), 'url': reverse('user_profiles:user_list') + f'?team={t.pk}', 'icon': 'users-cog', 'color': 'pink'} for t in teams])

            depts = Department.objects.filter(name__icontains=query)[:limit]
            suggestions.extend([{'type': 'department', 'title': d.name, 'context': _("Отдел"), 'url': reverse('user_profiles:user_list') + f'?department={d.pk}', 'icon': 'building', 'color': 'sky'} for d in depts])

            if Room:
                rooms = Room.objects.filter(name__icontains=query)[:limit]
                suggestions.extend([{'type': 'room', 'title': f"# {r.name}", 'context': _("Чат"), 'url': r.get_absolute_url(), 'icon': 'comments', 'color': 'green'} for r in rooms])

        return Response({'results': suggestions[:10]}) # Limit total results

class UserAutocompleteView(APIView):
    permission_classes = [permissions.IsAuthenticated]
    def get(self, request, *args, **kwargs):
        query = request.query_params.get('q', '').strip()
        project_id = request.query_params.get('project')
        page = int(request.query_params.get('page', 1))
        page_size = 20

        results = []
        more = False

        if len(query) >= 1:
            search_filter = (Q(username__icontains=query) | Q(first_name__icontains=query) | Q(last_name__icontains=query) | Q(email__icontains=query))
            queryset = User.objects.filter(is_active=True).filter(search_filter)

            # Implement project filtering logic here if needed
            if project_id:
                # Example: Filter users who are members of the project's team(s)
                # try:
                #     project = Project.objects.get(pk=project_id)
                #     # Assuming a relationship like project -> teams -> members
                #     team_ids = project.teams.values_list('id', flat=True) # Adjust relationship as needed
                #     queryset = queryset.filter(teams__id__in=team_ids).distinct()
                # except Project.DoesNotExist:
                #     queryset = queryset.none() # Or handle error differently
                pass # Placeholder for your project filtering logic

            start_index = (page - 1) * page_size
            end_index = start_index + page_size
            total_count = queryset.count()
            if total_count > end_index: more = True

            users = queryset.order_by('username')[start_index:end_index]
            results = [{'id': user.pk, 'text': user.display_name or user.username} for user in users]

        return Response({'results': results, 'pagination': {'more': more}})