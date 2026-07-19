"""Bounded configuration/readiness truth without secret-bearing diagnostics."""

from __future__ import annotations

import hashlib
import json
import os
import re
import uuid

from django.conf import settings
from django.core.exceptions import FieldDoesNotExist
from django.db import connection
from django.db.models import Q
from django.db.migrations.executor import MigrationExecutor
from django.utils import timezone
from django.utils.module_loading import import_string

from apps.spaces.generation_policy import (
    CANONICAL_DEEP_MODEL,
    CANONICAL_FAST_MODEL,
)
from apps.spaces.models import (
    GovernancePolicy,
    ModelProfile,
    WorkspaceCreationPolicy,
)

_SAFE_REVISION = re.compile(r"^[A-Za-z0-9._-]{1,64}$")


def _bounded_revision(value: object, default: str = "unknown") -> str:
    candidate = str(value or "").strip()
    return candidate if _SAFE_REVISION.fullmatch(candidate) else default


def _configuration_revision() -> str:
    values = {
        "capability_nav": bool(getattr(settings, "CAPABILITY_NAV", False)),
        "chat_stream_v2": bool(getattr(settings, "CHAT_STREAM_V2", False)),
        "deep": bool(getattr(settings, "DEEP_ANSWER_MODE", False)),
        "thinking": bool(getattr(settings, "THINKING_MODE", False)),
        "creation": bool(getattr(settings, "WORKSPACE_CREATION_APPROVAL", False)),
        "template_asset_copy": bool(
            getattr(settings, "TEMPLATE_ASSET_COPY_ENABLED", False)
        ),
        "join": bool(getattr(settings, "WORKSPACE_JOIN_V2", False)),
        "delete": bool(getattr(settings, "WORKSPACE_PERMANENT_DELETE", False)),
    }
    encoded = json.dumps(values, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()[:16]


def _database_state() -> str:
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            cursor.fetchone()
    except Exception:
        return "not_ready"
    return "ok"


def _migration_state() -> str:
    try:
        executor = MigrationExecutor(connection)
        targets = executor.loader.graph.leaf_nodes()
        return "ok" if not executor.migration_plan(targets) else "not_ready"
    except Exception:
        return "not_ready"


def _model_policy_details() -> tuple[str, dict]:
    aliases_match = all(
        getattr(settings, name, CANONICAL_FAST_MODEL) == CANONICAL_FAST_MODEL
        for name in ("QWEN_CHAT_MODEL", "RAG_LLM_MODEL")
    )
    try:
        fast = (
            ModelProfile.objects.filter(enabled=True, model_id=CANONICAL_FAST_MODEL)
            .order_by("pk")
            .first()
        )
        deep = (
            ModelProfile.objects.filter(enabled=True, model_id=CANONICAL_DEEP_MODEL)
            .order_by("pk")
            .first()
        )
        matching_revisions = []
        if fast is not None and deep is not None:
            for policy in GovernancePolicy.objects.only("id", "revision", "values"):
                if (
                    policy.values.get("fast_model_profile_id") == str(fast.id)
                    and policy.values.get("deep_model_profile_id") == str(deep.id)
                ):
                    matching_revisions.append(policy.revision)
        ready = bool(fast and deep and matching_revisions and aliases_match)
    except Exception:
        fast = deep = None
        matching_revisions = []
        ready = False

    details = {
        "expected_models": {
            "fast": CANONICAL_FAST_MODEL,
            "deep": CANONICAL_DEEP_MODEL,
        },
        "effective_models": {
            "fast": fast.model_id if fast else None,
            "deep": deep.model_id if deep else None,
        },
        "profile_ids": {
            "fast": str(fast.id) if fast else None,
            "deep": str(deep.id) if deep else None,
        },
        "policy_revisions": sorted(set(matching_revisions)),
        "legacy_alias_matches": aliases_match,
    }
    return ("ok" if ready else "not_ready"), details


def _worker_count() -> int:
    try:
        return max(1, int(os.environ.get("GUNICORN_WORKERS", "1")))
    except ValueError:
        return 1


def _worker_bucket(count: int) -> str:
    if count <= 1:
        return "1"
    if count <= 4:
        return "2-4"
    return "5+"


def _cache_kind() -> str:
    backend = settings.CACHES.get("default", {}).get("BACKEND", "")
    return "process_local" if "locmem" in backend.lower() else "shared"


def _creation_reviewer_state() -> str:
    """Require two distinct active platform reviewers before beta enablement."""

    try:
        from apps.spaces.governed import eligible_platform_reviewers

        reviewer_ids = eligible_platform_reviewers().values_list("pk", flat=True)
        return "ok" if reviewer_ids.order_by().distinct().count() >= 2 else "not_ready"
    except Exception:
        return "not_ready"


def _creation_policy_state() -> str:
    """Resolve an effective, explicitly beta-safe creation-policy revision."""

    now = timezone.now()
    try:
        ready = (
            WorkspaceCreationPolicy.objects.filter(
                status=WorkspaceCreationPolicy.STATUS_ACTIVE,
                audience=WorkspaceCreationPolicy.AUDIENCE_REGISTERED_BETA,
                review_route=WorkspaceCreationPolicy.ROUTE_PLATFORM,
                reviewer_separation_required=True,
                business_line__status="active",
                business_line__organization__status="active",
            )
            .filter(Q(effective_from__isnull=True) | Q(effective_from__lte=now))
            .filter(Q(effective_until__isnull=True) | Q(effective_until__gte=now))
            .exists()
        )
    except Exception:
        ready = False
    return "ok" if ready else "not_ready"


def _configured_secret(value: object) -> bool:
    """Recognize configured secret material without returning or logging it."""

    candidate = str(value or "").strip()
    return len(candidate.encode("utf-8")) >= 32 and "replace-with" not in candidate.lower()


def _join_contract_details() -> tuple[str, dict[str, bool]]:
    """Validate join credential rotation and invitation encryption inputs."""

    try:
        raw_peppers = getattr(settings, "SPACE_CREDENTIAL_PEPPERS", {}) or {}
        peppers = {
            int(version): secret
            for version, secret in raw_peppers.items()
            if int(version) >= 1 and _configured_secret(secret)
        }
        current = int(getattr(settings, "SPACE_CREDENTIAL_PEPPER_VERSION", 0))
        pepper_set_configured = bool(peppers)
        current_pepper_configured = current in peppers
    except (TypeError, ValueError, AttributeError):
        pepper_set_configured = False
        current_pepper_configured = False
    invitation_encryption_configured = _configured_secret(
        getattr(settings, "SPACE_INVITATION_ENCRYPTION_KEY", "")
    )
    try:
        delivery_adapter = import_string(
            str(getattr(settings, "ACTION_OUTBOX_DELIVERY_ADAPTER", "") or "").strip()
        )
        delivery_adapter_configured = callable(delivery_adapter)
    except (ImportError, AttributeError, ValueError):
        delivery_adapter_configured = False
    details = {
        "credential_pepper_set_configured": pepper_set_configured,
        "credential_current_version_configured": current_pepper_configured,
        "invitation_encryption_configured": invitation_encryption_configured,
        "external_delivery_adapter_configured": delivery_adapter_configured,
    }
    return (
        "ok" if all(details.values()) else "not_ready",
        details,
    )


def _template_clone_details() -> tuple[str, dict[str, bool]]:
    """Fail closed on the legacy asset-copy switch or surviving asset rows."""

    configured = bool(getattr(settings, "TEMPLATE_ASSET_COPY_ENABLED", False))
    try:
        from apps.scenario_templates.models import (
            ScenarioTemplateAsset,
            TemplateAssetApplication,
        )

        historical_rows = (
            ScenarioTemplateAsset.objects.exists()
            or TemplateAssetApplication.objects.exists()
        )
    except Exception:
        historical_rows = True
    details = {
        "template_asset_copy_enabled": configured,
        "template_historical_assets_present": historical_rows,
    }
    return ("not_ready" if any(details.values()) else "ok"), details


def _purge_registry_details() -> tuple[str, dict[str, object]]:
    """Consult the migration-owned dependency oracle without leaking its rows."""

    try:
        from apps.spaces.deletion_registry import audit_purge_registry

        audit = audit_purge_registry()
        ready = bool(audit.ready)
        code = str(audit.code)
    except Exception:
        ready = False
        code = "purge_registry_unavailable"
    return ("ok" if ready else "not_ready"), {
        "purge_registry_ready": ready,
        "purge_registry_code": code,
    }


def _expired_test_principal_count() -> int | None:
    from django.contrib.auth import get_user_model

    User = get_user_model()
    try:
        User._meta.get_field("account_purpose")
        User._meta.get_field("test_principal_expires_at")
    except FieldDoesNotExist:
        return None
    approved_legacy_ids = []
    for value in getattr(settings, "TEST_PRINCIPAL_LEGACY_ALLOWLIST", ()):
        try:
            approved_legacy_ids.append(uuid.UUID(str(value)))
        except (TypeError, ValueError, AttributeError):
            continue
    return (
        User.objects.filter(is_active=True)
        .filter(
            Q(
                account_purpose="test",
                test_principal_expires_at__lt=timezone.now(),
            )
            | Q(id__in=approved_legacy_ids)
        )
        .distinct()
        .count()
    )


def _paired_rollout_state() -> dict:
    def frontend_flag(name: str) -> bool:
        return os.environ.get(name, "false").strip().lower() in {
            "1",
            "true",
            "yes",
            "on",
        }

    return {
        "capability_nav": {
            "backend": bool(getattr(settings, "CAPABILITY_NAV", False)),
            "frontend": frontend_flag("VITE_CAPABILITY_NAV"),
        },
        "deep": {
            "backend": bool(getattr(settings, "DEEP_ANSWER_MODE", False)),
            "frontend": frontend_flag("VITE_DEEP_ANSWER_MODE"),
        },
        "thinking": {
            "backend": bool(getattr(settings, "THINKING_MODE", False)),
            "frontend": frontend_flag("VITE_THINKING_MODE"),
        },
        "creation": {
            "backend": bool(
                getattr(settings, "WORKSPACE_CREATION_APPROVAL", False)
            ),
            "frontend": frontend_flag("VITE_WORKSPACE_CREATION_APPROVAL"),
        },
        "join": {
            "backend": bool(getattr(settings, "WORKSPACE_JOIN_V2", False)),
            "frontend": frontend_flag("VITE_WORKSPACE_JOIN_V2"),
        },
        "delete": {
            "backend": bool(
                getattr(settings, "WORKSPACE_PERMANENT_DELETE", False)
            ),
            "frontend": frontend_flag("VITE_WORKSPACE_PERMANENT_DELETE"),
        },
    }


def collect_readiness() -> dict:
    canonical_state, model_details = _model_policy_details()
    cache_kind = _cache_kind()
    creation_enabled = bool(getattr(settings, "WORKSPACE_CREATION_APPROVAL", False))
    join_enabled = bool(getattr(settings, "WORKSPACE_JOIN_V2", False))
    delete_enabled = bool(getattr(settings, "WORKSPACE_PERMANENT_DELETE", False))
    reviewer_state = _creation_reviewer_state() if creation_enabled else "disabled"
    policy_state = _creation_policy_state() if creation_enabled else "disabled"
    join_state, join_details = _join_contract_details()
    template_state, template_details = _template_clone_details()
    purge_state, purge_details = _purge_registry_details()
    checks = {
        "database": _database_state(),
        "migrations": _migration_state(),
        "canonical_models": canonical_state,
        "creation_reviewers": reviewer_state,
        "creation_policy": policy_state,
        "join_credentials": join_state if join_enabled else "disabled",
        "template_clone_contract": template_state,
        "shared_rate_limit": "ok" if cache_kind == "shared" else "not_ready",
        "purge_registry": purge_state if delete_enabled else "disabled",
    }
    status_value = "not_ready" if "not_ready" in checks.values() else "ready"
    workers = _worker_count()
    return {
        "status": status_value,
        "build_revision": _bounded_revision(
            getattr(settings, "BUILD_REVISION", os.environ.get("BUILD_REVISION"))
        ),
        "configuration_revision": _configuration_revision(),
        "checks": checks,
        "details": {
            **model_details,
            "rollout": _paired_rollout_state(),
            "cache_backend_kind": cache_kind,
            "worker_count_bucket": _worker_bucket(workers),
            "expired_test_principal_count": _expired_test_principal_count(),
            **join_details,
            **template_details,
            **purge_details,
        },
    }
