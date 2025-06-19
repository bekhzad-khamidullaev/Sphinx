# tasks/views/api.py
from rest_framework import viewsets, permissions, status, filters
from rest_framework.views import APIView
from rest_framework.response import Response
from django_filters.rest_framework import DjangoFilterBackend
from django.db.models import Q, Count
from django.contrib.auth import get_user_model
from django.utils.translation import gettext_lazy as _
from django.urls import reverse # Keep for search suggestions
from django.db import transaction
from django.conf import settings
from django.db.models import Prefetch

from ..models import (Project, TaskCategory, TaskSubcategory, Task, TaskPhoto, TaskAssignment, Team, Department) # MODIFIED: Added TaskAssignment, Team, Department
from ..serializers import (
    ProjectSerializer, TaskCategorySerializer, TaskSubcategorySerializer,
    TaskSerializer, TaskPhotoSerializer, TaskAssignmentSerializer # MODIFIED: Added TaskAssignmentSerializer
)
# User model already imported via get_user_model if used below
# from user_profiles.models import User, Team, Department # REMOVED - imported from .models or get_user_model

# Optional imports
try: from checklists.models import ChecklistTemplate, ChecklistRun
except ImportError: ChecklistTemplate, ChecklistRun = None, None
try: from room.models import Room
except ImportError: Room = None

User = get_user_model()

class ProjectViewSet(viewsets.ModelViewSet):
    queryset = Project.objects.annotate(task_count=Count('tasks')).order_by('name')
    serializer_class = ProjectSerializer
    permission_classes = [permissions.IsAuthenticated] # Or more specific permissions
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['start_date', 'end_date'] # Add 'team', 'department' if they are on Project model
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
    filterset_fields = ['category', 'category__name'] # 'category' (PK) for filtering
    search_fields = ['name', 'description', 'category__name']
    ordering_fields = ['name', 'category__name', 'created_at']
    ordering = ['category__name', 'name']
    
    # list method override for Select2 AJAX (from original code, seems fine)
    def list(self, request, *args, **kwargs):
        category_id = request.query_params.get('category')
        queryset = self.filter_queryset(self.get_queryset())
        if category_id:
            queryset = queryset.filter(category_id=category_id)
        
        page = self.paginate_queryset(queryset)
        if page is not None:
            if request.accepted_renderer.format == 'json' and request.query_params.get('select2'):
                data = [{'id': sc.id, 'text': f"{sc.category.name} / {sc.name}"} for sc in page]
                return Response(data)
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)

        if request.accepted_renderer.format == 'json' and request.query_params.get('select2'):
            data = [{'id': sc.id, 'text': f"{sc.category.name} / {sc.name}"} for sc in queryset]
            return Response(data)

        serializer = self.get_serializer(queryset, many=True)
        return Response(serializer.data)


class TaskViewSet(viewsets.ModelViewSet):
    queryset = Task.objects.select_related(
        'project', 'category', 'subcategory', 'created_by', 'team', 'department' # Added team, department
    ).prefetch_related(
        'photos', 
        Prefetch('assignments', queryset=TaskAssignment.objects.select_related('user')) # MODIFIED
    ).order_by('-created_at')
    serializer_class = TaskSerializer
    permission_classes = [permissions.IsAuthenticated] # Add custom permissions as needed
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    # MODIFIED: Added team, department to filterset_fields
    filterset_fields = {
        'project': ['exact'], 'category': ['exact'], 'subcategory': ['exact'],
        'status': ['exact', 'in'], 'priority': ['exact', 'in'],
        'created_by': ['exact'], 'team': ['exact'], 'department': ['exact'],
        'deadline': ['exact', 'lte', 'gte', 'range'],
        'start_date': ['exact', 'lte', 'gte', 'range'],
        'completion_date': ['exact', 'lte', 'gte', 'range', 'isnull'],
        # For filtering by assigned users/roles (more complex, might need custom filter class)
        'assignments__user': ['exact'],
        'assignments__role': ['exact', 'in'],
    }
    search_fields = [
        'task_number', 'title', 'description', 
        'project__name', 'created_by__username',
        'assignments__user__username' # MODIFIED
    ]
    ordering_fields = [
        'task_number', 'title', 'status', 'priority', 'deadline', 
        'start_date', 'completion_date', 'created_at', 'project__name',
        'team__name', 'department__name' # Added
    ]
    ordering = ['-created_at']

    def perform_create(self, serializer):
        # created_by is set by the serializer if request.user is in context
        # assignments are handled by TaskSerializer.create
        serializer.save(created_by=self.request.user)

    def perform_update(self, serializer):
        # assignments are handled by TaskSerializer.update
        serializer.save()

