import base64
import hashlib
import secrets
from datetime import datetime, timezone as dt_timezone

from cryptography.fernet import Fernet
from django.conf import settings
from django.contrib.auth.hashers import check_password, make_password
from django.core.cache import cache
from django.utils import timezone
from rest_framework_simplejwt.tokens import RefreshToken

from .models import AuthSession


def _fernet():
    configured = getattr(settings, "MFA_ENCRYPTION_KEY", "") or settings.SECRET_KEY
    digest = hashlib.sha256(configured.encode("utf-8")).digest()
    return Fernet(base64.urlsafe_b64encode(digest))


def encrypt_mfa_secret(secret):
    return _fernet().encrypt(secret.encode("ascii"))


def decrypt_mfa_secret(ciphertext):
    return _fernet().decrypt(bytes(ciphertext)).decode("ascii")


def issue_token_pair(user, request=None):
    refresh = RefreshToken.for_user(user)
    expires_at = datetime.fromtimestamp(refresh["exp"], tz=dt_timezone.utc)
    session = AuthSession.objects.create(
        user=user,
        refresh_jti=refresh["jti"],
        expires_at=expires_at,
        ip_address=request.META.get("REMOTE_ADDR") if request else None,
        user_agent=(request.META.get("HTTP_USER_AGENT", "")[:500] if request else ""),
    )
    refresh["session_id"] = str(session.id)
    access = refresh.access_token
    access["session_id"] = str(session.id)
    return {"refresh": str(refresh), "access": str(access)}


def revoke_all_sessions(user):
    user.auth_sessions.filter(revoked_at__isnull=True).update(revoked_at=timezone.now())


def generate_recovery_codes(count=10):
    raw = [f"{secrets.token_hex(4)}-{secrets.token_hex(4)}" for _ in range(count)]
    return raw, [make_password(value) for value in raw]


def consume_recovery_code(user, candidate):
    for index, encoded in enumerate(user.mfa_recovery_codes):
        if check_password(candidate, encoded):
            remaining = list(user.mfa_recovery_codes)
            remaining.pop(index)
            user.mfa_recovery_codes = remaining
            user.save(update_fields=["mfa_recovery_codes"])
            return True
    return False


def create_mfa_challenge(user):
    challenge = secrets.token_urlsafe(32)
    cache.set(f"mfa-challenge:{challenge}", str(user.id), timeout=300)
    return challenge


def consume_mfa_challenge(challenge):
    key = f"mfa-challenge:{challenge}"
    user_id = cache.get(key)
    if user_id:
        cache.delete(key)
    return user_id
