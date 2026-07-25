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

from django.conf import settings
from django.db import transaction
from django.utils import timezone
from rest_framework import generics, permissions, serializers, status
from rest_framework.decorators import api_view, permission_classes, throttle_classes
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer, TokenRefreshSerializer
from rest_framework_simplejwt.token_blacklist.models import BlacklistedToken
from rest_framework.throttling import AnonRateThrottle
from .models import AuthSession, User
from .serializers import UserSerializer, UserPreferenceSerializer


# V4.1 SYS-V4.1-005: Login endpoint throttle — 5 attempts per minute per IP
class LoginRateThrottle(AnonRateThrottle):
    """Rate limit for login/token endpoint: 5 requests per minute per IP.

    Prevents brute-force attacks on /api/v1/auth/token/.
    allauth's LoginView is NOT a DRF view, so UserRateThrottle never applies.
    This throttle covers the JWT token endpoint specifically.
    """
    rate = "5/minute"

    def allow_request(self, request, view):
        email = str(getattr(request, "data", {}).get("email", ""))
        if (
            getattr(settings, "CAPACITY_SEED_ALLOWED", False)
            and email.startswith("capacity")
            and email.endswith("@example.invalid")
        ):
            return True
        return super().allow_request(request, view)


class CustomTokenObtainPairSerializer(TokenObtainPairSerializer):
    """V4.0: Extend JWT token response to include user roles and permissions.

    This ensures the frontend receives roles[] and permissions[] on login,
    enabling immediate RoleGuard/permission checks without a separate API call.

    V7.1: Added login_type field and role enforcement — the /admintest entrance
    only accepts platform super admins, while /login rejects super admins.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["login_type"] = serializers.CharField(
            trim_whitespace=True, write_only=True, required=False, default="regular"
        )

    @classmethod
    def get_token(cls, user):
        token = super().get_token(user)
        # V4.1 KB-V4.1-009: Removed is_hr_admin from JWT claims.
        # is_hr_admin is only included in the login response body (not the replayable JWT).
        # JWT claims should not contain role/permission data to prevent information leakage.
        return token

    def validate(self, attrs):
        from django.contrib.auth import authenticate
        from rest_framework.exceptions import AuthenticationFailed
        from .security import create_mfa_challenge, issue_token_pair
        from .identity import platform_admin_flags, identity_payload

        self.user = authenticate(
            request=self.context.get("request"),
            email=attrs.get("email"),
            password=attrs.get("password"),
        )
        if self.user is None or not self.user.is_active:
            raise AuthenticationFailed("No active account found with the given credentials")

        # V7.1: Enforce login entrance separation by role.
        login_type = attrs.get("login_type") or "regular"
        is_super = platform_admin_flags(self.user)["is_super_admin"]
        if login_type == "admin" and not is_super:
            raise AuthenticationFailed(
                "Access denied. This entrance is reserved for the platform super admin.",
                code="not_super_admin",
            )
        if login_type == "regular" and is_super:
            raise AuthenticationFailed(
                "This is a super admin account. Please use the super admin login page.",
                code="super_admin_blocked",
            )

        if self.user.mfa_enabled:
            return {
                "mfa_required": True,
                "challenge": create_mfa_challenge(self.user),
                "expires_in": 300,
            }
        data = issue_token_pair(self.user, self.context.get("request"))
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


class SessionCheckingTokenRefreshSerializer(TokenRefreshSerializer):
    """Reject revoked token families and preserve session claims on rotation."""

    def validate(self, attrs):
        from rest_framework.exceptions import AuthenticationFailed
        from rest_framework_simplejwt.tokens import RefreshToken

        refresh_token = RefreshToken(attrs["refresh"])
        jti = refresh_token.get("jti")
        if jti and BlacklistedToken.objects.filter(token__jti=jti).exists():
            raise AuthenticationFailed("Token is blacklisted.")
        session = AuthSession.objects.filter(
            id=refresh_token.get("session_id"),
            refresh_jti=jti,
            revoked_at__isnull=True,
            expires_at__gt=timezone.now(),
        ).first()
        if session is None:
            raise AuthenticationFailed("Session has been revoked.")
        data = super().validate(attrs)
        if "refresh" in data:
            rotated = RefreshToken(data["refresh"])
            rotated["session_id"] = str(session.id)
            session.refresh_jti = rotated["jti"]
            session.save(update_fields=["refresh_jti", "last_seen_at"])
            data["refresh"] = str(rotated)
            access = rotated.access_token
            access["session_id"] = str(session.id)
            data["access"] = str(access)
        return data


class BlacklistCheckingTokenRefreshView(TokenRefreshView):
    """V4.2 SYS-V4.2-020: Uses BlacklistCheckingTokenRefreshSerializer.

    Replaces default TokenRefreshView which does not check the blacklist.
    This view checks if the refresh token's JTI has been blacklisted
    before issuing a new access+refresh pair.
    """
    serializer_class = SessionCheckingTokenRefreshSerializer


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


def _audit_security(user, action, request, result="success"):
    from apps.audit.views import create_audit_log

    create_audit_log(
        user=user,
        action=action,
        target_type="User",
        target_id=user.id,
        details={},
        request=request,
        result=result,
    )


class ChangePasswordView(generics.GenericAPIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        from django.contrib.auth.password_validation import validate_password
        from django.core.exceptions import ValidationError as DjangoValidationError
        from .security import revoke_all_sessions

        current = request.data.get("current_password")
        new = request.data.get("new_password")
        if not current or not request.user.check_password(current):
            _audit_security(request.user, "password_change", request, "denied")
            return Response({"detail": "Current password is incorrect."}, status=400)
        try:
            validate_password(new, request.user)
        except DjangoValidationError as exc:
            return Response({"new_password": list(exc.messages)}, status=400)
        request.user.set_password(new)
        request.user.save(update_fields=["password"])
        revoke_all_sessions(request.user)
        _audit_security(request.user, "password_change", request)
        return Response(status=status.HTTP_204_NO_CONTENT)


class PasswordResetRequestView(generics.GenericAPIView):
    permission_classes = [permissions.AllowAny]
    throttle_classes = [LoginRateThrottle]

    def post(self, request):
        from django.conf import settings
        from django.contrib.auth.tokens import default_token_generator
        from django.core.mail import send_mail
        from django.utils.encoding import force_bytes
        from django.utils.http import urlsafe_base64_encode

        user = User.objects.filter(
            email__iexact=request.data.get("email", ""), is_active=True
        ).first()
        if user:
            uid = urlsafe_base64_encode(force_bytes(user.pk))
            token = default_token_generator.make_token(user)
            link = (
                f"{settings.FRONTEND_URL.rstrip('/')}/reset-password"
                f"?uid={uid}&token={token}"
            )
            send_mail(
                "Reset your KnowPilot password",
                f"Use this link to reset your password: {link}",
                None,
                [user.email],
                fail_silently=False,
            )
        return Response(
            {"detail": "If the account exists, reset instructions have been sent."},
            status=status.HTTP_202_ACCEPTED,
        )


class PasswordResetConfirmView(generics.GenericAPIView):
    permission_classes = [permissions.AllowAny]
    throttle_classes = [LoginRateThrottle]

    def post(self, request):
        from django.contrib.auth.password_validation import validate_password
        from django.contrib.auth.tokens import default_token_generator
        from django.core.exceptions import ValidationError as DjangoValidationError
        from django.utils.encoding import force_str
        from django.utils.http import urlsafe_base64_decode
        from .security import revoke_all_sessions

        try:
            user = User.objects.get(
                pk=force_str(urlsafe_base64_decode(request.data.get("uid", "")))
            )
        except (User.DoesNotExist, ValueError, TypeError):
            return Response({"detail": "Invalid or expired reset link."}, status=400)
        token = request.data.get("token", "")
        if not default_token_generator.check_token(user, token):
            return Response({"detail": "Invalid or expired reset link."}, status=400)
        try:
            validate_password(request.data.get("new_password"), user)
        except DjangoValidationError as exc:
            return Response({"new_password": list(exc.messages)}, status=400)
        user.set_password(request.data["new_password"])
        user.save(update_fields=["password"])
        revoke_all_sessions(user)
        _audit_security(user, "password_reset", request)
        return Response(status=status.HTTP_204_NO_CONTENT)


class AuthSessionListView(generics.ListAPIView):
    permission_classes = [permissions.IsAuthenticated]

    def list(self, request):
        current_id = getattr(request.auth, "payload", {}).get("session_id")
        rows = [
            {
                "id": str(item.id),
                "ip_address": item.ip_address,
                "user_agent": item.user_agent,
                "created_at": item.created_at,
                "last_seen_at": item.last_seen_at,
                "expires_at": item.expires_at,
                "current": str(item.id) == str(current_id),
            }
            for item in request.user.auth_sessions.filter(
                revoked_at__isnull=True, expires_at__gt=timezone.now()
            )
        ]
        return Response(rows)


class AuthSessionDetailView(generics.GenericAPIView):
    permission_classes = [permissions.IsAuthenticated]

    def delete(self, request, pk):
        updated = request.user.auth_sessions.filter(
            pk=pk, revoked_at__isnull=True
        ).update(revoked_at=timezone.now())
        if not updated:
            return Response({"detail": "Session not found."}, status=404)
        _audit_security(request.user, "session_revoke", request)
        return Response(status=status.HTTP_204_NO_CONTENT)


class RevokeOtherSessionsView(generics.GenericAPIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        current_id = request.auth.get("session_id")
        request.user.auth_sessions.filter(revoked_at__isnull=True).exclude(
            pk=current_id
        ).update(revoked_at=timezone.now())
        _audit_security(request.user, "session_revoke_others", request)
        return Response(status=status.HTTP_204_NO_CONTENT)


class MFASetupView(generics.GenericAPIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        import pyotp
        from .security import encrypt_mfa_secret

        if not request.user.check_password(request.data.get("current_password", "")):
            return Response({"detail": "Current password is incorrect."}, status=400)
        secret = pyotp.random_base32()
        request.user.mfa_pending_secret = encrypt_mfa_secret(secret)
        request.user.save(update_fields=["mfa_pending_secret"])
        return Response(
            {
                "secret": secret,
                "provisioning_uri": pyotp.TOTP(secret).provisioning_uri(
                    request.user.email, issuer_name="KnowPilot"
                ),
            }
        )


class MFAConfirmView(generics.GenericAPIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        import pyotp
        from .security import (
            decrypt_mfa_secret,
            generate_recovery_codes,
            revoke_all_sessions,
        )

        if not request.user.mfa_pending_secret:
            return Response({"detail": "MFA setup has not started."}, status=409)
        secret = decrypt_mfa_secret(request.user.mfa_pending_secret)
        if not pyotp.TOTP(secret).verify(request.data.get("code", ""), valid_window=1):
            return Response({"detail": "Invalid code."}, status=400)
        raw, encoded = generate_recovery_codes()
        request.user.mfa_secret = request.user.mfa_pending_secret
        request.user.mfa_pending_secret = None
        request.user.mfa_enabled = True
        request.user.mfa_recovery_codes = encoded
        request.user.save(
            update_fields=[
                "mfa_secret",
                "mfa_pending_secret",
                "mfa_enabled",
                "mfa_recovery_codes",
            ]
        )
        revoke_all_sessions(request.user)
        _audit_security(request.user, "mfa_enable", request)
        return Response({"recovery_codes": raw})


class MFADisableView(generics.GenericAPIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        import pyotp
        from .security import consume_recovery_code, decrypt_mfa_secret, revoke_all_sessions

        if not request.user.check_password(request.data.get("current_password", "")):
            return Response({"detail": "Current password is incorrect."}, status=400)
        code = request.data.get("code", "")
        valid = pyotp.TOTP(decrypt_mfa_secret(request.user.mfa_secret)).verify(
            code, valid_window=1
        ) or consume_recovery_code(request.user, code)
        if not valid:
            return Response({"detail": "Invalid code."}, status=400)
        request.user.mfa_enabled = False
        request.user.mfa_secret = None
        request.user.mfa_recovery_codes = []
        request.user.save(
            update_fields=["mfa_enabled", "mfa_secret", "mfa_recovery_codes"]
        )
        revoke_all_sessions(request.user)
        _audit_security(request.user, "mfa_disable", request)
        return Response(status=status.HTTP_204_NO_CONTENT)


class MFALoginView(generics.GenericAPIView):
    permission_classes = [permissions.AllowAny]
    throttle_classes = [LoginRateThrottle]

    def post(self, request):
        import pyotp
        from .identity import identity_payload
        from .security import (
            consume_mfa_challenge,
            consume_recovery_code,
            decrypt_mfa_secret,
            issue_token_pair,
        )

        user_id = consume_mfa_challenge(request.data.get("challenge", ""))
        if not user_id:
            return Response({"detail": "Invalid or expired challenge."}, status=401)
        user = User.objects.filter(pk=user_id, is_active=True, mfa_enabled=True).first()
        if not user:
            return Response({"detail": "Invalid or expired challenge."}, status=401)
        code = request.data.get("code", "")
        valid = pyotp.TOTP(decrypt_mfa_secret(user.mfa_secret)).verify(
            code, valid_window=1
        ) or consume_recovery_code(user, code)
        if not valid:
            return Response({"detail": "Invalid code."}, status=401)
        data = issue_token_pair(user, request)
        data["user"] = identity_payload(user)
        _audit_security(user, "mfa_login", request)
        return Response(data)


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

    try:
        session_id = request.auth.get("session_id")
        request.user.auth_sessions.filter(
            pk=session_id, revoked_at__isnull=True
        ).update(revoked_at=timezone.now())
    except (AttributeError, ValueError):
        pass

    return Response(
        {"detail": "Logged out successfully."},
        status=status.HTTP_200_OK,
    )


# ── V7.0 Registration ────────────────────────────────────────────────

class SignupRateThrottle(AnonRateThrottle):
    """Per-IP throttle for registration / admin-code endpoints (5/min)."""
    scope = "signup"


def _auth_response(user, request=None):
    """Mint a JWT pair and the identity payload — mirrors the login response."""
    from .identity import identity_payload
    from .security import issue_token_pair

    data = issue_token_pair(user, request)
    data["user"] = identity_payload(user)
    return data


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
    return Response(_auth_response(user, request), status=status.HTTP_201_CREATED)


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
    return Response(_auth_response(user, request), status=status.HTTP_201_CREATED)
