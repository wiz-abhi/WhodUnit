"""The seeded fault library.

Exactly one fault is active per run. Each fault is a small state machine that,
given a trace index and a per-trace RNG, decides the structural shape of the
trace and whether it is labelled *bad*. Each fault also emits a machine-checkable
ground-truth spec (mirrored by the ClickHouse validation SQL) so the mining
engine can be scored without a human in the loop.

Design invariant for the flagship ``conditional_dep`` fault: healthy traffic
*never* has the culprit conjunction, so the conjunction is a perfect separator
while each single conjunct appears in both cohorts (low single-predicate lift).
"""

from __future__ import annotations

import random
from dataclasses import dataclass

from .model import LogRecordPlan, SpanNode, TracePlan
from .topology import build_base_trace


# --------------------------------------------------------------------------- #
# Decoy overlay (always-available, strength configurable). Non-causal.
# --------------------------------------------------------------------------- #
_TIERS = ("free", "silver", "gold", "platinum")


def decoy_attrs(rng: random.Random, bad: bool, strength: float) -> dict[str, object]:
    """Return confounding attributes that *correlate* with ``bad`` but do not
    cause it, plus high-cardinality noise. ``strength`` in [0,1] is P(the decoy
    tier is 'gold' | bad) — i.e. how tightly the trap correlates."""
    if strength <= 0:
        return {}
    if bad:
        tier = "gold" if rng.random() < strength else rng.choice(_TIERS)
    else:
        tier = rng.choice(_TIERS) if rng.random() < strength else "gold"
    return {
        "tenant.tier": tier,  # correlated-but-non-causal trap
        "request.id": f"req-{rng.getrandbits(64):016x}",  # high-cardinality noise
        "session.bucket": rng.randint(0, 4096),  # medium-cardinality noise
    }


# --------------------------------------------------------------------------- #
# Log templating
# --------------------------------------------------------------------------- #
def _base_logs(rng: random.Random) -> list[LogRecordPlan]:
    logs = [
        LogRecordPlan(
            span_index=0,
            severity="INFO",
            body=f"checkout started order_id=ord-{rng.getrandbits(32):08x}",
            attributes={"log.template": "checkout.started"},
        )
    ]
    if rng.random() < 0.7:
        logs.append(
            LogRecordPlan(
                span_index=0,
                severity="INFO",
                body=f"cart loaded items={rng.randint(1, 8)}",
                attributes={"log.template": "cart.loaded"},
            )
        )
    return logs


def _error_log(body: str, template: str, severity: str = "ERROR") -> LogRecordPlan:
    return LogRecordPlan(
        span_index=0, severity=severity, body=body, attributes={"log.template": template}
    )


@dataclass
class Fault:
    name: str
    fault_rate: float
    error_visible: bool
    decoys_strength: float
    deploy_fraction: float = 0.4  # for time-based faults
    retry_max: int = 5

    # -- to be overridden per fault ---------------------------------------- #
    def plan(self, trace_index: int, total: int, rng: random.Random) -> TracePlan:
        raise NotImplementedError

    def ground_truth(self) -> dict:
        raise NotImplementedError

    # -- shared helpers ----------------------------------------------------- #
    def _decoys(self, rng: random.Random, bad: bool) -> dict[str, object]:
        return decoy_attrs(rng, bad, self.decoys_strength)


# --------------------------------------------------------------------------- #
# 1. conditional_dep  — the flagship: (checkout => payment => redis-retry) && NOT flag-service
# --------------------------------------------------------------------------- #
class ConditionalDep(Fault):
    def plan(self, trace_index, total, rng):
        u = rng.random()
        if u < self.fault_rate:
            # BAD: redis-retry present AND flag-service absent.
            bad = True
            flag_present, redis_present, cohort = False, True, "bad"
        else:
            # HEALTHY: never (redis AND ¬flag). Spread the two confounders so
            # each single predicate appears in healthy traffic.
            bad = False
            v = rng.random()
            if v < 0.45:  # confounder A: redis present, flag present
                flag_present, redis_present, cohort = True, True, "healthy_redis"
            elif v < 0.85:  # confounder B: flag absent, redis absent
                flag_present, redis_present, cohort = False, False, "healthy_noflag"
            else:  # plain healthy
                flag_present, redis_present, cohort = True, False, "healthy_plain"

        root = build_base_trace(
            rng,
            flag_present=flag_present,
            redis_retry_present=redis_present,
            redis_retry_count=1,
            error_visible=self.error_visible,
            bad=bad,
            decoy_attrs=self._decoys(rng, bad),
        )
        logs = _base_logs(rng)
        if bad:
            logs.append(
                _error_log(
                    "payment retry exhausted: redis-retry issued while feature flags unavailable",
                    "payment.retry_exhausted",
                )
            )
        return TracePlan(trace_index=trace_index, root=root, logs=logs, bad=bad, cohort=cohort)

    def ground_truth(self):
        return {
            "discriminator": "(checkout => payment => redis-retry) && NOT flag-service",
            "human": (
                "A trace is bad iff it contains a redis-retry span under "
                "payment (reachable checkout->payment->redis-retry) AND no "
                "flag-service span anywhere in the trace. Neither condition "
                "alone separates the cohorts; only their conjunction does. "
                "Durations overlap; no single attribute separates."
            ),
            "cohorts": {
                "bad": {
                    "all_of": [
                        {"tag_present": "redis-retry"},
                        {"edge_present": ["payment", "redis-retry"]},
                        {"tag_absent": "flag-service"},
                    ],
                    "label": {"attr": "order.completed", "equals": False},
                },
                "healthy": {
                    "any_of": [
                        {"tag_present": "flag-service"},
                        {"tag_absent": "redis-retry"},
                    ]
                },
            },
            "expressible_in_trace_operator": True,
            "notes": (
                "Perfect separator (precision=recall=1.0). Lift vs background = "
                "1/fault_rate, so fault_rate<=0.05 yields conjunction lift>=20x; "
                "each single conjunct has lift ~1/(fault_rate+confounder_rate) "
                "(~2-3x), which is the intended near-miss."
            ),
        }


