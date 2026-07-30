"""Stage 0 — cohort definition with nuisance-variable control.

The single most common failure mode of every tool in this category is returning
the axis the user *selected on*. If you pick outliers off a latency scatter,
``duration > X`` separates perfectly and explains nothing. Whodunit applies
**case-control matching** from epidemiology: the healthy cohort is a stratified
sample of healthy traffic chosen to mirror the bad cohort's marginal
distribution over the *selection axis* (endpoint mix, time bucket, and — the one
that actually bites — a duration stratum). A discriminator cannot be the
selection axis if the axis is held constant by construction.

This module resolves a :class:`CohortSpec` (bad cohort as an explicit
``trace_id`` list *or* a ClickHouse boolean filter fragment, over a time window)
into two concrete ``trace_id`` sets plus the axes they were matched on. It talks
to SigNoz only through the v5 ``clickhouse_sql`` path — never ``docker exec`` —
so it works against any SigNoz.

Honest limits (documented, not hidden):

* Matching is **stratified sampling on observed marginals**, not full
  propensity-score matching; it controls the axes we bucket on and nothing else.
* When the healthy pool is smaller than the requested matched size, we take the
  whole pool and report the achieved (imperfect) balance rather than fabricating
  rows. The ``strategy="all"`` mode skips sampling entirely (every healthy trace
  in window), which is the honest choice when the pool is already comparable in
  size to the bad cohort.
"""

from __future__ import annotations

import random
from collections import Counter
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Literal

from .sql import env_predicate, quote_ident, run_clickhouse_sql

if TYPE_CHECKING:
    from whodunit.signoz_client import SigNozClient

MatchStrategy = Literal["all", "stratified"]

_SERVICE_COL = quote_ident("resource_string_service$$name")
_TRACE_TABLE = "signoz_traces.distributed_signoz_index_v3"


@dataclass(frozen=True)
class CohortSpec:
    """Definition of the *bad* cohort and the window it lives in.

    Exactly one of ``trace_ids`` or ``ch_filter`` must be supplied.

    Parameters
    ----------
    window_start_unix_ms, window_end_unix_ms:
        The scan/verification window (also passed to the v5 envelope).
    trace_ids:
        An explicit bad set (a support ticket, an alert's condition result).
    ch_filter:
        A ClickHouse boolean expression over ``signoz_index_v3`` columns that a
        trace's spans are tested against; a trace is *bad* if any of its spans
        match. e.g. ``"has_error = 1"`` or ``"name = 'redis-retry'"``.
    environment:
        ``deployment.environment`` scope. Keeps other agents' artifacts out.
    """

    window_start_unix_ms: int
    window_end_unix_ms: int
    trace_ids: tuple[str, ...] | None = None
    ch_filter: str | None = None
    environment: str | None = "whodunit-demo"

    def __post_init__(self) -> None:
        if bool(self.trace_ids) == bool(self.ch_filter):
            raise ValueError(
                "CohortSpec needs exactly one of trace_ids or ch_filter"
            )


@dataclass(frozen=True)
class MatchingConfig:
    """How the healthy control cohort is drawn.

    Parameters
    ----------
    strategy:
        ``"all"`` — every healthy trace in window (no sampling). Correct when the
        healthy pool is already comparable to the bad cohort.
        ``"stratified"`` — sample healthy traces to mirror the bad cohort's
        marginal distribution over the matching axes.
    match_endpoint:
        Match on endpoint mix (root span name — the selection axis for
        request-scoped incidents).
    match_time_bucket:
        Match on coarse time bucket (guards against diurnal / deploy-window
        confounding). ``time_bucket_seconds`` sets the granularity.
    match_duration_stratum:
        Match on a root-span duration quantile stratum (``n_duration_strata``
        buckets). This is the axis that most often leaks as a false
        discriminator, so it is on by default.
    ratio:
        Target healthy:bad ratio for ``"stratified"``. The realised cohort may be
        smaller if a stratum's healthy pool is exhausted.
    seed:
        Deterministic sampling seed.
    """

    strategy: MatchStrategy = "stratified"
    match_endpoint: bool = True
    match_time_bucket: bool = True
    match_duration_stratum: bool = True
    time_bucket_seconds: int = 900
    n_duration_strata: int = 4
    ratio: float = 4.0
    seed: int = 42


