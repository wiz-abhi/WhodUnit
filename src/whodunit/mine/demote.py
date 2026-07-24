"""Topological demotion: distinguishing a cause from its symptoms.

A node whose anomaly is *fully explained by an anomalous descendant* is a
symptom, not a root cause. Concretely: if a finding's lift, once you condition
on the presence of an anomalous downstream feature, collapses below the effect
gate, then the finding was only anomalous because the descendant was — so it is
demoted (``Finding.demoted_by`` is set to the descendant it defers to).

With edges already materialised as features, this is a graph reduction over the
mined itemsets, not N conditional API round-trips. Optional per-feature
first-seen timestamps add onset ordering: a descendant cannot explain a parent
that became anomalous strictly earlier than it did.

The EWMA / z-score helpers here are the deliberately client-side onset detector.
SigNoz's ``anomaly()`` is Enterprise-only and off the critical path — it is
never called from this module.
"""

from __future__ import annotations

from whodunit.mine.config import MineConfig
from whodunit.mine.matrix import FeatureData, base_name
from whodunit.mine.stats import compute_lift
from whodunit.types import FeatureColumn, Finding


def _edge_endpoints(col: FeatureColumn) -> tuple[str | None, str | None]:
    """(upstream, downstream) service identity of a feature, best effort."""
    if col.edge_parent is not None or col.edge_child is not None:
        return col.edge_parent, col.edge_child
    # A plain span/service feature behaves as a node with no explicit edge.
    return col.service_name, col.service_name


def is_descendant_feature(
    parent_col: FeatureColumn,
    child_col: FeatureColumn,
) -> bool:
    """Whether ``child_col`` is topologically downstream of ``parent_col``.

    True when the parent edge's child service is the child edge's parent service
    (``p -> c`` feeds ``c -> d``), or when both share the same downstream node so
    the child edge sits under the parent's subtree.
    """
    _, p_down = _edge_endpoints(parent_col)
    c_up, c_down = _edge_endpoints(child_col)
    if p_down is None:
        return False
    if p_down == c_up and parent_col.name != child_col.name:
        return True
    # Ancestor-style: child edge strictly deeper under the same downstream node.
    return p_down == c_down and c_up is not None and c_up != p_down


def conditional_lift(data: FeatureData, itemset: frozenset[str], condition_item: str) -> float:
    """Lift of ``itemset`` vs the label restricted to rows where
    ``condition_item`` is present."""
    cond = data.bitsets.get(condition_item, 0)
    n_sub = cond.bit_count()
    if n_sub == 0:
        return 0.0
    n_bad_sub = (data.label_bad & cond).bit_count()
    present = data.cohort_mask(itemset) & cond
    a = (present & data.label_bad).bit_count()
    b = (present & data.label_healthy).bit_count()
    return compute_lift(a, b, n_bad_sub, n_sub)


def demote_findings(
    findings: list[Finding],
    data: FeatureData,
    columns: dict[str, FeatureColumn],
    config: MineConfig,
    first_seen: dict[str, float] | None = None,
) -> list[Finding]:
    """Set ``demoted_by`` on any finding fully explained by an anomalous
    descendant present in another finding. Returns a new list (inputs frozen)."""
    threshold = (
        config.demotion_lift_threshold
        if config.demotion_lift_threshold is not None
        else config.min_lift
    )
    # Candidate descendant items: presence features appearing across the findings.
    descendant_items: list[str] = []
    for f in findings:
        for item in f.itemset:
            bare = base_name(item)
            if bare in columns and item == bare:  # presence feature only
                descendant_items.append(item)

    result: list[Finding] = []
    for finding in findings:
        demoted_by: str | None = None
        parent_items = [base_name(i) for i in finding.itemset if base_name(i) in columns]
        for child_item in descendant_items:
            if child_item in finding.itemset:
                continue
            child_col = columns[child_item]
            # child must be downstream of at least one of the finding's features.
            downstream = any(
                is_descendant_feature(columns[pi], child_col)
                for pi in parent_items
                if pi in columns
            )
            if not downstream:
                continue
            if first_seen is not None:
                child_onset = first_seen.get(child_item)
                parent_onset = min(
                    (first_seen[pi] for pi in parent_items if pi in first_seen),
                    default=None,
                )
                if (
                    child_onset is not None
                    and parent_onset is not None
                    and child_onset > parent_onset
                ):
                    # Descendant became anomalous later; cannot explain the parent.
                    continue
            cond = conditional_lift(data, frozenset(finding.itemset), child_item)
            if cond < threshold:
                demoted_by = child_item
                break
        result.append(finding.model_copy(update={"demoted_by": demoted_by}))
    return result


# --------------------------------------------------------------------------- #
# Client-side onset detection (EWMA / z-score). anomaly() is EE-only: not used.
# --------------------------------------------------------------------------- #


def ewma_zscores(values: list[float], alpha: float = 0.3) -> list[float]:
    """Streaming EWMA z-score for each point vs the EWMA mean/variance of the
    points strictly before it. First point has an undefined baseline -> 0.0."""
    if not values:
        return []
    zscores: list[float] = [0.0]
    mean = values[0]
    var = 0.0
    for x in values[1:]:
        std = var**0.5
        zscores.append((x - mean) / std if std > 1e-12 else 0.0)
        diff = x - mean
        mean += alpha * diff
        var = (1 - alpha) * (var + alpha * diff * diff)
    return zscores


def onset_index(values: list[float], alpha: float = 0.3, z_threshold: float = 3.0) -> int | None:
    """Index of the first point whose EWMA z-score exceeds ``z_threshold``
    (client-side onset). ``None`` if the series never breaches it."""
    for i, z in enumerate(ewma_zscores(values, alpha)):
        if z >= z_threshold:
            return i
    return None