# TaskAssignmentViewSet (Optional - if direct CRUD on assignments is needed via API)
class TaskAssignmentViewSet(viewsets.ModelViewSet):
    queryset = TaskAssignment.objects.select_related('task', 'user', 'assigned_by').all()
    serializer_class = TaskAssignmentSerializer
    permission_classes = [permissions.IsAuthenticated] # Customize permissions
    filter_backends = [DjangoFilterBackend, filters.OrderingFilter]
    filterset_fields = ['task', 'user', 'role', 'assigned_by']
    ordering_fields = ['created_at', 'task__title', 'user__username', 'role']
    ordering = ['-created_at']

    def perform_create(self, serializer):
        # assigned_by can be set by serializer context or here
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


class SearchSuggestionsView(APIView): # (No direct changes for TaskAssignment, but ensure URLs are correct)
    permission_classes = [permissions.IsAuthenticated]
    def get(self, request, *args, **kwargs):
        query = request.query_params.get('q', '').strip()
        suggestions = []
        limit = 5 

        if len(query) >= 2:
            # Tasks
            tasks_qs = Task.objects.filter(
                Q(title__icontains=query) | Q(task_number__icontains=query)
            ).select_related('project')[:limit]
            suggestions.extend([{ 
                'type': 'task', 'id': t.id, 'title': f"#{t.task_number}: {t.title}", 
                'context': t.project.name if t.project else '', 
                'url': t.get_absolute_url(), 'icon': 'tasks', 'color': 'blue'
            } for t in tasks_qs])

            # Projects
            projects_qs = Project.objects.filter(name__icontains=query)[:limit]
            suggestions.extend([{ 
                'type': 'project', 'id': p.id, 'title': p.name, 'context': _("Проект"), 
                'url': p.get_absolute_url(), 'icon': 'project-diagram', 'color': 'purple'
            } for p in projects_qs])
            
            # Categories
            cats_qs = TaskCategory.objects.filter(name__icontains=query)[:limit]
            suggestions.extend([{
                'type': 'category', 'id': c.id, 'title': c.name, 'context': _("Категория"),
                'url': reverse('tasks:category_detail', kwargs={'pk': c.pk}), # Updated to detail view
                'icon': 'folder-open', 'color': 'teal'
            } for c in cats_qs])

            # Subcategories
            subcats_qs = TaskSubcategory.objects.filter(name__icontains=query).select_related('category')[:limit]
            suggestions.extend([{
                'type': 'subcategory', 'id': sc.id, 'title': f"{sc.category.name} / {sc.name}", 'context': _("Подкатегория"),
                'url': reverse('tasks:subcategory_detail', kwargs={'pk': sc.pk}), # Updated to detail view
                'icon': 'folder', 'color': 'cyan'
            } for sc in subcats_qs])

            # Users
            users_qs = User.objects.filter(
                Q(username__icontains=query) | Q(first_name__icontains=query) | Q(last_name__icontains=query) | Q(email__icontains=query), 
                is_active=True
            )[:limit]
            suggestions.extend([{
                'type': 'user', 'id': u.id, 'title': f"{u.display_name or u.username} (@{u.username})", 
                'context': u.job_title or _('Пользователь'), # Assuming job_title exists on user model
                'url': u.get_absolute_url() if hasattr(u, 'get_absolute_url') else '#', # Check for profile URL
                'icon': 'user', 'color': 'orange'
            } for u in users_qs])

            # Teams
            if hasattr(Team, 'objects'): # Check if Team model is more than a dummy
                teams_qs = Team.objects.filter(name__icontains=query)[:limit]
                suggestions.extend([{
                    'type': 'team', 'id': t.id, 'title': t.name, 'context': _("Команда"),
                    'url': reverse('user_profiles:user_list') + f'?team={t.pk}' if 'user_profiles' in settings.INSTALLED_APPS else '#', # Adjust URL
                    'icon': 'users-cog', 'color': 'pink'
                } for t in teams_qs])

            # Departments
            if hasattr(Department, 'objects'): # Check if Department model is more than a dummy
                depts_qs = Department.objects.filter(name__icontains=query)[:limit]
                suggestions.extend([{
                    'type': 'department', 'id': d.id, 'title': d.name, 'context': _("Отдел"),
                    'url': reverse('user_profiles:user_list') + f'?department={d.pk}' if 'user_profiles' in settings.INSTALLED_APPS else '#', # Adjust URL
                    'icon': 'building', 'color': 'sky'
                } for d in depts_qs])

            # Checklist (optional)
            if ChecklistTemplate:
                 templates = ChecklistTemplate.objects.filter(name__icontains=query, is_archived=False)[:limit]
                 suggestions.extend([{'type': 'checklist_template', 'id': t.id, 'title': t.name, 'context': _("Шаблон"), 'url': t.get_absolute_url(), 'icon': 'clipboard-list', 'color': 'indigo'} for t in templates])
            if ChecklistRun:
                runs = ChecklistRun.objects.filter(Q(template__name__icontains=query) | Q(performed_by__username__icontains=query)).select_related('template', 'performed_by').order_by('-performed_at')[:limit]
                suggestions.extend([{'type': 'checklist_run', 'id': r.id, 'title': f"{r.template.name} ({r.performed_at:%d.%m.%y})", 'context': f"{_('Выполнен')}: {r.performed_by.display_name if r.performed_by else '-'}", 'url': r.get_absolute_url(), 'icon': 'history', 'color': 'gray'} for r in runs])
            
            # Room (optional)
            if Room:
                rooms_qs = Room.objects.filter(name__icontains=query)[:limit]
                suggestions.extend([{'type': 'room', 'id': r.id, 'title': f"# {r.name}", 'context': _("Чат"), 'url': r.get_absolute_url(), 'icon': 'comments', 'color': 'green'} for r in rooms_qs])

        return Response({'results': suggestions[:15]}) # Limit total results

