"""Unit tests for cohort resolution and case-control matching (no network)."""

from __future__ import annotations

from typing import Any

import pytest

from whodunit.extract.cohort import (
    CohortSpec,
    MatchingConfig,
    _duration_edges,
    _stratum_key,
    _TraceRow,
    resolve_cohorts,
)


def _row(tid: str, ep: str, start_ns: int, dur: int) -> _TraceRow:
    return _TraceRow(trace_id=tid, root_name=ep, start_ns=start_ns, duration_ns=dur)


def _rows_payload(rows: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "data": {
            "meta": {},
            "data": {"results": [{"rows": [{"data": r} for r in rows]}]},
        }
    }


class FakeClient:
    """Returns a fixed root-span frame for every query."""

    def __init__(self, frame: list[dict[str, Any]]) -> None:
        self._frame = frame
        self.calls: list[str] = []

    def query_range(self, payload: dict[str, Any]) -> dict[str, Any]:
        sql = payload["compositeQuery"]["queries"][0]["spec"]["query"]
        self.calls.append(sql)
        return _rows_payload(self._frame)


def test_cohortspec_requires_exactly_one_selector() -> None:
    with pytest.raises(ValueError):
        CohortSpec(window_start_unix_ms=0, window_end_unix_ms=1)
    with pytest.raises(ValueError):
        CohortSpec(0, 1, trace_ids=("a",), ch_filter="has_error=1")
    # Either one alone is fine.
    CohortSpec(0, 1, trace_ids=("a",))
    CohortSpec(0, 1, ch_filter="has_error = 1")


def test_duration_edges_are_monotonic() -> None:
    rows = [_row(f"t{i}", "ep", 0, i * 100) for i in range(10)]
    edges = _duration_edges(rows, 4)
    assert edges == sorted(edges)
    assert len(edges) <= 3


def test_stratum_key_axes_toggle() -> None:
    r = _row("t", "checkout", 1_000_000_000_000, 5000)
    cfg = MatchingConfig(
        match_endpoint=True, match_time_bucket=False, match_duration_stratum=False
    )
    assert _stratum_key(r, cfg, []) == ("ep=checkout",)
    cfg2 = MatchingConfig(
        match_endpoint=False, match_time_bucket=True, match_duration_stratum=False,
        time_bucket_seconds=900,
    )
    key = _stratum_key(r, cfg2, [])
    assert key[0].startswith("tb=")


def test_resolve_all_strategy_keeps_full_healthy_pool() -> None:
    frame = [
        {"trace_id": "b1", "root_name": "checkout", "start_ns": 0, "duration_ns": 10},
        {"trace_id": "b2", "root_name": "checkout", "start_ns": 0, "duration_ns": 10},
        {"trace_id": "h1", "root_name": "checkout", "start_ns": 0, "duration_ns": 10},
        {"trace_id": "h2", "root_name": "checkout", "start_ns": 0, "duration_ns": 10},
        {"trace_id": "h3", "root_name": "checkout", "start_ns": 0, "duration_ns": 10},
    ]
    client = FakeClient(frame)
    spec = CohortSpec(0, 1, trace_ids=("b1", "b2"))
    resolved = resolve_cohorts(
        client,  # type: ignore[arg-type]
        spec,
        MatchingConfig(strategy="all"),
    )
    assert set(resolved.bad_ids) == {"b1", "b2"}
    assert set(resolved.healthy_ids) == {"h1", "h2", "h3"}
    assert "endpoint" in resolved.matched_on


def test_resolve_stratified_mirrors_marginals_and_is_deterministic() -> None:
    # 2 bad in stratum A; a big healthy pool in A and some in B.
    frame: list[dict[str, Any]] = []
    for i in range(2):
        frame.append({"trace_id": f"b{i}", "root_name": "A", "start_ns": 0,
                      "duration_ns": 10})
    for i in range(20):
        frame.append({"trace_id": f"hA{i}", "root_name": "A", "start_ns": 0,
                      "duration_ns": 10})
    for i in range(20):
        frame.append({"trace_id": f"hB{i}", "root_name": "B", "start_ns": 0,
                      "duration_ns": 10})
    spec = CohortSpec(0, 1, trace_ids=("b0", "b1"))
    cfg = MatchingConfig(strategy="stratified", ratio=3.0, seed=42,
                         match_time_bucket=False, match_duration_stratum=False)
    r1 = resolve_cohorts(FakeClient(frame), spec, cfg)  # type: ignore[arg-type]
    r2 = resolve_cohorts(FakeClient(frame), spec, cfg)  # type: ignore[arg-type]
    # Deterministic under seed.
    assert r1.healthy_ids == r2.healthy_ids
    # Bad cohort is only in stratum A, so no stratum-B healthy is drawn.
    assert all(h.startswith("hA") for h in r1.healthy_ids)
    # ratio 3 * 2 bad = 6 healthy requested from stratum A.
    assert len(r1.healthy_ids) == 6


def test_resolve_stratified_is_invariant_to_input_row_order() -> None:
    """The sampled healthy cohort must not depend on the order ClickHouse returns
    rows in. The scan is unordered and ``bad_ids`` is a set, so without sorting the
    pool before ``rng.sample`` the same seed draws a different cohort per process —
    breaking the verdict-hash determinism guarantee. This shuffles the frame and
    asserts an identical cohort; it fails before the sort-the-pool fix."""
    base: list[dict[str, Any]] = [
        {"trace_id": f"b{i}", "root_name": "A", "start_ns": 0, "duration_ns": 10}
        for i in range(2)
    ]
    base += [
        {"trace_id": f"hA{i:02d}", "root_name": "A", "start_ns": 0, "duration_ns": 10}
        for i in range(20)
    ]
    spec = CohortSpec(0, 1, trace_ids=("b0", "b1"))
    cfg = MatchingConfig(strategy="stratified", ratio=3.0, seed=42,
                         match_time_bucket=False, match_duration_stratum=False)

    forward = resolve_cohorts(FakeClient(base), spec, cfg)  # type: ignore[arg-type]
    reversed_ = resolve_cohorts(
        FakeClient(list(reversed(base))), spec, cfg  # type: ignore[arg-type]
    )
    rotated = resolve_cohorts(
        FakeClient(base[7:] + base[:7]), spec, cfg  # type: ignore[arg-type]
    )
    assert set(forward.healthy_ids) == set(reversed_.healthy_ids) == set(rotated.healthy_ids)
    assert len(forward.healthy_ids) == 6
