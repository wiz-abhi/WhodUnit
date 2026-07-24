"""Low-level helpers for talking to SigNoz's v5 ``clickhouse_sql`` query type.

Everything the extractor sends to SigNoz goes through here, so the "one product,
works against any SigNoz, never docker exec" contract is enforced in one place.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from whodunit.signoz_client import SigNozClient


def quote_ident(name: str) -> str:
    """Backtick-quote a ClickHouse identifier (needed for ``$$`` columns like
    ``resource_string_service$$name``). Backticks inside are doubled."""
    escaped = name.replace("`", "``")
    return f"`{escaped}`"


def sql_str(value: str) -> str:
    """Render a Python string as a single-quoted ClickHouse string literal."""
    return "'" + value.replace("\\", "\\\\").replace("'", "\\'") + "'"


def env_predicate(environment: str | None) -> str:
    """A ``deployment.environment`` scope predicate (always-true when None).

    Keeps concurrent probe agents' artifacts out of our cohorts.
    """
    if not environment:
        return "1 = 1"
    return f"resources_string['deployment.environment'] = {sql_str(environment)}"


def id_list_predicate(column: str, trace_ids: list[str] | tuple[str, ...]) -> str:
    """``column IN ('a','b',...)`` for scoping a scan to an explicit id set."""
    if not trace_ids:
        return "0 = 1"
    joined = ", ".join(sql_str(t) for t in trace_ids)
    return f"{column} IN ({joined})"


def build_envelope(sql: str, start_ms: int, end_ms: int, name: str = "S") -> dict[str, Any]:
    """The v5 ``clickhouse_sql`` envelope that the live stack accepts."""
    return {
        "schemaVersion": "v1",
        "start": start_ms,
        "end": end_ms,
        "requestType": "raw",
        "compositeQuery": {
            "queries": [
                {
                    "type": "clickhouse_sql",
                    "spec": {"name": name, "query": sql, "disabled": False},
                }
            ]
        },
    }


class ExecStats:
    """Cost-meter numbers surfaced from the response ``meta`` block.

    CAVEAT: ``bucket_cache.mergeBuckets`` sums stats from *cached* buckets into
    ExecStats, so these can over-report actual ClickHouse work when buckets are
    warm. Surfaced as a cost meter with that disclosure; not a billing figure.
    """

    __slots__ = ("bytes_scanned", "duration_ms", "rows_scanned")

    def __init__(
        self,
        rows_scanned: int | None,
        bytes_scanned: int | None,
        duration_ms: float | None,
    ) -> None:
        self.rows_scanned = rows_scanned
        self.bytes_scanned = bytes_scanned
        self.duration_ms = duration_ms

    @classmethod
    def from_meta(cls, meta: dict[str, Any] | None) -> ExecStats:
        meta = meta or {}
        rs = meta.get("rowsScanned")
        bs = meta.get("bytesScanned")
        dm = meta.get("durationMs")
        return cls(
            rows_scanned=int(rs) if rs is not None else None,
            bytes_scanned=int(bs) if bs is not None else None,
            duration_ms=float(dm) if dm is not None else None,
        )


def _extract_rows(payload: dict[str, Any]) -> list[dict[str, Any]]:
    data = payload.get("data", {})
    inner = data.get("data", {})
    results = inner.get("results") or []
    if not results:
        return []
    rows = results[0].get("rows") or []
    out: list[dict[str, Any]] = []
    for row in rows:
        d = row.get("data") if isinstance(row, dict) else None
        if isinstance(d, dict):
            out.append(d)
    return out


def query_clickhouse_sql(
    client: SigNozClient, sql: str, start_ms: int, end_ms: int, name: str = "S"
) -> tuple[list[dict[str, Any]], ExecStats]:
    """Run one ``clickhouse_sql`` query; return (rows, exec-stats)."""
    payload = client.query_range(build_envelope(sql, start_ms, end_ms, name))
    meta = payload.get("data", {}).get("meta")
    return _extract_rows(payload), ExecStats.from_meta(meta)


def run_clickhouse_sql(
    client: SigNozClient, sql: str, start_ms: int, end_ms: int, name: str = "S"
) -> list[dict[str, Any]]:
    """Convenience wrapper returning only the rows."""
    rows, _ = query_clickhouse_sql(client, sql, start_ms, end_ms, name)
    return rows
