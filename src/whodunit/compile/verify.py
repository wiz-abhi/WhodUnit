"""Differential verification — the money shot.

Execute the compiled companion scalar (``count_distinct(trace_id)`` over the
operator) against the live engine, compare to the count the miner computed
locally, and — by fetching the operator's actual result ``trace_id`` set —
report precision and recall against the labelled bad cohort.

Count scoping (verified, see ``ENGINE-NOTES.md`` / ``PROBES.md``): operator
results are span-scoped (one row per returned span); ``count_distinct(trace_id)``
collapses to trace scope, which is what we verify against.
"""

from __future__ import annotations

import copy
import re
from typing import Any

from whodunit.signoz_client import SigNozClient
from whodunit.types import CompiledQuery, Verification

_TRACE_LIMIT = 10000  # Limit > 10000 is rejected by the engine.


def operator_query_name(envelope: dict[str, Any]) -> str:
    """Return the name of the ``builder_trace_operator`` query in an envelope."""
    for query in _queries(envelope):
        if query.get("type") == "builder_trace_operator":
            spec = query.get("spec", {})
            name = spec.get("name") if isinstance(spec, dict) else None
            if isinstance(name, str):
                return name
    raise ValueError("envelope contains no builder_trace_operator query")


def _queries(envelope: dict[str, Any]) -> list[dict[str, Any]]:
    composite = envelope.get("compositeQuery", {})
    queries = composite.get("queries", []) if isinstance(composite, dict) else []
    return [q for q in queries if isinstance(q, dict)]


def scalar_value(response: dict[str, Any], query_name: str) -> int:
    """Extract a scalar aggregation value for ``query_name`` from a response."""
    results = _results(response)
    for result in results:
        if result.get("queryName") == query_name:
            data = result.get("data")
            if isinstance(data, list) and data and isinstance(data[0], list) and data[0]:
                return int(data[0][0])
            # The query ran but matched nothing: a genuine zero, not an error.
            # (A truly absent query name still raises below.)
            return 0
    raise ValueError(f"no scalar value for query {query_name!r} in response")


def _results(response: dict[str, Any]) -> list[dict[str, Any]]:
    data = response.get("data", {})
    inner = data.get("data", {}) if isinstance(data, dict) else {}
    results = inner.get("results", []) if isinstance(inner, dict) else []
    return [r for r in results if isinstance(r, dict)]


def _rows_scanned(response: dict[str, Any]) -> int | None:
    data = response.get("data", {})
    meta = data.get("meta", {}) if isinstance(data, dict) else {}
    value = meta.get("rowsScanned") if isinstance(meta, dict) else None
    return int(value) if isinstance(value, int) else None


def _scoped_envelope(compiled: CompiledQuery, start: int, end: int) -> dict[str, Any]:
    envelope = copy.deepcopy(compiled.envelope)
    envelope["start"] = start
    envelope["end"] = end
    return envelope


