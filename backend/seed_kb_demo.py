"""KB optimization — seed demo data for real-user browser verification.

Idempotent. Creates:
  - A published ReferenceLibrary space "IFRS 参考库" with 2 docs.
  - Sets the demo space to taxonomy_mode='space' + seeds the audit preset.
  - Three linked documents ([[wikilinks]]) in the demo space so Backlinks and
    Local Graph show real edges.

Run: docker compose exec -T backend python seed_kb_demo.py
"""
import os
import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.docker")
django.setup()

from django.contrib.auth import get_user_model
from apps.spaces.models import KnowledgeSpace, Organization, SpaceMembership
from apps.spaces.ownership import create_space_with_owner
from apps.knowledge.models import Document, DocumentLink, ReferenceLibrary
from apps.knowledge.links import sync_document_links
from apps.knowledge.taxonomy_presets import seed_space_taxonomy

User = get_user_model()

admin = User.objects.filter(is_superuser=True).order_by("date_joined").first()
if admin is None:
    admin = User.objects.filter(email="admin@test.ey.com").first()
print(f"admin = {admin.email if admin else None}")

org = Organization.objects.order_by("created_at").first()
print(f"org = {org.name if org else None}")

# 1) Reference library space (published) --------------------------------------
lib_space = KnowledgeSpace.objects.filter(code="ifrs-reference-lib").first()
if lib_space is None:
    lib_space = create_space_with_owner(
        organization=org, owner=admin,
        name="IFRS 参考库", code="ifrs-reference-lib", visibility="organization",
    )
    print(f"[NEW] lib space {lib_space.id}")
else:
    print(f"[EXISTS] lib space {lib_space.id}")

for title, body in [
    ("IFRS 15 收入确认", "IFRS 15 规定了五步法收入确认模型：识别合同、识别履约义务、确定交易价格、分摊价格、确认收入。"),
    ("IFRS 16 租赁", "IFRS 16 要求承租人对几乎所有租赁确认使用权资产和租赁负债。"),
]:
    doc, created = Document.objects.get_or_create(
        space=lib_space, title=title,
        defaults=dict(text_content=body, file_type="md", file_size=0,
                      uploaded_by=admin, status="active"),
    )
    print(f"  {'+' if created else '='} lib doc: {title}")

lib, created = ReferenceLibrary.objects.get_or_create(
    space=lib_space,
    defaults=dict(name="IFRS 参考库", description="国际财务报告准则权威参考",
                  category="ifrs", status="published", published_by=admin),
)
if not created and lib.status != "published":
    from django.utils import timezone
    lib.status = "published"
    lib.published_by = admin
    lib.published_at = timezone.now()
    lib.save()
if created:
    from django.utils import timezone
    lib.published_at = timezone.now()
    lib.save(update_fields=["published_at"])
print(f"  reference library status={lib.status}")

# 2) Demo space -> space taxonomy mode + audit preset + linked docs -----------
# Target the space the admin can open in the UI (Access Code Test Space),
# falling back to code lookup / first active space.
demo = (
    KnowledgeSpace.objects.filter(pk="e0b7076d-537b-4e55-8604-8f20b5e0ac00").first()
    or KnowledgeSpace.objects.filter(code="access-code-test-space").first()
    or KnowledgeSpace.objects.filter(status="active")
    .exclude(code="ifrs-reference-lib").order_by("created_at").first()
)
print(f"demo space = {demo.name} ({demo.code}) id={demo.id}")

if demo.taxonomy_mode != "space":
    demo.taxonomy_mode = "space"
    demo.save(update_fields=["taxonomy_mode"])
    print("  set demo taxonomy_mode=space")
created_dims = seed_space_taxonomy(demo, "audit_default")
print(f"  seeded {created_dims} preset dimensions into demo space")

# ensure admin is a member/owner of demo space so UI shows management controls
SpaceMembership.objects.get_or_create(
    space=demo, user=admin,
    defaults={"role": SpaceMembership.ROLE_OWNER, "status": "active"},
)

# Three linked docs: A -> B (wikilink), B -> C (wikilink)
doc_specs = [
    ("演示-收入循环底稿", "本底稿覆盖收入循环。参见 [[演示-应收账款分析]] 获取往来款明细。"),
    ("演示-应收账款分析", "应收账款账龄分析。相关坏账计提见 [[演示-坏账准备计提]]。"),
    ("演示-坏账准备计提", "按账龄组合计提坏账准备，方法遵循企业会计准则。"),
]
made = {}
for title, body in doc_specs:
    doc, created = Document.objects.get_or_create(
        space=demo, title=title,
        defaults=dict(text_content=body, file_type="md", file_size=0,
                      uploaded_by=admin, status="active"),
    )
    if not created and doc.text_content != body:
        doc.text_content = body
        doc.save(update_fields=["text_content"])
    made[title] = doc
    print(f"  {'+' if created else '='} demo doc: {title}")

for doc in made.values():
    n = sync_document_links(doc)
    print(f"    synced {n} links from {doc.title}")

link_count = DocumentLink.objects.filter(space=demo).count()
print(f"demo space DocumentLink rows = {link_count}")
print("DONE")
