# tasks/serializers.py
# -*- coding: utf-8 -*-

from rest_framework import serializers
from django.contrib.auth import get_user_model
from django.db import transaction
from django.utils.translation import gettext_lazy as _
from .models import (
    Project, TaskCategory, TaskSubcategory, Task, TaskPhoto, TaskAssignment # MODIFIED: Added TaskAssignment
)
# from user_profiles.models import User # User is now imported via get_user_model

User = get_user_model()

class ProjectSerializer(serializers.ModelSerializer):
    task_count = serializers.IntegerField(read_only=True, required=False) # Assuming annotated in queryset
    # team_name = serializers.CharField(source="team.name", read_only=True, allow_null=True)
    # department_name = serializers.CharField(source="department.name", read_only=True, allow_null=True)

    class Meta:
        model = Project
        fields = "__all__" # Will include task_count if annotated
        # fields = [
        #     "id", "name", "description", "start_date", "end_date", 
        #     "team", "team_name", "department", "department_name", # If Project has team/dept
        #     "created_at", "updated_at", "task_count"
        # ]
        # read_only_fields = ("created_at", "updated_at", "task_count", "team_name", "department_name")


class TaskCategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = TaskCategory
        fields = "__all__"

class TaskSubcategorySerializer(serializers.ModelSerializer):
    category_name = serializers.CharField(source="category.name", read_only=True)
    class Meta:
        model = TaskSubcategory
        fields = "__all__"

class TaskPhotoSerializer(serializers.ModelSerializer):
    uploaded_by_username = serializers.CharField(source="uploaded_by.username", read_only=True, allow_null=True)
    photo_url = serializers.ImageField(source="photo", read_only=True) # Or serializers.SerializerMethodField
    
    class Meta:
        model = TaskPhoto
        fields = [
            "id", "task", "photo", "photo_url", "description", 
            "uploaded_by", "uploaded_by_username", "created_at", "updated_at"
        ]
        read_only_fields = ("created_at", "updated_at", "uploaded_by_username", "photo_url")

# MODIFIED: TaskAssignmentSerializer
class TaskAssignmentSerializer(serializers.ModelSerializer):
    user_id = serializers.IntegerField(source='user.id') # For writing assignment by user_id
    username = serializers.CharField(source='user.username', read_only=True)
    user_display_name = serializers.CharField(source='user.display_name', read_only=True)
    role_display = serializers.CharField(source='get_role_display', read_only=True)

    class Meta:
        model = TaskAssignment
        fields = [
            'id', 'task', 'user', 'user_id', 'username', 'user_display_name', 
            'role', 'role_display', 
            'assigned_by', 'created_at', 'updated_at'
        ]
        read_only_fields = ('id', 'task', 'username', 'user_display_name', 'role_display', 'assigned_by', 'created_at', 'updated_at')
        # 'user' is writable by PK, user_id is for alternative write if PK not known but ID is
        # 'task' will be set by context or TaskSerializer

    def create(self, validated_data):
        # Handle user_id if 'user' (PK) is not provided directly
        user_data = validated_data.pop('user', None) # Main way to get user PK
        user_id = validated_data.pop('user_id', None) # Fallback or alternative
        
        if not user_data and user_id:
            try:
                user_data = User.objects.get(pk=user_id)
            except User.DoesNotExist:
                raise serializers.ValidationError({"user_id": _("Пользователь с ID %(id)s не найден.") % {'id': user_id}})
        
        if not user_data: # If still no user
             raise serializers.ValidationError({"user": _("Пользователь должен быть указан.")})

        validated_data['user'] = user_data
        
        # Set assigned_by from request context if available
        request = self.context.get('request')
        if request and hasattr(request, 'user') and request.user.is_authenticated:
            if 'assigned_by' not in validated_data or not validated_data['assigned_by']:
                validated_data['assigned_by'] = request.user
        
        return super().create(validated_data)


class TaskSerializer(serializers.ModelSerializer):
    priority_display = serializers.CharField(source="get_priority_display", read_only=True)
    status_display = serializers.CharField(source="get_status_display", read_only=True)
    category_name = serializers.CharField(source="category.name", read_only=True, allow_null=True)
    subcategory_name = serializers.CharField(source="subcategory.name", read_only=True, allow_null=True)
    project_name = serializers.CharField(source="project.name", read_only=True)
    created_by_username = serializers.CharField(source="created_by.username", read_only=True, allow_null=True)
    team_name = serializers.CharField(source="team.name", read_only=True, allow_null=True) # Added
    department_name = serializers.CharField(source="department.name", read_only=True, allow_null=True) # Added
    is_overdue = serializers.BooleanField(read_only=True)
    photos = TaskPhotoSerializer(many=True, read_only=True) # Nested serializer for photos
    
    # MODIFIED: Use TaskAssignmentSerializer for assignments
    assignments = TaskAssignmentSerializer(many=True, required=False) # Can be used for read and write

    class Meta:
        model = Task
        fields = [
            "id", "task_number", "title", "description",
            "project", "project_name",
            "category", "category_name",
            "subcategory", "subcategory_name",
            "status", "status_display",
            "priority", "priority_display",
            "start_date", "due_date", "completion_date",
            "estimated_time",
            "team", "team_name", # Added
            "department", "department_name", # Added
            "created_by", "created_by_username",
            "created_at", "updated_at",
            "is_overdue",
            "photos",
            "assignments", # MODIFIED
        ]
        read_only_fields = (
            "task_number", "created_at", "updated_at", "is_overdue", "photos",
            "status_display", "priority_display", "project_name", "category_name",
            "subcategory_name", "created_by_username", "completion_date",
            "team_name", "department_name"
        )

    @transaction.atomic
    def create(self, validated_data):
        assignments_data = validated_data.pop('assignments', [])
        task = Task.objects.create(**validated_data)
        
        for assignment_data in assignments_data:
            # User can be passed as PK or a User instance if resolved by a field
            user_obj = assignment_data.get('user')
            if isinstance(user_obj, int): # If user is passed as PK
                 user_obj = User.objects.get(pk=user_obj)
            
            TaskAssignment.objects.create(
                task=task, 
                user=user_obj, 
                role=assignment_data['role'],
                assigned_by=self.context['request'].user if 'request' in self.context else None
            )
        return task

    @transaction.atomic
    def update(self, instance, validated_data):
        assignments_data = validated_data.pop('assignments', None) # Use None to detect if key was passed
        
        # Update Task instance fields
        instance = super().update(instance, validated_data)

        if assignments_data is not None: # Only update assignments if 'assignments' key is in request
            # Simple strategy: Delete existing and create new ones
            # More complex: Diff and update/create/delete
            instance.assignments.all().delete() 
            for assignment_data in assignments_data:
                user_obj = assignment_data.get('user')
                if isinstance(user_obj, int):
                    user_obj = User.objects.get(pk=user_obj)

                TaskAssignment.objects.create(
                    task=instance, 
                    user=user_obj, 
                    role=assignment_data['role'],
                    assigned_by=(
                        self.context['request'].user if 'request' in self.context else None
                    )
                )
        
        instance.refresh_from_db() # To get updated assignments if needed by response
        return instance
