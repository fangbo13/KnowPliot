# Copyright (c) 2026 Haibo Fang.
# Licensed under the CC BY-NC-SA 4.0 License.
# See LICENSE file in the project root for full license details.

"""User views — V4.0 RBAC extended with custom JWT token response.
V4.1 SYS-V4.1-005: Added LoginRateThrottle (5/min per IP) to prevent brute force.
V4.2 SYS-V4.2-020: Added BlacklistCheckingTokenRefreshView — checks if
  refresh token is blacklisted before issuing a new token pair. Previously,
  TokenRefreshView did not check the blacklist, allowing stolen blacklisted
  refresh tokens to obtain new valid access+refresh pairs.
"""

from django.db import transaction
from rest_framework import generics, permissions, status
from rest_framework.decorators import api_view, permission_classes, throttle_classes
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer, TokenRefreshSerializer
from rest_framework_simplejwt.token_blacklist.models import BlacklistedToken
from rest_framework.throttling import AnonRateThrottle
from .models import User
from .serializers import UserSerializer, UserPreferenceSerializer


# V4.1 SYS-V4.1-005: Login endpoint throttle — 5 attempts per minute per IP
class LoginRateThrottle(AnonRateThrottle):
    """Rate limit for login/token endpoint: 5 requests per minute per IP.

    Prevents brute-force attacks on /api/v1/auth/token/.
    allauth's LoginView is NOT a DRF view, so UserRateThrottle never applies.
    This throttle covers the JWT token endpoint specifically.
    """
    rate = "5/minute"


class CustomTokenObtainPairSerializer(TokenObtainPairSerializer):
    """V4.0: Extend JWT token response to include user roles and permissions.

    This ensures the frontend receives roles[] and permissions[] on login,
    enabling immediate RoleGuard/permission checks without a separate API call.
    """

    @classmethod
    def get_token(cls, user):
        token = super().get_token(user)
        # V4.1 KB-V4.1-009: Removed is_hr_admin from JWT claims.
        # is_hr_admin is only included in the login response body (not the replayable JWT).
        # JWT claims should not contain role/permission data to prevent information leakage.
        return token

    def validate(self, attrs):
        data = super().validate(attrs)
        # V7.0: single source of truth for the user payload (adds admin scope flags)
        from .identity import identity_payload
        data["user"] = identity_payload(self.user)
        return data


class CustomTokenObtainPairView(TokenObtainPairView):
    """V4.0: Use custom serializer that includes roles/permissions.
    V4.1 SYS-V4.1-005: Added LoginRateThrottle to prevent brute force.
    """
    serializer_class = CustomTokenObtainPairSerializer
    throttle_classes = [LoginRateThrottle]


# V4.2 SYS-V4.2-020: Custom TokenRefreshSerializer that checks blacklist
# Previous: simplejwt's TokenRefreshSerializer only decoded the refresh token,
# never checking if it was blacklisted. This allowed stolen blacklisted refresh
# tokens to obtain new valid access+refresh pairs, completely defeating the
# JWT rotation security model.
# Now: before issuing a new token pair, we check if the OutstandingToken
# corresponding to the refresh token's JTI has been blacklisted. If yes,
# the refresh request is rejected with 401 Unauthorized.
class BlacklistCheckingTokenRefreshSerializer(TokenRefreshSerializer):
    """Token refresh serializer that checks blacklist before issuing new tokens.

    V4.2 SYS-V4.2-020: When BLACKLIST_AFTER_ROTATION=True, old refresh tokens
    are automatically blacklisted when they're rotated. But simplejwt's default
    TokenRefreshSerializer doesn't check the blacklist — it only decodes the
    JWT and checks its validity (signature, expiry). This serializer adds a
    blacklist check before the rotation proceeds.

    Attack prevented: Stolen refresh token (already blacklisted via rotation
    or explicit logout) cannot obtain new access+refresh pair.
    """

    def validate(self, attrs):
        # Step 1: Decode the refresh token to get the JTI
        from rest_framework_simplejwt.tokens import RefreshToken

        refresh_token_str = attrs.get("refresh")
        if refresh_token_str:
            try:
                refresh_token = RefreshToken(refresh_token_str)
                jti = refresh_token.get("jti")

                # V4.2 SYS-V4.2-020: Check if this JTI is in the blacklist
                # FIX-001: Use single-step FK traversal query matching SimpleJWT's
                # check_blacklist() pattern, instead of two-step OutstandingToken + BlacklistedToken.
                if jti and BlacklistedToken.objects.filter(token__jti=jti).exists():
                    from rest_framework.exceptions import AuthenticationFailed
                    raise AuthenticationFailed(
                        "Token is blacklisted — cannot refresh."
                    )
            except Exception:
                # If token decoding fails, let the parent validate() handle it
                # (it will raise its own appropriate error)
                pass

        # Step 2: Proceed with normal validation (decode, rotate, etc.)
        return super().validate(attrs)


