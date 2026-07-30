"""Whodunit benchmark harness — live, against the running SigNoz stack.

For each scenario: emit a fresh corpus run (distinct seed), wait for ingestion,
run the whodunit pipeline (contamination-robust, trace-id scoped) AND the flat
baseline on the SAME matrix, and score both against the manifest ground truth.

Run:  (env creds must be set — see benchmark/README.md)
    uv run python benchmark/run.py                # all scenarios
    uv run python benchmark/run.py conditional_dep new_edge   # a subset

Writes benchmark/results.json (raw) and benchmark/REPORT.md (the table).
The corpus emitter needs OpenTelemetry deps that are absent from the repo venv,
so emission shells out to the warmup-agent interpreter; the pipeline itself runs
under `uv run` (this process).
"""
from __future__ import annotations

import hashlib
import json
import os
import random
import subprocess
import sys
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
OUT = REPO / "corpus" / "out"
BENCH = REPO / "benchmark"
# The corpus emitter needs OpenTelemetry deps absent from the repo venv. Point
# WHODUNIT_EMITTER_PYTHON at any interpreter that has them (see benchmark/README.md);
# falls back to this process's interpreter so the harness is not machine-specific.
WARMUP_PY = Path(os.environ.get("WHODUNIT_EMITTER_PYTHON", sys.executable))
ENVIRONMENT = "whodunit-demo"
ENDPOINT = "http://localhost:4318"
DURATION_HOURS = 0.01  # ~36s spread: keep each run's traces tightly clustered
TRACE_TABLE = "signoz_traces.distributed_signoz_index_v3"

from baseline import run_baseline  # noqa: E402
from pipeline_scoped import all_trace_ids, explain_scoped  # noqa: E402
from scenarios import SCENARIOS, Scenario  # noqa: E402

from whodunit.extract import ScanConfig  # noqa: E402
from whodunit.extract.sql import id_list_predicate, run_clickhouse_sql  # noqa: E402
from whodunit.mine import MineConfig  # noqa: E402
from whodunit.signoz_client import SigNozClient  # noqa: E402

# Structural-only scan config (see REPORT.md methods): logs are EXCLUDED because
# the corpus injects ground-truth-leaking ERROR log lines whose bodies literally
# describe the fault (e.g. "payment retry exhausted: redis-retry issued while
# feature flags unavailable"); mining those would trivialise every scenario and
# derail the retry_storm abstention test. We test STRUCTURAL discrimination, the
# blog's actual thesis. tenant.tier is the only attribute (the decoy trap);
# order.completed/cache.hit are dropped as they mirror the label.
SCAN_CONFIG = ScanConfig(
    include_logs=False,
    include_edges=True,
    include_ancestors=False,  # direct '=>' edges capture the discriminators; the
    # transitive-ancestor WITH RECURSIVE closure roughly doubles the structural
    # feature count and blows up the k=3 FP-growth family + bootstrap (measured:
    # >7 min/scan vs ~30-60s). Off keeps the live loop tractable; the flagship
    # payment => redis-retry discriminator is a DIRECT edge and is unaffected.
    include_attributes=True,
    attribute_keys=("tenant.tier",),
    include_duration=True,
)

# Bootstrap CI resamples: 1000 (default) x 800 rows x (large FP-growth family) is
# ~10^9 pure-Python ops per scan and dominates wall-clock. The harness is
# explicitly allowed to sweep MineConfig; 300 resamples keep the lift-CI stable
# for these clean separations (ci_low, which drives every gate, is unchanged to
# 2 d.p.) while cutting mine time ~3x. Disclosed in REPORT.md.
MINE_CONFIG = MineConfig(n_bootstrap=300)


def make_runid(fault: str, seed: int, traces: int, fault_rate: float, decoys: float) -> str:
    extra = f"False|{decoys}"
    h = hashlib.sha256(
        f"{fault}|{seed}|{traces}|{fault_rate}|{extra}".encode()
    ).hexdigest()[:8]
    return f"{fault}-s{seed}-n{traces}-{h}"


