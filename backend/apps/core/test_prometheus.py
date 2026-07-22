from __future__ import annotations

import re
import uuid

from django.test import Client, SimpleTestCase, override_settings


@override_settings(PROMETHEUS_METRICS_TOKEN="metrics-secret")
class PrometheusEndpointTest(SimpleTestCase):
    def setUp(self):
        self.client = Client()

    def test_missing_or_wrong_token_is_non_disclosing_404(self):
        for headers in ({}, {"HTTP_AUTHORIZATION": "Bearer wrong"}):
            with self.subTest(headers=headers):
                response = self.client.get("/api/v1/internal/metrics/", **headers)
                self.assertEqual(response.status_code, 404)

    def test_correct_internal_token_returns_prometheus_text(self):
        response = self.client.get(
            "/api/v1/internal/metrics/",
            HTTP_AUTHORIZATION="Bearer metrics-secret",
        )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response["Content-Type"].startswith("text/plain"))
        self.assertIn(b"knowpilot_http_requests_total", response.content)

    def test_http_labels_use_route_names_and_never_request_identifiers(self):
        secret_user = f"user-{uuid.uuid4()}"
        secret_session = str(uuid.uuid4())
        secret_turn = str(uuid.uuid4())
        self.client.get(
            "/api/v1/internal/metrics/",
            HTTP_AUTHORIZATION="Bearer wrong",
            HTTP_X_TEST_USER=secret_user,
            HTTP_X_SESSION_ID=secret_session,
            HTTP_X_TURN_ID=secret_turn,
        )
        response = self.client.get(
            "/api/v1/internal/metrics/",
            HTTP_AUTHORIZATION="Bearer metrics-secret",
        )
        text = response.content.decode()

        self.assertRegex(
            text,
            re.compile(r'knowpilot_http_requests_total\{[^}]*route="internal-metrics"'),
        )
        self.assertNotIn(secret_user, text)
        self.assertNotIn(secret_session, text)
        self.assertNotIn(secret_turn, text)
        self.assertNotIn("/api/v1/internal/metrics/", text)