def fetch_matched_trace_ids(
    client: SigNozClient,
    compiled: CompiledQuery,
    *,
    start: int,
    end: int,
    limit: int = _TRACE_LIMIT,
) -> set[str]:
    """Fetch the operator's result ``trace_id`` set via the ``trace`` request type.

    Paginated by ``nextCursor`` and capped at ``limit`` rows per page.
    """
    envelope = _scoped_envelope(compiled, start, end)
    envelope["requestType"] = "trace"
    op_name = operator_query_name(envelope)

    # A "trace" request rejects scalar-only siblings (e.g. count_distinct
    # denominators lack a LIMIT). Keep only the operator and the leaves it
    # references by name.
    referenced = _referenced_leaf_names(envelope, op_name)
    kept: list[dict[str, Any]] = []
    for query in _queries(envelope):
        spec = query.get("spec", {})
        name = spec.get("name") if isinstance(spec, dict) else None
        if query.get("type") == "builder_trace_operator":
            # In "trace" mode the operator returns rows, not a scalar; a lingering
            # scalar aggregation makes ClickHouse emit an empty-LIMIT CTE.
            spec.pop("aggregations", None)
            spec["limit"] = limit
            spec["order"] = [{"key": {"name": "timestamp"}, "direction": "desc"}]
            spec["selectFields"] = [{"name": "trace_id"}]
            kept.append(query)
        elif name in referenced:
            kept.append(query)
    envelope["compositeQuery"]["queries"] = kept

    trace_ids: set[str] = set()
    cursor = ""
    while True:
        if cursor:
            for query in _queries(envelope):
                if query.get("type") == "builder_trace_operator":
                    query["spec"]["cursor"] = cursor
        response = client.query_range(envelope)
        next_cursor = ""
        rows_seen = 0
        for result in _results(response):
            if result.get("queryName") != op_name:
                continue
            next_cursor = str(result.get("nextCursor") or "")
            rows = result.get("rows")
            if isinstance(rows, list):
                for row in rows:
                    tid = _row_trace_id(row)
                    if tid is not None:
                        trace_ids.add(tid)
                        rows_seen += 1
        # Stop when the engine hands back no next page, or when the cursor stops
        # advancing (a guard against an empty page paired with a repeated cursor).
        # Crucially we do NOT stop merely because one page was empty while a *new*
        # cursor was returned — that would silently truncate the matched set.
        if not next_cursor or next_cursor == cursor:
            break
        cursor = next_cursor
    return trace_ids


def _referenced_leaf_names(envelope: dict[str, Any], op_name: str) -> set[str]:
    """Leaf query names appearing as tokens in the operator's expression."""
    for query in _queries(envelope):
        spec = query.get("spec", {})
        if query.get("type") == "builder_trace_operator" and isinstance(spec, dict):
            expression = str(spec.get("expression", ""))
            tokens = set(re.findall(r"[A-Za-z][A-Za-z0-9_]*", expression))
            return {t for t in tokens if t != "NOT" and t != op_name}
    return set()


def _row_trace_id(row: object) -> str | None:
    if isinstance(row, dict):
        data = row.get("data")
        if isinstance(data, dict):
            tid = data.get("trace_id")
            if isinstance(tid, str) and tid:
                return tid
    return None


def verify(
    client: SigNozClient,
    compiled: CompiledQuery,
    *,
    mined_count: int,
    start: int,
    end: int,
    bad_trace_ids: set[str] | None = None,
    with_precision_recall: bool = True,
) -> Verification:
    """Run the compiled companion scalar and build a verification receipt.

    ``bad_trace_ids`` is the labelled bad cohort; when provided (and
    ``with_precision_recall``), precision/recall are computed from the operator's
    actual matched ``trace_id`` set.
    """
    envelope = _scoped_envelope(compiled, start, end)
    op_name = operator_query_name(envelope)
    response = client.query_range(envelope)
    signoz_count = scalar_value(response, op_name)
    rows_scanned = _rows_scanned(response)

    precision: float | None = None
    recall: float | None = None
    if with_precision_recall and bad_trace_ids is not None:
        matched = fetch_matched_trace_ids(client, compiled, start=start, end=end)
        precision, recall = precision_recall(matched, bad_trace_ids)

    return Verification(
        mined_count=mined_count,
        signoz_count=signoz_count,
        match=signoz_count == mined_count,
        precision=precision,
        recall=recall,
        rows_scanned=rows_scanned,
    )


def precision_recall(
    matched: set[str], bad_trace_ids: set[str]
) -> tuple[float | None, float | None]:
    """Precision/recall of ``matched`` (compiled query hits) vs the bad cohort."""
    true_positives = len(matched & bad_trace_ids)
    precision = true_positives / len(matched) if matched else None
    recall = true_positives / len(bad_trace_ids) if bad_trace_ids else None
    return precision, recall


__all__ = [
    "fetch_matched_trace_ids",
    "operator_query_name",
    "precision_recall",
    "scalar_value",
    "verify",
]
