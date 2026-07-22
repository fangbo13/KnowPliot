"""Database-free contract tests for the asynchronous chat stream v3 rollout."""

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.test import SimpleTestCase

from apps.chat.models import ChatTurn
from apps.chat.serializers import ChatMessageRequestSerializer
from config.settings.parsing import validate_capacity_settings


class ChatV3ContractTest(SimpleTestCase):
    def test_serializer_accepts_v3_but_keeps_v1_default(self):
        explicit = ChatMessageRequestSerializer(
            data={"content": "hello", "protocol_version": 3}
        )

        self.assertTrue(explicit.is_valid(), explicit.errors)
        self.assertEqual(explicit.validated_data["protocol_version"], 3)

        legacy = ChatMessageRequestSerializer(data={"content": "hello"})

        self.assertTrue(legacy.is_valid(), legacy.errors)
        self.assertEqual(legacy.validated_data["protocol_version"], 1)

    def test_turn_persists_a_bounded_protocol_version(self):
        field = ChatTurn._meta.get_field("protocol_version")

        self.assertEqual(field.get_internal_type(), "PositiveSmallIntegerField")
        self.assertEqual(field.default, 1)
        self.assertTrue(
            any(
                constraint.name == "chat_turn_protocol_version_ck"
                for constraint in ChatTurn._meta.constraints
            )
        )

    def test_capacity_defaults_match_the_approved_spec(self):
        self.assertFalse(settings.CHAT_STREAM_V3)
        self.assertEqual(settings.CHAT_GENERATION_TARGET_ACTIVE, 500)
        self.assertEqual(settings.CHAT_GENERATION_MAX_OUTSTANDING, 625)
        self.assertEqual(settings.CHAT_GENERATION_RESERVATION_TTL_SECONDS, 180)
        self.assertEqual(settings.CHAT_GENERATION_RETRY_AFTER_SECONDS, 5)
        self.assertEqual(settings.CHAT_GENERATION_WORKER_CONCURRENCY, 25)
        self.assertEqual(settings.CHAT_EVENT_V3_TTL_SECONDS, 900)
        self.assertEqual(settings.CHAT_EVENT_V3_MAXLEN, 4096)
        self.assertEqual(settings.PROVIDER_HTTP_MAX_CONNECTIONS, 32)
        self.assertEqual(settings.PROVIDER_HTTP_MAX_KEEPALIVE_CONNECTIONS, 16)
        self.assertEqual(
            settings.CHAT_EVENTS_REDIS_URL,
            settings.CHAT_COORDINATION_REDIS_URL,
        )
        self.assertEqual(
            settings.CHAT_CAPACITY_REDIS_URL,
            settings.CHAT_EVENTS_REDIS_URL,
        )


class CapacitySettingsValidationTest(SimpleTestCase):
    def valid_values(self):
        return {
            "target_active": 500,
            "max_outstanding": 625,
            "reservation_ttl_seconds": 180,
            "retry_after_seconds": 5,
            "worker_concurrency": 25,
            "event_ttl_seconds": 900,
            "event_max_length": 4096,
            "provider_max_connections": 32,
            "provider_max_keepalive_connections": 16,
        }

    def test_accepts_the_approved_capacity_relationships(self):
        validate_capacity_settings(**self.valid_values())

    def test_rejects_non_positive_capacity_values(self):
        for key in self.valid_values():
            with self.subTest(key=key):
                values = self.valid_values()
                values[key] = 0
                with self.assertRaises(ImproperlyConfigured):
                    validate_capacity_settings(**values)

    def test_rejects_inverted_capacity_and_connection_limits(self):
        invalid_overrides = (
            {"target_active": 626},
            {"provider_max_connections": 24},
            {
                "provider_max_connections": 32,
                "provider_max_keepalive_connections": 33,
            },
        )

        for override in invalid_overrides:
            with self.subTest(override=override):
                values = {**self.valid_values(), **override}
                with self.assertRaises(ImproperlyConfigured):
                    validate_capacity_settings(**values)
