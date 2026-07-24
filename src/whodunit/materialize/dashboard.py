"""Native v6 (Perses) dashboard authoring.

Probe 3 established there is no v1->v6 read conversion, so the v6 dashboard must
be authored natively. This module builds and POSTs that native artifact to
``/api/v2/dashboards``. The exact schema was reverse-engineered live (see
``NOTES.md``); the load-bearing facts:

* Top level: ``{"schemaVersion": "v6", "name": <str>, "spec": {...}}``. Unknown
  fields are rejected (strict Go decoding), so the shape below is exact.
* A panel plugin is one of ``signoz/{TimeSeries,Number,Table,BarChart,Histogram,
  Pie,List}Panel``. **There is no text/markdown panel kind in v6** — the
  verification receipt therefore rides in a panel's ``display.description``
  (markdown) rather than a dedicated text panel.
* A panel takes exactly one query. The whole trace-operator composite (leaves +
  ``builder_trace_operator`` + optional formula) is wrapped in a single
  ``signoz/CompositeQuery`` query plugin, whose ``spec.queries`` is the familiar
  typed array. The operator survives this native round-trip verbatim.
* Layout is Perses ``{"kind": "Grid", "spec": {"items": [...]}}`` on a 12-column
  grid; each item's ``content.$ref`` points at ``#/spec/panels/<key>``.
"""

from __future__ import annotations

import re
from typing import Any

from whodunit.materialize import _http, _queries
from whodunit.signoz_client import SigNozClient
from whodunit.types import CompiledQuery

DASHBOARDS_V2_PATH = "/api/v2/dashboards"
SCHEMA_VERSION = "v6"
GRID_WIDTH = 12

_SLUG_STRIP = re.compile(r"[^a-z0-9]+")


def slugify(title: str) -> str:
    """Reduce ``title`` to an RFC-1123 label, as v6 requires for top-level ``name``.

    v6 validates the top-level ``name`` as a lowercase RFC-1123 label (like a k8s
    name): ``[a-z0-9]([-a-z0-9]*[a-z0-9])?``. The human title still rides in
    ``spec.display.name``.
    """
    slug = _SLUG_STRIP.sub("-", title.lower()).strip("-")
    return slug or "whodunit-dashboard"


def _composite_query_plugin(queries: list[dict[str, Any]]) -> dict[str, Any]:
    """Wrap a typed queries array as a single time_series ``signoz/CompositeQuery``."""
    return {
        "kind": "time_series",
        "spec": {"plugin": {"kind": "signoz/CompositeQuery", "spec": {"queries": queries}}},
    }


def _panel(
    name: str,
    description: str,
    queries: list[dict[str, Any]],
    *,
    plugin_kind: str = "signoz/TimeSeriesPanel",
) -> dict[str, Any]:
    return {
        "kind": "Panel",
        "spec": {
            "display": {"name": name, "description": description},
            "plugin": {"kind": plugin_kind, "spec": {}},
            "queries": [_composite_query_plugin(queries)],
        },
    }


def _grid_item(panel_key: str, x: int, y: int, width: int, height: int) -> dict[str, Any]:
    return {
        "x": x,
        "y": y,
        "width": width,
        "height": height,
        "content": {"$ref": f"#/spec/panels/{panel_key}"},
    }


def receipt_markdown(compiled: CompiledQuery) -> str:
    """A markdown receipt embedding the expression and verification result."""
    lines = [
        f"**Discriminator:** `{compiled.expression}`",
        "",
        f"- returnSpansFrom: `{compiled.return_spans_from}`",
        f"- leaves: {', '.join(leaf.name for leaf in compiled.leaf_queries)}",
    ]
    v = compiled.verification
    if v is not None:
        verdict = "MATCH" if v.match else "MISMATCH"
        lines.append(
            f"- verification: mined {v.mined_count} / SigNoz {v.signoz_count} "
            f"-> {verdict}"
        )
        if v.precision is not None and v.recall is not None:
            lines.append(f"- precision {v.precision:.2f} / recall {v.recall:.2f}")
    if compiled.signoz_version:
        lines.append(f"- compiled against SigNoz `{compiled.signoz_version}`")
    return "\n".join(lines)


def build_dashboard(compiled: CompiledQuery, *, title: str) -> dict[str, Any]:
    """Build the full native-v6 dashboard body for ``compiled``."""
    if not compiled.leaf_queries:
        raise ValueError("cannot build a dashboard for a query with no leaves")

    panels = {
        "0": _panel(
            "Matching traces over time",
            f"count_distinct(trace_id) of {compiled.expression}",
            _queries.matching_count_queries(compiled),
        ),
        "1": _panel(
            "Share of traffic",
            "operator matches / anchor traffic (F1)",
            _queries.share_of_traffic_queries(compiled),
        ),
        "2": _panel(
            "Verification receipt",
            receipt_markdown(compiled),
            _queries.matching_count_queries(compiled),
            plugin_kind="signoz/NumberPanel",
        ),
    }
    layout_items = [
        _grid_item("0", 0, 0, GRID_WIDTH, 8),
        _grid_item("1", 0, 8, GRID_WIDTH // 2, 8),
        _grid_item("2", GRID_WIDTH // 2, 8, GRID_WIDTH // 2, 8),
    ]
    return {
        "schemaVersion": SCHEMA_VERSION,
        "name": slugify(title),
        "spec": {
            "display": {"name": title},
            "variables": [],
            "panels": panels,
            "layouts": [{"kind": "Grid", "spec": {"items": layout_items}}],
        },
    }


def create_dashboard(
    client: SigNozClient, compiled: CompiledQuery, *, title: str
) -> str:
    """POST a native v6 dashboard and return its id."""
    body = build_dashboard(compiled, title=title)
    data = _http.data_of(_http.request_json(client, "POST", DASHBOARDS_V2_PATH, json=body))
    dashboard_id = data.get("id")
    if not isinstance(dashboard_id, str) or not dashboard_id:
        raise ValueError(f"dashboard create returned no id: {data!r:.200}")
    return dashboard_id


def delete_dashboard(client: SigNozClient, dashboard_id: str) -> None:
    """DELETE a v6 dashboard (answers 204)."""
    _http.request(client, "DELETE", f"{DASHBOARDS_V2_PATH}/{dashboard_id}")


def get_dashboard(client: SigNozClient, dashboard_id: str) -> dict[str, Any]:
    """GET a v6 dashboard's stored ``data`` object."""
    return _http.data_of(
        _http.request_json(client, "GET", f"{DASHBOARDS_V2_PATH}/{dashboard_id}")
    )


__all__ = [
    "build_dashboard",
    "create_dashboard",
    "delete_dashboard",
    "get_dashboard",
    "receipt_markdown",
]
