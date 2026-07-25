"""Provider HTTP pool capacity contracts."""

from unittest.mock import Mock, patch

from django.core.exceptions import ImproperlyConfigured
from django.test import SimpleTestCase, override_settings

from apps.rag import embedding
from config.settings.parsing import validate_capacity_settings


class ProviderPoolCapacityTest(SimpleTestCase):
    def setUp(self):
        self.original = embedding._global_httpx_client
        embedding._global_httpx_client = None

    def tearDown(self):
        embedding._global_httpx_client = self.original

    @override_settings(
        PROVIDER_HTTP_MAX_CONNECTIONS=32,
        PROVIDER_HTTP_MAX_KEEPALIVE_CONNECTIONS=16,
    )
    def test_shared_client_uses_capacity_defaults(self):
        sentinel_limits = object()
        with (
            patch("apps.rag.embedding.httpx.Limits", return_value=sentinel_limits) as limits,
            patch("apps.rag.embedding.httpx.Client", return_value=Mock()) as client,
        ):
            embedding.get_shared_httpx_client()

        limits.assert_called_once_with(
            max_connections=32,
            max_keepalive_connections=16,
            keepalive_expiry=60,
        )
        self.assertIs(client.call_args.kwargs["limits"], sentinel_limits)

    @override_settings(
        PROVIDER_HTTP_MAX_CONNECTIONS=64,
        PROVIDER_HTTP_MAX_KEEPALIVE_CONNECTIONS=32,
    )
    def test_recreated_client_honours_runtime_override(self):
        sentinel_limits = object()
        with (
            patch("apps.rag.embedding.httpx.Limits", return_value=sentinel_limits) as limits,
            patch("apps.rag.embedding.httpx.Client", return_value=Mock()),
        ):
            embedding.recreate_shared_httpx_client()

        limits.assert_called_once_with(
            max_connections=64,
            max_keepalive_connections=32,
            keepalive_expiry=60,
        )

    def test_startup_rejects_pool_smaller_than_worker_concurrency(self):
        with self.assertRaises(ImproperlyConfigured):
            validate_capacity_settings(
                target_active=500,
                max_outstanding=625,
                reservation_ttl_seconds=180,
                retry_after_seconds=5,
                worker_concurrency=25,
                event_ttl_seconds=900,
                event_max_length=4096,
                provider_max_connections=24,
                provider_max_keepalive_connections=16,
            )
