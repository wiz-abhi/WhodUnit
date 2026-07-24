"""Live materialisation tests against a real SigNoz instance.

Gated: run only when ``SIGNOZ_LIVE=1`` and ``SIGNOZ_EMAIL`` / ``SIGNOZ_PASSWORD``
/ ``SIGNOZ_ORG_ID`` are set. Each test creates real artifacts, verifies them via
GET, and always deletes them in a ``finally`` block.

    SIGNOZ_LIVE=1 uv run pytest tests/materialize/test_live.py -m live -q
"""

from __future__ import annotations

import os

import pytest

from whodunit.materialize import Materializer, alert, dashboard
from whodunit.signoz_client import SigNozClient
from whodunit.types import CompiledQuery

pytestmark = pytest.mark.live

_LIVE = os.environ.get("SIGNOZ_LIVE") == "1"
_skip = pytest.mark.skipif(not _LIVE, reason="set SIGNOZ_LIVE=1 to run live tests")


@pytest.fixture
def live_client() -> SigNozClient:
    client = SigNozClient()
    client.login()  # fail fast if creds are wrong
    return client


@_skip
def test_live_dashboard_roundtrip(
    live_client: SigNozClient, compiled: CompiledQuery
) -> None:
    dash_id = dashboard.create_dashboard(
        live_client, compiled, title="Whodunit — live test (delete me)"
    )
    try:
        stored = dashboard.get_dashboard(live_client, dash_id)
        assert stored["schemaVersion"] == "v6"
        panels = stored["spec"]["panels"]
        p0 = panels["0"]["spec"]["queries"][0]["spec"]["plugin"]["spec"]["queries"]
        op = [q for q in p0 if q["type"] == "builder_trace_operator"]
        assert op and op[0]["spec"]["expression"] == "(A => B) && NOT C"
    finally:
        dashboard.delete_dashboard(live_client, dash_id)


@_skip
def test_live_rule_arm_and_verify(
    live_client: SigNozClient, compiled: CompiledQuery
) -> None:
    mat = Materializer(live_client)
    channel_name = "whodunit-live-test"
    alert.ensure_channel(
        live_client, webhook_url="http://host.docker.internal:9099/whodunit", name=channel_name
    )
    channel_id = alert.channel_id_by_name(live_client, channel_name)
    rule_id = alert.create_rule(
        live_client,
        compiled,
        rule_name="whodunit-live-test (delete me)",
        warn_threshold=1,
        crit_threshold=5,
        channel=channel_name,
    )
    try:
        stored = mat.get_rule(rule_id)
        assert stored["schemaVersion"] == "v2alpha1"
        assert stored["evaluation"]["spec"]["evalWindow"] == "5m0s"
        tiers = stored["condition"]["thresholds"]["spec"]
        assert {t["name"] for t in tiers} == {"warning", "critical"}
    finally:
        alert.delete_rule(live_client, rule_id)
        if channel_id:
            alert.delete_channel(live_client, channel_id)
