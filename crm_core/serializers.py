# serializers.py
from rest_framework import serializers
from .models import (
    Campaign,
    Team,
    TaskCategory,
    TaskSubcategory,
    Task,
    TaskPhoto,
    Role,
    TaskUserRole
)
from django.contrib.auth import get_user_model

User = get_user_model()


class CampaignSerializer(serializers.ModelSerializer):
    class Meta:
        model = Campaign
        fields = "__all__"


class TeamSerializer(serializers.ModelSerializer):
    class Meta:
        model = Team
        fields = "__all__"


class TaskCategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = TaskCategory
        fields = "__all__"


class TaskSubcategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = TaskSubcategory
        fields = "__all__"


class TaskSerializer(serializers.ModelSerializer):
    priority_display = serializers.SerializerMethodField()
    priority = serializers.IntegerField(
        write_only=True
    )  # Use the correct field name
    status_name = serializers.CharField(source="get_status_display", read_only=True) # Use choice display
    category_name = serializers.CharField(source="category.name", read_only=True)
    subcategory_name = serializers.CharField(source="subcategory.name", read_only=True)
    campaign_name = serializers.CharField(source="campaign.name", read_only=True)
    team_name = serializers.CharField(source="team.name", read_only=True)
    assignee_username = serializers.CharField(source="assignee.username", read_only=True)
    created_by_username = serializers.CharField(
        source="created_by.username", read_only=True
    )
    is_overdue = serializers.ReadOnlyField() # Add is_overdue

    class Meta:
        model = Task
        fields = [
            "id",
            "task_number",
            "campaign",
            "category",
            "subcategory",
            "description",
            "assignee",
            "team",
            "status",
            "priority",
            "deadline",
            "start_date",
            "completion_date",
            "created_at",
            "updated_at",
            "photos",
            "estimated_time",
            "created_by",
            "status_name",
            "category_name",
            "subcategory_name",
            "campaign_name",
            "team_name",
            "assignee_username",
            "created_by_username",
            "priority_display",
            "is_overdue",
        ]

    def get_priority_display(self, obj):
        return obj.get_priority_display()


class TaskPhotoSerializer(serializers.ModelSerializer):
    class Meta:
        model = TaskPhoto
        fields = "__all__"


class UserSerializer(serializers.ModelSerializer):
    role_name = serializers.CharField(
        source="role.name", read_only=True
    )  # Assuming a 'role' ForeignKey

    class Meta:
        model = User
        fields = [
            "id",
            "username",
            "first_name",
            "last_name",
            "email",
            "role_name",
            "telegram_user_id",
        ]  # Adjust fields


class RoleSerializer(serializers.ModelSerializer):
    class Meta:
        model = Role
        fields = "__all__"