# Copyright (c) 2026 Haibo Fang.
# Licensed under the CC BY-NC-SA 4.0 License.
# See LICENSE file in the project root for full license details.

"""Seed governed model profiles and the default governance policy.

Creates the two SPEC §7 model profiles (fast = qwen3.6-flash, deep = qwen3.7-plus)
and an organization-level `GovernancePolicy` revision that binds them, so the
RAG generation resolver no longer falls back to the `.env` `QWEN_CHAT_MODEL`
value and governed fast/deep resolution can be exercised locally.

Run after `seed_identity` (which creates the default organization)::

    python manage.py seed_models

Safe to re-run: existing profiles are skipped, and a new policy revision is
only created when the desired binding differs from the latest revision.

Note: deep execution additionally requires ``DEEP_ANSWER_MODE=true`` in the
environment and a backend restart — `generation_policy` gates deep on that
Django setting (this seed cannot flip it).
"""

from django.core.management.base import BaseCommand

from apps.spaces.models import (
    GovernancePolicy,
    KnowledgeSpace,
    ModelProfile,
    Organization,
    create_policy_revision,
)

FAST_PROFILE = {
    "name": "qwen3.6-flash",
    "provider": "dashscope",
    "model_id": "qwen3.6-flash",
}
DEEP_PROFILE = {
    "name": "qwen3.7-plus",
    "provider": "dashscope",
    "model_id": "qwen3.7-plus",
}
# SPEC §7: model tier and thinking are independent. Both governed budgets start
# at 1024, and thinking remains off unless each question explicitly requests it.
# retrieval_top_k mirrors the
# project default (RAG_TOP_K=8).
DESIRED_VALUES = {
    "fast_thinking_budget": 1024,
    "deep_thinking_budget": 1024,
    "retrieval_top_k": 8,
}


class Command(BaseCommand):
    help = "Seed governed ModelProfile rows and the default GovernancePolicy binding."

    def handle(self, *args, **options):
        out = self.stdout
        out.write("Seeding governed model profiles and policy...\n")

        org, created = Organization.objects.get_or_create(
            slug="default", defaults={"name": "KnowPilot Demo Org"}
        )
        out.write(f"  {'+' if created else '='} Organization: {org.name}")

        profiles = {}
        for cfg in (FAST_PROFILE, DEEP_PROFILE):
            profile, p_created = ModelProfile.objects.get_or_create(
                name=cfg["name"],
                defaults={
                    "provider": cfg["provider"],
                    "model_id": cfg["model_id"],
                    "enabled": True,
                },
            )
            # Keep provider/model_id/enabled in sync if the row pre-existed.
            updated = []
            for field in ("provider", "model_id", "enabled"):
                if getattr(profile, field) != cfg.get(field, True):
                    setattr(profile, field, cfg.get(field, True))
                    updated.append(field)
            if updated:
                profile.save(update_fields=updated)
            out.write(
                f"  {'+' if p_created else '='} ModelProfile: {profile.name} "
                f"({profile.provider}/{profile.model_id}, enabled={profile.enabled})"
            )
            profiles[profile.name] = profile

        fast = profiles[FAST_PROFILE["name"]]
        deep = profiles[DEEP_PROFILE["name"]]
        desired_values = dict(DESIRED_VALUES)
        desired_values["fast_model_profile_id"] = str(fast.id)
        desired_values["deep_model_profile_id"] = str(deep.id)

        latest = (
            GovernancePolicy.objects.filter(organization=org)
            .order_by("-revision", "-created_at")
            .first()
        )
        already_bound = (
            latest is not None
            and all(latest.values.get(key) == value for key, value in desired_values.items())
        )
        if already_bound:
            out.write(
                f"  = GovernancePolicy revision {latest.revision} already binds "
                f"fast={fast.name}, deep={deep.name} (skipped)"
            )
        else:
            policy = create_policy_revision(
                organization=org, values=desired_values
            )
            out.write(
                self.style.SUCCESS(
                    f"  + GovernancePolicy revision {policy.revision} created: "
                    f"fast={fast.name}, deep={deep.name}, "
                    f"thinking_budgets={desired_values['fast_thinking_budget']}/"
                    f"{desired_values['deep_thinking_budget']}, "
                    f"retrieval_top_k={desired_values['retrieval_top_k']}"
                )
            )

        out.write(
            self.style.WARNING(
                "\n  Note: deep execution also requires DEEP_ANSWER_MODE=true in the\n"
                "  environment and a backend restart (generation_policy gates deep on\n"
                "  that Django setting; this seed cannot flip it). Independent thinking\n"
                "  also requires THINKING_MODE=true. The legacy QWEN_CHAT_MODEL alias\n"
                "  must remain exactly qwen3.6-flash or readiness fails closed.\n"
            )
        )
        out.write(self.style.SUCCESS("\n[OK] seed_models complete."))
