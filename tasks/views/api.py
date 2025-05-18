# tasks/views/api.py
import logging
from rest_framework import viewsets, permissions, status, filters
from rest_framework.views import APIView
from rest_framework.response import Response
from django_filters.rest_framework import DjangoFilterBackend
from django.db.models import Q, Count, Prefetch
from django.contrib.auth import get_user_model
from django.utils.translation import gettext_lazy as _
from django.urls import reverse
from django.conf import settings
from django.templatetags.static import static

from ..models import (
    Project, TaskCategory, TaskSubcategory, Task, TaskPhoto, TaskAssignment
)
# Импортируем Team и Department из user_profiles, так как они там определены
from user_profiles.models import Team, Department, JobTitle

from ..serializers import (
    ProjectSerializer, TaskCategorySerializer, TaskSubcategorySerializer,
    TaskSerializer, TaskPhotoSerializer, TaskAssignmentSerializer
)

# Опциональные импорты
try:
    from checklists.models import ChecklistTemplate, Checklist
except ImportError:
    ChecklistTemplate, Checklist = None, None
    logging.warning("Checklist models (ChecklistTemplate, Checklist) not found.")
try:
    from room.models import Room
except ImportError:
    Room = None
    logging.warning("Room model not found.")

User = get_user_model()
logger = logging.getLogger(__name__)

