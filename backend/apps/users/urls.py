# Copyright (c) 2026 Haibo Fang.
# Licensed under the CC BY-NC-SA 4.0 License.
# See LICENSE file in the project root for full license details.

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
    register,  # V7.0
    register_admin,  # V7.0
    AuthSessionDetailView,
    AuthSessionListView,
    ChangePasswordView,
    MFAConfirmView,
    MFADisableView,
    MFALoginView,
    MFASetupView,
    PasswordResetConfirmView,
    PasswordResetRequestView,
    RevokeOtherSessionsView,
)

urlpatterns = [
    path("me/", user_me, name="user-me"),
    path("me/preferences/", update_preference, name="user-preferences"),
    path("token/", CustomTokenObtainPairView.as_view(), name="token-obtain"),
    path("token/refresh/", BlacklistCheckingTokenRefreshView.as_view(), name="token-refresh"),  # V4.2 SYS-V4.2-020
    path("token/mfa/", MFALoginView.as_view(), name="token-mfa"),
    path("password/change/", ChangePasswordView.as_view(), name="password-change"),
    path("password/reset/request/", PasswordResetRequestView.as_view(), name="password-reset-request"),
    path("password/reset/confirm/", PasswordResetConfirmView.as_view(), name="password-reset-confirm"),
    path("sessions/", AuthSessionListView.as_view(), name="auth-session-list"),
    path("sessions/revoke-others/", RevokeOtherSessionsView.as_view(), name="auth-session-revoke-others"),
    path("sessions/<uuid:pk>/", AuthSessionDetailView.as_view(), name="auth-session-detail"),
    path("mfa/setup/", MFASetupView.as_view(), name="mfa-setup"),
    path("mfa/confirm/", MFAConfirmView.as_view(), name="mfa-confirm"),
    path("mfa/disable/", MFADisableView.as_view(), name="mfa-disable"),
    path("logout/", logout, name="logout"),
    # V7.0 self-registration
    path("register/", register, name="register"),
    path("register-admin/", register_admin, name="register-admin"),
]
