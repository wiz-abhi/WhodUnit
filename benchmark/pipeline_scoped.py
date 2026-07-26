"""Contamination-robust driver for the whodunit pipeline.

WHY THIS EXISTS (see benchmark/ISSUES.md #1): the shared live stack holds many
other agents' ``deployment.environment='whodunit-demo'`` corpora, and SigNoz's
``clickhouse_sql`` query type IGNORES the ``start``/``end`` window (empirically:
a 3-minute window and a 1-year window return byte-identical rows). Therefore the
stock ``whodunit.pipeline.explain`` — whose healthy cohort is "every trace in
window not in the bad set" — pulls *other runs'* traces into the healthy cohort,
inflating ``support_healthy`` and depressing the mined discriminator.

The sanctioned fallback (per the benchmark brief) is to scope by explicit
trace-id SETS. Every corpus trace id is a pure function of ``(seed, index)``, so
we reconstruct this run's *complete* id set, split it into bad (manifest labels)
and healthy (the rest), and hand BOTH explicit sets to ``run_scan`` — whose
``scope = trace_id IN (...)`` predicate genuinely restricts the scan to this run.

``explain_scoped`` is a line-for-line mirror of ``whodunit.pipeline.explain`` with
exactly that one change (explicit healthy ids instead of ``resolve_cohorts``); it
calls the identical real engines — ``run_scan``, ``mine``, ``compile_finding``,
``verify`` — so the numbers are the pipeline's, not a reimplementation's.
"""
from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass, field

from whodunit.compile import verify
from whodunit.extract import ScanConfig, build_feature_matrix, run_scan
from whodunit.mine import MineConfig, mine
from whodunit.pipeline import (
    Cost,
    ExplainResult,
    _base_filter,
    _headline,
    _overall_verdict,
    _select_finding,
    adapt_columns_for_compiler,
    booleanize_frame,
    compute_verdict_hash,
)
from whodunit.signoz_client import SigNozClient
from whodunit.types import Refusal, Verification


def make_trace_id_hex(seed: int, idx: int) -> str:
    """Reproduce ``corpus.ids.make_trace_id`` without importing OTel deps."""
    key = "|".join([str(seed), str(idx), "trace"]).encode("utf-8")
    v = int.from_bytes(hashlib.sha256(key).digest()[:16], "big") or 1
    return f"{v:032x}"


def all_trace_ids(seed: int, total: int) -> list[str]:
    return [make_trace_id_hex(seed, i) for i in range(total)]


@dataclass
class ScopedRun:
    result: ExplainResult
    elapsed_s: float
    n_bad_matrix: int
    n_healthy_matrix: int
    # label-set metrics vs manifest bad ids (contamination-robust)
    label_recall: float | None
    label_precision_incorpus: float | None  # precision restricted to THIS run's ids
    matched_ids: set[str]
    # the exact matrix the miner saw, so the baseline scores the SAME data.
    frame: object = None
    columns: list = field(default_factory=list)


