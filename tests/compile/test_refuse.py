"""Adversarial tests for the refusal path — refusals are a feature."""

from __future__ import annotations

from whodunit.compile import refuse
from whodunit.compile.emit import compile_finding
from whodunit.types import FeatureColumn, FeatureKind, Finding, Verdict


def _finding(itemset: list[str]) -> Finding:
    return Finding(
        itemset=itemset,
        lift=10.0,
        ci_low=5.0,
        ci_high=15.0,
        support_bad=10,
        support_healthy=1,
        verdict=Verdict.DISCRIMINATOR,
    )


def test_span_level_negation_is_refused() -> None:
    col = FeatureColumn(
        name="cache_get",
        kind=FeatureKind.SPAN_PREDICATE,
        span_name="cache-get",
        requires_span_level_negation=True,
    )
    anchor = FeatureColumn(name="anchor", kind=FeatureKind.SPAN_PREDICATE, service_name="s")
    compiled = compile_finding(_finding(["anchor", "NOT cache_get"]), [col, anchor])
    assert compiled.envelope == {}
    assert len(compiled.refusals) == 1
    assert "trace-scoped" in compiled.refusals[0].reason
    assert compiled.refusals[0].itemset == ["anchor", "NOT cache_get"]


def test_log_feature_is_refused_with_clear_reason() -> None:
    col = FeatureColumn(name="tmpl", kind=FeatureKind.LOG, description="connection pool exhausted")
    compiled = compile_finding(_finding(["tmpl"]), [col])
    assert compiled.refusals[0].reason == refuse.REASON_LOG
    assert "ClickHouse join" in compiled.refusals[0].reason


def test_metric_feature_is_refused() -> None:
    col = FeatureColumn(name="m", kind=FeatureKind.METRIC)
    compiled = compile_finding(_finding(["m"]), [col])
    assert compiled.refusals[0].reason == refuse.REASON_METRIC


def test_unresolved_name_is_refused() -> None:
    compiled = compile_finding(_finding(["does_not_exist"]), [])
    assert "does not resolve" in compiled.refusals[0].reason


def test_absence_only_itemset_is_refused() -> None:
    col = FeatureColumn(name="f", kind=FeatureKind.SPAN_PREDICATE, service_name="flag")
    compiled = compile_finding(_finding(["NOT f"]), [col])
    assert compiled.envelope == {}
    assert "absence-only" in compiled.refusals[0].reason


def test_eleven_operators_exceeds_cap() -> None:
    # 6 edge features => 6 "=>" + 5 "&&" = 11 operators > MaxTraceOperators (10).
    cols = [
        FeatureColumn(
            name=f"e{i}", kind=FeatureKind.EDGE, edge_parent=f"p{i}", edge_child=f"c{i}"
        )
        for i in range(6)
    ]
    compiled = compile_finding(_finding([c.name for c in cols]), cols)
    assert compiled.envelope == {}
    assert "MaxTraceOperators" in compiled.refusals[0].reason


def test_ten_operators_is_allowed() -> None:
    # 5 edges + 1 span predicate => 5 "=>" + 5 "&&" = 10 operators (at the cap).
    cols: list[FeatureColumn] = [
        FeatureColumn(
            name=f"e{i}", kind=FeatureKind.EDGE, edge_parent=f"p{i}", edge_child=f"c{i}"
        )
        for i in range(5)
    ]
    cols.append(FeatureColumn(name="sp", kind=FeatureKind.SPAN_PREDICATE, service_name="s"))
    compiled = compile_finding(_finding([c.name for c in cols]), cols)
    assert not compiled.refusals
    assert compiled.envelope != {}
