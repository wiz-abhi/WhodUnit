"""Unit tests for the SigNoz client, using a mocked httpx transport."""

from __future__ import annotations

import json
from collections.abc import Callable

import httpx
import pytest

from whodunit.signoz_client import (
    SigNozAuthError,
    SigNozClient,
    SigNozConfig,
    SigNozError,
)

Handler = Callable[[httpx.Request], httpx.Response]


def _client(handler: Handler, **cfg: str) -> SigNozClient:
    config = SigNozConfig(
        url=cfg.get("url", "http://signoz.test"),
        email=cfg.get("email", "user@example.com"),
        password=cfg.get("password", "secret"),
        org_id=cfg.get("org_id", "org-123"),
    )
    return SigNozClient(config, transport=httpx.MockTransport(handler))


def _ok(body: dict[str, object]) -> httpx.Response:
    return httpx.Response(200, content=json.dumps(body))


# --------------------------------------------------------------------------- #
# auth
# --------------------------------------------------------------------------- #


def test_login_sends_orgid_and_reads_access_token() -> None:
    seen: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/v2/sessions/email_password"
        seen.update(json.loads(request.content))
        return _ok({"data": {"accessToken": "tok-abc"}})

    with _client(handler) as client:
        token = client.login()

    assert token == "tok-abc"
    assert seen == {
        "email": "user@example.com",
        "password": "secret",
        "orgID": "org-123",
    }


def test_login_missing_credentials_raises() -> None:
    config = SigNozConfig(url="http://signoz.test", email=None, password=None, org_id=None)
    client = SigNozClient(config, transport=httpx.MockTransport(lambda r: _ok({})))
    with pytest.raises(SigNozAuthError, match="must all be set"):
        client.login()


def test_login_http_error_raises_auth_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(403, content="forbidden")

    with _client(handler) as client, pytest.raises(SigNozAuthError, match="HTTP 403"):
        client.login()


def test_login_without_token_raises() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return _ok({"data": {"somethingElse": True}})

    with _client(handler) as client, pytest.raises(SigNozAuthError, match="accessToken"):
        client.login()


# --------------------------------------------------------------------------- #
# query_range
# --------------------------------------------------------------------------- #


def test_query_range_roundtrip_auto_logs_in_and_sends_bearer() -> None:
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request.url.path)
        if request.url.path.endswith("email_password"):
            return _ok({"data": {"accessToken": "tok-xyz"}})
        assert request.headers["Authorization"] == "Bearer tok-xyz"
        assert json.loads(request.content) == {"start": 1, "end": 2}
        return _ok({"data": {"result": [{"count": 1284}]}})

    with _client(handler) as client:
        result = client.query_range({"start": 1, "end": 2})

    assert result["data"]["result"][0]["count"] == 1284
    # login happened exactly once, before the query.
    assert calls[0].endswith("email_password")
    assert calls[1] == "/api/v5/query_range"


def test_query_range_reloguin_on_401() -> None:
    state = {"logins": 0, "queries": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("email_password"):
            state["logins"] += 1
            return _ok({"data": {"accessToken": f"tok-{state['logins']}"}})
        state["queries"] += 1
        if state["queries"] == 1:
            return httpx.Response(401, content="expired")
        return _ok({"data": {"ok": True}})

    with _client(handler) as client:
        result = client.query_range({"q": 1})

    assert result["data"]["ok"] is True
    assert state["logins"] == 2  # re-authenticated after the 401
    assert state["queries"] == 2


def test_query_range_error_raises() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("email_password"):
            return _ok({"data": {"accessToken": "t"}})
        return httpx.Response(500, content="boom")

    with _client(handler) as client, pytest.raises(SigNozError, match="HTTP 500"):
        client.query_range({})


def test_non_json_response_raises() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("email_password"):
            return _ok({"data": {"accessToken": "t"}})
        return httpx.Response(200, content="<html>not json</html>")

    with _client(handler) as client, pytest.raises(SigNozError, match="not valid JSON"):
        client.query_range({})


# --------------------------------------------------------------------------- #
# other endpoints
# --------------------------------------------------------------------------- #


def test_get_field_keys_passes_signal() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("email_password"):
            return _ok({"data": {"accessToken": "t"}})
        assert request.url.path == "/api/v3/fields/keys"
        assert request.url.params["signal"] == "logs"
        return _ok({"data": {"keys": []}})

    with _client(handler) as client:
        result = client.get_field_keys("logs")

    assert result["data"]["keys"] == []


def test_create_helpers_post_expected_paths() -> None:
    paths: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("email_password"):
            return _ok({"data": {"accessToken": "t"}})
        paths.append(request.url.path)
        return _ok({"data": {"id": "created"}})

    with _client(handler) as client:
        assert client.create_dashboard({"title": "d"})["data"]["id"] == "created"
        assert client.create_rule({"alert": "r"})["data"]["id"] == "created"
        assert client.create_channel({"name": "c"})["data"]["id"] == "created"

    assert paths == [
        "/api/v1/dashboards",
        "/api/v1/rules",
        "/api/v1/channels",
    ]


def test_config_reads_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SIGNOZ_URL", "http://env.test:9000/")
    monkeypatch.setenv("SIGNOZ_EMAIL", "env@example.com")
    monkeypatch.setenv("SIGNOZ_PASSWORD", "envpass")
    monkeypatch.setenv("SIGNOZ_ORG_ID", "env-org")
    config = SigNozConfig()
    assert config.url == "http://env.test:9000"  # trailing slash stripped
    assert config.require_credentials() == ("env@example.com", "envpass", "env-org")