def emit_corpus(sc: Scenario) -> tuple[dict, float, float]:
    """Shell out to the OTel-capable interpreter; return (manifest, t_pre, _t_post)."""
    runid = make_runid(sc.fault, sc.seed, sc.traces, sc.fault_rate, sc.decoys)
    t_pre = time.time()
    cmd = [
        str(WARMUP_PY), "-m", "corpus.generate",
        "--traces", str(sc.traces), "--seed", str(sc.seed),
        "--fault", sc.fault, "--fault-rate", str(sc.fault_rate),
        "--duration-hours", str(DURATION_HOURS),
        "--endpoint", ENDPOINT, "--out-dir", str(OUT), "--quiet",
    ]
    if sc.decoys > 0:
        cmd += ["--decoys", str(sc.decoys)]
    proc = subprocess.run(cmd, cwd=REPO, capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(f"emit failed for {sc.key}: {proc.stderr[-500:]}")
    _t_post = time.time()
    manifest = json.loads((OUT / f"manifest-{runid}.json").read_text(encoding="utf-8"))
    return manifest, t_pre, _t_post


def poll_ingestion(
    client: SigNozClient, ids: list[str], win_s: int, target: int,
    *, timeout_s: float = 200.0,
) -> int:
    """Poll until `target` of `ids` are visible in-env, or timeout. Returns count."""
    pred = id_list_predicate("trace_id", ids)
    sql = (
        f"SELECT countDistinct(trace_id) t FROM {TRACE_TABLE} "
        f"WHERE resources_string['deployment.environment']='{ENVIRONMENT}' AND {pred}"
    )
    deadline = time.time() + timeout_s
    last, stable = 0, 0
    while time.time() < deadline:
        now_ms = int(time.time() * 1000)
        got = int(run_clickhouse_sql(client, sql, win_s, now_ms)[0]["t"])
        if got >= target:
            return got
        stable = stable + 1 if got == last else 0
        last = got
        if stable >= 6 and got > 0:  # plateaued below target (some dropped)
            return got
        time.sleep(5)
    return last


@dataclass
class ScenarioResult:
    key: str
    fault: str
    seed: int
    expected: str
    got: str = ""
    headline: str = ""
    chosen_itemset: list[str] = field(default_factory=list)
    expression: str = ""
    precision_at_1: bool = False
    label_recall: float | None = None
    label_precision: float | None = None
    verify_mined: int | None = None
    verify_signoz: int | None = None
    verify_match: bool | None = None
    abstained_correctly: bool | None = None
    false_culprit: bool = False
    baseline_predicate: str = ""
    baseline_found: bool = False
    baseline_precision: float | None = None
    baseline_recall: float | None = None
    baseline_z: float | None = None
    wall_clock_s: float = 0.0
    rows_scanned: int | None = None
    n_features: int = 0
    family_size: int = 0
    n_bad: int = 0
    n_healthy: int = 0
    ingested_bad: int = 0
    verdict_correct: bool = False
    passed: bool = False
    refusals: list[str] = field(default_factory=list)
    notes: str = ""


def score_scenario(client: SigNozClient, sc: Scenario) -> ScenarioResult:
    print(f"\n=== {sc.key} (seed {sc.seed}, fault {sc.fault}) ===", flush=True)
    manifest, t_pre, _t_post = emit_corpus(sc)
    all_ids = all_trace_ids(sc.seed, sc.traces)
    all_set = set(all_ids)

    if sc.synth_random_cohort_frac > 0:
        # null: no labelled bad set — synthesise a random suspected cohort.
        rng = random.Random(sc.seed)
        k = max(10, int(sc.synth_random_cohort_frac * len(all_ids)))
        bad_ids = sorted(rng.sample(all_ids, k))
    else:
        bad_ids = list(manifest.get("bad_trace_ids", []))
    healthy_ids = [t for t in all_ids if t not in set(bad_ids)]

    win_s = int((t_pre - DURATION_HOURS * 3600 - 120) * 1000)
    print(f"emitted {sc.traces} traces, {len(bad_ids)} bad; waiting for ingestion...",
          flush=True)
    ingested = poll_ingestion(client, bad_ids or all_ids, win_s,
                              target=len(bad_ids) if bad_ids else sc.traces)
    win_e = int(time.time() * 1000) + 120_000
    print(f"ingested {ingested}/{len(bad_ids) if bad_ids else sc.traces}", flush=True)

    res = ScenarioResult(
        key=sc.key, fault=sc.fault, seed=sc.seed,
        expected=sc.expected_verdict, ingested_bad=ingested,
        notes=sc.note,
    )

    run = explain_scoped(
        client, bad_ids=bad_ids, healthy_ids=healthy_ids,
        window_start_ms=win_s, window_end_ms=win_e, environment=ENVIRONMENT,
        scan_config=SCAN_CONFIG, mine_config=MINE_CONFIG, do_verify=True,
        all_corpus_ids=all_set,
    )
    r = run.result
    res.got = r.verdict.value
    res.headline = r.headline
    res.chosen_itemset = list(r.chosen_finding.itemset) if r.chosen_finding else []
    res.expression = r.compiled.expression if r.compiled else ""
    res.wall_clock_s = round(run.elapsed_s, 1)
    res.rows_scanned = r.cost.scan_rows_scanned
    res.n_features = r.cost.n_features
    res.family_size = r.family_size
    res.n_bad = run.n_bad_matrix
    res.n_healthy = run.n_healthy_matrix
    res.refusals = [f"{'/'.join(x.itemset)}: {x.reason[:80]}" for x in r.refusals[:4]]
    if r.verification:
        res.verify_mined = r.verification.mined_count
        res.verify_signoz = r.verification.signoz_count
        res.verify_match = r.verification.match
        res.label_precision = (round(run.label_precision_incorpus, 3)
                               if run.label_precision_incorpus is not None else None)
    res.label_recall = round(run.label_recall, 3) if run.label_recall is not None else None

    # verdict correctness
    res.verdict_correct = res.got in sc.accepted()
    # abstention correctness (for the non-structural scenarios)
    if not sc.ground_truth_is_structural:
        res.abstained_correctly = res.got in ("abstain", "partial")
        res.false_culprit = res.got == "discriminator"
    # precision@1: the winner IS the ground-truth structural separator.
    if sc.ground_truth_is_structural and r.chosen_finding is not None:
        res.precision_at_1 = bool(
            res.label_recall is not None and res.label_recall >= 0.99
            and (res.label_precision is None or res.label_precision >= 0.99)
        )

    # baseline on the EXACT SAME matrix the miner saw (reused, no re-scan)
    top, _ranking = run_baseline(run.frame, run.columns)
    if top is not None:
        res.baseline_predicate = top.predicate
        res.baseline_found = top.found
        res.baseline_precision = round(top.precision, 3) if top.precision is not None else None
        res.baseline_recall = round(top.recall, 3) if top.recall is not None else None
        res.baseline_z = round(top.z, 2) if top.z not in (float("inf"), float("-inf")) else 999.0

    # overall PASS: verdict correct AND (for structural) precision@1, (for
    # non-structural) no false culprit.
    if sc.ground_truth_is_structural:
        res.passed = res.verdict_correct and res.precision_at_1
    else:
        res.passed = res.verdict_correct and not res.false_culprit

    print(f"  verdict={res.got} (expect {sc.expected_verdict}) pass={res.passed} "
          f"recall={res.label_recall} signoz={res.verify_signoz}/{res.verify_mined} "
          f"baseline={res.baseline_predicate} found={res.baseline_found}", flush=True)
    return res


def main(argv: list[str]) -> int:
    keys = set(argv) if argv else None
    todo = [s for s in SCENARIOS if keys is None or s.key in keys]
    t_all = time.time()
    results: list[ScenarioResult] = []
    with SigNozClient() as client:
        client.login()
        for i, sc in enumerate(todo):
            try:
                results.append(score_scenario(client, sc))
            except Exception as exc:  # keep going; record the failure
                import traceback
                traceback.print_exc()
                results.append(ScenarioResult(
                    key=sc.key, fault=sc.fault, seed=sc.seed,
                    expected=sc.expected_verdict, got="ERROR",
                    notes=f"harness error: {exc}",
                ))
            if i < len(todo) - 1:
                time.sleep(20)  # keep sequential runs' windows disjoint
    total_s = round(time.time() - t_all, 1)

    payload = {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "total_wall_clock_s": total_s,
        "duration_hours_per_run": DURATION_HOURS,
        "scan_config": {
            "include_logs": SCAN_CONFIG.include_logs,
            "include_edges": SCAN_CONFIG.include_edges,
            "include_ancestors": SCAN_CONFIG.include_ancestors,
            "attribute_keys": list(SCAN_CONFIG.attribute_keys),
        },
        "mine_config": {"n_bootstrap": MINE_CONFIG.n_bootstrap,
                        "max_itemset_size": MINE_CONFIG.max_itemset_size},
        "results": [asdict(r) for r in results],
    }
    (BENCH / "results.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")
    write_report(payload)
    print(f"\nTOTAL wall-clock {total_s}s -> benchmark/results.json + REPORT.md",
          flush=True)
    return 0


def write_report(payload: dict) -> None:
    from report import render_report
    (BENCH / "REPORT.md").write_text(render_report(payload), encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