def explain_scoped(
    client: SigNozClient,
    *,
    bad_ids: list[str],
    healthy_ids: list[str],
    window_start_ms: int,
    window_end_ms: int,
    environment: str,
    scan_config: ScanConfig,
    mine_config: MineConfig | None = None,
    do_verify: bool = True,
    all_corpus_ids: set[str] | None = None,
) -> ScopedRun:
    mine_config = mine_config or MineConfig()
    t0 = time.time()

    # Stage 0/1 — one scan over THIS run's explicit id set only.
    scan = run_scan(
        client,
        bad_ids=tuple(bad_ids),
        healthy_ids=tuple(healthy_ids),
        window_start_unix_ms=window_start_ms,
        window_end_unix_ms=window_end_ms,
        environment=environment,
        config=scan_config,
    )
    mm = build_feature_matrix(
        scan,
        n_traces_bad=len(bad_ids),
        n_traces_healthy=len(healthy_ids),
        window_start_unix_ms=window_start_ms,
        window_end_unix_ms=window_end_ms,
    )

    # Stage 2 — mine (identical to explain()).
    frame = booleanize_frame(mm.frame, mm.meta.columns)
    n_bad_matrix = int(frame["label"].sum()) if frame.height else 0
    n_healthy_matrix = frame.height - n_bad_matrix
    mine_result = mine(frame, mm.meta.columns, mine_config)

    # Stage 4 — compile best-first (identical to explain()).
    adapted = adapt_columns_for_compiler(mm.meta.columns)
    base_filter = _base_filter(environment)
    chosen, compiled, refusals = _select_finding(
        mine_result.findings, adapted,
        base_filter=base_filter, start=window_start_ms, end=window_end_ms,
        near_misses=mine_result.near_misses,
    )
    for itemset in mine_result.noncompilable_itemsets:
        refusals.append(Refusal(
            itemset=list(itemset),
            reason=("itemset references a complement requiring span-level negation; "
                    "the trace-scoped NOT cannot express it soundly"),
        ))

    # Stage 5 — differential verification (identical to explain()).
    verification: Verification | None = None
    mined_count: int | None = None
    matched_ids: set[str] = set()
    label_recall: float | None = None
    label_precision_incorpus: float | None = None
    bad_set = set(bad_ids)
    if chosen is not None and compiled is not None and compiled.envelope:
        mined_count = chosen.support_bad + chosen.support_healthy
        if do_verify:
            # Skip verify()'s own precision/recall fetch; we fetch the matched id
            # set once here and derive both standard and in-corpus precision.
            verification = verify(
                client, compiled, mined_count=mined_count,
                start=window_start_ms, end=window_end_ms,
                bad_trace_ids=bad_set, with_precision_recall=False,
            )
            from whodunit.compile.verify import (
                fetch_matched_trace_ids,
                precision_recall,
            )
            matched_ids = fetch_matched_trace_ids(
                client, compiled, start=window_start_ms, end=window_end_ms
            )
            prec, rec = precision_recall(matched_ids, bad_set)
            verification = verification.model_copy(
                update={"precision": prec, "recall": rec}
            )
            compiled = compiled.model_copy(update={"verification": verification})
            tp = len(matched_ids & bad_set)
            label_recall = tp / len(bad_set) if bad_set else None
            # precision counting only ids that belong to THIS corpus run
            universe = all_corpus_ids if all_corpus_ids is not None else (bad_set | set(healthy_ids))  # noqa: E501
            matched_incorpus = matched_ids & universe
            label_precision_incorpus = (
                tp / len(matched_incorpus) if matched_incorpus else None
            )

    verdict = _overall_verdict(chosen, mine_result.abstained)
    headline = _headline(chosen, verdict)
    counts = {
        "family_size": mine_result.family_size,
        "mined": mined_count,
        "signoz": verification.signoz_count if verification is not None else None,
    }
    verdict_hash = compute_verdict_hash(
        mine_result.findings, compiled.expression if compiled is not None else "", counts,
    )
    cost = Cost(
        scan_rows_scanned=mm.meta.rows_scanned,
        scan_bytes_scanned=mm.meta.bytes_scanned,
        scan_duration_ms=mm.meta.duration_ms,
        verify_rows_scanned=verification.rows_scanned if verification else None,
        family_size=mine_result.family_size,
        n_features=len(mm.meta.columns),
    )
    result = ExplainResult(
        verdict=verdict, headline=headline, matrix_meta=mm.meta,
        mine_result_findings=mine_result.findings, near_misses=mine_result.near_misses,
        family_size=mine_result.family_size, abstained=mine_result.abstained,
        chosen_finding=chosen, compiled=compiled, verification=verification,
        refusals=refusals, verdict_hash=verdict_hash, cost=cost,
        environment=environment, window_start_unix_ms=window_start_ms,
        window_end_unix_ms=window_end_ms,
    )
    return ScopedRun(
        result=result, elapsed_s=time.time() - t0,
        n_bad_matrix=n_bad_matrix, n_healthy_matrix=n_healthy_matrix,
        label_recall=label_recall, label_precision_incorpus=label_precision_incorpus,
        matched_ids=matched_ids, frame=frame, columns=list(mm.meta.columns),
    )
