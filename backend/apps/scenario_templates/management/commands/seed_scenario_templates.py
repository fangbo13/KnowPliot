# Copyright (c) 2026 Haibo Fang.
# Licensed under the CC BY-NC-SA 4.0 License.
# See LICENSE file in the project root for full license details.

from django.core.management.base import BaseCommand
from apps.scenario_templates.models import ScenarioTemplate


TEMPLATES_TO_SEED = [
    {
        "name": "New Hire Onboarding",
        "code": "new-hire-onboarding",
        "scenario_type": "onboarding",
        "description": "Template for onboarding new hires into the company or specific departments.",
        "icon": "user-add",
        "default_language": "en",
        "default_visibility": "private",
        "quick_questions": [
            "How do I set up my laptop and development environment?",
            "Where can I find the reimbursement and travel policies?",
            "Who do I contact for HR and payroll questions?",
            "What is the training curriculum for the first week?",
        ],
    },
    {
        "name": "Audit Methodology Q&A",
        "code": "audit-methodology-qa",
        "scenario_type": "audit",
        "description": "Query audit methodology manuals, guidelines, and compliance standards.",
        "icon": "audit",
        "default_language": "en",
        "default_visibility": "business_line",
        "quick_questions": [
            "What are the documentation standards for controls testing?",
            "How do we define sample sizes under the new audit policy?",
            "What is the procedure for reporting audit exceptions?",
            "Where can I find the templates for working papers?",
        ],
    },
    {
        "name": "Tax Policy Assistant",
        "code": "tax-policy-assistant",
        "scenario_type": "tax",
        "description": "Ask tax policies, codes, and internal corporate tax guides.",
        "icon": "percentage",
        "default_language": "en",
        "default_visibility": "business_line",
        "quick_questions": [
            "What is the filing deadline for international corporate tax returns?",
            "What are the rules for R&D tax credit eligibility?",
            "How do we handle transfer pricing documentation?",
            "What is the current policy on VAT reclaim submissions?",
        ],
    },
    {
        "name": "Consulting Engagement Assistant",
        "code": "consulting-engagement",
        "scenario_type": "consulting",
        "description": "Accelerate consulting project kickoffs and client deliverables guidelines.",
        "icon": "project",
        "default_language": "en",
        "default_visibility": "private",
        "quick_questions": [
            "What is the standard format for project kickoff decks?",
            "Where do I find the consulting engagement proposal template?",
            "What are the client confidentiality and data protection rules?",
            "How do we log project hours and billing milestones?",
        ],
    },
    {
        "name": "Core Services Helpdesk",
        "code": "core-services-helpdesk",
        "scenario_type": "core_services",
        "description": "Helpdesk assistant for corporate IT, facilities, and internal services.",
        "icon": "customer-service",
        "default_language": "en",
        "default_visibility": "organization",
        "quick_questions": [
            "How do I request access to internal file shares?",
            "What is the guest Wi-Fi policy and passcode?",
            "How do I book a conference room in the main office?",
            "Who do I contact for office supplies and logistics?",
        ],
    },
]


class Command(BaseCommand):
    help = "Seed Scenario Templates idempotently"

    def handle(self, *args, **options):
        self.stdout.write("Seeding Scenario Templates...")
        
        for t_data in TEMPLATES_TO_SEED:
            template, created = ScenarioTemplate.objects.get_or_create(
                code=t_data["code"],
                defaults={
                    "name": t_data["name"],
                    "scenario_type": t_data["scenario_type"],
                    "description": t_data["description"],
                    "icon": t_data["icon"],
                    "default_language": t_data["default_language"],
                    "default_visibility": t_data["default_visibility"],
                    "quick_questions": t_data["quick_questions"],
                    "prompt_policy": {},
                    "retrieval_policy": {},
                    "is_active": True,
                }
            )
            
            status_str = "Created" if created else "Skipped (exists)"
            self.stdout.write(f"  - {template.name} ({template.code}): {status_str}")
            
        self.stdout.write(self.style.SUCCESS("Seeding complete!"))
