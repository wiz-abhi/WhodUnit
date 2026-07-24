"""Trace Explorer permalink construction.

Reverse-engineered live from SigNoz v0.132.2 (see ``NOTES.md``). The Explorer
reads a single ``compositeQuery`` URL parameter holding the front-end builder
state as JSON. Two facts, both verified against a running instance:

* The parameter value is **double** URL-encoded — the SPA stores the state
  already ``encodeURIComponent``-encoded, then serialises it into the query
  string, encoding a second time. So ``{`` appears as ``%257B``. We reproduce
  that with a double :func:`urllib.parse.quote`.
* The builder state carries a first-class ``builder.queryTraceOperator`` array
  and every leaf carries a v5 ``filter.expression``. That means the trace
  operator **does** deep-link: navigating the constructed URL renders the leaves
  and the ``(A => B) && NOT C`` operator and fires a ``200`` ``query_range`` — no
  fallback to a bare leaf-A view is needed on this version.

Absolute time is NOT URL-addressable here: the Explorer's global time picker
strips ``startTime``/``endTime`` params on load. We still append them (harmless)
so the caller's window is recorded in the link, and document the limitation.
"""

from __future__ import annotations

import json
import uuid
from typing import Any
from urllib.parse import quote

from whodunit.materialize import _queries
from whodunit.types import CompiledQuery

EXPLORER_PATH = "/traces-explorer"


def _query_data_entry(name: str, expression: str) -> dict[str, Any]:
    """One ``builder.queryData`` leaf in the front-end builder shape.

    Marked ``disabled`` because leaves are operands of the trace operator, not
    standalone series the Explorer should also plot.
    """
    return {
        "dataSource": "traces",
        "queryName": name,
        "aggregateAttribute": {"id": "----", "dataType": "", "key": "", "type": ""},
        "timeAggregation": "rate",
        "spaceAggregation": "sum",
        "filter": {"expression": expression},
        "aggregations": [{"expression": "count()"}],
        "functions": [],
        "filters": {"items": [], "op": "AND"},
        "expression": name,
        "disabled": True,
        "stepInterval": None,
        "having": [],
        "limit": None,
        "orderBy": [],
        "groupBy": [],
        "legend": "",
        "reduceTo": "avg",
    }


def _trace_operator_entry(compiled: CompiledQuery) -> dict[str, Any]:
    from whodunit.compile.emit import COUNT_DISTINCT_TRACE

    return {
        "name": _queries.operator_name(compiled),
        "expression": compiled.expression,
        "returnSpansFrom": compiled.return_spans_from,
        "aggregations": [{"expression": COUNT_DISTINCT_TRACE}],
        "filter": {"expression": ""},
        "disabled": False,
        "stepInterval": None,
        "legend": "",
    }


def composite_query_state(compiled: CompiledQuery) -> dict[str, Any]:
    """The decoded ``compositeQuery`` front-end state for ``compiled``."""
    query_data = [
        _query_data_entry(leaf.name, _queries.leaf_expression(leaf))
        for leaf in compiled.leaf_queries
    ]
    return {
        "queryType": "builder",
        "builder": {
            "queryData": query_data,
            "queryFormulas": [],
            "queryTraceOperator": [_trace_operator_entry(compiled)],
        },
        "promql": [{"name": "A", "query": "", "legend": "", "disabled": False}],
        "clickhouse_sql": [
            {"name": "A", "legend": "", "disabled": False, "query": ""}
        ],
        "id": str(uuid.uuid4()),
        "unit": "",
    }


def _encode_composite(state: dict[str, Any]) -> str:
    """Double URL-encode the compact JSON, matching the SPA's own encoding."""
    compact = json.dumps(state, separators=(",", ":"))
    return quote(quote(compact, safe=""), safe="")


def build_permalink(
    compiled: CompiledQuery,
    *,
    ui_base_url: str,
    window_start_ms: int,
    window_end_ms: int,
) -> str:
    """Construct the Trace Explorer permalink for ``compiled``.

    ``window_start_ms`` / ``window_end_ms`` are appended as ``startTime`` /
    ``endTime`` for provenance; the v0.132.2 Explorer manages time via its global
    picker and may ignore them (see module docstring / ``NOTES.md``).
    """
    if not compiled.leaf_queries:
        raise ValueError("cannot build a permalink for a query with no leaves")
    encoded = _encode_composite(composite_query_state(compiled))
    base = ui_base_url.rstrip("/")
    return (
        f"{base}{EXPLORER_PATH}?compositeQuery={encoded}"
        f"&startTime={window_start_ms}&endTime={window_end_ms}"
    )


__all__ = ["build_permalink", "composite_query_state"]
