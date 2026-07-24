"""The "arm it" beat: a webhook channel plus a v2alpha1 two-threshold rule.

The rule schema is the one Probe 1 proved fires end-to-end and delivers a webhook,
re-confirmed live during this build (see ``NOTES.md``). Load-bearing facts:

* ``POST /api/v2/rules`` with top-level ``version: "v5"`` **and**
  ``schemaVersion: "v2alpha1"``.
* ``evaluation`` is an object: ``{"kind": "rolling", "spec": {"evalWindow", "frequency"}}``
  — not top-level ``evalWindow``/``frequency``.
* ``condition.thresholds = {"kind": "basic", "spec": [ ...named tiers... ]}`` with
  channels attached by **name**, plus ``condition.selectedQueryName`` naming the
  operator query. ``op: "1"`` is greater-than, ``matchType: "1"`` is at-least-once.
* The condition's composite is the leaves + ``builder_trace_operator`` counted with
  ``count_distinct(trace_id)``.

Channels are created via ``POST /api/v1/channels`` and referenced by name.
Deletes: rules via ``DELETE /api/v1/rules/{id}`` (200), channels via
``DELETE /api/v1/channels/{id}`` (204).
"""

from __future__ import annotations

from typing import Any

from whodunit.materialize import _http, _queries
from whodunit.signoz_client import SigNozClient
from whodunit.types import CompiledQuery

RULES_V2_PATH = "/api/v2/rules"
RULES_V1_PATH = "/api/v1/rules"
CHANNELS_V1_PATH = "/api/v1/channels"

DEFAULT_CHANNEL_NAME = "whodunit-default"
DEFAULT_WEBHOOK_URL = "http://host.docker.internal:9099/whodunit"

OP_GREATER_THAN = "1"
MATCH_AT_LEAST_ONCE = "1"


# --------------------------------------------------------------------------- #
# channels
# --------------------------------------------------------------------------- #


def _channel_body(name: str, webhook_url: str) -> dict[str, Any]:
    return {
        "name": name,
        "type": "webhook",
        "webhook_configs": [{"send_resolved": True, "url": webhook_url}],
    }


def list_channels(client: SigNozClient) -> list[dict[str, Any]]:
    payload = _http.request_json(client, "GET", CHANNELS_V1_PATH)
    data = payload.get("data")
    if not isinstance(data, list):
        return []
    return [c for c in data if isinstance(c, dict)]


def ensure_channel(
    client: SigNozClient,
    *,
    webhook_url: str | None,
    name: str = DEFAULT_CHANNEL_NAME,
) -> str:
    """Return the name of a webhook channel, creating/reusing as needed.

    When ``webhook_url`` is ``None`` a default named channel is reused if it
    already exists, else created against :data:`DEFAULT_WEBHOOK_URL`. When a URL
    is given, an existing channel with the same name is reused verbatim (channels
    are immutable here); otherwise it is created.
    """
    for existing in list_channels(client):
        if existing.get("name") == name:
            return name
    url = webhook_url or DEFAULT_WEBHOOK_URL
    _http.request_json(client, "POST", CHANNELS_V1_PATH, json=_channel_body(name, url))
    return name


def delete_channel(client: SigNozClient, channel_id: str) -> None:
    """DELETE a channel by id (answers 204)."""
    _http.request(client, "DELETE", f"{CHANNELS_V1_PATH}/{channel_id}")


def channel_id_by_name(client: SigNozClient, name: str) -> str | None:
    for channel in list_channels(client):
        if channel.get("name") == name:
            cid = channel.get("id")
            if isinstance(cid, str):
                return cid
    return None


# --------------------------------------------------------------------------- #
# rules
# --------------------------------------------------------------------------- #


def _threshold(name: str, target: float, channel: str) -> dict[str, Any]:
    return {
        "name": name,
        "target": target,
        "matchType": MATCH_AT_LEAST_ONCE,
        "op": OP_GREATER_THAN,
        "channels": [channel],
    }


def build_rule(
    compiled: CompiledQuery,
    *,
    rule_name: str,
    warn_threshold: float,
    crit_threshold: float,
    channel: str,
    window: str = "5m0s",
    frequency: str = "30s",
) -> dict[str, Any]:
    """Build the exact v2alpha1 rule body for ``compiled``."""
    if not compiled.leaf_queries:
        raise ValueError("cannot build a rule for a query with no leaves")
    op_name = _queries.operator_name(compiled)
    queries = _queries.matching_count_queries(compiled)
    return {
        "version": "v5",
        "schemaVersion": "v2alpha1",
        "alert": rule_name,
        "alertType": "TRACES_BASED_ALERT",
        "ruleType": "threshold_rule",
        "evaluation": {
            "kind": "rolling",
            "spec": {"evalWindow": window, "frequency": frequency},
        },
        "condition": {
            "compositeQuery": {
                "queries": queries,
                "panelType": "graph",
                "queryType": "builder",
            },
            "selectedQueryName": op_name,
            "thresholds": {
                "kind": "basic",
                "spec": [
                    _threshold("warning", warn_threshold, channel),
                    _threshold("critical", crit_threshold, channel),
                ],
            },
        },
        "labels": {"severity": "critical", "team": "whodunit"},
        "annotations": {
            "description": (
                f"Whodunit discriminator {compiled.expression} — "
                "count_distinct(trace_id) of matching traces."
            ),
            "summary": f"Whodunit: {compiled.expression} is firing.",
        },
        "notificationSettings": {
            "groupBy": [],
            "usePolicy": False,
            "renotify": {"enabled": False},
        },
        "disabled": False,
    }


def create_rule(
    client: SigNozClient,
    compiled: CompiledQuery,
    *,
    rule_name: str,
    warn_threshold: float,
    crit_threshold: float,
    channel: str,
    window: str = "5m0s",
) -> str:
    """POST a v2alpha1 rule and return its id."""
    body = build_rule(
        compiled,
        rule_name=rule_name,
        warn_threshold=warn_threshold,
        crit_threshold=crit_threshold,
        channel=channel,
        window=window,
    )
    data = _http.data_of(_http.request_json(client, "POST", RULES_V2_PATH, json=body))
    rule_id = data.get("id")
    if not isinstance(rule_id, str) or not rule_id:
        raise ValueError(f"rule create returned no id: {data!r:.200}")
    return rule_id


def get_rule(client: SigNozClient, rule_id: str) -> dict[str, Any]:
    """GET a rule's stored ``data`` object (v2)."""
    return _http.data_of(_http.request_json(client, "GET", f"{RULES_V2_PATH}/{rule_id}"))


def delete_rule(client: SigNozClient, rule_id: str) -> None:
    """DELETE a rule by id (v1 path, answers 200)."""
    _http.request(client, "DELETE", f"{RULES_V1_PATH}/{rule_id}")


__all__ = [
    "build_rule",
    "channel_id_by_name",
    "create_rule",
    "delete_channel",
    "delete_rule",
    "ensure_channel",
    "get_rule",
    "list_channels",
]