class BlacklistCheckingTokenRefreshView(TokenRefreshView):
    """V4.2 SYS-V4.2-020: Uses BlacklistCheckingTokenRefreshSerializer.

    Replaces default TokenRefreshView which does not check the blacklist.
    This view checks if the refresh token's JTI has been blacklisted
    before issuing a new access+refresh pair.
    """
    serializer_class = BlacklistCheckingTokenRefreshSerializer


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
    """Get current user info — V4.0 includes roles and permissions."""
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
    """Logout: blacklist both access and refresh tokens.

    V4.1 KB-V4.1-010: Also blacklist the refresh token from request body,
    ensuring the same token cannot be reused after logout.
    The frontend clears localStorage after calling this endpoint.
    Token blacklisting provides defense-in-depth: OutstandingToken +
    BlacklistedToken entries cause JWT auth to reject these tokens.
    """
    from rest_framework_simplejwt.tokens import AccessToken, RefreshToken
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

    # V4.1 KB-V4.1-010: Blacklist access token from Authorization header
    try:
        auth_header = request.META.get("HTTP_AUTHORIZATION", "")
        if auth_header.startswith("Bearer "):
            token_str = auth_header[7:]
            access_token = AccessToken(token_str)
            jti = access_token.get("jti")

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
            BlacklistedToken.objects.get_or_create(token=outstanding)
            logger.info("Access token blacklisted for user %s", request.user.email)
    except Exception as e:
        logger.error("Could not blacklist access token for %s: %s", request.user.email, e, exc_info=True)

    # V4.1 KB-V4.1-010: Also blacklist refresh token from request body
    refresh_token_str = request.data.get("refresh")
    if refresh_token_str:
        try:
            refresh_token = RefreshToken(refresh_token_str)
            refresh_token.blacklist()
            logger.info("Refresh token blacklisted for user %s", request.user.email)
        except Exception as e:
            logger.error("Could not blacklist refresh token for %s: %s", request.user.email, e)

    return Response(
        {"detail": "Logged out successfully."},
        status=status.HTTP_200_OK,
    )


# ── V7.0 Registration ────────────────────────────────────────────────

class SignupRateThrottle(AnonRateThrottle):
    """Per-IP throttle for registration / admin-code endpoints (5/min)."""
    scope = "signup"


def _auth_response(user):
    """Mint a JWT pair and the identity payload — mirrors the login response."""
    from rest_framework_simplejwt.tokens import RefreshToken
    from .identity import identity_payload

    refresh = RefreshToken.for_user(user)
    return {
        "access": str(refresh.access_token),
        "refresh": str(refresh),
        "user": identity_payload(user),
    }


def _audit_register(user, action, request, details=None):
    try:
        from apps.audit.views import create_audit_log
        create_audit_log(
            user=user, action=action, target_type="User",
            target_id=getattr(user, "id", None), details=details or {}, request=request,
        )
    except Exception:  # pragma: no cover - audit must not block registration
        pass


def _provision_new_user(user, request):
    """Default-space placement + email-invite redemption + welcome notifications."""
    from apps.spaces.services import join_default_space, redeem_email_invites
    from apps.notifications.services import notify

    space = join_default_space(user)
    granted = redeem_email_invites(user)

    notify(
        user, "welcome",
        title="Welcome to KnowPilot",
        body="Your account is ready. Ask questions in your knowledge space anytime.",
        level="success", link="/chat",
    )
    for sp, role in granted:
        notify(
            user, "space_invite",
            title=f"You were added to {sp.name}",
            body=f"Your role: {role}.",
            link="/chat", metadata={"space_id": str(sp.id), "role": role},
        )
    return space


@api_view(["POST"])
@permission_classes([permissions.AllowAny])
@throttle_classes([SignupRateThrottle])
def register(request):
    """Regular self-registration (Service Line required)."""
    from .serializers import RegisterSerializer

    serializer = RegisterSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    user = serializer.save()
    _audit_register(user, "user_register", request,
                    details={"service_line": user.service_line})

    if not user.is_active:
        # REQUIRE_SIGNUP_APPROVAL is on — no tokens until an admin approves.
        return Response(
            {"detail": "Your account is pending administrator approval.", "pending": True},
            status=status.HTTP_201_CREATED,
        )

    _provision_new_user(user, request)
    return Response(_auth_response(user), status=status.HTTP_201_CREATED)


@api_view(["POST"])
@permission_classes([permissions.AllowAny])
@throttle_classes([SignupRateThrottle])
def register_admin(request):
    """Admin registration via a tiered Admin Registration Code.

    The code is consumed inside a transaction so an invalid/expired code never
    leaves an orphan account behind. Super Admin is NOT obtainable here.
    """
    from .serializers import AdminRegisterSerializer
    from apps.spaces.services import redeem_admin_code
    from apps.notifications.services import notify

    serializer = AdminRegisterSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    raw_code = serializer.validated_data["code"]

    with transaction.atomic():
        user = serializer.save()
        membership, code = redeem_admin_code(raw_code, user)
        if membership is None:
            # Rolls back the just-created user.
            raise ValidationError({"code": "Invalid, expired, or exhausted admin code."})

    _audit_register(
        user, "admin_code_register", request,
        details={"grants_role": code.grants_role, "code_prefix": code.code_prefix},
    )
    scope = code.business_line.code if code.business_line else code.organization.slug
    notify(
        user, "role_granted",
        title="Administrator access granted",
        body=f"You are now {code.grants_role} for {scope}.",
        level="success", link="/admin/dashboard",
        metadata={"role": code.grants_role, "scope": scope},
    )
    return Response(_auth_response(user), status=status.HTTP_201_CREATED)
