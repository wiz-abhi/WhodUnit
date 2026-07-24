"""Live differential-verification tests against the running SigNoz stack.

Gated on ``SIGNOZ_LIVE=1`` (plus SigNoz credentials in the environment). These
prove the crown-jewel claim end-to-end: the ground-truth conjunction compiles to
a query the engine agrees with (``signoz_count == 55 == mined_count``), with
precision/recall against the labelled cohort.
"""

from __future__ import annotations

import os
import time

import pytest

from whodunit.compile.conformance import run_conformance, to_markdown
from whodunit.compile.emit import compile_finding
from whodunit.compile.verify import fetch_matched_trace_ids, verify
from whodunit.signoz_client import SigNozClient, SigNozConfig
from whodunit.types import FeatureColumn, FeatureKind, Finding, Verdict

pytestmark = [
    pytest.mark.live,
    pytest.mark.skipif(
        os.environ.get("SIGNOZ_LIVE") != "1",
        reason="live SigNoz stack required (set SIGNOZ_LIVE=1)",
    ),
]

BASE_FILTER = "deployment.environment = 'whodunit-demo'"


def _window() -> tuple[int, int]:
    now = int(time.time() * 1000)
    return now - 30 * 24 * 3600 * 1000, now


def _ground_truth() -> tuple[Finding, list[FeatureColumn]]:
    cols = [
        FeatureColumn(
            name="pay_redis_edge",
            kind=FeatureKind.EDGE,
            edge_parent="shop-payment",
            edge_child="span:redis-retry",
        ),
        FeatureColumn(
            name="flag_service",
            kind=FeatureKind.SPAN_PREDICATE,
            service_name="shop-flag-service",
        ),
    ]
    finding = Finding(
        itemset=["NOT flag_service", "pay_redis_edge"],
        lift=41.0,
        ci_low=30.0,
        ci_high=55.0,
        support_bad=55,
        support_healthy=1,
        verdict=Verdict.DISCRIMINATOR,
    )
    return finding, cols


def test_ground_truth_conjunction_verifies_55() -> None:
    finding, cols = _ground_truth()
    start, end = _window()
    compiled = compile_finding(finding, cols, base_filter=BASE_FILTER, start=start, end=end)
    assert not compiled.refusals

    with SigNozClient(SigNozConfig()) as client:
        matched = fetch_matched_trace_ids(client, compiled, start=start, end=end)
        result = verify(
            client,
            compiled,
            mined_count=55,
            start=start,
            end=end,
            bad_trace_ids=matched,
        )

    assert result.signoz_count == 55
    assert result.mined_count == 55
    assert result.match is True
    # Compiled query hits exactly the cohort it is verified against.
    assert result.precision == 1.0
    assert result.recall == 1.0


def test_conformance_table_ground_truth_row() -> None:
    start, end = _window()
    leaves = {
        "A": "service.name = 'shop-payment'",
        "B": "name = 'redis-retry'",
        "C": "service.name = 'shop-flag-service'",
    }
    with SigNozClient(SigNozConfig()) as client:
        rows = run_conformance(client, leaves, base_filter=BASE_FILTER, start=start, end=end)

    table = {r.expression: r for r in rows}
    assert table["(A => B) && NOT C"].operator_count == 55
    assert table["A => B"].operator_count == 276
    assert table["B => A"].operator_count == 0  # directional
    # Markdown renders without error.
    assert "| Shape |" in to_markdown(rows)
