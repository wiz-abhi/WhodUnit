"""Unit tests for native v6 dashboard authoring."""

from __future__ import annotations

import json

import httpx

from whodunit.materialize import dashboard
from whodunit.types import CompiledQuery

from .conftest import load_golden, make_client


def test_dashboard_body_matches_golden(compiled: CompiledQuery) -> None:
    body = dashboard.build_dashboard(compiled, title="Whodunit — (A => B) && NOT C")
    assert body == load_golden("dashboard_v6.json")


def test_dashboard_shape_invariants(compiled: CompiledQuery) -> None:
    body = dashboard.build_dashboard(compiled, title="Whodunit — x")
    assert body["schemaVersion"] == "v6"
    panels = body["spec"]["panels"]
    assert set(panels) == {"0", "1", "2"}
    # every panel has exactly one query, wrapped as signoz/CompositeQuery.
    for panel in panels.values():
        queries = panel["spec"]["queries"]
        assert len(queries) == 1
        assert queries[0]["spec"]["plugin"]["kind"] == "signoz/CompositeQuery"
    # the operator survives inside panel 0's composite.
    p0 = panels["0"]["spec"]["queries"][0]["spec"]["plugin"]["spec"]["queries"]
    op = [q for q in p0 if q["type"] == "builder_trace_operator"]
    assert op and op[0]["spec"]["expression"] == "(A => B) && NOT C"
    assert op[0]["spec"]["aggregations"][0]["expression"] == "count_distinct(trace_id)"
    # share panel carries a formula; receipt panel is a NumberPanel with markdown.
    p1 = panels["1"]["spec"]["queries"][0]["spec"]["plugin"]["spec"]["queries"]
    assert any(q["type"] == "builder_formula" for q in p1)
    assert panels["2"]["spec"]["plugin"]["kind"] == "signoz/NumberPanel"
    assert "mined 1284" in panels["2"]["spec"]["display"]["description"]
    # grid layout is Perses, 12-wide.
    grid = body["spec"]["layouts"][0]
    assert grid["kind"] == "Grid"
    assert grid["spec"]["items"][0]["width"] == 12


def test_create_dashboard_posts_v2_and_returns_id(compiled: CompiledQuery) -> None:
    seen: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("email_password"):
            return httpx.Response(200, json={"data": {"accessToken": "t"}})
        assert request.method == "POST"
        assert request.url.path == "/api/v2/dashboards"
        seen["body"] = json.loads(request.content)
        return httpx.Response(201, json={"data": {"id": "dash-123"}})

    with make_client(handler) as client:
        dash_id = dashboard.create_dashboard(client, compiled, title="Whodunit — x")

    assert dash_id == "dash-123"
    assert seen["body"]["schemaVersion"] == "v6"  # type: ignore[index]


def test_delete_dashboard_uses_v2_path(compiled: CompiledQuery) -> None:
    calls: list[tuple[str, str]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("email_password"):
            return httpx.Response(200, json={"data": {"accessToken": "t"}})
        calls.append((request.method, request.url.path))
        return httpx.Response(204)

    with make_client(handler) as client:
        dashboard.delete_dashboard(client, "dash-123")

    assert calls == [("DELETE", "/api/v2/dashboards/dash-123")]
