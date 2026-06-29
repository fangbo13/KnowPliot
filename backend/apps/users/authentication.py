"""Custom JWT authentication that checks the blacklist table.

SYS-V4.2-020: The default JWTAuthentication only validates signature + expiry,
completely ignoring the blacklisted_tokens table. This means that after a user
calls /auth/logout/ (which blacklists both access and refresh tokens), the
access token remains valid for its full 15-minute lifetime.

This class extends JWTAuthentication.authenticate() to also check whether the
token's JTI has been blacklisted. If so, it raises AuthenticationFailed,
causing DRF to return 401 Unauthorized — which is the expected behavior.
"""

from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework_simplejwt.token_blacklist.models import BlacklistedToken
from rest_framework.exceptions import AuthenticationFailed


class BlacklistCheckingJWTAuthentication(JWTAuthentication):
    """
    V4.2 SYS-V4.2-020: JWT authentication that rejects blacklisted tokens.

    The default simplejwt JWTAuthentication.authenticate() flow:
      1. Decode JWT, verify signature and exp claim
      2. Look up user in outstanding_tokens table
      3. **Completely ignore blacklisted_tokens table** ← this is the bug

    This class adds step 3: after successful signature/expiry validation,
    check if the token's JTI has a corresponding BlacklistedToken entry.
    If yes, raise AuthenticationFailed so DRF returns 401.

    This ensures that after /auth/logout/ blacklists an access token,
    any subsequent API call using that token is immediately rejected,
    instead of remaining valid for the token's 15-minute lifetime.
    """

    def authenticate(self, request):
        result = super().authenticate(request)
        if result is None:
            # No token provided → skip (allows anonymous access where permitted)
            return None

        user, validated_token = result

        # V4.2 SYS-V4.2-020: Check blacklist for this token's JTI
        # FIX-001: Use single-step query matching SimpleJWT's check_blacklist() pattern.
        # Previously used two-step query (OutstandingToken first → BlacklistedToken second)
        # which would silently skip the blacklist check if OutstandingToken entry was missing.
        # Now uses FK traversal: BlacklistedToken.token__jti, which is both more robust
        # and more efficient (single DB query instead of two).
        jti = validated_token.get("jti")
        if jti and BlacklistedToken.objects.filter(token__jti=jti).exists():
            raise AuthenticationFailed("Token has been blacklisted.")

        return result
