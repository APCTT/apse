import threading
import time
from collections import defaultdict

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Simple in-memory per-IP fixed-window rate limiter.

    Render's free tier runs a single instance, so an in-memory store is
    sufficient — no need for Redis. Protects against a single client (or a
    misbehaving script) hammering the API and starving other visitors, or
    exhausting the external Korea NTB / IP Australia rate limits.
    """

    def __init__(self, app, max_requests: int = 60, window_seconds: int = 60):
        super().__init__(app)
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self._hits: dict[str, list[float]] = defaultdict(list)
        self._lock = threading.Lock()

    def _client_ip(self, request) -> str:
        forwarded = request.headers.get("x-forwarded-for")
        if forwarded:
            return forwarded.split(",")[0].strip()
        return request.client.host if request.client else "unknown"

    async def dispatch(self, request, call_next):
        if request.url.path == "/health":
            return await call_next(request)

        client_ip = self._client_ip(request)
        now = time.time()
        cutoff = now - self.window_seconds

        with self._lock:
            hits = self._hits[client_ip]
            while hits and hits[0] < cutoff:
                hits.pop(0)

            if len(hits) >= self.max_requests:
                return JSONResponse(
                    status_code=429,
                    content={"detail": "Too many requests — please slow down and try again shortly."},
                    headers={"Retry-After": str(self.window_seconds)},
                )

            hits.append(now)

        return await call_next(request)
