"""Authorization-first workspace discovery and privacy-minimal usage helpers."""

from __future__ import annotations

import base64
import json
import unicodedata
import uuid
from datetime import UTC, timedelta

from django.db import transaction
from django.db.models import Count, Q
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from .governed import digest_payload
from .models import (
    KnowledgeSpace,
    SpaceAccessRequest,
    SpaceMembership,
    WorkspaceUsageDaily,
    WorkspaceUsageSummary,
)
from .permissions import effective_space_memberships


def _parse_uuid(value, field):
    if value in (None, ""):
        return None
    try:
        return uuid.UUID(str(value))
    except (TypeError, ValueError, AttributeError) as exc:
        raise ValidationError({field: "Must be a UUID."}) from exc


def _normalized_query(value):
    if value in (None, ""):
        return ""
    if not isinstance(value, str):
        raise ValidationError({"q": "Must be a string."})
    query = unicodedata.normalize("NFC", value).strip()
    if not 1 <= len(query) <= 100:
        raise ValidationError({"q": "Must contain 1 to 100 characters."})
    return query


def _scope_sets(user):
    memberships = effective_space_memberships(user)
    business_line_ids = set(
        memberships.exclude(space__business_line_id=None).values_list(
            "space__business_line_id", flat=True
        )
    )
    # Spec §1: the user's registered business line grants discovery of that
    # line's spaces even before joining any of them.
    registered_bl_id = getattr(user, "business_line_id", None)
    if registered_bl_id:
        business_line_ids.add(registered_bl_id)
    return (
        set(memberships.values_list("space__organization_id", flat=True)),
        business_line_ids,
        set(memberships.values_list("space_id", flat=True)),
    )


def _invited_space_ids(user):
    """Resolve live targeted invitations when join-v2 is installed."""

    try:
        from .models import SpaceInvitation

        now = timezone.now()
        return set(
            SpaceInvitation.objects.filter(
                status="pending",
                expires_at__gte=now,
                target_user=user,
            )
            .values_list("space_id", flat=True)
        )
    except (ImportError, AttributeError):
        return set()


def authorized_discovery_queryset(user):
    """Apply authorization before any text/filter/rank operation."""

    organization_ids, business_line_ids, member_ids = _scope_sets(user)
    pending_ids = set(
        SpaceAccessRequest.objects.filter(user=user, status="pending").values_list(
            "space_id", flat=True
        )
    )
    invited_ids = _invited_space_ids(user)
    # Spec §1 discovery-layer isolation: globally joinable spaces that declare
    # business_line visibility are only discoverable by same-line users.
    # Memberships/invitations/access codes remain the cross-line escape hatch.
    global_visible = Q(join_policy="global") & ~Q(visibility="business_line")
    if business_line_ids:
        global_visible |= Q(
            join_policy="global",
            visibility="business_line",
            business_line_id__in=business_line_ids,
        )
    visible = (
        Q(id__in=member_ids)
        | Q(id__in=pending_ids)
        | Q(id__in=invited_ids)
        | Q(visibility="public_demo")
        | global_visible
    )
    if organization_ids:
        visible |= Q(visibility="organization", organization_id__in=organization_ids)
    if business_line_ids:
        visible |= Q(visibility="business_line", business_line_id__in=business_line_ids)
    return (
        KnowledgeSpace.objects.filter(
            status="active",
            organization__status="active",
        )
        .filter(visible)
        .select_related("organization", "business_line", "work_group")
        .prefetch_related("office_locations")
        .distinct()
    )


def _access_state(user, space, *, member_ids, invited_ids, pending_ids):
    if space.id in member_ids:
        return "member"
    if space.id in invited_ids:
        return "invited"
    if space.id in pending_ids:
        return "pending"
    return "requestable"