# --------------------------------------------------------------------------- #
# 2. new_edge — after a deploy marker, cart calls a new inventory-sync child.
# --------------------------------------------------------------------------- #
class NewEdge(Fault):
    def plan(self, trace_index, total, rng):
        post_deploy = trace_index >= int(total * self.deploy_fraction)
        has_edge = post_deploy and rng.random() < self.fault_rate
        bad = has_edge
        cohort = "bad" if has_edge else ("healthy_post" if post_deploy else "healthy_pre")
        root = build_base_trace(
            rng,
            flag_present=True,
            inventory_sync_present=has_edge,
            error_visible=self.error_visible,
            bad=bad,
            decoy_attrs=self._decoys(rng, bad),
        )
        logs = _base_logs(rng)
        if has_edge:
            logs.append(
                _error_log(
                    "inventory-sync fanout enabled build=2026.07.24-canary",
                    "inventory.sync_fanout",
                    severity="WARN",
                )
            )
        return TracePlan(trace_index=trace_index, root=root, logs=logs, bad=bad, cohort=cohort)

    def ground_truth(self):
        return {
            "discriminator": "checkout => cart => inventory-sync  (post-deploy only)",
            "human": (
                "After the deploy marker (trace index >= "
                f"{self.deploy_fraction:.0%} of the run), a fraction of traces "
                "gain a new cart->inventory-sync edge that did not exist before. "
                "Bad = the new edge is present."
            ),
            "cohorts": {
                "bad": {
                    "all_of": [
                        {"tag_present": "inventory-sync"},
                        {"edge_present": ["cart", "inventory-sync"]},
                    ]
                },
                "healthy": {"tag_absent": "inventory-sync"},
            },
            "expressible_in_trace_operator": True,
            "notes": "New-edge appearance; deploy marker is the temporal split.",
        }


# --------------------------------------------------------------------------- #
# 3. cache_bypass — cache-get span vanishes in a subset; db-read inflates.
# --------------------------------------------------------------------------- #
class CacheBypass(Fault):
    def plan(self, trace_index, total, rng):
        bad = rng.random() < self.fault_rate
        root = build_base_trace(
            rng,
            flag_present=True,
            cache_get_present=not bad,  # the cache-get span vanishes
            db_read_inflation=1.1 if bad else 0.0,  # ~3x heavier db read
            error_visible=self.error_visible,
            bad=bad,
            decoy_attrs=self._decoys(rng, bad),
        )
        logs = _base_logs(rng)
        if bad:
            logs.append(
                _error_log(
                    "cache bypass: cart-items read fell through to postgresql full scan",
                    "cache.bypass",
                    severity="WARN",
                )
            )
        return TracePlan(
            trace_index=trace_index,
            root=root,
            logs=logs,
            bad=bad,
            cohort="bad" if bad else "healthy",
        )

    def ground_truth(self):
        return {
            "discriminator": "NOT cache-get  (with inflated db-read)",
            "human": (
                "Bad traces are missing the cache-get span entirely (trace-level "
                "absence); the downstream db-read is inflated as a consequence. "
                "NOTE: absence is trace-scoped; a span-level anti-join would be "
                "unsound here, so the compiler must express this as trace-scoped "
                "NOT and refuse span-level negation."
            ),
            "cohorts": {
                "bad": {"all_of": [{"tag_absent": "cache-get"}]},
                "healthy": {"tag_present": "cache-get"},
            },
            "expressible_in_trace_operator": True,
            "notes": "Trace-scoped NOT; tests correct absence semantics.",
        }


