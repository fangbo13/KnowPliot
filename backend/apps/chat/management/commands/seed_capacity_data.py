from __future__ import annotations

import uuid

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.hashers import make_password
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from apps.audit.models import AuditLog
from apps.chat.models import ChatSession, Message
from apps.notifications.models import Notification
from apps.spaces.models import (
    BusinessLine,
    GovernancePolicy,
    KnowledgeSpace,
    ModelProfile,
    Organization,
    SpaceMembership,
    create_policy_revision,
)

NAMESPACE = uuid.UUID("40acbc43-a3af-48aa-9c5a-3775691ef50e")
CAPACITY_PASSWORD = "CapacityOnly!2026"


def stable_uuid(kind: str, *parts: int) -> uuid.UUID:
    return uuid.uuid5(NAMESPACE, ":".join([kind, *(str(part) for part in parts)]))


class Command(BaseCommand):
    help = "Seed deterministic synthetic rows in the isolated capacity database."

    def add_arguments(self, parser):
        parser.add_argument("--users", type=int, default=5000)
        parser.add_argument("--spaces", type=int, default=10)
        parser.add_argument("--sessions-per-user", type=int, default=20)
        parser.add_argument("--messages-per-session", type=int, default=40)
        parser.add_argument("--notifications-per-user", type=int, default=2)
        parser.add_argument("--audits-per-user", type=int, default=1)
        parser.add_argument("--batch-size", type=int, default=5000)

    def handle(self, *args, **options):
        if not getattr(settings, "CAPACITY_SEED_ALLOWED", False):
            raise CommandError("capacity_seed_disabled")
        counts = {
            name: options[name]
            for name in (
                "users",
                "spaces",
                "sessions_per_user",
                "messages_per_session",
                "notifications_per_user",
                "audits_per_user",
            )
        }
        if any(value < 0 for value in counts.values()) or counts["spaces"] < 1:
            raise CommandError("capacity_seed_counts_invalid")
        batch_size = max(100, options["batch_size"])

        with transaction.atomic():
            users = self._users(counts["users"], batch_size)
            organization, business_line = self._taxonomy()
            self._model_policy(organization)
            spaces = self._spaces(counts["spaces"], users, organization, business_line)
            self._memberships(users, spaces, batch_size)
            self._sessions_and_messages(
                users,
                spaces,
                counts["sessions_per_user"],
                counts["messages_per_session"],
                batch_size,
            )
            self._notifications(users, counts["notifications_per_user"], batch_size)
            self._audits(users, spaces, counts["audits_per_user"], batch_size)

        self.stdout.write(
            self.style.SUCCESS(
                "capacity_seed_complete "
                + " ".join(f"{key}={value}" for key, value in counts.items())
            )
        )

    def _users(self, count, batch_size):
        User = get_user_model()
        password = make_password(CAPACITY_PASSWORD)
        rows = [
            User(
                id=stable_uuid("user", index),
                username=f"capacity{index:05d}",
                email=f"capacity{index:05d}@example.invalid",
                employee_id=f"CAP{index:05d}",
                password=password,
                is_active=True,
                account_purpose=User.ACCOUNT_PURPOSE_TEST,
                test_run_id="capacity-500",
            )
            for index in range(count)
        ]
        User.objects.bulk_create(rows, batch_size=batch_size, ignore_conflicts=True)
        return list(User.objects.filter(test_run_id="capacity-500").order_by("username")[:count])

    def _taxonomy(self):
        organization, _ = Organization.objects.get_or_create(
            id=stable_uuid("organization", 0),
            defaults={"name": "Capacity Organization", "slug": "capacity-organization"},
        )
        business_line, _ = BusinessLine.objects.get_or_create(
            id=stable_uuid("business-line", 0),
            defaults={
                "organization": organization,
                "name": "Capacity Line",
                "code": "CAPACITY",
            },
        )
        return organization, business_line

    def _model_policy(self, organization):
        profiles = {}
        for model_id in ("qwen3.6-flash", "qwen3.7-plus"):
            profile, _ = ModelProfile.objects.update_or_create(
                name=model_id,
                defaults={
                    "provider": "dashscope",
                    "model_id": model_id,
                    "enabled": True,
                },
            )
            profiles[model_id] = profile
        values = {
            "fast_model_profile_id": str(profiles["qwen3.6-flash"].id),
            "deep_model_profile_id": str(profiles["qwen3.7-plus"].id),
            "fast_thinking_budget": 1024,
            "deep_thinking_budget": 1024,
            "retrieval_top_k": 8,
        }
        latest = (
            GovernancePolicy.objects.filter(organization=organization, space__isnull=True)
            .order_by("-revision", "-created_at")
            .first()
        )
        if latest is None or latest.values != values:
            create_policy_revision(organization=organization, values=values)

    def _spaces(self, count, users, organization, business_line):
        if len(users) < count:
            raise CommandError("capacity_seed_requires_at_least_one_owner_per_space")
        rows = [
            KnowledgeSpace(
                id=stable_uuid("space", index),
                organization=organization,
                business_line=business_line,
                name=f"Capacity Space {index:02d}",
                code=f"capacity-space-{index:02d}",
                visibility="organization",
                join_policy=KnowledgeSpace.JOIN_POLICY_GLOBAL,
                classification_state=KnowledgeSpace.CLASSIFICATION_LEGACY,
                owner=users[index],
                created_by=users[index],
            )
            for index in range(count)
        ]
        KnowledgeSpace.objects.bulk_create(rows, ignore_conflicts=True)
        return list(KnowledgeSpace.objects.filter(code__startswith="capacity-space-").order_by("code")[:count])

    def _memberships(self, users, spaces, batch_size):
        rows = []
        for index, user in enumerate(users):
            space_index = index % len(spaces)
            rows.append(SpaceMembership(
                id=stable_uuid("membership", index),
                user=user,
                space=spaces[space_index],
                role=(
                    SpaceMembership.ROLE_OWNER
                    if index < len(spaces) and space_index == index
                    else SpaceMembership.ROLE_MEMBER
                ),
                status="active",
                source_kind=SpaceMembership.SOURCE_OWNERSHIP if index < len(spaces) else SpaceMembership.SOURCE_MANUAL,
            ))
            user.default_space = spaces[space_index]
        SpaceMembership.objects.bulk_create(rows, batch_size=batch_size, ignore_conflicts=True)
        get_user_model().objects.bulk_update(users, ["default_space"], batch_size=batch_size)

    def _sessions_and_messages(self, users, spaces, sessions_per_user, messages_per_session, batch_size):
        session_rows = []
        for user_index, user in enumerate(users):
            space = spaces[user_index % len(spaces)]
            for session_index in range(sessions_per_user):
                session_rows.append(ChatSession(
                    id=stable_uuid("session", user_index, session_index),
                    user=user,
                    space=space,
                    title=f"Capacity session {session_index:02d}",
                ))
        ChatSession.objects.bulk_create(session_rows, batch_size=batch_size, ignore_conflicts=True)

        message_rows = []
        for user_index, user in enumerate(users):
            space = spaces[user_index % len(spaces)]
            for session_index in range(sessions_per_user):
                session_id = stable_uuid("session", user_index, session_index)
                for message_index in range(messages_per_session):
                    message_id = stable_uuid("message", user_index, session_index, message_index)
                    message_rows.append(Message(
                        id=message_id,
                        session_id=session_id,
                        space=space,
                        role="user" if message_index % 2 == 0 else "assistant",
                        content=f"Synthetic capacity message {message_index:02d}",
                        version_group_id=message_id,
                    ))
                    if len(message_rows) >= batch_size:
                        Message.objects.bulk_create(message_rows, batch_size=batch_size, ignore_conflicts=True)
                        message_rows.clear()
        if message_rows:
            Message.objects.bulk_create(message_rows, batch_size=batch_size, ignore_conflicts=True)

    def _notifications(self, users, per_user, batch_size):
        rows = [
            Notification(
                id=stable_uuid("notification", user_index, item_index),
                recipient=user,
                type=Notification.TYPE_SYSTEM,
                title="Capacity notification",
                body="Synthetic load data",
            )
            for user_index, user in enumerate(users)
            for item_index in range(per_user)
        ]
        Notification.objects.bulk_create(rows, batch_size=batch_size, ignore_conflicts=True)

    def _audits(self, users, spaces, per_user, batch_size):
        rows = [
            AuditLog(
                id=stable_uuid("audit", user_index, item_index),
                user=user,
                actor_uuid=user.id,
                action="system_health_view",
                target_type="capacity_fixture",
                target_id=stable_uuid("audit-target", user_index, item_index),
                details={"synthetic": True},
                role_used="employee",
                organization_id=spaces[user_index % len(spaces)].organization_id,
                business_line_id=spaces[user_index % len(spaces)].business_line_id,
            )
            for user_index, user in enumerate(users)
            for item_index in range(per_user)
        ]
        AuditLog.objects.bulk_create(rows, batch_size=batch_size, ignore_conflicts=True)
