import unittest
from types import SimpleNamespace

from starlette.datastructures import Headers

from backend.middleware.rate_limit import RateLimitMiddleware


class RateLimitClientAddressTests(unittest.TestCase):
    def setUp(self):
        self.middleware = RateLimitMiddleware(
            app=lambda scope, receive, send: None,
            max_requests=10,
            max_clients=100,
        )

    @staticmethod
    def request(forwarded: str | None, client_host: str = "10.0.0.5"):
        headers = Headers(
            {"x-forwarded-for": forwarded} if forwarded is not None else {}
        )
        return SimpleNamespace(
            headers=headers,
            client=SimpleNamespace(host=client_host),
        )

    def test_uses_rightmost_forwarded_address(self):
        request = self.request("198.51.100.7, 203.0.113.9")
        self.assertEqual(self.middleware._client_ip(request), "203.0.113.9")

    def test_invalid_forwarded_address_falls_back_to_socket_peer(self):
        request = self.request("<script>", "192.0.2.20")
        self.assertEqual(self.middleware._client_ip(request), "192.0.2.20")

    def test_invalid_addresses_collapse_to_bounded_unknown_bucket(self):
        request = self.request("not-an-ip", "proxy.internal")
        self.assertEqual(self.middleware._client_ip(request), "unknown")
