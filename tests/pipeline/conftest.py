"""Fixtures for the pipeline + CLI tests.

A ``FakeClient`` stands in for the network: it answers the compiled query's
scalar ``count_distinct(trace_id)`` with a fixed number, so verification runs for
real against a controlled response. The synthetic matrix plants an EDGE feature
(``shop-payment`` -> ``redis-retry`` span) plus a ``shop-flag-service`` presence
feature so ``edge ∧ ¬flag`` is a perfect separator — mirroring the corpus
``conditional_dep`` flagship and exercising the edge-naming contract seam.
"""

from __future__ import annotations

from typing import Any

import polars as pl
import pytest

from whodunit.extract import MaterializedMatrix
from whodunit.types import FeatureColumn, FeatureKind, FeatureMatrix

EDGE_NAME = "edge__shop_payment__redis_retry"
FLAG_NAME = "svc__shop_flag_service"
NOISE_NAME = "svc__shop_cart"

N_BAD = 40
N_HEALTHY_GROUP = 40  # three healthy groups -> 120 healthy


def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line(
        "markers",
        "live: full-pipeline tests against a running SigNoz stack (SIGNOZ_LIVE=1).",
    )


class FakeClient:
    """A minimal SigNozClient stand-in that only answers scalar query_range."""

    def __init__(self, scalar_count: int, rows_scanned: int = 4880) -> None:
        self.scalar_count = scalar_count
        self.rows_scanned = rows_scanned
        self.calls: list[dict[str, Any]] = []

    def query_range(self, payload: dict[str, Any]) -> dict[str, Any]:
        self.calls.append(payload)
        op_name = "T1"
        for query in payload.get("compositeQuery", {}).get("queries", []):
            if query.get("type") == "builder_trace_operator":
                op_name = query["spec"]["name"]
        return {
            "data": {
                "data": {"results": [{"queryName": op_name, "data": [[self.scalar_count]]}]},
                "meta": {"rowsScanned": self.rows_scanned},
            }
        }

    def __enter__(self) -> FakeClient:
        return self

    def __exit__(self, *_: object) -> None:
        return None

    def close(self) -> None:
        return None


def build_synthetic_matrix() -> MaterializedMatrix:
    """A trace x feature matrix where ``edge ∧ ¬flag`` separates perfectly."""
    columns = [
        FeatureColumn(
            name=EDGE_NAME,
            kind=FeatureKind.EDGE,
            description="a 'redis-retry' span directly under a 'shop-payment' span",
            edge_parent="shop-payment",
            edge_child="redis-retry",  # a SPAN name (the seam the pipeline reconciles)
        ),
        FeatureColumn(
            name=FLAG_NAME,
            kind=FeatureKind.SPAN_PREDICATE,
            description="trace contains any 'shop-flag-service' span",
            service_name="shop-flag-service",
        ),
        FeatureColumn(
            name=NOISE_NAME,
            kind=FeatureKind.SPAN_PREDICATE,
            description="trace contains any 'shop-cart' span",
            service_name="shop-cart",
        ),
    ]

    labels: list[int] = []
    edge: list[int] = []
    flag: list[int] = []
    noise: list[int] = []
    tids: list[str] = []
    i = 0

    def add(n: int, label: int, e: int, f: int) -> None:
        nonlocal i
        for _ in range(n):
            tids.append(f"trace{i:05d}")
            labels.append(label)
            edge.append(e)
            flag.append(f)
            noise.append(i % 2)  # decorrelated from label
            i += 1

    add(N_BAD, 1, 1, 0)  # bad: edge present, flag absent
    add(N_HEALTHY_GROUP, 0, 1, 1)  # healthy: edge present but flag present
    add(N_HEALTHY_GROUP, 0, 0, 0)  # healthy: no edge, flag absent
    add(N_HEALTHY_GROUP, 0, 0, 1)  # healthy: no edge, flag present

    frame = pl.DataFrame(
        {
            "trace_id": tids,
            "label": pl.Series(labels, dtype=pl.Int8),
            EDGE_NAME: pl.Series(edge, dtype=pl.Int8),
            FLAG_NAME: pl.Series(flag, dtype=pl.Int8),
            NOISE_NAME: pl.Series(noise, dtype=pl.Int8),
        }
    )
    meta = FeatureMatrix(
        columns=columns,
        n_traces_bad=N_BAD,
        n_traces_healthy=3 * N_HEALTHY_GROUP,
        matched_on=["endpoint", "duration_stratum"],
        window_start_unix_ms=1_000,
        window_end_unix_ms=2_000,
        bad_cohort_filter="order.completed = false",
        rows_scanned=4880,
        bytes_scanned=123456,
        duration_ms=42.0,
    )
    return MaterializedMatrix(frame=frame, meta=meta)


@pytest.fixture
def synthetic_matrix() -> MaterializedMatrix:
    return build_synthetic_matrix()


@pytest.fixture
def fake_client() -> FakeClient:
    # The perfect separator matches exactly the 40 bad traces.
    return FakeClient(scalar_count=N_BAD)