@dataclass(frozen=True)
class _TraceRow:
    trace_id: str
    root_name: str
    start_ns: int
    duration_ns: int


@dataclass(frozen=True)
class ResolvedCohorts:
    """The output of :func:`resolve_cohorts` — two concrete id sets + provenance."""

    bad_ids: tuple[str, ...]
    healthy_ids: tuple[str, ...]
    matched_on: tuple[str, ...]
    # Per-axis marginal share of the bad vs the healthy cohort, for honesty.
    balance: dict[str, dict[str, float]] = field(default_factory=dict)

    @property
    def all_ids(self) -> tuple[str, ...]:
        return self.bad_ids + self.healthy_ids


def _fetch_trace_rows(
    client: SigNozClient, spec: CohortSpec
) -> list[_TraceRow]:
    """Root-span metadata for every trace in the window/env (the matching frame)."""
    env = env_predicate(spec.environment)
    # Root span = the min-timestamp span with empty parent_span_id; fall back to
    # global min-timestamp span if a trace has no captured root.
    sql = f"""
    WITH base AS (
        SELECT trace_id, name, parent_span_id,
               toUnixTimestamp64Nano(timestamp) AS start_ns, duration_nano
        FROM {_TRACE_TABLE}
        WHERE {env}
    )
    SELECT
        toString(trace_id) AS trace_id,
        argMin(name, if(parent_span_id = '', 0, 1)) AS root_name,
        min(start_ns) AS start_ns,
        max(duration_nano) AS duration_ns
    FROM base
    GROUP BY trace_id
    """
    rows = run_clickhouse_sql(
        client, sql, spec.window_start_unix_ms, spec.window_end_unix_ms
    )
    out: list[_TraceRow] = []
    for r in rows:
        out.append(
            _TraceRow(
                trace_id=str(r["trace_id"]),
                root_name=str(r.get("root_name", "")),
                start_ns=int(r.get("start_ns", 0) or 0),
                duration_ns=int(r.get("duration_ns", 0) or 0),
            )
        )
    return out


def _resolve_bad_ids(
    client: SigNozClient, spec: CohortSpec, frame: list[_TraceRow]
) -> set[str]:
    if spec.trace_ids is not None:
        return set(spec.trace_ids)
    assert spec.ch_filter is not None
    env = env_predicate(spec.environment)
    sql = f"""
    SELECT DISTINCT toString(trace_id) AS trace_id
    FROM {_TRACE_TABLE}
    WHERE {env} AND ({spec.ch_filter})
    """
    rows = run_clickhouse_sql(
        client, sql, spec.window_start_unix_ms, spec.window_end_unix_ms
    )
    return {str(r["trace_id"]) for r in rows}


def _stratum_key(
    row: _TraceRow,
    cfg: MatchingConfig,
    duration_edges: list[int],
) -> tuple[str, ...]:
    parts: list[str] = []
    if cfg.match_endpoint:
        parts.append(f"ep={row.root_name}")
    if cfg.match_time_bucket:
        bucket = row.start_ns // (cfg.time_bucket_seconds * 1_000_000_000)
        parts.append(f"tb={bucket}")
    if cfg.match_duration_stratum:
        stratum = 0
        for i, edge in enumerate(duration_edges):
            if row.duration_ns >= edge:
                stratum = i + 1
        parts.append(f"ds={stratum}")
    return tuple(parts)


def _duration_edges(bad_rows: list[_TraceRow], n_strata: int) -> list[int]:
    """Quantile edges of the *bad* cohort's durations (so strata track the axis
    the bad cohort spans, which is what we must hold constant)."""
    if n_strata <= 1 or not bad_rows:
        return []
    durs = sorted(r.duration_ns for r in bad_rows)
    edges: list[int] = []
    for i in range(1, n_strata):
        q = i / n_strata
        idx = min(len(durs) - 1, int(q * len(durs)))
        edges.append(durs[idx])
    # Keep monotonic & de-duplicated.
    uniq: list[int] = []
    for e in edges:
        if not uniq or e > uniq[-1]:
            uniq.append(e)
    return uniq


