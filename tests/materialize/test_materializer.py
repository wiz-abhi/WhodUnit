"""Unit tests for the Materializer facade over a mocked transport."""

from __future__ import annotations

import httpx

from whodunit.materialize import Materializer
from whodunit.types import CompiledQuery

from .conftest import make_client


def _handler(request: httpx.Request) -> httpx.Response:
    path = request.url.path
    if path.endswith("email_password"):
        return httpx.Response(200, json={"data": {"accessToken": "t"}})
    if path == "/api/v1/channels" and request.method == "GET":
        return httpx.Response(200, json={"data": []})
    if path == "/api/v1/channels":
        return httpx.Response(201, json={"data": {"id": "chan-1", "name": "whodunit-default"}})
    if path == "/api/v2/rules":
        return httpx.Response(201, json={"data": {"id": "rule-1"}})
    if path == "/api/v2/dashboards":
        return httpx.Response(201, json={"data": {"id": "dash-1"}})
    return httpx.Response(404, json={"data": {}})


def test_permalink_via_facade(compiled: CompiledQuery) -> None:
    with make_client(lambda r: httpx.Response(200, json={"data": {}})) as client:
        mat = Materializer(client, ui_base_url="http://ui.test")
        url = mat.permalink(compiled, window_start_ms=1, window_end_ms=2)
    assert url.startswith("http://ui.test/traces-explorer?compositeQuery=")


def test_arm_alert_creates_channel_then_rule(compiled: CompiledQuery) -> None:
    with make_client(_handler) as client:
        mat = Materializer(client)
        rid = mat.arm_alert(
            compiled,
            rule_name="r",
            warn_threshold=1,
            crit_threshold=5,
            channel_webhook_url=None,
        )
    assert rid == "rule-1"


def test_create_dashboard_via_facade(compiled: CompiledQuery) -> None:
    with make_client(_handler) as client:
        mat = Materializer(client)
        dash_id = mat.create_dashboard(compiled, title="Whodunit — x")
        assert dash_id == "dash-1"
        assert mat.dashboard_url(dash_id) == "http://signoz.test/dashboard/dash-1"


def test_ui_base_defaults_to_client_config(compiled: CompiledQuery) -> None:
    with make_client(lambda r: httpx.Response(200, json={"data": {}})) as client:
        mat = Materializer(client)
        url = mat.permalink(compiled, window_start_ms=0, window_end_ms=0)
    assert url.startswith("http://signoz.test/traces-explorer")
