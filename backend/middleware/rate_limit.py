import ipaddress
import threading
import time
from collections import OrderedDict, deque

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Simple in-memory per-IP fixed-window rate limiter.

    Render's free tier runs a single instance, so an in-memory store is
    sufficient — no need for Redis. Protects against a single client (or a
    misbehaving script) hammering the API and starving other visitors, or
    exhausting external live-source API quotas such as Korea NTB.
    """

    def __init__(
        self,
        app,
        max_requests: int = 60,
        window_seconds: int = 60,
        max_clients: int = 10_000,
    ):
        super().__init__(app)
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self.max_clients = max(100, max_clients)
        self._hits: OrderedDict[str, deque[float]] = OrderedDict()
        self._lock = threading.Lock()

    def _client_ip(self, request) -> str:
        forwarded = request.headers.get("x-forwarded-for")
        if forwarded:
            # A client can prepend a forged value to X-Forwarded-For. Render's
            # edge proxy appends the address it actually received, so prefer
            # the right-most valid address instead of the attacker-controlled
            # first entry.
            candidate = forwarded.split(",")[-1].strip()
            try:
                return str(ipaddress.ip_address(candidate))
            except ValueError:
                pass
        fallback = request.client.host if request.client else "unknown"
        try:
            return str(ipaddress.ip_address(fallback))
        except ValueError:
            return "unknown"

    async def dispatch(self, request, call_next):
        if request.url.path == "/health":
            return await call_next(request)

        client_ip = self._client_ip(request)
        now = time.time()
        cutoff = now - self.window_seconds

        with self._lock:
            hits = self._hits.get(client_ip)
            if hits is None:
                if len(self._hits) >= self.max_clients:
                    self._hits.popitem(last=False)
                hits = deque()
                self._hits[client_ip] = hits
            else:
                self._hits.move_to_end(client_ip)

            while hits and hits[0] < cutoff:
                hits.popleft()

            if len(hits) >= self.max_requests:
                return JSONResponse(
                    status_code=429,
                    content={"detail": "Too many requests — please slow down and try again shortly."},
                    headers={"Retry-After": str(self.window_seconds)},
                )

            hits.append(now)

        return await call_next(request)
