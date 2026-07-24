"""CLI entry point: generate the demo corpus and its manifest.

Example
-------
    python -m corpus.generate --traces 5000 --seed 42 \
        --fault conditional_dep --fault-rate 0.12 \
        --endpoint http://localhost:4318

Everything is deterministic in ``--seed``: the same seed produces identical
trace ids, cohort assignments, and manifest. ``--no-emit`` builds the manifest
and runs the self-check without touching the network (useful in CI / tests).
"""

from __future__ import annotations

import argparse
import random
import sys
import time
from pathlib import Path

from .faults import FAULTS, make_fault
from .manifest import (
    add_self_check,
    build_manifest,
    make_runid,
    write_manifest,
)

_DEFAULT_OUT = Path(__file__).resolve().parent / "out"


def _bool(s: str) -> bool:
    return str(s).lower() in ("1", "true", "yes", "y", "on")


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="corpus.generate",
        description="Whodunit demo corpus + seeded fault engine (OTLP emitter).",
    )
    p.add_argument("--traces", type=int, default=5000, help="number of traces to emit")
    p.add_argument("--seed", type=int, default=42, help="deterministic seed")
    p.add_argument(
        "--fault",
        choices=sorted(FAULTS),
        default="conditional_dep",
        help="which fault to inject (exactly one active per run)",
    )
    p.add_argument(
        "--fault-rate",
        type=float,
        default=0.12,
        help="fraction of traces exhibiting the fault (bad cohort share)",
    )
    p.add_argument(
        "--endpoint",
        default="http://localhost:4318",
        help="OTLP/HTTP base endpoint (/v1/traces and /v1/logs are appended)",
    )
    p.add_argument(
        "--error-visible",
        type=_bool,
        default=False,
        help="if true bad traces carry ERROR status; else fail politely "
        "(order.completed=false, status OK). Default false.",
    )
    p.add_argument(
        "--decoys",
        type=float,
        default=0.0,
        help="decoy overlay strength [0..1]: injects a correlated-but-non-causal "
        "attribute + high-cardinality noise into any fault. Default 0 (off).",
    )
    p.add_argument(
        "--duration-hours",
        type=float,
        default=1.0,
        help="spread the emitted traces over this many hours ending ~now",
    )
    p.add_argument(
        "--no-emit",
        action="store_true",
        help="plan + manifest + self-check only; do not send OTLP",
    )
    p.add_argument("--out-dir", default=str(_DEFAULT_OUT), help="manifest output directory")
    p.add_argument("--quiet", action="store_true")
    return p


def run(argv: list[str] | None = None) -> dict:
    args = build_parser().parse_args(argv)
    total = args.traces
    seed = args.seed
    window_ns = int(args.duration_hours * 3600 * 1e9)
    base_time_ns = time.time_ns() - window_ns

    fault = make_fault(
        args.fault,
        fault_rate=args.fault_rate,
        error_visible=args.error_visible,
        decoys_strength=args.decoys,
    )

    runid = make_runid(
        args.fault,
        seed,
        total,
        args.fault_rate,
        extra=f"{args.error_visible}|{args.decoys}",
    )

    emitter = None
    if not args.no_emit:
        # Imported lazily so --no-emit works without OTLP deps configured.
        from .emit import Emitter

        emitter = Emitter(args.endpoint, seed)

    plans = []
    plans_meta = []
    bad_trace_ids: list[str] = []
    t_start = time.time()

    for idx in range(total):
        rng = random.Random(f"{seed}:{idx}")
        plan = fault.plan(idx, total, rng)
        # Spread across the window; deterministic jitter.
        plan.start_offset_ns = int((idx + rng.random()) / total * window_ns)

        span_count = plan.root.count()
        log_count = len(plan.logs)

        if emitter is not None:
            trace_hex = emitter.emit_trace(plan, base_time_ns)
        else:
            from .ids import make_trace_id

            trace_hex = f"{make_trace_id(seed, idx):032x}"

        if plan.bad:
            bad_trace_ids.append(trace_hex)

        plans.append(plan)
        plans_meta.append(
            {"cohort": plan.cohort, "span_count": span_count, "log_count": log_count}
        )

        if not args.quiet and total >= 1000 and idx and idx % 1000 == 0:
            print(f"  ... {idx}/{total} traces planned", file=sys.stderr)

    if emitter is not None:
        if not args.quiet:
            print("  flushing OTLP exporters ...", file=sys.stderr)
        emitter.shutdown()

    duration_s = time.time() - t_start
    ground_truth = fault.ground_truth()

    args_dict = {
        "runid": runid,
        "seed": seed,
        "fault_rate": args.fault_rate,
        "error_visible": args.error_visible,
        "decoys": args.decoys,
        "endpoint": args.endpoint,
        "duration_hours": args.duration_hours,
    }
    manifest = build_manifest(
        args_dict=args_dict,
        fault_name=args.fault,
        ground_truth=ground_truth,
        plans_meta=plans_meta,
        bad_trace_ids=bad_trace_ids,
        duration_s=duration_s,
        base_time_ns=base_time_ns,
    )
    add_self_check(manifest, ground_truth, plans)
    paths = write_manifest(manifest, bad_trace_ids, Path(args.out_dir))

    if not args.quiet:
        c = manifest["counts"]
        sc = manifest["self_check"]
        print(
            f"[whodunit-corpus] runid={runid} fault={args.fault} "
            f"traces={c['total_traces']} bad={c['bad_traces']} "
            f"spans={c['total_spans']} logs={c['total_logs']} "
            f"lift={c['conjunction_lift_vs_background']} "
            f"self_check.spec_matches_label={sc.get('spec_matches_label')} "
            f"emitted={emitter is not None} -> {paths['manifest']}"
        )
    return {"manifest": manifest, "paths": paths}


def main(argv: list[str] | None = None) -> int:
    result = run(argv)
    sc = result["manifest"]["self_check"]
    # Fail CI if an expressible fault's spec does not select exactly the label.
    if sc.get("spec_matches_label") is False:
        print("SELF-CHECK FAILED: ground-truth spec != labels", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