class ProjectViewSet(viewsets.ModelViewSet):
    queryset = Project.objects.annotate(task_count=Count('tasks')).order_by('name')
    serializer_class = ProjectSerializer
    permission_classes = [permissions.IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['start_date', 'end_date', 'owner', 'is_active'] # Добавил owner, is_active
    search_fields = ['name', 'description', 'owner__username'] # Добавил owner
    ordering_fields = ['name', 'start_date', 'end_date', 'created_at', 'task_count', 'owner__username']
    ordering = ['name']

    def get_serializer_context(self):
        return {'request': self.request} # Для UserNestedSerializer в ProjectSerializer, если используется

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
            try:
                queryset = queryset.filter(category_id=int(category_id))
            except ValueError:
                queryset = queryset.none()
        
        page = self.paginate_queryset(queryset)
        serializer_context = self.get_serializer_context() # Получаем контекст
        if page is not None:
            serializer = self.get_serializer(page, many=True, context=serializer_context) # Передаем контекст
            if request.query_params.get('select2') == 'true':
                 select2_data = [{'id': item['id'], 'text': item.get('name', str(item['id']))} for item in serializer.data]
                 return Response({'results': select2_data, 'pagination': {'more': self.paginator.page.has_next() if self.paginator else False}})
            return self.get_paginated_response(serializer.data)

        serializer = self.get_serializer(queryset, many=True, context=serializer_context) # Передаем контекст
        if request.query_params.get('select2') == 'true':
            select2_data = [{'id': item['id'], 'text': item.get('name', str(item['id']))} for item in serializer.data]
            return Response({'results': select2_data})
        return Response(serializer.data)

    def get_serializer_context(self): # Добавляем метод для передачи request
        return {'request': self.request}


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

    def get_serializer_context(self):
        return {'request': self.request}

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

    def get_serializer_context(self):
        return {'request': self.request}

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

    def get_serializer_context(self):
        return {'request': self.request}

    def perform_create(self, serializer):
        serializer.save(uploaded_by=self.request.user)


class SearchSuggestionsView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get_absolute_url_for_suggestion(self, request, instance_obj):
        if hasattr(instance_obj, 'get_absolute_url'):
            try:
                url = instance_obj.get_absolute_url()
                # Для API, build_absolute_uri может быть избыточным, если фронтенд сам знает хост
                # Но для консистентности и если URL могут быть относительными, лучше его использовать
                return request.build_absolute_uri(url) if url and request else url
            except Exception:
                return None
        return None

    def get(self, request, *args, **kwargs):
        query = request.query_params.get('q', '').strip()
        suggestions = []
        limit_per_type = getattr(settings, 'SEARCH_SUGGESTIONS_LIMIT_PER_TYPE', 3)

        if len(query) < 2:
            return Response({'results': suggestions})

        # --- Задачи ---
        tasks_qs = Task.objects.filter(
            Q(title__icontains=query) | Q(task_number__icontains=query) | Q(description__icontains=query)
        ).select_related('project')[:limit_per_type]
        for task_obj in tasks_qs:
            suggestions.append({
                "type": "task", "id": task_obj.id, "type_display": _("Задача"),
                "title": f"#{task_obj.task_number or task_obj.id}: {task_obj.title}",
                "subtitle": task_obj.project.name if task_obj.project else "",
                "url": self.get_absolute_url_for_suggestion(request, task_obj),
                "icon_class": "fas fa-tasks", "color_class": "text-blue-500"
            })

        # --- Проекты ---
        projects_qs = Project.objects.filter(name__icontains=query)[:limit_per_type]
        for proj_obj in projects_qs:
            suggestions.append({
                "type": "project", "id": proj_obj.id, "type_display": _("Проект"),
                "title": proj_obj.name,
                "url": self.get_absolute_url_for_suggestion(request, proj_obj),
                "icon_class": "fas fa-project-diagram", "color_class": "text-purple-500"
            })
        
        # --- Категории Задач ---
        if TaskCategory and hasattr(TaskCategory, 'objects'):
            cats_qs = TaskCategory.objects.filter(name__icontains=query)[:limit_per_type]
            for cat_obj in cats_qs:
                suggestions.append({
                    "type": "task_category", "id": cat_obj.id, "type_display": _("Категория задач"),
                    "title": cat_obj.name,
                    "url": self.get_absolute_url_for_suggestion(request, cat_obj),
                    "icon_class": "fas fa-folder-open", "color_class": "text-teal-500"
                })

        # --- Подкатегории Задач ---
        if TaskSubcategory and hasattr(TaskSubcategory, 'objects'):
            subcats_qs = TaskSubcategory.objects.filter(name__icontains=query).select_related('category')[:limit_per_type]
            for subcat_obj in subcats_qs:
                suggestions.append({
                    "type": "task_subcategory", "id": subcat_obj.id, "type_display": _("Подкатегория задач"),
                    "title": f"{subcat_obj.category.name} / {subcat_obj.name}" if subcat_obj.category else subcat_obj.name,
                    "url": self.get_absolute_url_for_suggestion(request, subcat_obj),
                    "icon_class": "fas fa-folder", "color_class": "text-cyan-500"
                })
        
        # --- Пользователи ---
        users_qs = User.objects.filter(
            Q(username__icontains=query) | Q(first_name__icontains=query) | 
            Q(last_name__icontains=query) | Q(email__icontains=query),
            is_active=True
        )[:limit_per_type]
        for user_obj in users_qs:
            avatar_url = None
            if user_obj.image and hasattr(user_obj.image, 'url') and user_obj.image.url:
                avatar_url = request.build_absolute_uri(user_obj.image.url)
            
            suggestions.append({
                "type": "user", "id": user_obj.id, "type_display": _("Пользователь"),
                "title": user_obj.display_name,
                "subtitle": f"@{user_obj.username}",
                "avatar_url": avatar_url,
                "url": self.get_absolute_url_for_suggestion(request, user_obj),
                "icon_class": "fas fa-user", "color_class": "text-orange-500"
            })

        # --- Команды (из user_profiles) ---
        if Team and hasattr(Team, 'objects'):
            teams_qs = Team.objects.filter(name__icontains=query)[:limit_per_type]
            for team_obj in teams_qs:
                suggestions.append({
                    "type": "team", "id": team_obj.id, "type_display": _("Команда"),
                    "title": team_obj.name,
                    "url": self.get_absolute_url_for_suggestion(request, team_obj),
                    "icon_class": "fas fa-users-cog", "color_class": "text-pink-500"
                })

        # --- Отделы (из user_profiles) ---
        if Department and hasattr(Department, 'objects'):
            depts_qs = Department.objects.filter(name__icontains=query)[:limit_per_type]
            for dept_obj in depts_qs:
                suggestions.append({
                    "type": "department", "id": dept_obj.id, "type_display": _("Отдел"),
                    "title": dept_obj.name,
                    "url": self.get_absolute_url_for_suggestion(request, dept_obj),
                    "icon_class": "fas fa-building", "color_class": "text-sky-500"
                })
        
        # --- Шаблоны Чеклистов ---
        if ChecklistTemplate:
            templates_qs = ChecklistTemplate.objects.filter(name__icontains=query, is_archived=False, is_active=True)[:limit_per_type]
            for ct_obj in templates_qs:
                suggestions.append({
                    "type": "checklist_template", "id": str(ct_obj.uuid), "type_display": _("Шаблон чеклиста"),
                    "title": ct_obj.name,
                    "url": self.get_absolute_url_for_suggestion(request, ct_obj),
                    "icon_class": "fas fa-clipboard-list", "color_class": "text-indigo-500"
                })

        # --- Выполненные Чеклисты (Checklist) ---
        if Checklist:
            runs_qs = Checklist.objects.filter(
                Q(template__name__icontains=query) | Q(performed_by__username__icontains=query),
                # is_archived=False # У модели Checklist нет is_archived, у Template есть
            ).select_related('template', 'performed_by').order_by('-performed_at')[:limit_per_type]
            for cr_obj in runs_qs:
                suggestions.append({
                    "type": "checklist_run", "id": str(cr_obj.id), "type_display": _("Выполненный чеклист"),
                    "title": f"{cr_obj.template.name} ({cr_obj.performed_at:%d.%m.%y})",
                    "subtitle": f"{_('Выполнил')}: {cr_obj.performed_by.display_name if cr_obj.performed_by else '-'}",
                    "url": self.get_absolute_url_for_suggestion(request, cr_obj),
                    "icon_class": "fas fa-history", "color_class": "text-gray-500"
                })
            
        # --- Чат-комнаты ---
        if Room:
            rooms_qs = Room.objects.filter(name__icontains=query, is_archived=False)[:limit_per_type]
            for room_obj in rooms_qs:
                suggestions.append({
                    "type": "room", "id": str(room_obj.id), "type_display": _("Чат-комната"),
                    "title": f"# {room_obj.name}",
                    "url": self.get_absolute_url_for_suggestion(request, room_obj),
                    "icon_class": "fas fa-comments", "color_class": "text-green-500"
                })

        return Response({'results': suggestions[:getattr(settings, 'SEARCH_SUGGESTIONS_TOTAL_LIMIT', 15)]})


class UserAutocompleteView(APIView):
    permission_classes = [permissions.IsAuthenticated]
    def get(self, request, *args, **kwargs):
        query = request.query_params.get('q', '').strip()
        # project_id_str = request.query_params.get('project') # Для возможной фильтрации
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
            
            total_count = queryset.count()
            start_index = (page - 1) * page_size
            end_index = start_index + page_size
            
            if total_count > end_index:
                more = True

            users = queryset.order_by('username')[start_index:end_index]
            results = [{'id': user_obj.pk, 'text': user_obj.display_name} for user_obj in users]
        
        return Response({'results': results, 'pagination': {'more': more}})