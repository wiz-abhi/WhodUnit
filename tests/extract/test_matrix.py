"""Unit tests for matrix materialisation, persistence and absence encoding.

Uses a small synthetic :class:`ScanResult` fixture — no network.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from whodunit.extract.matrix import (
    build_feature_matrix,
    load_matrix,
    save_matrix,
    virtual_negation,
)
from whodunit.extract.scan import ScanResult
from whodunit.extract.sql import ExecStats
from whodunit.types import FeatureColumn, FeatureKind


@pytest.fixture
def synthetic_scan() -> ScanResult:
    cols = [
        FeatureColumn(
            name="edge__shop_payment__redis_retry",
            kind=FeatureKind.EDGE,
            edge_parent="shop-payment",
            edge_child="redis-retry",
            requires_span_level_negation=False,
        ),
        FeatureColumn(
            name="svc__shop_flag_service",
            kind=FeatureKind.SPAN_PREDICATE,
            service_name="shop-flag-service",
            requires_span_level_negation=False,
        ),
        FeatureColumn(
            name="attr__cache_hit__false",
            kind=FeatureKind.SPAN_PREDICATE,
            requires_span_level_negation=True,
        ),
    ]
    # 4 traces: 2 bad (edge & not-flag), 2 healthy.
    rows: list[dict[str, object]] = [
        {"trace_id": "t1", "label": 1, "edge__shop_payment__redis_retry": 1,
         "svc__shop_flag_service": 0, "attr__cache_hit__false": 1},
        {"trace_id": "t2", "label": 1, "edge__shop_payment__redis_retry": 1,
         "svc__shop_flag_service": 0, "attr__cache_hit__false": 0},
        {"trace_id": "t3", "label": 0, "edge__shop_payment__redis_retry": 1,
         "svc__shop_flag_service": 1, "attr__cache_hit__false": 0},
        {"trace_id": "t4", "label": 0, "edge__shop_payment__redis_retry": 0,
         "svc__shop_flag_service": 1, "attr__cache_hit__false": 0},
    ]
    stats = ExecStats(rows_scanned=99, bytes_scanned=1234, duration_ms=5.0)
    return ScanResult(rows=rows, columns=cols, exec_stats=stats, sql="SELECT ...")


def test_build_matrix_shape_and_meta(synthetic_scan: ScanResult) -> None:
    mm = build_feature_matrix(
        synthetic_scan, n_traces_bad=2, n_traces_healthy=2,
        matched_on=["endpoint", "duration_stratum"],
        window_start_unix_ms=1, window_end_unix_ms=2,
    )
    assert mm.frame.height == 4
    assert set(mm.frame.columns) == {
        "trace_id", "label", "edge__shop_payment__redis_retry",
        "svc__shop_flag_service", "attr__cache_hit__false",
    }
    assert mm.meta.n_traces_total == 4
    assert mm.meta.rows_scanned == 99
    assert mm.meta.bytes_scanned == 1234
    assert mm.meta.matched_on == ["endpoint", "duration_stratum"]


def test_prevalence_by_cohort(synthetic_scan: ScanResult) -> None:
    mm = build_feature_matrix(synthetic_scan, n_traces_bad=2, n_traces_healthy=2)
    # edge present in all bad, and in 1 of 2 healthy.
    assert mm.prevalence("edge__shop_payment__redis_retry", cohort="bad") == 2
    assert mm.prevalence("edge__shop_payment__redis_retry", cohort="healthy") == 1
    # flag-service present in neither bad, both healthy — the discriminator.
    assert mm.prevalence("svc__shop_flag_service", cohort="bad") == 0
    assert mm.prevalence("svc__shop_flag_service", cohort="healthy") == 2


def test_conjunction_is_perfect_separator(synthetic_scan: ScanResult) -> None:
    """edge AND NOT flag selects exactly the bad cohort (the ground truth)."""
    import polars as pl

    mm = build_feature_matrix(synthetic_scan, n_traces_bad=2, n_traces_healthy=2)
    selected = mm.frame.filter(
        (pl.col("edge__shop_payment__redis_retry") == 1)
        & (pl.col("svc__shop_flag_service") == 0)
    )
    assert sorted(selected["trace_id"].to_list()) == ["t1", "t2"]
    assert selected["label"].to_list() == [1, 1]


def test_virtual_negation_flags() -> None:
    trace_scoped = FeatureColumn(
        name="edge__a__b", kind=FeatureKind.EDGE, requires_span_level_negation=False
    )
    span_scoped = FeatureColumn(
        name="attr__x__y", kind=FeatureKind.SPAN_PREDICATE,
        requires_span_level_negation=True,
    )
    assert virtual_negation(trace_scoped) == ("NOT edge__a__b", False)
    assert virtual_negation(span_scoped) == ("NOT attr__x__y", True)


def test_save_load_roundtrip(synthetic_scan: ScanResult, tmp_path: Path) -> None:
    mm = build_feature_matrix(synthetic_scan, n_traces_bad=2, n_traces_healthy=2)
    parquet = save_matrix(mm, tmp_path, "m")
    assert parquet.exists()
    assert (tmp_path / "m.meta.json").exists()
    reloaded = load_matrix(tmp_path, "m")
    assert reloaded.frame.equals(mm.frame)
    assert reloaded.meta.n_traces_total == 4
    assert [c.name for c in reloaded.meta.columns] == [c.name for c in mm.meta.columns]
    # requires_span_level_negation survives the round trip.
    assert reloaded.meta.columns[2].requires_span_level_negation is True


def test_empty_scan_builds_empty_frame() -> None:
    empty = ScanResult(rows=[], columns=[], exec_stats=ExecStats(None, None, None),
                       sql="")
    mm = build_feature_matrix(empty, n_traces_bad=0, n_traces_healthy=0)
    assert mm.frame.height == 0
    assert mm.frame.columns == ["trace_id", "label"]
