"""API client for UVI tenant portals."""

from __future__ import annotations

import asyncio
import logging
import re
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any
from urllib.parse import urljoin

try:
    from aiohttp import ClientError, ClientSession
except ModuleNotFoundError:  # pragma: no cover - fallback for local unit tests
    class ClientError(Exception):
        """Fallback ClientError when aiohttp is not installed."""

    class ClientSession:  # type: ignore[too-many-ancestors]
        """Fallback ClientSession type for type checking in local tests."""

from .const import API_TIMEOUT_SECONDS

_LOGGER = logging.getLogger(__name__)


class UviApiError(Exception):
    """Base API error for UVI."""


class UviAuthenticationError(UviApiError):
    """Raised when authentication failed."""


@dataclass(slots=True)
class UviRequestError(UviApiError):
    """Raised when a request returned an error response."""

    message: str
    path: str
    status: int | None = None

    def __str__(self) -> str:
        """Return human-readable error message."""
        return self.message


class UviApiClient:
    """Async client for UVI portals."""

    def __init__(
        self,
        session: ClientSession,
        base_url: str,
        email: str,
        password: str,
        timeout_seconds: int = API_TIMEOUT_SECONDS,
    ) -> None:
        self._session = session
        self._base_url = base_url.rstrip("/")
        self._email = email
        self._password = password
        self._timeout_seconds = timeout_seconds
        self._authenticated = False

    @property
    def base_url(self) -> str:
        """Return configured base url."""
        return self._base_url

    async def authenticate(self, force: bool = False) -> None:
        """Authenticate against the portal and store session cookies."""
        if self._authenticated and not force:
            return

        sign_in_path = "/tenant_portal_users/sign_in"
        sign_in_url = urljoin(f"{self._base_url}/", sign_in_path.lstrip("/"))

        try:
            async with asyncio.timeout(self._timeout_seconds):
                async with self._session.get(
                    sign_in_url,
                    headers={"Accept": "text/html,application/xhtml+xml"},
                ) as response:
                    html = await response.text()
                    if response.status >= 400:
                        raise UviAuthenticationError(
                            f"Sign-in page returned HTTP {response.status}"
                        )

                csrf = self._extract_csrf_token(html)
                if not csrf:
                    raise UviAuthenticationError(
                        "Could not extract authenticity_token from sign-in page"
                    )

                payload = {
                    "authenticity_token": csrf,
                    "tenant_portal_user[email]": self._email,
                    "tenant_portal_user[password]": self._password,
                }

                async with self._session.post(
                    sign_in_url,
                    data=payload,
                    headers={
                        "Content-Type": "application/x-www-form-urlencoded",
                        "Referer": sign_in_url,
                    },
                    allow_redirects=True,
                ) as response:
                    await response.read()
                    if response.status >= 400:
                        raise UviAuthenticationError(
                            f"Sign-in request returned HTTP {response.status}"
                        )
        except (TimeoutError, ClientError) as err:
            raise UviAuthenticationError(f"Failed to authenticate: {err}") from err

        # Verify with /api/user. This raises if the session is not valid.
        await self.fetch_user(retry_auth=False)
        self._authenticated = True

    async def fetch_user(self, retry_auth: bool = True) -> dict[str, Any]:
        """Fetch /api/user."""
        return await self._request_json("/api/user", retry_auth=retry_auth)

    async def fetch_estate_units(self) -> dict[str, Any]:
        """Fetch /api/estate-units."""
        return await self._request_json("/api/estate-units")

    async def fetch_summary(self, date_from: str, date_to: str) -> dict[str, Any]:
        """Fetch /api/summary for a date range."""
        return await self._request_json(
            "/api/summary",
            params={"filter[from]": date_from, "filter[to]": date_to},
        )

    async def fetch_heating(self, date_from: str, date_to: str) -> dict[str, Any]:
        """Fetch /api/heating for a date range."""
        return await self._request_json(
            "/api/heating",
            params={"filter[from]": date_from, "filter[to]": date_to},
        )

    async def fetch_warm_water(self, date_from: str, date_to: str) -> dict[str, Any]:
        """Fetch /api/warm-water for a date range."""
        return await self._request_json(
            "/api/warm-water",
            params={"filter[from]": date_from, "filter[to]": date_to},
        )

    async def fetch_cold_water(self, date_from: str, date_to: str) -> dict[str, Any]:
        """Fetch /api/cold-water for a date range."""
        return await self._request_json(
            "/api/cold-water",
            params={"filter[from]": date_from, "filter[to]": date_to},
        )

    async def fetch_monthly_comparison(
        self, group: str, base_year: int, comparison_year: int
    ) -> dict[str, Any]:
        """Fetch /api/monthly-comparison for a group."""
        return await self._request_json(
            "/api/monthly-comparison",
            params={
                "filter[base-year]": str(base_year),
                "filter[comparison-year]": str(comparison_year),
                "filter[group]": group.lower(),
            },
        )

    async def _request_json(
        self,
        path: str,
        params: Mapping[str, str] | None = None,
        retry_auth: bool = True,
    ) -> dict[str, Any]:
        """Perform authenticated JSON request."""
        if retry_auth and not self._authenticated:
            await self.authenticate()

        url = urljoin(f"{self._base_url}/", path.lstrip("/"))

        try:
            async with asyncio.timeout(self._timeout_seconds):
                async with self._session.get(
                    url,
                    params=params,
                    headers={"Accept": "application/vnd.api+json"},
                ) as response:
                    if response.status in (401, 403):
                        if retry_auth:
                            _LOGGER.debug("Session expired for %s, trying re-auth", path)
                            self._authenticated = False
                            await self.authenticate(force=True)
                            return await self._request_json(
                                path,
                                params=params,
                                retry_auth=False,
                            )
                        raise UviAuthenticationError(
                            f"Authentication failed while calling {path}"
                        )

                    if response.status >= 400:
                        body = await response.text()
                        raise UviRequestError(
                            message=(
                                f"Unexpected HTTP {response.status} for {path}: "
                                f"{body[:200]}"
                            ),
                            path=path,
                            status=response.status,
                        )

                    try:
                        return await response.json(content_type=None)
                    except ValueError as err:
                        body = await response.text()
                        raise UviRequestError(
                            message=(
                                f"Invalid JSON response for {path}: "
                                f"{body[:200]}"
                            ),
                            path=path,
                            status=response.status,
                        ) from err
        except UviApiError:
            raise
        except (TimeoutError, ClientError) as err:
            raise UviRequestError(
                message=f"Error calling {path}: {err}",
                path=path,
            ) from err

    @staticmethod
    def _extract_csrf_token(html: str) -> str | None:
        """Extract Rails authenticity token from the sign-in page."""
        patterns = (
            r'name="authenticity_token"\s+value="([^"]+)"',
            r'<meta\s+name="csrf-token"\s+content="([^"]+)"',
        )
        for pattern in patterns:
            match = re.search(pattern, html)
            if match:
                return match.group(1)
        return None
