"""The six benchmark scenarios and their machine-checkable expectations.

Each scenario emits a fresh corpus run (distinct seed) and is scored against the
manifest ground truth. ``expected_verdict`` is what a correct, calibrated engine
must return; ``ground_truth_is_structural`` says whether a sound structural
discriminator exists at all (the abstention scenarios have none).
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Scenario:
    key: str
    fault: str
    seed: int
    fault_rate: float
    decoys: float
    traces: int
    expected_verdict: str            # "discriminator" | "partial" | "abstain"
    ground_truth_is_structural: bool  # a sound structural separator exists
    note: str
    # For the null scenario we have no labelled bad set; we synthesise a random
    # "suspected" cohort from the reconstructed id space to test abstention.
    synth_random_cohort_frac: float = 0.0
    # verdicts that count as a benchmark PASS (some scenarios accept a set).
    accept_verdicts: tuple[str, ...] = ()

    def accepted(self) -> tuple[str, ...]:
        return self.accept_verdicts or (self.expected_verdict,)


SCENARIOS: list[Scenario] = [
    Scenario(
        key="conditional_dep", fault="conditional_dep", seed=101,
        fault_rate=0.12, decoys=0.0, traces=800,
        expected_verdict="discriminator", ground_truth_is_structural=True,
        note="Flagship: (payment => redis-retry) && NOT flag-service. No single "
             "predicate separates; only the conjunction does. Expect recall 1.0.",
    ),
    Scenario(
        key="new_edge", fault="new_edge", seed=102,
        fault_rate=0.30, decoys=0.0, traces=800,
        expected_verdict="discriminator", ground_truth_is_structural=True,
        note="New cart => inventory-sync edge post-deploy. Single-feature "
             "presence discriminator — the flat baseline should also find it.",
    ),
    Scenario(
        key="cache_bypass", fault="cache_bypass", seed=103,
        fault_rate=0.20, decoys=0.0, traces=800,
        expected_verdict="discriminator", ground_truth_is_structural=True,
        note="Bad traces miss the cache-get span entirely. Trace-scoped absence "
             "discriminator (NOT cache-get); must compile (trace-scoped NOT safe).",
    ),
    Scenario(
        key="retry_storm", fault="retry_storm", seed=104,
        fault_rate=0.20, decoys=0.0, traces=800,
        expected_verdict="abstain", ground_truth_is_structural=False,
        accept_verdicts=("abstain", "partial"),
        note="2-5 redis-retry siblings vs 1: a CARDINALITY fault, inexpressible "
             "in the presence/absence algebra. redis-retry is present in BOTH "
             "cohorts. Correct = ABSTAIN/PARTIAL. A confident DISCRIMINATOR here "
             "is a FAILURE.",
    ),
    Scenario(
        key="decoys", fault="decoys", seed=105,
        fault_rate=0.15, decoys=0.85, traces=800,
        expected_verdict="abstain", ground_truth_is_structural=False,
        note="tenant.tier=gold correlates ~85% with the bad label but does NOT "
             "cause it; plus high-cardinality noise. Correct = ABSTAIN. A "
             "DISCRIMINATOR on the decoy is a false culprit (FAILURE).",
    ),
    Scenario(
        key="null_scenario", fault="null_scenario", seed=106,
        fault_rate=0.0, decoys=0.0, traces=800,
        expected_verdict="abstain", ground_truth_is_structural=False,
        synth_random_cohort_frac=0.12,
        note="Nothing is wrong; only natural structural variation. We select a "
             "RANDOM 12% 'suspected' cohort (no structural cause) and require "
             "the engine to ABSTAIN rather than invent a culprit.",
    ),
]
