"""Sanity tests for the shared pydantic models."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from whodunit.types import (
    CompiledQuery,
    FeatureColumn,
    FeatureKind,
    FeatureMatrix,
    Finding,
    LeafQuery,
    Verdict,
    Verification,
)


def test_feature_matrix_total() -> None:
    matrix = FeatureMatrix(
        columns=[FeatureColumn(name="svc_a__error", kind=FeatureKind.SPAN_PREDICATE)],
        n_traces_bad=100,
        n_traces_healthy=400,
        matched_on=["endpoint", "latency_stratum"],
    )
    assert matrix.n_traces_total == 500


def test_leaf_query_name_pattern_rejected() -> None:
    with pytest.raises(ValidationError):
        LeafQuery(name="1bad-name")


def test_finding_and_verdict() -> None:
    finding = Finding(
        itemset=["svc_payment__redis", "NOT flag-service"],
        lift=41.0,
        ci_low=30.0,
        ci_high=55.0,
        support_bad=1284,
        support_healthy=12,
        verdict=Verdict.DISCRIMINATOR,
    )
    assert finding.verdict is Verdict.DISCRIMINATOR
    assert "NOT flag-service" in finding.itemset


def test_compiled_query_carries_verification() -> None:
    compiled = CompiledQuery(
        envelope={"type": "builder_trace_operator"},
        expression="(A => B) && NOT C",
        return_spans_from="A",
        leaf_queries=[LeafQuery(name="A"), LeafQuery(name="B"), LeafQuery(name="C")],
        verification=Verification(
            mined_count=1284, signoz_count=1284, match=True, precision=0.98, recall=0.95
        ),
    )
    assert compiled.verification is not None
    assert compiled.verification.match is True
