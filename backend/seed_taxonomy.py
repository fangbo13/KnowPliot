"""Seed EY service-line business lines, EY China office locations,
default work groups, and workspace creation policies.

Run inside the backend container:
    python seed_taxonomy.py
"""
import os
import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.base")
django.setup()

from django.db import transaction
from apps.spaces.models import (
    BusinessLine,
    OfficeLocation,
    WorkGroup,
    WorkspaceCreationPolicy,
    Organization,
)

# ── Service-line definitions (mirror frontend SERVICE_LINES) ──────────
SERVICE_LINES = [
    ("assurance", "Assurance"),
    ("consulting", "Consulting"),
    ("tax", "Tax"),
    ("strategy_transactions", "Strategy & Transactions"),
    ("core", "Core Business Services"),
]

# ── EY China office locations (mirror frontend EY_OFFICE_LOCATIONS) ────
EY_OFFICES = [
    ("beijing", "北京"),
    ("shanghai", "上海"),
    ("guangzhou", "广州"),
    ("shenzhen", "深圳"),
    ("chengdu", "成都"),
    ("wuhan", "武汉"),
    ("hangzhou", "杭州"),
    ("nanjing", "南京"),
    ("qingdao", "青岛"),
    ("dalian", "大连"),
    ("xiamen", "厦门"),
    ("tianjin", "天津"),
    ("suzhou", "苏州"),
    ("xian", "西安"),
    ("chongqing", "重庆"),
    ("jinan", "济南"),
    ("shenyang", "沈阳"),
    ("changsha", "长沙"),
    ("zhengzhou", "郑州"),
    ("hefei", "合肥"),
    ("kunming", "昆明"),
    ("haikou", "海口"),
    ("hongkong", "香港"),
    ("macau", "澳门"),
]

# ── Default work group per business line ──────────────────────────────
DEFAULT_WORK_GROUP_CODE = "default"
DEFAULT_WORK_GROUP_NAME = "Default Team"


def run():
    org = Organization.objects.get(slug="ey-internal")
    print(f"Using organization: {org.name} (id={org.id})")

    with transaction.atomic():
        # 1) Create service-line business lines
        print("\n── Creating BusinessLines ──")
        created_lines = []
        for code, name in SERVICE_LINES:
            bl, created = BusinessLine.objects.get_or_create(
                organization=org,
                code=code,
                defaults={"name": name, "status": "active"},
            )
            tag = "NEW" if created else "EXISTS"
            print(f"  [{tag}] {bl.name} (code={bl.code}, id={bl.id})")
            created_lines.append(bl)

        # 2) Create office locations
        print("\n── Creating OfficeLocations ──")
        for idx, (code, name) in enumerate(EY_OFFICES):
            ol, created = OfficeLocation.objects.get_or_create(
                organization=org,
                normalized_code=code,
                defaults={"display_name": name, "active": True, "sort_order": idx},
            )
            tag = "NEW" if created else "EXISTS"
            print(f"  [{tag}] {ol.display_name} (code={ol.normalized_code}, id={ol.id})")

        # 3) Create default work group per business line
        print("\n── Creating WorkGroups ──")
        for bl in created_lines:
            wg, created = WorkGroup.objects.get_or_create(
                business_line=bl,
                normalized_code=DEFAULT_WORK_GROUP_CODE,
                defaults={"display_name": DEFAULT_WORK_GROUP_NAME, "active": True},
            )
            tag = "NEW" if created else "EXISTS"
            print(f"  [{tag}] {wg.display_name} under {bl.name} (code={wg.normalized_code}, id={wg.id})")

        # 4) Create workspace creation policies
        print("\n── Creating WorkspaceCreationPolicies ──")
        for bl in created_lines:
            existing = WorkspaceCreationPolicy.objects.filter(
                business_line=bl, status=WorkspaceCreationPolicy.STATUS_ACTIVE
            ).first()
            if existing:
                print(f"  [EXISTS] active policy for {bl.name} (id={existing.id})")
                continue
            policy = WorkspaceCreationPolicy.objects.create(
                business_line=bl,
                revision=1,
                status=WorkspaceCreationPolicy.STATUS_ACTIVE,
                audience=WorkspaceCreationPolicy.AUDIENCE_REGISTERED_BETA,
                review_route=WorkspaceCreationPolicy.ROUTE_PLATFORM,
                reviewer_separation_required=True,
            )
            print(f"  [NEW] active policy for {bl.name} (id={policy.id})")

    # Summary
    print("\n=== Summary ===")
    print(f"  BusinessLines: {BusinessLine.objects.count()}")
    print(f"  OfficeLocations: {OfficeLocation.objects.count()}")
    print(f"  WorkGroups: {WorkGroup.objects.count()}")
    print(f"  Active Policies: {WorkspaceCreationPolicy.objects.filter(status='active').count()}")
    print("\nDone!")


if __name__ == "__main__":
    run()
