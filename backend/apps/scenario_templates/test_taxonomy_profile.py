# Copyright (c) 2026 Haibo Fang.
# Licensed under the CC BY-NC-SA 4.0 License.
# See LICENSE file in the project root for full license details.

"""KB optimization spec §2.3 — template taxonomy_profile tests.

Covers contract validation of workspace_defaults.taxonomy_profile, snapshot
extraction, and the creation-flow default derivation (profile wins, scenario
type is the fallback).
"""

from django.core.exceptions import ValidationError
from django.test import TestCase

from apps.spaces.creation_services import _default_taxonomy_mode_for

from .contract import (
    legacy_template_components,
    revision_snapshot,
    taxonomy_profile_from_snapshot,
)


def _source(**overrides):
    base = {
        "name": "T",
        "code": "t",
        "scenario_type": "audit",
        "description": "",
        "icon": "audit",
        "default_language": "en",
        "default_visibility": "private",
        "quick_questions": [],
        "prompt_policy": {},
        "retrieval_policy": {},
        "tags": [],
        "category": None,
    }
    base.update(overrides)
    return base


class _FakeRevision:
    def __init__(self, snapshot, scenario_type="audit"):
        self.snapshot = snapshot
        self.template = type("T", (), {"scenario_type": scenario_type})()


class TaxonomyProfileContractTests(TestCase):
    def test_profile_round_trips_through_snapshot(self):
        snapshot = revision_snapshot(
            legacy_template_components(
                _source(taxonomy_profile={"mode": "none", "preset": None})
            )
        )
        profile = taxonomy_profile_from_snapshot(snapshot)
        self.assertEqual(profile, {"mode": "none", "preset": None})

    def test_profile_with_preset(self):
        snapshot = revision_snapshot(
            legacy_template_components(
                _source(taxonomy_profile={"mode": "default_seed", "preset": "audit_default"})
            )
        )
        profile = taxonomy_profile_from_snapshot(snapshot)
        self.assertEqual(profile, {"mode": "default_seed", "preset": "audit_default"})

    def test_missing_profile_returns_none(self):
        snapshot = revision_snapshot(legacy_template_components(_source()))
        self.assertIsNone(taxonomy_profile_from_snapshot(snapshot))

    def test_invalid_mode_rejected(self):
        with self.assertRaises(ValidationError):
            legacy_template_components(
                _source(taxonomy_profile={"mode": "everything"})
            )

    def test_unknown_profile_keys_rejected(self):
        with self.assertRaises(ValidationError):
            legacy_template_components(
                _source(taxonomy_profile={"mode": "none", "documents_hint": 1})
            )


class TaxonomyInitModeDerivationTests(TestCase):
    def test_no_template_defaults_to_custom(self):
        self.assertEqual(_default_taxonomy_mode_for(None), "custom")

    def test_profile_wins_over_scenario_type(self):
        snapshot = revision_snapshot(
            legacy_template_components(
                _source(taxonomy_profile={"mode": "none", "preset": None})
            )
        )
        revision = _FakeRevision(snapshot, scenario_type="audit")
        self.assertEqual(_default_taxonomy_mode_for(revision), "none")

    def test_scenario_type_fallback(self):
        snapshot = revision_snapshot(legacy_template_components(_source()))
        self.assertEqual(
            _default_taxonomy_mode_for(_FakeRevision(snapshot, "audit")), "default_seed"
        )
        self.assertEqual(
            _default_taxonomy_mode_for(_FakeRevision(snapshot, "enablement")), "none"
        )
        self.assertEqual(
            _default_taxonomy_mode_for(_FakeRevision(snapshot, "tax")), "custom"
        )
