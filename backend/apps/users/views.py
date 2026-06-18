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



@api_view(["POST"])
@permission_classes([permissions.IsAuthenticated])
def logout(request):
    """Logout: blacklist the access token and clear session.

    The frontend clears localStorage after calling this endpoint,
    which is the primary logout mechanism. Token blacklisting provides
    an additional layer: we create an OutstandingToken + BlacklistedToken
    entry so the JWT auth middleware rejects this token on future requests.
    """
    from rest_framework_simplejwt.tokens import AccessToken
    from rest_framework_simplejwt.token_blacklist.models import (
        BlacklistedToken,
        OutstandingToken,
    )
    from django.utils import timezone
    from rest_framework import status
    import datetime
    import logging

    logger = logging.getLogger(__name__)
    logger.info("Logout requested for user %s", request.user.email)

    try:
        auth_header = request.META.get("HTTP_AUTHORIZATION", "")
        if auth_header.startswith("Bearer "):
            token_str = auth_header[7:]
            access_token = AccessToken(token_str)
            jti = access_token.get("jti")

            # Create outstanding token record for this access token
            outstanding, _ = OutstandingToken.objects.get_or_create(
                jti=jti,
                defaults={
                    "user": request.user,
                    "token": token_str,
                    "created_at": timezone.now(),
                    "expires_at": timezone.datetime.fromtimestamp(
                        access_token.get("exp"), tz=datetime.timezone.utc
                    ),
                },
            )
            # Blacklist it
            BlacklistedToken.objects.get_or_create(token=outstanding)
            logger.info("Access token blacklisted for user %s", request.user.email)
    except Exception as e:
        logger.error("Could not blacklist token for %s: %s", request.user.email, e, exc_info=True)

    return Response(
        {"detail": "Logged out successfully."},
        status=status.HTTP_200_OK,
    )