class UserAutocompleteView(APIView): # (No direct changes for TaskAssignment)
    permission_classes = [permissions.IsAuthenticated]
    def get(self, request, *args, **kwargs):
        query = request.query_params.get('q', '').strip()
        project_id_str = request.query_params.get('project') # project ID as string
        page = int(request.query_params.get('page', 1))
        page_size = 20 # Standard Select2 page size

        results = []
        more = False

        if len(query) >= 1: # Minimum query length
            search_filter = (
                Q(username__icontains=query) | 
                Q(first_name__icontains=query) | 
                Q(last_name__icontains=query) | 
                Q(email__icontains=query)
            )
            queryset = User.objects.filter(is_active=True).filter(search_filter)

            if project_id_str and project_id_str.isdigit():
                project_id = int(project_id_str)
                # Example: Filter users assigned to tasks in this project
                # This can be complex. A simpler filter might be by project's team if Project has a Team FK.
                # For now, this example shows filtering users who are assigned to ANY task in the project.
                # This might not be what you want if you need users *available* for assignment.
                # tasks_in_project = Task.objects.filter(project_id=project_id).values_list('id', flat=True)
                # assigned_user_ids = TaskAssignment.objects.filter(task_id__in=tasks_in_project).values_list('user_id', flat=True).distinct()
                # queryset = queryset.filter(id__in=assigned_user_ids)
                # Or, if project has a direct team link:
                # try:
                #     project = Project.objects.get(pk=project_id)
                #     if project.team: # Assuming Project.team is a FK to Team model
                #          queryset = queryset.filter(teams=project.team) # Assuming User.teams is M2M
                # except Project.DoesNotExist:
                #     queryset = queryset.none()
                pass # Keep project filtering logic as per your requirements.

            total_count = queryset.count()
            start_index = (page - 1) * page_size
            end_index = start_index + page_size
            
            if total_count > end_index:
                more = True

            users = queryset.order_by('username')[start_index:end_index]
            results = [{'id': user.pk, 'text': user.display_name or user.username} for user in users]
        
        return Response({'results': results, 'pagination': {'more': more}})