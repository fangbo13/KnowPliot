"""User serializers."""

from rest_framework import serializers
from .models import User


class UserSerializer(serializers.ModelSerializer):
    """Serializer for user profile."""

    class Meta:
        model = User
        fields = [
            "id",
            "email",
            "username",
            "employee_id",
            "service_line",
            "office_location",
            "role_level",
            "start_date",
            "language_preference",
            "is_hr_admin",
        ]
        read_only_fields = ["id", "email", "username", "employee_id"]


class UserPreferenceSerializer(serializers.ModelSerializer):
    """Serializer for updating user preferences."""

    class Meta:
        model = User
        fields = ["language_preference"]
