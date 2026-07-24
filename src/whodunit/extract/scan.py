"""Stage 1 — THE ONE SCAN.

A single generated ClickHouse ``SELECT`` (executed via the v5 ``clickhouse_sql``
query type, *never* ``docker exec``) materialises a per-``trace_id`` boolean
feature matrix + label:

* **span-predicate** features — ``(service, name)`` presence, ``status ERROR``
  presence, latency buckets from **raw ``duration_nano``** (never
  ``signoz_latency.bucket`` whose 18 coarse boundaries cannot support a
  distributional test), and selected ``attributes_string`` values
  (``cache.hit``, feature-flag keys, ``order.completed``);
* **edge** features — ``parent => child`` via a self-join on
  ``p.trace_id = c.trace_id AND p.span_id = c.parent_span_id``;
* **ancestor** features — depth-bounded reachability via a ``WITH RECURSIVE``
  closure (mirroring ``buildIndirectDescendantCTE``'s ``depth < 100``, capped at
  a sane depth like 10);
* **log** features — error-template + body-token presence from
  ``signoz_logs`` joined by ``trace_id`` (the cross-signal move — same
  ClickHouse, physically impossible on Tempo+Loki);
* the **outcome label** from the cohort spec.

Before the scan we prime a cheap **vocabulary oracle**: the span/edge/attribute
vocabularies come from lightweight ``GROUP BY`` probes (and the
``dependency_graph_minutes_v2`` service-edge oracle), each candidate ranked by
its *prevalence gap* between the bad and healthy cohorts so the cardinality cap
keeps the most discriminative columns first.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal

from whodunit.types import FeatureColumn, FeatureKind

from .sql import (
    ExecStats,
    env_predicate,
    id_list_predicate,
    query_clickhouse_sql,
    quote_ident,
    run_clickhouse_sql,
    sql_str,
)

if TYPE_CHECKING:
    from whodunit.signoz_client import SigNozClient

_TRACE_TABLE = "signoz_traces.distributed_signoz_index_v3"
_LOGS_TABLE = "signoz_logs.distributed_logs_v2"
_DEPGRAPH_TABLE = "signoz_traces.distributed_dependency_graph_minutes_v2"
_SVC = quote_ident("resource_string_service$$name")

_IDENT_RE = re.compile(r"[^0-9a-zA-Z]+")


def _slug(text: str) -> str:
    s = _IDENT_RE.sub("_", text).strip("_")
    return s or "x"


@dataclass(frozen=True)
class ScanConfig:
    """Knobs for the one scan.

    Parameters
    ----------
    max_features:
        Hard cardinality cap. Candidates are ranked by prevalence gap between
        cohorts and the top ``max_features`` survive.
    include_edges, include_ancestors, include_logs, include_attributes,
    include_duration:
        Toggle whole feature families.
    ancestor_max_depth:
        Recursion bound for the reachability closure (mirrors the engine's
        ``depth < 100``, kept sane).
    attribute_keys:
        ``attributes_string`` keys to expand into value-presence features. Each
        observed value (capped by ``max_attribute_values``) becomes one column.
    log_tokens:
        Body substrings to turn into log-presence features (case-insensitive).
    n_duration_buckets:
        Number of raw-``duration_nano`` quantile buckets.
    min_prevalence_gap:
        Drop candidates whose |bad_share - healthy_share| is below this (pure
        noise columns). ``0.0`` keeps everything up to ``max_features``.
    """

    max_features: int = 500
    include_edges: bool = True
    include_ancestors: bool = True
    include_logs: bool = True
    include_attributes: bool = True
    include_duration: bool = True
    ancestor_max_depth: int = 10
    attribute_keys: tuple[str, ...] = ("cache.hit", "order.completed")
    max_attribute_values: int = 6
    log_tokens: tuple[str, ...] = ()
    auto_error_log_feature: bool = True
    n_duration_buckets: int = 6
    max_edge_features: int = 120
    min_prevalence_gap: float = 0.0


_Mode = Literal["agg", "edge", "ancestor", "log"]


@dataclass(frozen=True)
class _ScanFeature:
    """A candidate column: its metadata + how the wide SQL computes it."""

    column: FeatureColumn
    mode: _Mode
    gap: float
    agg_expr: str | None = None  # mode="agg": boolean expr over a base span row
    parent_pred: str | None = None  # mode edge/ancestor
    child_pred: str | None = None  # mode edge/ancestor
    log_pred: str | None = None  # mode="log"


@dataclass
class ScanResult:
    """Rows (list of dicts, one per trace) + column metadata + cost meter."""

    rows: list[dict[str, object]]
    columns: list[FeatureColumn]
    exec_stats: ExecStats
    sql: str


# --------------------------------------------------------------------------- #
# Vocabulary discovery (the cheap oracle)
# --------------------------------------------------------------------------- #
def _shares(n_bad: int, n_healthy: int, tot_bad: int, tot_healthy: int) -> float:
    sb = n_bad / tot_bad if tot_bad else 0.0
    sh = n_healthy / tot_healthy if tot_healthy else 0.0
    return abs(sb - sh)


def _discover_span_features(
    client: SigNozClient,
    *,
    env: str,
    scope: str,
    badlist: str,
    start_ms: int,
    end_ms: int,
    tot_bad: int,
    tot_healthy: int,
) -> list[_ScanFeature]:
    sql = f"""
    SELECT svc, name,
        countDistinctIf(trace_id, is_bad) AS nb,
        countDistinctIf(trace_id, NOT is_bad) AS nh
    FROM (
        SELECT trace_id, {_SVC} AS svc, name, {badlist} AS is_bad
        FROM {_TRACE_TABLE} WHERE {env} AND {scope}
    )
    GROUP BY svc, name
    """
    rows = run_clickhouse_sql(client, sql, start_ms, end_ms)
    feats: list[_ScanFeature] = []
    services: set[str] = set()
    for r in rows:
        svc = str(r.get("svc", ""))
        name = str(r.get("name", ""))
        nb, nh = int(r.get("nb", 0)), int(r.get("nh", 0))
        gap = _shares(nb, nh, tot_bad, tot_healthy)
        col = FeatureColumn(
            name=f"span__{_slug(svc)}__{_slug(name)}",
            kind=FeatureKind.SPAN_PREDICATE,
            description=f"trace contains a {svc!r} span named {name!r}",
            service_name=svc,
            span_name=name,
            requires_span_level_negation=False,  # existence → trace-scoped, safe
        )
        expr = f"svc = {sql_str(svc)} AND name = {sql_str(name)}"
        feats.append(_ScanFeature(col, "agg", gap, agg_expr=expr))
        services.add(svc)
    # Service-presence features (coarser structural predicate).
    svc_counts = _service_counts(client, env=env, scope=scope, badlist=badlist,
                                 start_ms=start_ms, end_ms=end_ms)
    for svc in sorted(services):
        nb, nh = svc_counts.get(svc, (0, 0))
        gap = _shares(nb, nh, tot_bad, tot_healthy)
        col = FeatureColumn(
            name=f"svc__{_slug(svc)}",
            kind=FeatureKind.SPAN_PREDICATE,
            description=f"trace contains any {svc!r} span",
            service_name=svc,
            requires_span_level_negation=False,
        )
        feats.append(
            _ScanFeature(col, "agg", gap, agg_expr=f"svc = {sql_str(svc)}")
        )
    return feats


def _service_counts(
    client: SigNozClient, *, env: str, scope: str, badlist: str,
    start_ms: int, end_ms: int,
) -> dict[str, tuple[int, int]]:
    sql = f"""
    SELECT svc,
        countDistinctIf(trace_id, is_bad) AS nb,
        countDistinctIf(trace_id, NOT is_bad) AS nh
    FROM (SELECT trace_id, {_SVC} AS svc, {badlist} AS is_bad
          FROM {_TRACE_TABLE} WHERE {env} AND {scope})
    GROUP BY svc
    """
    out: dict[str, tuple[int, int]] = {}
    for r in run_clickhouse_sql(client, sql, start_ms, end_ms):
        out[str(r.get("svc", ""))] = (int(r.get("nb", 0)), int(r.get("nh", 0)))
    return out


def _status_feature(
    client: SigNozClient, *, env: str, scope: str, badlist: str,
    start_ms: int, end_ms: int, tot_bad: int, tot_healthy: int,
) -> _ScanFeature | None:
    sql = f"""
    SELECT countDistinctIf(trace_id, is_bad AND has_error) AS nb,
           countDistinctIf(trace_id, (NOT is_bad) AND has_error) AS nh
    FROM (SELECT trace_id, has_error, {badlist} AS is_bad
          FROM {_TRACE_TABLE} WHERE {env} AND {scope})
    """
    rows = run_clickhouse_sql(client, sql, start_ms, end_ms)
    if not rows:
        return None
    nb, nh = int(rows[0].get("nb", 0)), int(rows[0].get("nh", 0))
    col = FeatureColumn(
        name="status_error",
        kind=FeatureKind.SPAN_PREDICATE,
        description="trace contains a span with ERROR status",
        status="ERROR",
        requires_span_level_negation=False,
    )
    return _ScanFeature(col, "agg", _shares(nb, nh, tot_bad, tot_healthy),
                        agg_expr="has_error")


def _discover_duration_features(
    client: SigNozClient, *, env: str, scope: str, start_ms: int, end_ms: int,
    n_buckets: int,
) -> list[_ScanFeature]:
    if n_buckets < 2:
        return []
    qs = [round(i / n_buckets, 4) for i in range(1, n_buckets)]
    qexpr = ", ".join(str(q) for q in qs)
    sql = f"""
    SELECT quantilesExact({qexpr})(duration_nano) AS q
    FROM {_TRACE_TABLE} WHERE {env} AND {scope}
    """
    rows = run_clickhouse_sql(client, sql, start_ms, end_ms)
    if not rows:
        return []
    raw = rows[0].get("q") or []
    edges = sorted({int(x) for x in raw})
    bounds: list[tuple[int | None, int | None]] = []
    prev: int | None = None
    for e in edges:
        bounds.append((prev, e))
        prev = e
    bounds.append((prev, None))
    feats: list[_ScanFeature] = []
    for lo, hi in bounds:
        conds = []
        if lo is not None:
            conds.append(f"duration_nano >= {lo}")
        if hi is not None:
            conds.append(f"duration_nano < {hi}")
        expr = " AND ".join(conds) if conds else "1"
        col = FeatureColumn(
            name=f"dur__ge{lo or 0}_lt{hi if hi is not None else 'inf'}",
            kind=FeatureKind.SPAN_PREDICATE,
            description=f"trace has a span with duration_nano in [{lo}, {hi})",
            duration_ge_ns=lo,
            duration_lt_ns=hi,
            # span-quantitative predicate: the *useful* negation ("this span
            # type is present but not slow") is span-scoped → flag it.
            requires_span_level_negation=True,
        )
        # gap unknown cheaply; assign a neutral mid gap so they survive unless
        # crowded out (duration is context, not usually the discriminator).
        feats.append(_ScanFeature(col, "agg", 0.05, agg_expr=expr))
    return feats


def _discover_attribute_features(
    client: SigNozClient, *, env: str, scope: str, badlist: str,
    start_ms: int, end_ms: int, keys: tuple[str, ...], max_values: int,
    tot_bad: int, tot_healthy: int,
) -> list[_ScanFeature]:
    feats: list[_ScanFeature] = []
    for key in keys:
        klit = sql_str(key)
        sql = f"""
        SELECT val,
            countDistinctIf(trace_id, is_bad) AS nb,
            countDistinctIf(trace_id, NOT is_bad) AS nh
        FROM (
            SELECT trace_id, attributes_string[{klit}] AS val, {badlist} AS is_bad
            FROM {_TRACE_TABLE}
            WHERE {env} AND {scope} AND has(attributes_string, {klit})
        )
        WHERE val != ''
        GROUP BY val ORDER BY (nb + nh) DESC LIMIT {max_values}
        """
        for r in run_clickhouse_sql(client, sql, start_ms, end_ms):
            val = str(r.get("val", ""))
            nb, nh = int(r.get("nb", 0)), int(r.get("nh", 0))
            col = FeatureColumn(
                name=f"attr__{_slug(key)}__{_slug(val)}",
                kind=FeatureKind.SPAN_PREDICATE,
                description=f"trace has a span with {key}={val!r}",
                # attribute-on-a-span: negation "that span lacks the attr value"
                # is span-scoped → the compiler must refuse to complement it.
                requires_span_level_negation=True,
            )
            expr = f"attributes_string[{klit}] = {sql_str(val)}"
            feats.append(
                _ScanFeature(col, "agg", _shares(nb, nh, tot_bad, tot_healthy),
                             agg_expr=expr)
            )
    return feats


def _oracle_service_edges(
    client: SigNozClient, *, environment: str | None, start_ms: int, end_ms: int,
) -> set[tuple[str, str]]:
    """Cheap service-edge vocabulary from dependency_graph_minutes_v2.

    Cross-service edges only (it is pre-aggregated and cannot see intra-service
    parent/child structure like ``payment => redis-retry``); used to confirm the
    cross-service edge vocabulary exists in-window before the scan spends work.
    """
    where = "1 = 1"
    if environment:
        where = f"deployment_environment = {sql_str(environment)}"
    sql = f"SELECT DISTINCT src, dest FROM {_DEPGRAPH_TABLE} WHERE {where}"
    edges: set[tuple[str, str]] = set()
    try:
        for r in run_clickhouse_sql(client, sql, start_ms, end_ms):
            edges.add((str(r.get("src", "")), str(r.get("dest", ""))))
    except Exception:
        return set()
    return edges


def _discover_edge_features(
    client: SigNozClient, *, env: str, scope: str, badlist: str,
    start_ms: int, end_ms: int, tot_bad: int, tot_healthy: int, cap: int,
) -> list[_ScanFeature]:
    # Name-level edge oracle via the self-join (catches intra-service edges the
    # dependency-graph oracle cannot see, e.g. payment.charge => redis-retry).
    sql = f"""
    WITH base AS (
        SELECT trace_id, span_id, parent_span_id, name, {_SVC} AS svc
        FROM {_TRACE_TABLE} WHERE {env} AND {scope}
    )
    SELECT p.svc AS psvc, c.name AS cname,
        countDistinctIf(c.trace_id, {badlist.replace('trace_id', 'c.trace_id')}) AS nb,
        countDistinctIf(c.trace_id, NOT ({badlist.replace('trace_id', 'c.trace_id')})) AS nh
    FROM base p INNER JOIN base c
      ON p.trace_id = c.trace_id AND p.span_id = c.parent_span_id
    GROUP BY psvc, cname
    ORDER BY abs(nb - nh) DESC
    LIMIT {cap}
    """
    feats: list[_ScanFeature] = []
    for r in run_clickhouse_sql(client, sql, start_ms, end_ms):
        psvc = str(r.get("psvc", ""))
        cname = str(r.get("cname", ""))
        nb, nh = int(r.get("nb", 0)), int(r.get("nh", 0))
        col = FeatureColumn(
            name=f"edge__{_slug(psvc)}__{_slug(cname)}",
            kind=FeatureKind.EDGE,
            description=f"a {cname!r} span directly under a {psvc!r} span",
            edge_parent=psvc,
            edge_child=cname,
            requires_span_level_negation=False,  # edge existence → trace-scoped
        )
        feats.append(
            _ScanFeature(
                col, "edge", _shares(nb, nh, tot_bad, tot_healthy),
                parent_pred=f"p.svc = {sql_str(psvc)}",
                child_pred=f"c.name = {sql_str(cname)}",
            )
        )
    return feats


def _ancestor_features_from_edges(edges: list[_ScanFeature]) -> list[_ScanFeature]:
    """Depth-bounded ancestor version of each edge (reachability, not just
    direct parenthood). Reuses the edge vocabulary."""
    feats: list[_ScanFeature] = []
    for e in edges:
        assert e.column.edge_parent is not None
        assert e.column.edge_child is not None
        col = FeatureColumn(
            name=f"anc__{_slug(e.column.edge_parent)}__{_slug(e.column.edge_child)}",
            kind=FeatureKind.ANCESTOR,
            description=(
                f"a {e.column.edge_child!r} span reachable below a "
                f"{e.column.edge_parent!r} span (depth-bounded)"
            ),
            edge_parent=e.column.edge_parent,
            edge_child=e.column.edge_child,
            requires_span_level_negation=False,
        )
        feats.append(
            _ScanFeature(
                col, "ancestor", e.gap,
                parent_pred=f"anc_svc = {sql_str(e.column.edge_parent)}",
                child_pred=f"cur_name = {sql_str(e.column.edge_child)}",
            )
        )
    return feats


def _log_features(
    client: SigNozClient, *, environment: str | None, scope: str, badlist: str,
    start_ms: int, end_ms: int, tokens: tuple[str, ...], auto_error: bool,
    tot_bad: int, tot_healthy: int,
) -> list[_ScanFeature]:
    logenv = env_predicate(environment)
    all_tokens = list(tokens)
    feats: list[_ScanFeature] = []

    def token_counts(pred: str) -> tuple[int, int]:
        sql = f"""
        SELECT countDistinctIf(trace_id, is_bad) AS nb,
               countDistinctIf(trace_id, NOT is_bad) AS nh
        FROM (SELECT toString(trace_id) AS trace_id, {badlist} AS is_bad
              FROM {_LOGS_TABLE} WHERE {logenv} AND ({pred}))
        """
        rows = run_clickhouse_sql(client, sql, start_ms, end_ms)
        if not rows:
            return (0, 0)
        return (int(rows[0].get("nb", 0)), int(rows[0].get("nh", 0)))

    for tok in all_tokens:
        pred = f"body ILIKE {sql_str('%' + tok + '%')}"
        nb, nh = token_counts(pred)
        col = FeatureColumn(
            name=f"log__{_slug(tok)}",
            kind=FeatureKind.LOG,
            description=f"a log line on this trace contains {tok!r}",
            requires_span_level_negation=False,
        )
        feats.append(_ScanFeature(col, "log", _shares(nb, nh, tot_bad, tot_healthy),
                                  log_pred=pred))

    if auto_error:
        pred = "severity_text IN ('ERROR', 'FATAL', 'Error', 'error')"
        nb, nh = token_counts(pred)
        col = FeatureColumn(
            name="log__error_template",
            kind=FeatureKind.LOG,
            description="this trace has an ERROR/FATAL-severity log line",
            requires_span_level_negation=False,
        )
        feats.append(_ScanFeature(col, "log", _shares(nb, nh, tot_bad, tot_healthy),
                                  log_pred=pred))
    return feats


# --------------------------------------------------------------------------- #
# Wide-scan SQL generation
# --------------------------------------------------------------------------- #
def _build_scan_sql(
    *, env: str, scope: str, badlist: str, environment: str | None,
    features: list[_ScanFeature], ancestor_max_depth: int,
) -> str:
    agg = [f for f in features if f.mode == "agg"]
    edges = [f for f in features if f.mode == "edge"]
    ancestors = [f for f in features if f.mode == "ancestor"]
    logs = [f for f in features if f.mode == "log"]

    ctes: list[str] = []
    recursive = bool(ancestors)
    ctes.append(
        f"""base AS (
        SELECT trace_id, span_id, parent_span_id, name,
               {_SVC} AS svc, duration_nano, has_error, attributes_string
        FROM {_TRACE_TABLE} WHERE {env} AND {scope}
    )"""
    )

    edge_names: list[tuple[str, _ScanFeature]] = []
    for i, f in enumerate(edges):
        cte = f"edge_{i}"
        edge_names.append((cte, f))
        ctes.append(
            f"""{cte} AS (
            SELECT DISTINCT c.trace_id AS trace_id
            FROM base p INNER JOIN base c
              ON p.trace_id = c.trace_id AND p.span_id = c.parent_span_id
            WHERE {f.parent_pred} AND {f.child_pred}
        )"""
        )

    if recursive:
        ctes.append(
            f"""closure AS (
            SELECT trace_id, span_id AS cur, name AS cur_name, svc AS anc_svc, 0 AS depth
            FROM base
            UNION ALL
            SELECT r.trace_id, ch.span_id, ch.name, r.anc_svc, r.depth + 1
            FROM closure r INNER JOIN base ch
              ON r.trace_id = ch.trace_id AND r.cur = ch.parent_span_id
            WHERE r.depth < {ancestor_max_depth}
        )"""
        )
    anc_names: list[tuple[str, _ScanFeature]] = []
    for i, f in enumerate(ancestors):
        cte = f"anc_{i}"
        anc_names.append((cte, f))
        ctes.append(
            f"""{cte} AS (
            SELECT DISTINCT trace_id FROM closure
            WHERE depth > 0 AND {f.parent_pred} AND {f.child_pred}
        )"""
        )

    logenv = env_predicate(environment)
    log_names: list[tuple[str, _ScanFeature]] = []
    for i, f in enumerate(logs):
        cte = f"log_{i}"
        log_names.append((cte, f))
        ctes.append(
            f"""{cte} AS (
            SELECT DISTINCT toString(trace_id) AS trace_id
            FROM {_LOGS_TABLE} WHERE {logenv} AND ({f.log_pred})
        )"""
        )

    # per_trace aggregation for the agg-mode features.
    agg_selects = [
        f"maxIf(toUInt8(1), {f.agg_expr}) AS {f.column.name}" for f in agg
    ]
    pt_body = ",\n            ".join(["trace_id", *agg_selects]) or "trace_id"
    ctes.append(
        f"""per_trace AS (
        SELECT {pt_body}
        FROM base GROUP BY trace_id
    )"""
    )

    final_cols: list[str] = [
        "toString(pt.trace_id) AS trace_id",
        f"toUInt8({badlist.replace('trace_id', 'pt.trace_id')}) AS label",
    ]
    for f in agg:
        final_cols.append(f"toUInt8(pt.{f.column.name}) AS {f.column.name}")
    for cte, f in edge_names:
        final_cols.append(
            f"toUInt8(pt.trace_id IN (SELECT trace_id FROM {cte})) AS {f.column.name}"
        )
    for cte, f in anc_names:
        final_cols.append(
            f"toUInt8(pt.trace_id IN (SELECT trace_id FROM {cte})) AS {f.column.name}"
        )
    for cte, f in log_names:
        final_cols.append(
            f"toUInt8(pt.trace_id IN (SELECT trace_id FROM {cte})) AS {f.column.name}"
        )

    with_kw = "WITH RECURSIVE" if recursive else "WITH"
    select_body = ",\n        ".join(final_cols)
    joined_ctes = ",\n    ".join(ctes)
    return f"{with_kw} {joined_ctes}\n    SELECT {select_body}\n    FROM per_trace pt"


# --------------------------------------------------------------------------- #
# Public entry point
# --------------------------------------------------------------------------- #
def run_scan(
    client: SigNozClient,
    *,
    bad_ids: tuple[str, ...] | list[str],
    healthy_ids: tuple[str, ...] | list[str],
    window_start_unix_ms: int,
    window_end_unix_ms: int,
    environment: str | None = "whodunit-demo",
    config: ScanConfig | None = None,
) -> ScanResult:
    """Discover a bounded feature vocabulary, then run THE ONE SCAN.

    Returns per-trace boolean rows (with a ``label`` column), the surviving
    :class:`FeatureColumn` metadata, the ExecStats cost meter, and the exact SQL.
    """
    cfg = config or ScanConfig()
    bad = tuple(bad_ids)
    healthy = tuple(healthy_ids)
    all_ids = list(bad) + list(healthy)

    env = env_predicate(environment)
    scope = id_list_predicate("trace_id", all_ids)
    badlist = id_list_predicate("trace_id", bad)
    start_ms, end_ms = window_start_unix_ms, window_end_unix_ms
    tot_bad, tot_healthy = len(bad), len(healthy)

    candidates: list[_ScanFeature] = []
    candidates += _discover_span_features(
        client, env=env, scope=scope, badlist=badlist, start_ms=start_ms,
        end_ms=end_ms, tot_bad=tot_bad, tot_healthy=tot_healthy,
    )
    status = _status_feature(
        client, env=env, scope=scope, badlist=badlist, start_ms=start_ms,
        end_ms=end_ms, tot_bad=tot_bad, tot_healthy=tot_healthy,
    )
    if status is not None:
        candidates.append(status)
    if cfg.include_duration:
        candidates += _discover_duration_features(
            client, env=env, scope=scope, start_ms=start_ms, end_ms=end_ms,
            n_buckets=cfg.n_duration_buckets,
        )
    if cfg.include_attributes:
        candidates += _discover_attribute_features(
            client, env=env, scope=scope, badlist=badlist, start_ms=start_ms,
            end_ms=end_ms, keys=cfg.attribute_keys,
            max_values=cfg.max_attribute_values, tot_bad=tot_bad,
            tot_healthy=tot_healthy,
        )
    edge_feats: list[_ScanFeature] = []
    if cfg.include_edges:
        # Prime the service-edge oracle (advisory, documented) then discover
        # name-level edges via the self-join.
        _oracle_service_edges(
            client, environment=environment, start_ms=start_ms, end_ms=end_ms
        )
        edge_feats = _discover_edge_features(
            client, env=env, scope=scope, badlist=badlist, start_ms=start_ms,
            end_ms=end_ms, tot_bad=tot_bad, tot_healthy=tot_healthy,
            cap=cfg.max_edge_features,
        )
        candidates += edge_feats
    if cfg.include_ancestors and edge_feats:
        candidates += _ancestor_features_from_edges(edge_feats)
    if cfg.include_logs:
        candidates += _log_features(
            client, environment=environment, scope=scope, badlist=badlist,
            start_ms=start_ms, end_ms=end_ms, tokens=cfg.log_tokens,
            auto_error=cfg.auto_error_log_feature, tot_bad=tot_bad,
            tot_healthy=tot_healthy,
        )

    # Cardinality guard: drop below-threshold gaps, keep top-gap features, then
    # de-duplicate column names deterministically.
    kept = _prune(candidates, cfg)

    sql = _build_scan_sql(
        env=env, scope=scope, badlist=badlist, environment=environment,
        features=kept, ancestor_max_depth=cfg.ancestor_max_depth,
    )
    rows, stats = query_clickhouse_sql(client, sql, start_ms, end_ms, name="SCAN")
    return ScanResult(rows=rows, columns=[f.column for f in kept],
                      exec_stats=stats, sql=sql)


def _prune(candidates: list[_ScanFeature], cfg: ScanConfig) -> list[_ScanFeature]:
    seen: set[str] = set()
    uniq: list[_ScanFeature] = []
    for f in candidates:
        if f.column.name in seen:
            continue
        if f.gap < cfg.min_prevalence_gap:
            continue
        seen.add(f.column.name)
        uniq.append(f)
    # Stable sort by prevalence gap (desc), then name for determinism.
    uniq.sort(key=lambda f: (-f.gap, f.column.name))
    return uniq[: cfg.max_features]
