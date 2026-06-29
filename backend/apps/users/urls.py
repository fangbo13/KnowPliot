"""User URLs — V4.0 uses custom JWT view with roles/permissions.

V4.2 SYS-V4.2-020: Replaced TokenRefreshView with BlacklistCheckingTokenRefreshView
that checks if the refresh token is blacklisted before issuing a new token pair.
"""

from django.urls import path
from .views import (
    CustomTokenObtainPairView,
    BlacklistCheckingTokenRefreshView,  # V4.2 SYS-V4.2-020
    user_me,
    update_preference,
    logout,
)

urlpatterns = [
    path("me/", user_me, name="user-me"),
    path("me/preferences/", update_preference, name="user-preferences"),
    path("token/", CustomTokenObtainPairView.as_view(), name="token-obtain"),
    path("token/refresh/", BlacklistCheckingTokenRefreshView.as_view(), name="token-refresh"),  # V4.2 SYS-V4.2-020
    path("logout/", logout, name="logout"),
]
