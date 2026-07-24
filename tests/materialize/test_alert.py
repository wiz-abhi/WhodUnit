"""Unit tests for the v2alpha1 alert rule + channel materialisation."""

from __future__ import annotations

import json

import httpx

from whodunit.materialize import alert
from whodunit.types import CompiledQuery

from .conftest import load_golden, make_client


def test_rule_body_matches_golden(compiled: CompiledQuery) -> None:
    body = alert.build_rule(
        compiled,
        rule_name="whodunit-(A => B) && NOT C",
        warn_threshold=1,
        crit_threshold=5,
        channel="whodunit-default",
    )
    assert body == load_golden("rule_v2alpha1.json")


def test_rule_schema_invariants(compiled: CompiledQuery) -> None:
    body = alert.build_rule(
        compiled,
        rule_name="r",
        warn_threshold=2.0,
        crit_threshold=8.0,
        channel="chan",
        window="10m0s",
    )
    assert body["version"] == "v5"
    assert body["schemaVersion"] == "v2alpha1"
    assert body["evaluation"] == {
        "kind": "rolling",
        "spec": {"evalWindow": "10m0s", "frequency": "30s"},
    }
    cond = body["condition"]
    assert cond["selectedQueryName"] == "T1"
    thresholds = cond["thresholds"]
    assert thresholds["kind"] == "basic"
    tiers = thresholds["spec"]
    assert [t["name"] for t in tiers] == ["warning", "critical"]
    assert [t["target"] for t in tiers] == [2.0, 8.0]  # WARN low, CRIT higher
    for tier in tiers:
        assert tier["op"] == "1" and tier["matchType"] == "1"
        assert tier["channels"] == ["chan"]
    # the operator is the selected series, counted trace-scoped.
    op = next(
        q
        for q in cond["compositeQuery"]["queries"]
        if q["type"] == "builder_trace_operator"
    )
    assert op["spec"]["aggregations"][0]["expression"] == "count_distinct(trace_id)"


def test_create_rule_posts_v2(compiled: CompiledQuery) -> None:
    seen: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("email_password"):
            return httpx.Response(200, json={"data": {"accessToken": "t"}})
        assert request.url.path == "/api/v2/rules"
        seen["body"] = json.loads(request.content)
        return httpx.Response(201, json={"data": {"id": "rule-9"}})

    with make_client(handler) as client:
        rid = alert.create_rule(
            client,
            compiled,
            rule_name="r",
            warn_threshold=1,
            crit_threshold=5,
            channel="chan",
        )

    assert rid == "rule-9"
    assert seen["body"]["schemaVersion"] == "v2alpha1"  # type: ignore[index]


def test_ensure_channel_reuses_existing() -> None:
    posts: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("email_password"):
            return httpx.Response(200, json={"data": {"accessToken": "t"}})
        if request.method == "GET" and request.url.path == "/api/v1/channels":
            return httpx.Response(
                200, json={"data": [{"id": "c1", "name": "whodunit-default"}]}
            )
        posts.append(request.url.path)
        return httpx.Response(201, json={"data": {"id": "cX"}})

    with make_client(handler) as client:
        name = alert.ensure_channel(client, webhook_url=None)

    assert name == "whodunit-default"
    assert posts == []  # no create when it already exists


def test_ensure_channel_creates_default_when_missing() -> None:
    created: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("email_password"):
            return httpx.Response(200, json={"data": {"accessToken": "t"}})
        if request.method == "GET":
            return httpx.Response(200, json={"data": []})
        created["body"] = json.loads(request.content)
        return httpx.Response(201, json={"data": {"id": "cX", "name": "whodunit-default"}})

    with make_client(handler) as client:
        name = alert.ensure_channel(client, webhook_url=None)

    assert name == "whodunit-default"
    body = created["body"]
    assert body["type"] == "webhook"  # type: ignore[index]
    assert body["webhook_configs"][0]["url"] == alert.DEFAULT_WEBHOOK_URL  # type: ignore[index]


def test_delete_rule_uses_v1_path() -> None:
    calls: list[tuple[str, str]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("email_password"):
            return httpx.Response(200, json={"data": {"accessToken": "t"}})
        calls.append((request.method, request.url.path))
        return httpx.Response(200, json={"data": "deleted"})

    with make_client(handler) as client:
        alert.delete_rule(client, "rule-9")

    assert calls == [("DELETE", "/api/v1/rules/rule-9")]
