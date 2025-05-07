# tasks/serializers.py
# -*- coding: utf-8 -*-

from datetime import timedelta
from rest_framework import serializers
from .models import (
    Project, TaskCategory, TaskSubcategory, Task, TaskPhoto
)
# from user_profiles.models import User # Not directly used here unless for created_by types



class ProjectSerializer(serializers.ModelSerializer):
    task_count = serializers.IntegerField(read_only=True, source='tasks.count') # Если нужно кол-во задач

    class Meta:
        model = Project
        fields = "__all__"
        # fields = ['id', 'name', 'description', 'start_date', 'end_date', 'created_at', 'updated_at', 'task_count']


class TaskCategorySerializer(serializers.ModelSerializer):
    task_count = serializers.IntegerField(read_only=True, source='tasks.count')
    subcategory_count = serializers.IntegerField(read_only=True, source='subcategories.count')

    class Meta:
        model = TaskCategory
        fields = "__all__"
        # fields = ['id', 'name', 'description', 'created_at', 'updated_at', 'task_count', 'subcategory_count']


class TaskSubcategorySerializer(serializers.ModelSerializer):
    # Отображаем имя родительской категории для удобства
    category_name = serializers.CharField(source="category.name", read_only=True)
    task_count = serializers.IntegerField(read_only=True, source='tasks.count')

    class Meta:
        model = TaskSubcategory
        fields = "__all__" # includes 'category' (PK), add 'category_name' for convenience
        # fields = ['id', 'name', 'description', 'category', 'category_name', 'created_at', 'updated_at', 'task_count']


class TaskPhotoSerializer(serializers.ModelSerializer):
    uploaded_by_username = serializers.CharField(source="uploaded_by.username", read_only=True, allow_null=True)
    photo_url = serializers.ImageField(source="photo", read_only=True) # Используем ImageField для URL

    class Meta:
        model = TaskPhoto
        fields = ['id', 'task', 'photo', 'photo_url', 'description', 'uploaded_by', 'uploaded_by_username', 'created_at']
        # 'photo' (для загрузки файла), 'photo_url' (для чтения URL)
        read_only_fields = ('photo_url', 'uploaded_by_username', 'created_at')

    def create(self, validated_data):
        # При создании через API, если пользователь аутентифицирован, можно установить uploaded_by
        request = self.context.get('request')
        if request and hasattr(request, 'user') and request.user.is_authenticated:
            validated_data['uploaded_by'] = request.user
        return super().create(validated_data)


class TaskSerializer(serializers.ModelSerializer):
    priority_display = serializers.CharField(source="get_priority_display", read_only=True)
    status_display = serializers.CharField(source="get_status_display", read_only=True)
    category_name = serializers.CharField(source="category.name", read_only=True, allow_null=True)
    subcategory_name = serializers.CharField(source="subcategory.name", read_only=True, allow_null=True)
    project_name = serializers.CharField(source="project.name", read_only=True)
    created_by_username = serializers.CharField(source="created_by.username", read_only=True, allow_null=True)
    is_overdue = serializers.BooleanField(read_only=True) # Используем @property из модели

    photos = TaskPhotoSerializer(many=True, read_only=True) # Вложенный сериализатор для чтения фото
    # Для загрузки фото используйте отдельный эндпоинт TaskPhotoViewSet

    # Поля для представления ролей (если TaskUserRole используется)
    # responsible_users = UserSimpleSerializer(many=True, read_only=True, source='get_responsible_users')
    # executors = UserSimpleSerializer(many=True, read_only=True, source='get_executors')
    # watchers = UserSimpleSerializer(many=True, read_only=True, source='get_watchers')
    # Для этого нужен UserSimpleSerializer в user_profiles.serializers

    class Meta:
        model = Task
        fields = [
            "id", "task_number", "title", "description",
            "project", "project_name",
            "category", "category_name",
            "subcategory", "subcategory_name",
            "status", "status_display",
            "priority", "priority_display", # 'priority' (int) для записи, 'priority_display' (str) для чтения
            "deadline", "start_date", "completion_date",
            "estimated_time",
            "created_by", "created_by_username",
            "created_at", "updated_at",
            "is_overdue",
            "photos",
            # "responsible_users", "executors", "watchers", # Если добавлены
        ]
        read_only_fields = (
            "task_number", "created_at", "updated_at", "is_overdue", "photos",
            "status_display", "priority_display", "project_name", "category_name",
            "subcategory_name", "created_by_username", "completion_date",
            # "responsible_users", "executors", "watchers", # Если добавлены
        )

    def create(self, validated_data):
        # Установка created_by при создании задачи через API
        request = self.context.get('request')
        if request and hasattr(request, 'user') and request.user.is_authenticated:
            validated_data['created_by'] = request.user
        
        # Роли пользователей (responsible, executors, watchers) лучше обрабатывать отдельно
        # после создания задачи, возможно, через кастомный метод в ViewSet или сигналы,
        # если они передаются в запросе на создание задачи.
        # Например, validated_data.pop('responsible_user_ids', []) и т.д.

        task = super().create(validated_data)
        # Здесь можно добавить логику для создания TaskUserRole, если ID пользователей переданы
        return task

    def update(self, instance, validated_data):
        # Аналогично, обработка ролей при обновлении
        # validated_data.pop('responsible_user_ids', None) и т.д.
        task = super().update(instance, validated_data)
        # Обновление TaskUserRole
        return task

    # Можно добавить validate_estimated_time, если нужна специальная логика для API,
    # отличающаяся от той, что в форме.
    def validate_estimated_time(self, value):
        # DRF ожидает timedelta или None для DurationField.
        # Если API принимает строку (например, "2h 30m"), ее нужно парсить здесь.
        # Но обычно для API лучше передавать ISO 8601 duration format (e.g., "PT2H30M")
        # или просто количество секунд. Django DurationField сам справится с ISO 8601.
        if isinstance(value, str):
            # Простая реализация для формата "ЧЧ:ММ:СС" или "ЧЧ:ММ"
            parts = list(map(int, value.split(':')))
            if len(parts) == 3:
                return timedelta(hours=parts[0], minutes=parts[1], seconds=parts[2])
            elif len(parts) == 2:
                return timedelta(hours=parts[0], minutes=parts[1])
            raise serializers.ValidationError("Invalid duration format. Use HH:MM:SS or HH:MM or ISO 8601.")
        return value # Ожидается timedelta