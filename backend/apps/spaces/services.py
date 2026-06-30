# Copyright (c) 2026 Haibo Fang.
# Licensed under the CC BY-NC-SA 4.0 License.
# See LICENSE file in the project root for full license details.

"""Cross-app space services — V7.0.

Centralises the identity-provisioning logic the ``users`` app needs at
registration time, so the dependency direction stays clean (users -> spaces).

    hash_code            — SHA-256 of a code (shared with views._hash_code)
    generate_admin_code  — human-friendly admin code string
    redeem_admin_code    — consume an admin code, grant OrganizationMembership
    redeem_email_invites — turn pending SpaceEmailInvites into memberships
    join_default_space   — place a new user in their Service Line's default space
"""

from __future__ import annotations

import hashlib
import logging
import secrets

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from .models import (
    AdminRegistrationCode,
    KnowledgeSpace,
    OrganizationMembership,
    SpaceEmailInvite,
    SpaceMembership,
)

logger = logging.getLogger(__name__)

DEFAULT_SPACE_CODE = "general"


def hash_code(code: str) -> str:
    return hashlib.sha256(code.strip().encode("utf-8")).hexdigest()


def generate_admin_code(prefix: str = "ADM") -> str:
    """A human-friendly admin code: '<PREFIX>-<random>'."""
    return f"{prefix.upper()[:6]}-{secrets.token_urlsafe(8)}"


def redeem_admin_code(raw_code: str, user):
    """Validate + consume an admin code; grant OrganizationMembership.

    Returns ``(membership, code)`` on success, or ``(None, None)`` if the code is
    missing / invalid. Idempotent on the membership (get_or_create).
    """
    code = (
        AdminRegistrationCode.objects.filter(code_hash=hash_code(raw_code))
        .select_related("organization", "business_line")
        .first()
    )
    if code is None or not code.is_valid():
        return None, None

    business_line = (
        code.business_line
        if code.grants_role == OrganizationMembership.ROLE_BUSINESS_ADMIN
        else None
    )
    with transaction.atomic():
        membership, _ = OrganizationMembership.objects.get_or_create(
            user=user,
            organization=code.organization,
            business_line=business_line,
            role=code.grants_role,
        )
        AdminRegistrationCode.objects.filter(pk=code.pk).update(
            used_count=code.used_count + 1
        )
    return membership, code


def redeem_email_invites(user):
    """Materialise pending SpaceEmailInvites for this user's email.

    Returns a list of ``(space, role)`` granted. Called right after a user
    registers so admin-by-email invitations take effect automatically.
    """
    granted = []
    invites = (
        SpaceEmailInvite.objects.filter(email__iexact=user.email, status="pending")
        .select_related("space")
    )
    for inv in invites:
        if not inv.is_valid():
            continue
        membership, created = SpaceMembership.objects.get_or_create(
            space=inv.space,
            user=user,
            defaults={
                "role": inv.role,
                "status": "active",
                "invited_by": inv.invited_by,
                "last_accessed_at": timezone.now(),
            },
        )
        if not created:
            membership.role = inv.role
            membership.status = "active"
            membership.invited_by = inv.invited_by
            membership.last_accessed_at = timezone.now()
            membership.save(
                update_fields=[
                    "role",
                    "status",
                    "invited_by",
                    "last_accessed_at",
                    "updated_at",
                ]
            )
        inv.status = "accepted"
        inv.save(update_fields=["status"])
        granted.append((inv.space, inv.role))
    return granted


def join_default_space(user):
    """Place a new user in their Service Line's default space (or 'general').

    Returns the joined space, or None if no suitable space exists yet.
    """
    mapping = getattr(settings, "SERVICE_LINE_DEFAULT_SPACE", {}) or {}
    code = mapping.get(user.service_line) or DEFAULT_SPACE_CODE
    space = (
        KnowledgeSpace.objects.filter(code=code).first()
        or KnowledgeSpace.objects.filter(code=DEFAULT_SPACE_CODE).first()
    )
    if space is None:
        return None
    SpaceMembership.objects.get_or_create(
        space=space,
        user=user,
        defaults={
            "role": SpaceMembership.ROLE_MEMBER,
            "status": "active",
            "last_accessed_at": timezone.now(),
        },
    )
    return space
