"""The single place that reaches into :class:`SigNozClient` internals.

``signoz_client`` exposes ``query_range`` / ``create_dashboard`` / ``create_rule``
/ ``create_channel`` but nothing for the v2 rules API, for GETs, or for DELETEs
that answer ``204 No Content`` (its ``_request`` insists on a JSON body). The
materializer needs all three, so this module borrows the client's authenticated
transport — auth header, token cache and the 401-retry dance — and returns the
raw :class:`httpx.Response` so callers control parsing.

Keeping every ``client._…`` access here means the rest of the package speaks a
clean, typed surface.
"""

from __future__ import annotations

from typing import Any, cast

from whodunit.signoz_client import SigNozClient, SigNozError


def request(
    client: SigNozClient, method: str, path: str, *, json: Any = None
) -> Any:
    """Issue an authenticated request, retrying once on a 401, raising on >=400.

    Returns the raw ``httpx.Response`` (typed ``Any`` to avoid leaking httpx into
    signatures). Mirrors :meth:`SigNozClient._request` but without the mandatory
    JSON decode, so ``204`` responses are handled by the caller.
    """
    resp = client._client.request(
        method, path, json=json, headers=client._auth_headers()
    )
    if resp.status_code == 401:
        client._token = None  # force a re-login, matching SigNozClient._request
        resp = client._client.request(
            method, path, json=json, headers=client._auth_headers()
        )
    if resp.status_code >= 400:
        raise SigNozError(
            f"{method} {path} failed: HTTP {resp.status_code}: {resp.text[:500]}"
        )
    return resp


def request_json(
    client: SigNozClient, method: str, path: str, *, json: Any = None
) -> dict[str, Any]:
    """Like :func:`request` but decode a JSON object body and return it."""
    resp = request(client, method, path, json=json)
    parsed: Any = resp.json()
    if not isinstance(parsed, dict):
        raise SigNozError(
            f"{method} {path}: expected a JSON object, got {type(parsed).__name__}"
        )
    return cast(dict[str, Any], parsed)


def data_of(payload: dict[str, Any]) -> dict[str, Any]:
    """Return the ``data`` object of a SigNoz envelope, or raise."""
    data = payload.get("data")
    if not isinstance(data, dict):
        raise SigNozError(f"response missing a 'data' object: {payload!r:.200}")
    return cast(dict[str, Any], data)


def ui_base_url(client: SigNozClient) -> str:
    """The instance base URL (API and UI share an origin)."""
    return client._config.url


__all__ = ["data_of", "request", "request_json", "ui_base_url"]
