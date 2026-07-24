"""Topological demotion and the client-side onset detector."""

from __future__ import annotations

import polars as pl

from whodunit.mine.config import MineConfig
from whodunit.mine.demote import (
    conditional_lift,
    demote_findings,
    ewma_zscores,
    is_descendant_feature,
    onset_index,
)
from whodunit.mine.matrix import build_feature_data
from whodunit.types import FeatureColumn, FeatureKind, Finding, Verdict


def _edge(name: str, parent: str, child: str) -> FeatureColumn:
    return FeatureColumn(
        name=name, kind=FeatureKind.EDGE, edge_parent=parent, edge_child=child
    )


def _finding(itemset: list[str], lift: float) -> Finding:
    return Finding(
        itemset=itemset,
        lift=lift,
        ci_low=lift * 0.8,
        ci_high=lift * 1.2,
        support_bad=50,
        support_healthy=1,
        verdict=Verdict.DISCRIMINATOR,
    )


def _demotion_scenario() -> tuple[pl.DataFrame, list[FeatureColumn]]:
    # edge_pc: payment->redis (parent/symptom); edge_cd: redis->db (descendant/cause).
    # label == edge_cd present. edge_pc present on every edge_cd row (so its
    # anomaly is fully explained by edge_cd) plus a few extra healthy rows.
    n = 200
    label: list[bool] = []
    pc: list[bool] = []
    cd: list[bool] = []
    for i in range(n):
        cd_present = i < 50  # 50 bad traces
        label.append(cd_present)
        cd.append(cd_present)
        pc.append(cd_present or (50 <= i < 60))  # extra 10 healthy carrying pc
    frame = pl.DataFrame(
        {"trace_id": [f"t{i}" for i in range(n)], "label": label, "edge_pc": pc, "edge_cd": cd}
    )
    cols = [_edge("edge_pc", "payment", "redis"), _edge("edge_cd", "redis", "db")]
    return frame, cols


def test_is_descendant_feature_directionality() -> None:
    pc = _edge("edge_pc", "payment", "redis")
    cd = _edge("edge_cd", "redis", "db")
    assert is_descendant_feature(pc, cd) is True
    assert is_descendant_feature(cd, pc) is False


def test_conditional_lift_collapses_for_symptom() -> None:
    frame, cols = _demotion_scenario()
    data = build_feature_data(frame, cols)
    # Unconditionally edge_pc is highly lifted; conditioning on edge_cd it
    # collapses (every edge_cd row is bad, so pc adds nothing).
    cond = conditional_lift(data, frozenset({"edge_pc"}), "edge_cd")
    assert cond < 3.0


def test_demotion_marks_symptom_not_cause() -> None:
    frame, cols = _demotion_scenario()
    data = build_feature_data(frame, cols)
    findings = [_finding(["edge_pc"], lift=3.3), _finding(["edge_cd"], lift=4.0)]
    out = demote_findings(findings, data, data.columns_by_name, MineConfig())
    by_name = {tuple(f.itemset): f for f in out}
    assert by_name[("edge_pc",)].demoted_by == "edge_cd"
    assert by_name[("edge_cd",)].demoted_by is None


def test_demotion_respects_onset_ordering() -> None:
    frame, cols = _demotion_scenario()
    data = build_feature_data(frame, cols)
    findings = [_finding(["edge_pc"], lift=3.3), _finding(["edge_cd"], lift=4.0)]
    # Descendant appeared strictly AFTER the parent -> cannot explain it.
    first_seen = {"edge_pc": 100.0, "edge_cd": 200.0}
    out = demote_findings(findings, data, data.columns_by_name, MineConfig(), first_seen)
    by_name = {tuple(f.itemset): f for f in out}
    assert by_name[("edge_pc",)].demoted_by is None


def test_ewma_zscores_flags_spike() -> None:
    series = [1.0, 1.1, 0.9, 1.05, 0.95, 10.0]
    z = ewma_zscores(series)
    assert len(z) == len(series)
    assert z[-1] > 3.0
    assert onset_index(series) == 5


def test_onset_index_none_for_flat() -> None:
    assert onset_index([1.0, 1.01, 0.99, 1.0, 1.0]) is None
