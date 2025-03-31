# user_profiles/serializers.py
from rest_framework import serializers
# Удаляем импорт Role
# from .models import User, Role, Team, Department
from .models import User, Team, Department # <-- ИСПРАВЛЕННЫЙ ИМПОРТ

class DepartmentSerializer(serializers.ModelSerializer):
    """Serializer for Department model."""
    # Optionally add nested serializers or more fields
    parent_name = serializers.CharField(source='parent.name', read_only=True, allow_null=True)
    head_name = serializers.CharField(source='head.display_name', read_only=True, allow_null=True)
    children_count = serializers.IntegerField(source='children.count', read_only=True) # Example related count
    employee_count = serializers.IntegerField(source='employees.count', read_only=True) # Example related count

    class Meta:
        model = Department
        fields = [
            'id', 'name', 'parent', 'parent_name', 'head', 'head_name',
            'description', 'created_at', 'updated_at',
            'children_count', 'employee_count', # Example extra fields
        ]
        read_only_fields = ('created_at', 'updated_at')


class UserSerializer(serializers.ModelSerializer):
    # Используем display_name для лучшего представления
    display_name = serializers.CharField(read_only=True)
    # Добавляем связанные поля для большей информативности
    department_name = serializers.CharField(source='department.name', read_only=True, allow_null=True)
    # Можно добавить список названий команд или групп
    team_names = serializers.SerializerMethodField(read_only=True)
    group_names = serializers.SerializerMethodField(read_only=True)

    class Meta:
        model = User
        fields = [
            "id", "username", "display_name", "first_name", "last_name", "email",
            "phone_number", "job_title", "department", "department_name",
            "image", "is_active", "is_staff", "date_joined",
            "team_names", "group_names",
            # Не включаем пароль в стандартный сериализатор
        ]
        read_only_fields = ('date_joined',)
        # Поля, которые могут быть установлены при создании/обновлении через API
        # extra_kwargs = {'password': {'write_only': True, 'min_length': 8}}

    def get_team_names(self, obj):
        # Возвращает список названий команд пользователя
        return list(obj.teams.values_list('name', flat=True))

    def get_group_names(self, obj):
         # Возвращает список названий групп пользователя
        return list(obj.groups.values_list('name', flat=True))


# --- Удаляем RoleSerializer ---
# class RoleSerializer(serializers.ModelSerializer):
#     class Meta:
#         model = Role
#         fields = "__all__"
# ---

class TeamSerializer(serializers.ModelSerializer):
    # Добавляем связанные поля для информативности
    team_leader_name = serializers.CharField(source='team_leader.display_name', read_only=True, allow_null=True)
    department_name = serializers.CharField(source='department.name', read_only=True, allow_null=True)
    member_count = serializers.IntegerField(source='members.count', read_only=True)
    # Можно добавить список имен участников
    member_names = serializers.SerializerMethodField(read_only=True)

    class Meta:
        model = Team
        fields = [
            'id', 'name', 'description', 'team_leader', 'team_leader_name',
            'department', 'department_name', 'members', # members - это ID, можно убрать если member_names достаточно
            'created_at', 'updated_at', 'member_count', 'member_names',
        ]
        read_only_fields = ('created_at', 'updated_at')

    def get_member_names(self, obj):
        return list(obj.members.values_list('username', flat=True)) # Или display_name

# Можно добавить TaskUserRoleSerializer, если нужен API для управления ролями в задачах
from .models import TaskUserRole
class TaskUserRoleSerializer(serializers.ModelSerializer):
     user_name = serializers.CharField(source='user.display_name', read_only=True)
     task_number = serializers.CharField(source='task.task_number', read_only=True)

     class Meta:
          model = TaskUserRole
          fields = ['id', 'task', 'task_number', 'user', 'user_name', 'role', 'created_at']
          read_only_fields = ('created_at',)