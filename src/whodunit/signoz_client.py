"""Thin authenticated SigNoz HTTP client.

Environment-variable driven. NO hardcoded credentials.

Login uses ``POST /api/v2/sessions/email_password`` whose body needs
``email``, ``password`` and ``orgID`` and whose response carries the token at
``data.accessToken`` (NOT ``accessJwt`` — a documented landmine).
"""

from __future__ import annotations

import os
from types import TracebackType
from typing import Any

import httpx

DEFAULT_URL = "http://localhost:8080"
_LOGIN_PATH = "/api/v2/sessions/email_password"
_QUERY_RANGE_PATH = "/api/v5/query_range"
_DASHBOARDS_PATH = "/api/v1/dashboards"
_RULES_PATH = "/api/v1/rules"
_CHANNELS_PATH = "/api/v1/channels"
_FIELD_KEYS_PATH = "/api/v3/fields/keys"


class SigNozError(RuntimeError):
    """Raised when the SigNoz API returns an error or an unexpected shape."""


class SigNozAuthError(SigNozError):
    """Raised when authentication fails or no token can be obtained."""


class SigNozConfig:
    """Resolved connection settings, sourced from the environment."""

    def __init__(
        self,
        *,
        url: str | None = None,
        email: str | None = None,
        password: str | None = None,
        org_id: str | None = None,
    ) -> None:
        self.url: str = (url or os.environ.get("SIGNOZ_URL") or DEFAULT_URL).rstrip("/")
        self.email: str | None = email or os.environ.get("SIGNOZ_EMAIL")
        self.password: str | None = password or os.environ.get("SIGNOZ_PASSWORD")
        self.org_id: str | None = org_id or os.environ.get("SIGNOZ_ORG_ID")

    def require_credentials(self) -> tuple[str, str, str]:
        if not self.email or not self.password or not self.org_id:
            raise SigNozAuthError(
                "SIGNOZ_EMAIL, SIGNOZ_PASSWORD and SIGNOZ_ORG_ID must all be set "
                "(via env vars or SigNozConfig arguments)."
            )
        return self.email, self.password, self.org_id


class SigNozClient:
    """Authenticated client over a single httpx transport.

    A custom ``transport`` (or fully-built ``client``) may be injected for
    testing; production code just relies on env-var configuration.
    """

    def __init__(
        self,
        config: SigNozConfig | None = None,
        *,
        client: httpx.Client | None = None,
        transport: httpx.BaseTransport | None = None,
        timeout: float = 30.0,
    ) -> None:
        self._config = config or SigNozConfig()
        self._token: str | None = None
        if client is not None:
            self._client = client
        else:
            self._client = httpx.Client(
                base_url=self._config.url,
                transport=transport,
                timeout=timeout,
            )

    # -- lifecycle --------------------------------------------------------- #

    def __enter__(self) -> SigNozClient:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        self.close()

    def close(self) -> None:
        self._client.close()

    # -- auth -------------------------------------------------------------- #

    def login(self) -> str:
        """Authenticate and cache the access token. Returns the token."""
        email, password, org_id = self._config.require_credentials()
        resp = self._client.post(
            _LOGIN_PATH,
            json={"email": email, "password": password, "orgID": org_id},
        )
        if resp.status_code >= 400:
            raise SigNozAuthError(
                f"login failed: HTTP {resp.status_code}: {resp.text[:500]}"
            )
        payload = _json(resp)
        data = payload.get("data")
        token = data.get("accessToken") if isinstance(data, dict) else None
        if not isinstance(token, str) or not token:
            raise SigNozAuthError(
                "login response did not contain data.accessToken"
            )
        self._token = token
        return token

    def _auth_headers(self) -> dict[str, str]:
        if self._token is None:
            self.login()
        assert self._token is not None  # narrowed by login()
        return {"Authorization": f"Bearer {self._token}"}

    def _request(self, method: str, path: str, *, json: Any = None) -> dict[str, Any]:
        resp = self._client.request(
            method, path, json=json, headers=self._auth_headers()
        )
        if resp.status_code == 401:
            # Token may have expired; re-login once and retry.
            self._token = None
            resp = self._client.request(
                method, path, json=json, headers=self._auth_headers()
            )
        if resp.status_code >= 400:
            raise SigNozError(
                f"{method} {path} failed: HTTP {resp.status_code}: {resp.text[:500]}"
            )
        return _json(resp)

    # -- query ------------------------------------------------------------- #

    def query_range(self, payload: dict[str, Any]) -> dict[str, Any]:
        """POST a v5 query_range envelope and return the parsed response."""
        return self._request("POST", _QUERY_RANGE_PATH, json=payload)

    def get_field_keys(
        self, signal: str = "traces", *, params: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """Fetch attribute field keys for a signal (traces/logs/metrics)."""
        query: dict[str, Any] = {"signal": signal}
        if params:
            query.update(params)
        resp = self._client.get(
            _FIELD_KEYS_PATH, params=query, headers=self._auth_headers()
        )
        if resp.status_code >= 400:
            raise SigNozError(
                f"GET {_FIELD_KEYS_PATH} failed: HTTP {resp.status_code}: "
                f"{resp.text[:500]}"
            )
        return _json(resp)

    # -- materialisation --------------------------------------------------- #

    def create_dashboard(self, dashboard: dict[str, Any]) -> dict[str, Any]:
        """Create a dashboard from a v1 JSON definition."""
        return self._request("POST", _DASHBOARDS_PATH, json=dashboard)

    def create_rule(self, rule: dict[str, Any]) -> dict[str, Any]:
        """Create an alert rule."""
        return self._request("POST", _RULES_PATH, json=rule)

    def create_channel(self, channel: dict[str, Any]) -> dict[str, Any]:
        """Create a notification channel."""
        return self._request("POST", _CHANNELS_PATH, json=channel)


def _json(resp: httpx.Response) -> dict[str, Any]:
    try:
        parsed: Any = resp.json()
    except ValueError as exc:
        raise SigNozError(f"response was not valid JSON: {exc}") from exc
    if not isinstance(parsed, dict):
        raise SigNozError(f"expected a JSON object, got {type(parsed).__name__}")
    return parsed
