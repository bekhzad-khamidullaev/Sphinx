# tasks/serializers.py
# -*- coding: utf-8 -*-

from rest_framework import serializers
from .models import (
    Project, TaskCategory, TaskSubcategory, Task, TaskPhoto
)
# from user_profiles.models import User # Not directly used here unless for created_by types

class ProjectSerializer(serializers.ModelSerializer):
    class Meta:
        model = Project
        fields = "__all__"

class TaskCategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = TaskCategory
        fields = "__all__"

class TaskSubcategorySerializer(serializers.ModelSerializer):
    category_name = serializers.CharField(source="category.name", read_only=True)
    class Meta:
        model = TaskSubcategory
        fields = "__all__" # includes 'category' (PK), add 'category_name' for convenience

class TaskPhotoSerializer(serializers.ModelSerializer):
    uploaded_by_username = serializers.CharField(source="uploaded_by.username", read_only=True, allow_null=True)
    class Meta:
        model = TaskPhoto
        fields = "__all__" # includes 'uploaded_by' (PK), add 'uploaded_by_username'

class TaskSerializer(serializers.ModelSerializer):
    priority_display = serializers.CharField(source="get_priority_display", read_only=True)
    status_display = serializers.CharField(source="get_status_display", read_only=True)
    category_name = serializers.CharField(source="category.name", read_only=True, allow_null=True)
    subcategory_name = serializers.CharField(source="subcategory.name", read_only=True, allow_null=True)
    project_name = serializers.CharField(source="project.name", read_only=True)
    created_by_username = serializers.CharField(source="created_by.username", read_only=True, allow_null=True)
    is_overdue = serializers.BooleanField(read_only=True)
    photos = TaskPhotoSerializer(many=True, read_only=True) # Nested serializer for photos

    # For write operations, 'priority' is an IntegerField on the model.
    # 'project', 'category', 'subcategory', 'created_by' are ForeignKey, DRF handles them by PK by default.

    class Meta:
        model = Task
        fields = [
            "id", "task_number", "title", "description",
            "project", "project_name",
            "category", "category_name",
            "subcategory", "subcategory_name",
            "status", "status_display",
            "priority", "priority_display", # 'priority' for writing int, 'priority_display' for reading text
            "deadline", "start_date", "completion_date",
            "estimated_time",
            "created_by", "created_by_username",
            "created_at", "updated_at",
            "is_overdue",
            "photos", # List of photo details
        ]
        read_only_fields = ("task_number", "created_at", "updated_at", "is_overdue", "photos",
                            "status_display", "priority_display", "project_name", "category_name",
                            "subcategory_name", "created_by_username", "completion_date")

    # If 'priority' needs to be writable as integer but displayable as text,
    # ensure 'priority' (the IntegerField) is in fields for writing,
    # and 'priority_display' (SerializerMethodField or source=get_priority_display) for reading.
    # The current setup with 'priority' (model field) and 'priority_display' (read-only) is fine.