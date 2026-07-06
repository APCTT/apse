import asyncio
import logging
import time

import httpx

from backend.config import settings

logger = logging.getLogger(__name__)

_API_BASE = "https://ip-data.jpo.go.jp/api"


class JPOClient:
    """Client for JPO's Patent Information Retrieval APIs.

    This is a lookup-by-application-number service (not a keyword search
    API) — every endpoint requires an exact 10-digit Japanese application
    number and returns that one application's official status.

    Auth flow: exchange username/password for an access token (valid 1h)
    and a refresh token (valid 8h); refresh instead of re-authenticating
    when possible. Token is cached in memory and shared across requests.
    """

    def __init__(self):
        self._access_token: str | None = None
        self._refresh_token: str | None = None
        self._expires_at: float = 0.0
        self._lock = asyncio.Lock()

    async def _authenticate(self, client: httpx.AsyncClient) -> None:
        resp = await client.post(
            settings.JPO_TOKEN_URL,
            data={
                "grant_type": "password",
                "username": settings.JPO_API_USERNAME,
                "password": settings.JPO_API_PASSWORD,
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        resp.raise_for_status()
        self._store_tokens(resp.json())
        logger.info("JPO: authenticated with username/password")

    async def _refresh(self, client: httpx.AsyncClient) -> None:
        resp = await client.post(
            settings.JPO_TOKEN_URL,
            data={"grant_type": "refresh_token", "refresh_token": self._refresh_token},
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        resp.raise_for_status()
        self._store_tokens(resp.json())
        logger.info("JPO: refreshed access token")

    def _store_tokens(self, data: dict) -> None:
        self._access_token = data["access_token"]
        self._refresh_token = data["refresh_token"]
        # Refresh a little early to avoid racing against the 1h expiry
        self._expires_at = time.time() + data["expires_in"] - 30

    async def _get_token(self, client: httpx.AsyncClient) -> str:
        async with self._lock:
            if self._access_token and time.time() < self._expires_at:
                return self._access_token
            try:
                if self._refresh_token:
                    await self._refresh(client)
                else:
                    await self._authenticate(client)
            except Exception as e:
                logger.warning("JPO: refresh failed (%s) — re-authenticating", e)
                await self._authenticate(client)
            return self._access_token

    async def get_patent_status(self, application_number: str, simple: bool = False) -> dict:
        endpoint = "app_progress_simple" if simple else "app_progress"
        async with httpx.AsyncClient(timeout=15.0) as client:
            token = await self._get_token(client)
            resp = await client.get(
                f"{_API_BASE}/patent/v1/{endpoint}/{application_number}",
                headers={"Authorization": f"Bearer {token}"},
            )
            resp.raise_for_status()
            return resp.json()


jpo_client = JPOClient()
