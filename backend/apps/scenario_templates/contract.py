"""Deterministic, content-free scenario-template revision contract.

V3 templates are configuration snapshots only.  This module deliberately has
no dependency on workspace content models so revision creation cannot grow an
accidental document/chat/member copy path.
"""

from __future__ import annotations

import hashlib
import json
import unicodedata
from copy import deepcopy
from typing import Any

from django.core.exceptions import ValidationError


COMPONENT_KEYS = (
    "category_tree",
    "scenario_definitions",
    "quality_rubric",
    "workspace_defaults",
    "model_policy_refs",
)

EXCLUDED_COMPONENTS = (
    "documents",
    "chunks_and_indexes",
    "chats_and_history",
    "members_and_ownership",
    "invitations_and_access_codes",
    "audit_history",
    "secrets_and_api_credentials",
    "shares",
    "tasks",
    "retention_holds",
)

_FORBIDDEN_KEYS = frozenset(
    {
        "document",
        "documents",
        "document_ids",
        "file",
        "files",
        "file_url",
        "storage_path",
        "chunks",
        "chunk_ids",
        "indexes",
        "index_ids",
        "chat",
        "chats",
        "messages",
        "history",
        "members",
        "memberships",
        "owner",
        "ownership",
        "invitations",
        "access_codes",
        "audit",
        "audit_history",
        "secret",
        "secrets",
        "credentials",
        "api_credentials",
        "shares",
        "tasks",
        "task_ids",
        "retention_holds",
        "holds",
    }
)


def _normalize_json_strings(value: Any) -> Any:
    if isinstance(value, str):
        return unicodedata.normalize("NFC", value)
    if isinstance(value, list):
        return [_normalize_json_strings(item) for item in value]
    if isinstance(value, dict):
        normalized = {}
        for key, nested in value.items():
            normalized_key = unicodedata.normalize("NFC", str(key))
            if normalized_key in normalized:
                raise ValidationError(
                    {"components": "Unicode-normalized component keys must be unique."}
                )
            normalized[normalized_key] = _normalize_json_strings(nested)
        return normalized
    return value


def _reject_reserved_keys(value: Any, *, path: str = "components") -> None:
    if isinstance(value, dict):
        for key, nested in value.items():
            normalized = str(key).strip().lower().replace("-", "_")
            if normalized in _FORBIDDEN_KEYS:
                raise ValidationError(
                    {"components": f"{path}.{key} is excluded from template revisions."}
                )
            _reject_reserved_keys(nested, path=f"{path}.{key}")
    elif isinstance(value, list):
        for index, nested in enumerate(value):
            _reject_reserved_keys(nested, path=f"{path}[{index}]")


def normalize_components(value: Any) -> dict[str, Any]:
    """Validate the exact v3 component envelope and return a detached copy."""

    if not isinstance(value, dict):
        raise ValidationError({"components": "Must be an object."})
    unknown = sorted(set(value) - set(COMPONENT_KEYS))
    missing = sorted(set(COMPONENT_KEYS) - set(value))
    if unknown or missing:
        errors = []
        if unknown:
            errors.append(f"Unknown component keys: {', '.join(unknown)}.")
        if missing:
            errors.append(f"Missing component keys: {', '.join(missing)}.")
        raise ValidationError({"components": errors})

    expected_types = {
        "category_tree": list,
        "scenario_definitions": list,
        "quality_rubric": dict,
        "workspace_defaults": dict,
        "model_policy_refs": list,
    }
    for key, expected in expected_types.items():
        if not isinstance(value[key], expected):
            raise ValidationError(
                {"components": f"{key} must be a {expected.__name__}."}
            )

    components = _normalize_json_strings(
        {key: deepcopy(value[key]) for key in COMPONENT_KEYS}
    )
    _reject_reserved_keys(components)
    allowed_scenarios = {
        "onboarding",
        "audit",
        "tax",
        "consulting",
        "core_services",
        "standards_qa",
        "project_ai",
    }
    for index, scenario in enumerate(components["scenario_definitions"]):
        if not isinstance(scenario, dict):
            raise ValidationError(
                {"components": f"scenario_definitions[{index}] must be an object."}
            )
        scenario_type = scenario.get("scenario_type")
        if scenario_type is not None and scenario_type not in allowed_scenarios:
            raise ValidationError(
                {"components": f"scenario_definitions[{index}].scenario_type is unsupported."}
            )
        if "prompt_policy" in scenario and not isinstance(
            scenario["prompt_policy"], dict
        ):
            raise ValidationError(
                {"components": f"scenario_definitions[{index}].prompt_policy must be an object."}
            )
        questions = scenario.get("quick_questions")
        if questions is not None and (
            not isinstance(questions, list)
            or any(not isinstance(question, str) for question in questions)
        ):
            raise ValidationError(
                {"components": f"scenario_definitions[{index}].quick_questions must be a string array."}
            )

    defaults = components["workspace_defaults"]
    visibility = defaults.get("default_visibility")
    if visibility is not None and visibility not in {
        "private",
        "business_line",
        "organization",
        "public_demo",
    }:
        raise ValidationError(
            {"components": "workspace_defaults.default_visibility is unsupported."}
        )
    language = defaults.get("default_language")
    if language is not None and (
        not isinstance(language, str) or not 1 <= len(language) <= 32
    ):
        raise ValidationError(
            {"components": "workspace_defaults.default_language is invalid."}
        )
    if "retrieval_policy" in defaults and not isinstance(
        defaults["retrieval_policy"], dict
    ):
        raise ValidationError(
            {"components": "workspace_defaults.retrieval_policy must be an object."}
        )
    try:
        encoded = json.dumps(
            components,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )
    except (TypeError, ValueError) as exc:
        raise ValidationError({"components": "Must contain finite JSON values."}) from exc
    if len(encoded.encode("utf-8")) > 262_144:
        raise ValidationError({"components": "Serialized components exceed 256 KiB."})
    return components