def _matched_on(cfg: MatchingConfig) -> tuple[str, ...]:
    axes: list[str] = []
    if cfg.match_endpoint:
        axes.append("endpoint")
    if cfg.match_time_bucket:
        axes.append("time_bucket")
    if cfg.match_duration_stratum:
        axes.append("duration_stratum")
    return tuple(axes)


def _balance_report(
    bad_rows: list[_TraceRow],
    healthy_rows: list[_TraceRow],
    cfg: MatchingConfig,
    duration_edges: list[int],
) -> dict[str, dict[str, float]]:
    """Marginal share per stratum for bad vs healthy — a legibility receipt."""

    def marginals(rows: list[_TraceRow]) -> dict[str, float]:
        if not rows:
            return {}
        counts = Counter(
            "|".join(_stratum_key(r, cfg, duration_edges)) for r in rows
        )
        n = float(len(rows))
        return {k: round(v / n, 4) for k, v in counts.items()}

    return {"bad": marginals(bad_rows), "healthy": marginals(healthy_rows)}


def resolve_cohorts(
    client: SigNozClient,
    spec: CohortSpec,
    matching: MatchingConfig | None = None,
) -> ResolvedCohorts:
    """Resolve a :class:`CohortSpec` into matched bad/healthy ``trace_id`` sets.

    Steps: pull the root-span matching frame; resolve the bad set (explicit or
    via the ClickHouse filter); the candidate healthy pool is *every other trace
    in window*; then either take all of it (``strategy="all"``) or stratified-
    sample it to mirror the bad cohort's marginals.
    """
    cfg = matching or MatchingConfig()
    frame = _fetch_trace_rows(client, spec)
    by_id = {r.trace_id: r for r in frame}

    bad_ids = _resolve_bad_ids(client, spec, frame) & set(by_id)
    bad_rows = [by_id[t] for t in bad_ids]
    healthy_pool = [r for r in frame if r.trace_id not in bad_ids]

    edges = _duration_edges(bad_rows, cfg.n_duration_strata)

    if cfg.strategy == "all" or not bad_rows:
        healthy_rows = healthy_pool
    else:
        healthy_rows = _stratified_sample(bad_rows, healthy_pool, cfg, edges)

    balance = _balance_report(bad_rows, healthy_rows, cfg, edges)
    return ResolvedCohorts(
        bad_ids=tuple(sorted(bad_ids)),
        healthy_ids=tuple(sorted(r.trace_id for r in healthy_rows)),
        matched_on=_matched_on(cfg),
        balance=balance,
    )


def _stratified_sample(
    bad_rows: list[_TraceRow],
    healthy_pool: list[_TraceRow],
    cfg: MatchingConfig,
    duration_edges: list[int],
) -> list[_TraceRow]:
    """Draw healthy traces so their stratum marginals mirror the bad cohort.

    For each stratum we want ``round(ratio * n_bad_in_stratum)`` healthy traces;
    if the stratum's healthy pool is thinner we take all of it (and the balance
    report will show the shortfall honestly).
    """
    rng = random.Random(cfg.seed)

    bad_by_stratum: dict[tuple[str, ...], int] = Counter(
        _stratum_key(r, cfg, duration_edges) for r in bad_rows
    )
    healthy_by_stratum: dict[tuple[str, ...], list[_TraceRow]] = {}
    for r in healthy_pool:
        healthy_by_stratum.setdefault(
            _stratum_key(r, cfg, duration_edges), []
        ).append(r)

    chosen: list[_TraceRow] = []
    # Iterate strata and pools in a fixed order so the seeded RNG draws the same
    # healthy cohort across processes. Without this, ``bad_ids`` is a set and the
    # healthy pool order follows the (unordered) scan, so the sample — and thus the
    # verdict hash — varies with PYTHONHASHSEED / ClickHouse row order.
    for stratum, n_bad in sorted(bad_by_stratum.items()):
        pool = sorted(healthy_by_stratum.get(stratum, []), key=lambda r: r.trace_id)
        want = round(cfg.ratio * n_bad)
        if want >= len(pool):
            chosen.extend(pool)
        else:
            chosen.extend(rng.sample(pool, want))
    return chosen
