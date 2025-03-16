from rest_framework import serializers
from .models import User, Role, Team


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

class TeamSerializer(serializers.ModelSerializer):
    class Meta:
        model = Team
        fields = "__all__"