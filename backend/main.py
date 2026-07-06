import logging
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from backend.routers import search, sources
# JPO patent status lookup (backend/routers/jpo.py, backend/integrations/jpo_client.py)
# is intentionally not wired up right now — pending further permission from
# JPO on the account's intended use. Re-enable by importing jpo above and
# adding app.include_router(jpo.router, prefix="/api/v1") below.
from backend.middleware.rate_limit import RateLimitMiddleware
from backend.middleware.security_headers import SecurityHeadersMiddleware

logging.basicConfig(level=logging.INFO)

app = FastAPI(
    title="APSE Technology Gateway API",
    description="Federated search across Asia-Pacific technology transfer databases",
    version="0.1.0",
)

# Public read-only API — no cookies/credentials involved, so a fixed allow-list
# (rather than "*") mainly limits which sites can drive load against it via
# browser CORS, not a confidentiality boundary.
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://apsei.onrender.com",
        "https://apctt.org",
        "https://www.apctt.org",
        "http://localhost:5501",
        "http://127.0.0.1:5501",
    ],
    allow_methods=["GET"],
    allow_headers=["*"],
)

app.add_middleware(RateLimitMiddleware, max_requests=240, window_seconds=60)
app.add_middleware(SecurityHeadersMiddleware)

app.include_router(search.router, prefix="/api/v1")
app.include_router(sources.router, prefix="/api/v1")


@app.get("/health")
def health():
    return {"status": "ok"}