def _card(space, access_state, *, popularity_bucket=None):
    locations = [
        {"id": str(location.id), "code": location.normalized_code, "display_name": location.display_name}
        for location in space.office_locations.all()
    ]
    card = {
        "id": str(space.id),
        "name": space.name,
        "code": space.code,
        "purpose": (space.description or "")[:280],
        "visibility": space.visibility,
        "join_policy": space.join_policy,
        "classification_state": space.classification_state,
        "business_line": (
            {"id": str(space.business_line_id), "code": space.business_line.code, "display_name": space.business_line.name}
            if space.business_line_id
            else None
        ),
        "work_group": (
            {"id": str(space.work_group_id), "code": space.work_group.normalized_code, "display_name": space.work_group.display_name}
            if space.work_group_id
            else None
        ),
        "office_locations": locations,
        "access_state": access_state,
        "allowed_action": {
            "member": "open",
            "invited": "review_invitation",
            "pending": "view_request",
            "requestable": "global_join" if space.join_policy == "global" else "request_access",
        }[access_state],
    }
    if popularity_bucket is not None:
        card["activity_bucket"] = popularity_bucket
    return card


def _cursor_signature(params):
    return digest_payload({key: params[key] for key in sorted(params) if key != "cursor"})[:24]


def _decode_cursor(cursor, signature):
    if not cursor:
        return 0
    try:
        padding = "=" * (-len(cursor) % 4)
        data = json.loads(base64.urlsafe_b64decode(cursor + padding).decode("utf-8"))
        if data != {"v": 1, "s": signature, "o": int(data["o"])}:
            raise ValueError
        if data["o"] < 0:
            raise ValueError
        return data["o"]
    except (ValueError, TypeError, KeyError, json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise ValidationError({"cursor": "invalid_cursor"}) from exc


def _encode_cursor(offset, signature):
    raw = json.dumps({"v": 1, "s": signature, "o": offset}, separators=(",", ":")).encode("utf-8")
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def discover(user, params):
    queryset = authorized_discovery_queryset(user)
    query = _normalized_query(params.get("q"))
    business_line_id = _parse_uuid(params.get("business_line_id"), "business_line_id")
    work_group_id = _parse_uuid(params.get("work_group_id"), "work_group_id")
    office_values = params.get("office_location_ids") or params.get("office_location_id") or []
    if isinstance(office_values, str):
        office_values = [office_values]
    office_ids = [_parse_uuid(value, "office_location_id") for value in office_values]
    access_filter = params.get("access_state") or ""
    if access_filter and access_filter not in {"member", "invited", "pending", "requestable"}:
        raise ValidationError({"access_state": "Unsupported access state."})
    sort = params.get("sort") or "name"
    if sort not in {"name", "recent", "popular"}:
        raise ValidationError({"sort": "Unsupported sort."})

    # Well-formed but invisible/unknown facet IDs deliberately return an empty
    # page rather than a different validation response or leaked label.
    if business_line_id and not queryset.filter(business_line_id=business_line_id).exists():
        queryset = queryset.none()
    elif business_line_id:
        queryset = queryset.filter(business_line_id=business_line_id)
    if work_group_id and not queryset.filter(work_group_id=work_group_id).exists():
        queryset = queryset.none()
    elif work_group_id:
        queryset = queryset.filter(work_group_id=work_group_id)
    if office_ids:
        if any(not queryset.filter(office_locations__id=office_id).exists() for office_id in office_ids):
            queryset = queryset.none()
        else:
            queryset = queryset.filter(office_locations__id__in=office_ids)
    if query:
        queryset = queryset.filter(
            Q(name__icontains=query)
            | Q(code__icontains=query)
            | Q(description__icontains=query)
            | Q(business_line__name__icontains=query)
            | Q(business_line__code__icontains=query)
            | Q(work_group__display_name__icontains=query)
            | Q(work_group__normalized_code__icontains=query)
            | Q(office_locations__display_name__icontains=query)
            | Q(office_locations__normalized_code__icontains=query)
        ).distinct()

    now = timezone.now()
    popularity = {}
    if sort == "popular":
        queryset = queryset.annotate(
            visible_active_users=Count(
                "usage_daily__user",
                filter=Q(
                    usage_daily__date__gte=(now - timedelta(days=30)).date(),
                    usage_daily__user__is_active=True,
                ),
                distinct=True,
            )
        ).filter(visible_active_users__gte=5).order_by("-visible_active_users", "name", "id")
    elif sort == "recent":
        queryset = queryset.order_by("-updated_at", "name", "id")
    else:
        queryset = queryset.order_by("name", "id")

    member_ids = set(effective_space_memberships(user).values_list("space_id", flat=True))
    invited_ids = _invited_space_ids(user)
    pending_ids = set(SpaceAccessRequest.objects.filter(user=user, status="pending").values_list("space_id", flat=True))
    rows = list(queryset)
    if access_filter:
        rows = [
            row
            for row in rows
            if _access_state(user, row, member_ids=member_ids, invited_ids=invited_ids, pending_ids=pending_ids)
            == access_filter
        ]
    normalized_params = {
        "q": query,
        "business_line_id": str(business_line_id or ""),
        "work_group_id": str(work_group_id or ""),
        "office_location_ids": sorted(str(value) for value in office_ids),
        "access_state": access_filter,
        "sort": sort,
    }
    signature = _cursor_signature(normalized_params)
    offset = _decode_cursor(params.get("cursor"), signature)
    page_size = 20
    page = rows[offset : offset + page_size]
    cards = []
    for row in page:
        count = getattr(row, "visible_active_users", None)
        bucket = None
        if count is not None:
            bucket = "5-9" if count < 10 else "10-24" if count < 25 else "25-49" if count < 50 else "50+"
        cards.append(
            _card(
                row,
                _access_state(user, row, member_ids=member_ids, invited_ids=invited_ids, pending_ids=pending_ids),
                popularity_bucket=bucket,
            )
        )
    next_offset = offset + len(page)
    return {
        "results": cards,
        "next_cursor": _encode_cursor(next_offset, signature) if next_offset < len(rows) else None,
    }


def highlights(user):
    accessible = set(effective_space_memberships(user).values_list("space_id", flat=True))
    summaries = (
        WorkspaceUsageSummary.objects.filter(user=user, space_id__in=accessible)
        .select_related("space", "space__organization", "space__business_line", "space__work_group")
        .prefetch_related("space__office_locations")
        .order_by("-interaction_count_30d", "-last_interacted_at", "space_id")[:5]
    )
    frequent = [_card(item.space, "member") for item in summaries]
    popular_page = discover(user, {"sort": "popular"})
    return {"frequent": frequent, "popular": popular_page["results"][:5]}


def record_authorized_usage(*, user, space, count=1, occurred_at=None):
    """Increment one private UTC-day bucket and its 30-day summary."""

    occurred_at = occurred_at or timezone.now()
    day = (
        occurred_at.astimezone(UTC).date()
        if timezone.is_aware(occurred_at)
        else occurred_at.date()
    )
    with transaction.atomic():
        daily, _ = WorkspaceUsageDaily.objects.select_for_update().get_or_create(
            user=user,
            space=space,
            date=day,
            defaults={"interaction_count": 0, "last_interacted_at": occurred_at},
        )
        daily.interaction_count += max(int(count), 0)
        daily.last_interacted_at = max(filter(None, [daily.last_interacted_at, occurred_at]))
        daily.save(update_fields=["interaction_count", "last_interacted_at"])
        cutoff = day - timedelta(days=29)
        aggregates = WorkspaceUsageDaily.objects.filter(
            user=user, space=space, date__gte=cutoff, date__lte=day
        ).aggregate(total=models.Sum("interaction_count"), last=models.Max("last_interacted_at"))
        WorkspaceUsageSummary.objects.update_or_create(
            user=user,
            space=space,
            defaults={
                "interaction_count_30d": aggregates["total"] or 0,
                "last_interacted_at": aggregates["last"],
                "computed_through": day,
            },
        )


# Imported lazily above in most paths; required for aggregate helpers.
from django.db import models  # noqa: E402


__all__ = [
    "authorized_discovery_queryset",
    "discover",
    "highlights",
    "record_authorized_usage",
]
