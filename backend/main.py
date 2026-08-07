import logging
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from backend.routers import analytics, search, sources
# JPO patent status lookup (backend/routers/jpo.py, backend/integrations/jpo_client.py)
# is intentionally not wired up right now — pending further permission from
# JPO on the account's intended use. Re-enable by importing jpo above and
# adding app.include_router(jpo.router, prefix="/api/v1") below.
from backend.middleware.rate_limit import RateLimitMiddleware
from backend.middleware.security_headers import SecurityHeadersMiddleware

logging.basicConfig(level=logging.INFO)

app = FastAPI(
    title="Asia-Pacific Tech Gateway API",
    description="Search across participating Asia-Pacific technology transfer databases",
    version="0.1.0",
)

# Public API with one narrow analytics write endpoint. It accepts only a query,
# maps it to a predefined topic, and stores no raw text or user identifiers.
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://apsei.onrender.com",
        "https://apctt.org",
        "https://www.apctt.org",
        "https://ap-tg.net",
        "https://www.ap-tg.net",
        "http://localhost:5501",
        "http://127.0.0.1:5501",
    ],
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)

app.add_middleware(RateLimitMiddleware, max_requests=120, window_seconds=60)
app.add_middleware(SecurityHeadersMiddleware)

app.include_router(search.router, prefix="/api/v1")
app.include_router(sources.router, prefix="/api/v1")
app.include_router(analytics.router, prefix="/api/v1")


@app.get("/health")
def health():
    return {"status": "ok"}
