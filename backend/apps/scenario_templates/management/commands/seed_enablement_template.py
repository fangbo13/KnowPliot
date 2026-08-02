# Copyright (c) 2026 Haibo Fang.
# Licensed under the CC BY-NC-SA 4.0 License.
# See LICENSE file in the project root for full license details.

"""KB optimization spec §2.3 — seed the Enablement Team scenario template.

Enablement (赋能) teams do not manage audit accounts, so the template's
scenario type maps to taxonomy_init_mode="none" during workspace creation
(see creation_services._default_taxonomy_mode_for).

Run after migrations:  python manage.py seed_enablement_template
Safe to re-run: existing records are skipped (get_or_create).
"""

from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from apps.scenario_templates.contract import legacy_template_components, revision_snapshot
from apps.scenario_templates.models import ScenarioTemplate, ScenarioTemplateRevision


ENABLEMENT_TEMPLATE = {
    "name": "赋能团队知识助手",
    "code": "enablement-team-assistant",
    "scenario_type": "enablement",
    "description": "面向赋能团队（培训/方法论/内部支持）的知识空间模板，无需会计科目体系。",
    "icon": "team",
    "default_language": "zh",
    "default_visibility": "private",
    "quick_questions": [
        "团队的培训材料和方法论文档在哪里？",
        "如何提交内部支持请求？",
        "最新的赋能项目进展是什么？",
        "有哪些可复用的项目模板和最佳实践？",
    ],
    # KB spec §2.3: enablement teams do not use the account taxonomy.
    "taxonomy_profile": {"mode": "none", "preset": None},
}


class Command(BaseCommand):
    help = "Seed the Enablement Team scenario template (KB optimization spec §2.3)."

    def handle(self, *args, **options):
        with transaction.atomic():
            template, created = ScenarioTemplate.objects.get_or_create(
                code=ENABLEMENT_TEMPLATE["code"],
                defaults={
                    "name": ENABLEMENT_TEMPLATE["name"],
                    "scenario_type": ENABLEMENT_TEMPLATE["scenario_type"],
                    "description": ENABLEMENT_TEMPLATE["description"],
                    "icon": ENABLEMENT_TEMPLATE["icon"],
                    "default_language": ENABLEMENT_TEMPLATE["default_language"],
                    "default_visibility": ENABLEMENT_TEMPLATE["default_visibility"],
                    "quick_questions": ENABLEMENT_TEMPLATE["quick_questions"],
                    "prompt_policy": {},
                    "retrieval_policy": {},
                    "is_active": True,
                },
            )
            if created:
                source = {
                    **ENABLEMENT_TEMPLATE,
                    "prompt_policy": {},
                    "retrieval_policy": {},
                    "tags": [],
                    "category": None,
                }
                revision = ScenarioTemplateRevision.objects.create(
                    template=template,
                    version=1,
                    snapshot=revision_snapshot(legacy_template_components(source)),
                    published_at=timezone.now(),
                    change_note="seeded enablement template",
                )
                template.current_revision = revision
                template.save(update_fields=["current_revision", "updated_at"])

        status_str = "Created" if created else "Skipped (exists)"
        self.stdout.write(
            self.style.SUCCESS(f"[OK] {template.name} ({template.code}): {status_str}")
        )
