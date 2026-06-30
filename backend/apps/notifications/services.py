# Copyright (c) 2026 Haibo Fang.
# Licensed under the CC BY-NC-SA 4.0 License.
# See LICENSE file in the project root for full license details.

"""Notification services — V7.0.

Public API:
    notify(recipient, type, title, ...)   -> best-effort targeted message
    user_feed(user)                       -> merged feed (targeted + announcements)
    unread_count(user)                    -> int
    mark_read(user, item_id)              -> bool
    mark_all_read(user)                   -> int

Announcement audience matching reuses ``apps.spaces.permissions`` so the
notification layer never re-implements who-can-see-what.
"""

from __future__ import annotations

import logging

from django.db.models import Q
from django.utils import timezone

logger = logging.getLogger(__name__)


# ── Targeted notifications ───────────────────────────────────────────

def notify(recipient, type, title, body="", level="info", link="", metadata=None):
    """Create a targeted notification. Best-effort — never raises.

    Mirrors the ``_audit()`` pattern in apps.spaces.views: a delivery failure
    must not break the business action that triggered it.
    """
    try:
        from .models import Notification
        return Notification.objects.create(
            recipient=recipient,
            type=type,
            title=title,
            body=body or "",
            level=level or "info",
            link=link or "",
            metadata=metadata or {},
        )
    except Exception as exc:  # pragma: no cover - delivery is non-critical
        logger.warning("notify() failed for recipient=%s: %s", getattr(recipient, "id", None), exc)
        return None


def notify_many(recipients, type, title, **kwargs):
    """Fan a targeted notification out to an iterable of users."""
    out = []
    for r in recipients:
        n = notify(r, type, title, **kwargs)
        if n:
            out.append(n)
    return out


# ── Audience resolution for announcements ────────────────────────────

def _user_role_tags(user) -> set[str]:
    """Platform-role tags the user satisfies, for ``role`` audience matching."""
    tags = {"employee"}  # everyone is at least an employee for broadcast purposes
    try:
        from apps.spaces.permissions import is_platform_admin, admin_scope
        if is_platform_admin(user):
            tags.add("super_admin")
        org_ids, bl_ids = admin_scope(user)
        if org_ids:
            tags.add("org_admin")
        if bl_ids:
            tags.add("business_admin")
    except Exception as exc:  # pragma: no cover
        logger.warning("role tag resolution failed: %s", exc)
    return tags


def _user_scope_refs(user) -> tuple[set, set]:
    """(org slugs, business-line codes) the user can see — for org/BL audiences."""
    org_slugs: set = set()
    bl_codes: set = set()
    try:
        from apps.spaces.permissions import accessible_spaces
        spaces = accessible_spaces(user).select_related("organization", "business_line")
        for s in spaces:
            if s.organization_id and s.organization:
                org_slugs.add(s.organization.slug)
            if s.business_line_id and s.business_line:
                bl_codes.add(s.business_line.code)
    except Exception as exc:  # pragma: no cover
        logger.warning("scope ref resolution failed: %s", exc)
    return org_slugs, bl_codes


def matching_announcements(user):
    """Active announcements whose audience includes ``user`` (queryset)."""
    from .models import Announcement
    role_tags = _user_role_tags(user)
    org_slugs, bl_codes = _user_scope_refs(user)

    q = Q(audience=Announcement.AUDIENCE_ALL)
    if role_tags:
        q |= Q(audience=Announcement.AUDIENCE_ROLE, audience_ref__in=list(role_tags))
    if org_slugs:
        q |= Q(audience=Announcement.AUDIENCE_ORG, audience_ref__in=list(org_slugs))
    if bl_codes:
        q |= Q(audience=Announcement.AUDIENCE_BUSINESS_LINE, audience_ref__in=list(bl_codes))
    return Announcement.objects.filter(is_active=True).filter(q)


# ── Merged feed + counts ─────────────────────────────────────────────

def _dismissed_ids(user, announcements):
    from .models import AnnouncementDismissal
    return set(
        AnnouncementDismissal.objects.filter(
            user=user, announcement__in=announcements
        ).values_list("announcement_id", flat=True)
    )


def user_feed(user, limit=50):
    """Merged, time-sorted feed of targeted notifications + matching announcements."""
    from .models import Notification

    items = []
    for n in Notification.objects.filter(recipient=user)[:limit]:
        items.append({
            "id": str(n.id),
            "kind": "notification",
            "type": n.type,
            "title": n.title,
            "body": n.body,
            "level": n.level,
            "link": n.link,
            "version": "",
            "is_read": n.is_read,
            "created_at": n.created_at,
        })

    anns = list(matching_announcements(user)[:limit])
    dismissed = _dismissed_ids(user, anns)
    for a in anns:
        items.append({
            "id": str(a.id),
            "kind": "announcement",
            "type": "system_broadcast",
            "title": a.title,
            "body": a.body,
            "level": a.level,
            "link": "",
            "version": a.version,
            "is_read": a.id in dismissed,
            "created_at": a.published_at or a.created_at,
        })

    items.sort(key=lambda x: x["created_at"], reverse=True)
    # Normalise datetimes to ISO strings for JSON.
    for it in items:
        it["created_at"] = it["created_at"].isoformat() if it["created_at"] else None
    return items[:limit]


def unread_count(user) -> int:
    from .models import Notification
    targeted = Notification.objects.filter(recipient=user, is_read=False).count()
    anns = list(matching_announcements(user))
    dismissed = _dismissed_ids(user, anns)
    ann_unread = sum(1 for a in anns if a.id not in dismissed)
    return targeted + ann_unread


def mark_read(user, item_id) -> bool:
    """Mark a feed item read. Resolves targeted notification first, else announcement."""
    from .models import Notification, Announcement, AnnouncementDismissal

    n = Notification.objects.filter(recipient=user, id=item_id).first()
    if n is not None:
        if not n.is_read:
            n.is_read = True
            n.read_at = timezone.now()
            n.save(update_fields=["is_read", "read_at"])
        return True

    ann = Announcement.objects.filter(id=item_id, is_active=True).first()
    if ann is not None:
        AnnouncementDismissal.objects.get_or_create(user=user, announcement=ann)
        return True

    return False


def mark_all_read(user) -> int:
    """Mark every targeted notification read and dismiss all matching announcements."""
    from .models import Notification, AnnouncementDismissal

    count = Notification.objects.filter(recipient=user, is_read=False).update(
        is_read=True, read_at=timezone.now()
    )
    anns = list(matching_announcements(user))
    dismissed = _dismissed_ids(user, anns)
    new_dismissals = [
        AnnouncementDismissal(user=user, announcement=a)
        for a in anns if a.id not in dismissed
    ]
    if new_dismissals:
        AnnouncementDismissal.objects.bulk_create(new_dismissals, ignore_conflicts=True)
    return count + len(new_dismissals)
