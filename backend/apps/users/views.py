"""User views."""

from rest_framework import generics, permissions
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response
from .models import User
from .serializers import UserSerializer, UserPreferenceSerializer


class UserMeView(generics.RetrieveUpdateAPIView):
    """Get and update current user profile."""

    serializer_class = UserSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_object(self):
        return self.request.user


class UserPreferenceView(generics.UpdateAPIView):
    """Update user preferences (language, etc.)."""

    serializer_class = UserPreferenceSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_object(self):
        return self.request.user


@api_view(["GET"])
@permission_classes([permissions.IsAuthenticated])
def user_me(request):
    """Get current user info."""
    serializer = UserSerializer(request.user)
    return Response(serializer.data)


@api_view(["PATCH"])
@permission_classes([permissions.IsAuthenticated])
def update_preference(request):
    """Update user preference."""
    serializer = UserPreferenceSerializer(request.user, data=request.data, partial=True)
    serializer.is_valid(raise_exception=True)
    serializer.save()
    return Response(serializer.data)
