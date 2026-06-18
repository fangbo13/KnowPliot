"""User URLs."""

from django.urls import path
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView
from .views import user_me, update_preference

urlpatterns = [
    path("me/", user_me, name="user-me"),
    path("me/preferences/", update_preference, name="user-preferences"),
    path("token/", TokenObtainPairView.as_view(), name="token-obtain"),
    path("token/refresh/", TokenRefreshView.as_view(), name="token-refresh"),
]