# --------------------------------------------------------------------------- #
# 4. retry_storm — payment gains 2-5 sibling retry spans. NOT expressible.
# --------------------------------------------------------------------------- #
class RetryStorm(Fault):
    def plan(self, trace_index, total, rng):
        bad = rng.random() < self.fault_rate
        count = rng.randint(2, self.retry_max) if bad else 1
        root = build_base_trace(
            rng,
            flag_present=True,
            redis_retry_present=True,  # present in BOTH cohorts (1 vs 2-5)
            redis_retry_count=count,
            error_visible=self.error_visible,
            bad=bad,
            decoy_attrs=self._decoys(rng, bad),
        )
        logs = _base_logs(rng)
        if bad:
            logs.append(
                _error_log(
                    f"payment retry storm: {count} redis-retry attempts before success",
                    "payment.retry_storm",
                )
            )
        return TracePlan(
            trace_index=trace_index,
            root=root,
            logs=logs,
            bad=bad,
            cohort="bad" if bad else "healthy",
        )

    def ground_truth(self):
        return {
            "discriminator": "count(redis-retry under payment) >= 2",
            "human": (
                "Bad traces have 2-5 redis-retry siblings under payment; healthy "
                "traces have exactly 1. The redis-retry span is PRESENT in both "
                "cohorts, so presence/absence cannot separate them."
            ),
            "cohorts": {
                "bad": {"count": {"tag": "redis-retry", "min": 2}},
                "healthy": {"count": {"tag": "redis-retry", "max": 1}},
            },
            "expressible_in_trace_operator": False,
            "notes": (
                "INEXPRESSIBLE in the builder_trace_operator algebra: it has no "
                "per-trace cardinality qualifier. cart-service => redis-retry "
                "matches the 1-child baseline and the 5-child regression "
                "IDENTICALLY. Ground truth = the engine should ABSTAIN / refuse, "
                "not fabricate a presence-based discriminator. Tests honest "
                "refusal."
            ),
        }


# --------------------------------------------------------------------------- #
# 5. decoys — only a non-causal correlated attribute; no structural cause.
# --------------------------------------------------------------------------- #
class Decoys(Fault):
    def plan(self, trace_index, total, rng):
        bad = rng.random() < self.fault_rate
        # Force a meaningful decoy correlation even if user left strength at 0.
        strength = self.decoys_strength if self.decoys_strength > 0 else 0.65
        root = build_base_trace(
            rng,
            flag_present=True,
            error_visible=self.error_visible,
            bad=bad,
            decoy_attrs=decoy_attrs(rng, bad, strength),
        )
        logs = _base_logs(rng)
        if bad:
            logs.append(
                _error_log(
                    "order flagged for manual review",
                    "order.flagged",
                    severity="WARN",
                )
            )
        return TracePlan(
            trace_index=trace_index,
            root=root,
            logs=logs,
            bad=bad,
            cohort="bad" if bad else "healthy",
        )

    def ground_truth(self):
        return {
            "discriminator": None,
            "human": (
                "There is NO structural discriminator. A single attribute "
                "(tenant.tier=gold) correlates ~60-70% with the bad label but "
                "does not cause it, and high-cardinality noise (request.id, "
                "session.bucket) is present as distraction. Correct answer = "
                "ABSTAIN: no structural cause; report the decoy as a low-"
                "confidence non-causal correlation at most."
            ),
            "cohorts": {
                "bad": {"note": "randomly assigned; only correlates with tenant.tier"},
                "healthy": {"note": "randomly assigned"},
            },
            "expressible_in_trace_operator": False,
            "ground_truth_verdict": "abstain",
            "notes": "Tests false-culprit avoidance / calibrated abstention.",
        }


# --------------------------------------------------------------------------- #
# 6. null_scenario — nothing is wrong.
# --------------------------------------------------------------------------- #
class NullScenario(Fault):
    def plan(self, trace_index, total, rng):
        root = build_base_trace(
            rng,
            flag_present=rng.random() < 0.9,
            redis_retry_present=rng.random() < 0.3,
            cache_get_present=rng.random() < 0.9,
            error_visible=self.error_visible,
            bad=False,
            decoy_attrs=self._decoys(rng, False),
        )
        return TracePlan(
            trace_index=trace_index,
            root=root,
            logs=_base_logs(rng),
            bad=False,
            cohort="healthy",
        )

    def ground_truth(self):
        return {
            "discriminator": None,
            "human": "Nothing is wrong. Natural structural variation only.",
            "cohorts": {"bad": {"note": "none"}, "healthy": {"note": "all traces"}},
            "expressible_in_trace_operator": False,
            "ground_truth_verdict": "abstain",
            "notes": "Tests that the engine abstains when there is no fault.",
        }


FAULTS: dict[str, type[Fault]] = {
    "conditional_dep": ConditionalDep,
    "new_edge": NewEdge,
    "cache_bypass": CacheBypass,
    "retry_storm": RetryStorm,
    "decoys": Decoys,
    "null_scenario": NullScenario,
}


def make_fault(
    name: str,
    *,
    fault_rate: float,
    error_visible: bool,
    decoys_strength: float,
) -> Fault:
    if name not in FAULTS:
        raise ValueError(f"unknown fault '{name}'; choices: {sorted(FAULTS)}")
    return FAULTS[name](
        name=name,
        fault_rate=fault_rate,
        error_visible=error_visible,
        decoys_strength=decoys_strength,
    )
