from types import SimpleNamespace

from django.core.cache.backends.locmem import LocMemCache
from django.test import SimpleTestCase
from rest_framework.exceptions import Throttled
from rest_framework.test import APIRequestFactory

from apps.core.exceptions import custom_exception_handler
from apps.core.throttling import (
    AuthenticatedMutationThrottle,
    AuthenticatedReadBurstThrottle,
    AuthenticatedReadSustainedThrottle,
)


class NavigationThrottleContractTest(SimpleTestCase):
    def setUp(self):
        self.factory = APIRequestFactory()
        self.user = SimpleNamespace(is_authenticated=True, pk="user-1")

    def _request(self, method="get"):
        request = getattr(self.factory, method)("/api/v1/admin/example/")
        request.user = self.user
        return request

    def _throttle(self, cls, name):
        throttle = cls()
        throttle.cache = LocMemCache(name, {})
        throttle.timer = lambda: 1000.0
        return throttle

    def test_read_contract_is_240_per_minute_with_60_per_ten_second_burst(self):
        sustained = self._throttle(AuthenticatedReadSustainedThrottle, "sustained")
        burst = self._throttle(AuthenticatedReadBurstThrottle, "burst")

        self.assertEqual((sustained.num_requests, sustained.duration), (240, 60))
        self.assertEqual((burst.num_requests, burst.duration), (60, 10))
        request = self._request()
        self.assertTrue(all(burst.allow_request(request, None) for _ in range(60)))
        self.assertFalse(burst.allow_request(request, None))

    def test_reads_do_not_consume_mutation_quota_and_mutations_do_not_use_read_quota(self):
        mutation = self._throttle(AuthenticatedMutationThrottle, "mutation")
        sustained = self._throttle(AuthenticatedReadSustainedThrottle, "read")

        self.assertTrue(mutation.allow_request(self._request("get"), None))
        self.assertTrue(sustained.allow_request(self._request("post"), None))
        post = self._request("post")
        self.assertTrue(all(mutation.allow_request(post, None) for _ in range(30)))
        self.assertFalse(mutation.allow_request(post, None))

    def test_throttled_error_is_stable_and_preserves_retry_after(self):
        response = custom_exception_handler(
            Throttled(wait=7),
            {"view": None, "request": self._request()},
        )

        self.assertEqual(response.status_code, 429)
        self.assertEqual(response.data["code"], "rate_limited")
        self.assertEqual(response["Retry-After"], "7")
