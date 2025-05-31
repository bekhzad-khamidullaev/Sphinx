# user_profiles/serializers.py
from rest_framework import serializers
from django.contrib.auth.models import Group
from .models import User, Team, Department, JobTitle

class DepartmentSerializer(serializers.ModelSerializer):
    parent_name = serializers.CharField(source='parent.name', read_only=True, allow_null=True)
    head_display_name = serializers.CharField(source='head.display_name', read_only=True, allow_null=True)
    employee_count = serializers.IntegerField(source='employees.count', read_only=True)
    team_count = serializers.IntegerField(source='teams.count', read_only=True)

    class Meta:
        model = Department
        fields = [
            'id', 'name', 'description', 'parent', 'parent_name',
            'head', 'head_display_name', 'employee_count', 'team_count',
            'created_at', 'updated_at',
        ]
        read_only_fields = ('created_at', 'updated_at', 'employee_count', 'team_count')


class JobTitleSerializer(serializers.ModelSerializer):
    user_count = serializers.IntegerField(source='users.count', read_only=True)
    class Meta:
        model = JobTitle
        fields = ['id', 'name', 'description', 'user_count']
        read_only_fields = ('user_count',)

class UserNestedSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ['id', 'username', 'display_name', 'email', 'image']


class UserSerializer(serializers.ModelSerializer):
    display_name = serializers.CharField(read_only=True)
    department_name = serializers.CharField(source='department.name', read_only=True, allow_null=True)
    job_title_name = serializers.CharField(source='job_title.name', read_only=True, allow_null=True)
    team_names = serializers.SerializerMethodField(read_only=True)
    group_names = serializers.SerializerMethodField(read_only=True)
    image_url = serializers.ImageField(source='image', read_only=True)
    teams = serializers.PrimaryKeyRelatedField(many=True, queryset=Team.objects.all(), required=False, write_only=True)

    class Meta:
        model = User
        fields = [
            "id", "username", "display_name", "first_name", "last_name", "email",
            "phone_number",
            "job_title", "job_title_name",
            "department", "department_name",
            "image", "image_url",
            "is_active", "is_staff", "is_superuser", "date_joined", "last_login",
            "team_names", "teams", "group_names", "settings"
        ]
        read_only_fields = ('date_joined', 'last_login', 'is_superuser', 'image_url', 'team_names', 'group_names')
        extra_kwargs = {
            'password': {'write_only': True, 'min_length': 8, 'style': {'input_type': 'password'}},
            'first_name': {'required': False},
            'last_name': {'required': False},
        }

    def get_team_names(self, obj):
        return list(obj.teams.all().values_list('name', flat=True))

    def get_group_names(self, obj):
        return list(obj.groups.values_list('name', flat=True))

    def create(self, validated_data):
        teams_data = validated_data.pop('teams', None)
        groups_data = validated_data.pop('groups', None)
        user_permissions_data = validated_data.pop('user_permissions', None)

        password = validated_data.pop('password', None)
        user = User(**validated_data)
        if password:
            user.set_password(password)
        user.save()

        if teams_data is not None:
            user.teams.set(teams_data)
        if groups_data is not None:
            user.groups.set(groups_data)
        if user_permissions_data is not None:
            user.user_permissions.set(user_permissions_data)
            
        return user

    def update(self, instance, validated_data):
        teams_data = validated_data.pop('teams', None)
        groups_data = validated_data.pop('groups', None)
        user_permissions_data = validated_data.pop('user_permissions', None)

        password = validated_data.pop('password', None)
        if password:
            instance.set_password(password)
        
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()

        if teams_data is not None:
            instance.teams.set(teams_data)
        if groups_data is not None:
            instance.groups.set(groups_data)
        if user_permissions_data is not None:
            instance.user_permissions.set(user_permissions_data)
            
        return instance


class TeamSerializer(serializers.ModelSerializer):
    team_leader_details = UserNestedSerializer(source='team_leader', read_only=True)
    department_name = serializers.CharField(source='department.name', read_only=True, allow_null=True)
    member_count = serializers.IntegerField(source='members.count', read_only=True)
    members_details = UserNestedSerializer(source='members', many=True, read_only=True)
    members = serializers.PrimaryKeyRelatedField(many=True, queryset=User.objects.all(), required=False, write_only=True)


    class Meta:
        model = Team
        fields = [
            'id', 'name', 'description',
            'team_leader', 'team_leader_details',
            'department', 'department_name',
            'members', 'members_details', 
            'created_at', 'updated_at', 'member_count',
        ]
        read_only_fields = ('created_at', 'updated_at', 'member_count', 'members_details')
        extra_kwargs = {
            'team_leader': {'allow_null': True, 'required': False},
            'department': {'allow_null': True, 'required': False},
        }