def legacy_template_components(snapshot: Any) -> dict[str, Any]:
    """Project historical template metadata into the bounded v3 schema.

    Only configuration fields that existed on the template row are projected.
    Asset/application/content identifiers are intentionally ignored.
    """

    source = snapshot if isinstance(snapshot, dict) else {}
    category = source.get("category")
    category_tree = []
    if category:
        category_tree.append({"category_id": str(category)})

    scenario_definition = {
        "scenario_type": source.get("scenario_type", "onboarding"),
        "prompt_policy": deepcopy(source.get("prompt_policy") or {}),
        "quick_questions": deepcopy(source.get("quick_questions") or []),
    }
    workspace_defaults = {
        "default_language": source.get("default_language", "en"),
        "default_visibility": source.get("default_visibility", "private"),
        "retrieval_policy": deepcopy(source.get("retrieval_policy") or {}),
        "classification_tags": deepcopy(source.get("tags") or []),
    }
    return normalize_components(
        {
            "category_tree": category_tree,
            "scenario_definitions": [scenario_definition],
            "quality_rubric": {},
            "workspace_defaults": workspace_defaults,
            "model_policy_refs": [],
        }
    )


def revision_snapshot(components: Any) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "components": normalize_components(components),
    }


def normalize_revision_snapshot(snapshot: Any) -> dict[str, Any]:
    if (
        isinstance(snapshot, dict)
        and snapshot.get("schema_version") == 1
        and set(snapshot) == {"schema_version", "components"}
    ):
        return revision_snapshot(snapshot["components"])
    return revision_snapshot(legacy_template_components(snapshot))


def snapshot_hash(snapshot: Any) -> str:
    normalized = normalize_revision_snapshot(snapshot)
    encoded = json.dumps(
        normalized,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def preview_payload(revision) -> dict[str, Any]:
    snapshot = normalize_revision_snapshot(revision.snapshot)
    components = snapshot["components"]
    return {
        "id": str(revision.id),
        "template_id": str(revision.template_id),
        "version": revision.version,
        "snapshot_hash": revision.snapshot_hash,
        "published_at": revision.published_at,
        "included_components": [key for key in COMPONENT_KEYS if components[key]],
        "excluded_components": list(EXCLUDED_COMPONENTS),
        "components": components,
    }


def legacy_template_projection(snapshot: Any) -> dict[str, Any]:
    """Project an authoritative revision into legacy template columns.

    These columns remain compatibility/cache fields; the revision and its hash
    stay authoritative.  Only bounded configuration keys are projected.
    """

    components = normalize_revision_snapshot(snapshot)["components"]
    scenario = (
        components["scenario_definitions"][0]
        if components["scenario_definitions"]
        and isinstance(components["scenario_definitions"][0], dict)
        else {}
    )
    defaults = components["workspace_defaults"]
    projection = {}
    if isinstance(scenario.get("scenario_type"), str):
        projection["scenario_type"] = scenario["scenario_type"]
    if isinstance(scenario.get("prompt_policy"), dict):
        projection["prompt_policy"] = deepcopy(scenario["prompt_policy"])
    if isinstance(scenario.get("quick_questions"), list):
        projection["quick_questions"] = deepcopy(scenario["quick_questions"])
    if isinstance(defaults.get("default_language"), str):
        projection["default_language"] = defaults["default_language"]
    if isinstance(defaults.get("default_visibility"), str):
        projection["default_visibility"] = defaults["default_visibility"]
    if isinstance(defaults.get("retrieval_policy"), dict):
        projection["retrieval_policy"] = deepcopy(defaults["retrieval_policy"])
    return projection


__all__ = [
    "COMPONENT_KEYS",
    "EXCLUDED_COMPONENTS",
    "legacy_template_components",
    "legacy_template_projection",
    "normalize_components",
    "normalize_revision_snapshot",
    "preview_payload",
    "revision_snapshot",
    "snapshot_hash",
]
