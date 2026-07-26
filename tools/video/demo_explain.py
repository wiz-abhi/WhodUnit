"""On-camera driver for `whodunit explain`, scoped to ONE corpus run.

Why this exists (demo only — the product entry point is `whodunit explain`):
the shared live stack holds several overlapping `whodunit-demo` corpora and
`clickhouse_sql` ignores the envelope time window (`benchmark/ISSUES.md` #1), so
a plain time-scoped run pulls other runs' traces into the healthy cohort and
into the SigNoz verification count. Every number on camera has to be internally
consistent, so this driver does exactly what `benchmark/pipeline_scoped.py`
does: reconstruct this run's complete trace-id set from `(seed, index)`, split
it into the manifest's bad ids and the rest, and hand BOTH explicit sets to the
real engines (`run_scan` / `mine` / `compile_finding` / `verify`).

The rendering is `whodunit.cli.render` verbatim — the board, the compiled panel,
the receipt and the hash on screen are the product's own output, not a mock.

    uv run python tools/video/demo_explain.py \
        --manifest corpus/out/manifest-conditional_dep-s777-n800-<h>.json \
        --seed 777 --traces 800

Flags: --json (full ExplainResult), --hash-only (determinism beat),
--permalink (print the Trace Explorer URL), --arm, --dashboard.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "benchmark"))

from _console import make_console, status  # noqa: E402
from pipeline_scoped import all_trace_ids, explain_scoped  # noqa: E402

from whodunit.cli import render  # noqa: E402
from whodunit.extract import ScanConfig  # noqa: E402
from whodunit.mine import MineConfig  # noqa: E402
from whodunit.pipeline import load_materializer  # noqa: E402
from whodunit.signoz_client import SigNozClient  # noqa: E402

ENVIRONMENT = "whodunit-demo"

# Identical to benchmark/run.py's SCAN_CONFIG + MINE_CONFIG so the on-camera
# numbers are the benchmarked numbers.
SCAN_CONFIG = ScanConfig(
    include_logs=False,
    include_edges=True,
    include_ancestors=False,
    include_attributes=True,
    attribute_keys=("tenant.tier",),
    include_duration=True,
)
MINE_CONFIG = MineConfig(n_bootstrap=300)


def resolve_cohort(a: argparse.Namespace) -> tuple[list[str], list[str], list[str], str]:
    """(bad_ids, healthy_ids, all_corpus_ids, human label) for the chosen run.

    ``--latest <fault>`` picks the newest ``corpus/out/manifest-<fault>-s*.json``
    and reads the seed / trace count straight out of the filename, so the
    on-camera command stays short without hiding anything: the label printed on
    screen names the exact manifest.
    """
    manifest_path = a.manifest
    seed, traces = a.seed, a.traces
    if getattr(a, "latest", None):
        cands = sorted(
            (REPO / "corpus" / "out").glob(f"manifest-{a.latest}-s*-n*-*.json"),
            key=lambda p: p.stat().st_mtime,
        )
        if not cands:
            raise SystemExit(f"no manifest for fault {a.latest!r} in corpus/out/")
        manifest_path = cands[-1]
    if manifest_path is None:
        raise SystemExit("supply --manifest or --latest <fault>")
    parts = manifest_path.stem.split("-")  # manifest-<fault>-s<seed>-n<traces>-<hash>
    if seed is None:
        seed = int(parts[-3][1:])
    if traces is None:
        traces = int(parts[-2][1:])
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    bad_ids = [str(x) for x in manifest["bad_trace_ids"]]
    all_ids = all_trace_ids(seed, traces)
    bad_set = set(bad_ids)
    healthy_ids = [t for t in all_ids if t not in bad_set]
    return bad_ids, healthy_ids, all_ids, f"{manifest_path.name}  seed {seed}"


def window_bounds(a: argparse.Namespace) -> tuple[int, int]:
    """Explicit window end wins; else ``WHODUNIT_WINDOW_END_MS``; else now+2min.

    The scan is trace-id scoped, but differential VERIFY is a builder query that
    DOES honour the time window — so for a clean on-camera receipt the window
    must cover the corpus and nothing later (see tools/video/README.md).
    """
    end = (
        a.window_end_ms
        or int(os.environ.get("WHODUNIT_WINDOW_END_MS") or 0)
        or int(time.time() * 1000) + 120_000
    )
    hours = a.window_h
    if os.environ.get("WHODUNIT_WINDOW_H"):
        hours = float(os.environ["WHODUNIT_WINDOW_H"])
    return end - int(hours * 3600 * 1000), end


def build_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(prog="whodunit explain (scoped demo driver)")
    p.add_argument("--manifest", type=Path)
    p.add_argument("--latest", default=None, help="Newest manifest for this fault.")
    p.add_argument("--seed", type=int)
    p.add_argument("--traces", type=int)
    p.add_argument("--window-h", type=float, default=2.0)
    p.add_argument(
        "--window-end-ms",
        type=int,
        default=None,
        help=(
            "Explicit window end (epoch ms). The scan is trace-id scoped, but "
            "the differential VERIFY is a builder query that honours the time "
            "window — so the window must not extend past the corpus into later "
            "traffic (e.g. tools/video/trickle.py, which feeds the alert beat). "
            "Defaults to now + 2 min."
        ),
    )
    p.add_argument("--json", action="store_true", dest="as_json")
    p.add_argument("--hash-only", action="store_true")
    p.add_argument(
        "--board",
        action="store_true",
        help=(
            "Render the verdict + THE ELIMINATION BOARD only (beat 2). The "
            "compiled query and the receipt are beat 4's subject; splitting "
            "them keeps each beat's text large enough to read on video."
        ),
    )
    p.add_argument(
        "--quiet",
        action="store_true",
        help="Skip the result render; print only what --permalink/--arm/--dashboard emit.",
    )
    p.add_argument(
        "--receipt",
        action="store_true",
        help="Render ONLY the compiled query + the verification receipt (beat 4 close-up).",
    )
    p.add_argument("--permalink", action="store_true")
    p.add_argument("--arm", action="store_true")
    p.add_argument("--dashboard", action="store_true")
    p.add_argument("--webhook-url", default=None)
    p.add_argument("--no-verify", action="store_true")
    p.add_argument(
        "--cache",
        type=Path,
        default=None,
        help="Write the ExplainResult JSON here after a live run.",
    )
    p.add_argument(
        "--replay",
        type=Path,
        default=None,
        help=(
            "Re-render / re-materialize a cached ExplainResult without re-mining "
            "(the mine is ~7 min; the permalink and alert beats do not need a "
            "second lattice enumeration). The compiled query and every number "
            "are the cached LIVE run's."
        ),
    )
    return p.parse_args()


def _board(result, console) -> None:
    """Beat 2: the verdict panel and THE ELIMINATION BOARD, nothing else."""
    from rich.panel import Panel

    from whodunit.cli import _render_elimination_board, _verdict_style

    style = _verdict_style(result.verdict)
    console.print(
        Panel(
            f"[{style}]{result.verdict.value.upper()}[/]\n{result.headline}",
            title="whodunit | verdict",
            border_style=style,
        )
    )
    _render_elimination_board(result, console)
    c = result.cost
    console.print(
        f"[dim]cost meter[/] one scan, {c.scan_rows_scanned:,} rows, "
        f"{c.scan_duration_ms:.0f} ms  [dim](cached buckets may over-report)[/]"
    )


def _receipt(result, console) -> None:
    """Beat 4: the compiled query and the differential receipt, nothing else."""
    from whodunit.cli import _render_compiled, _render_receipt

    _render_compiled(result, console)
    _render_receipt(result, console)
    c = result.cost
    console.print(
        f"\n[dim]verdict hash[/] [bold]{result.verdict_hash[:16]}[/]"
        f"[dim]{result.verdict_hash[16:]}[/]\n"
        f"[dim]cost meter[/] scan {c.scan_rows_scanned:,} rows  |  "
        f"verify {c.verify_rows_scanned:,} rows  "
        f"[dim](cached buckets may over-report)[/]"
    )


def _materialize(console, client, result, a) -> None:
    mat = load_materializer(client)
    if mat is None or result.compiled is None or not result.compiled.envelope:
        console.print("[yellow]nothing to materialize[/]")
        return
    if a.permalink:
        url = mat.permalink(
            result.compiled,
            window_start_ms=result.window_start_unix_ms,
            window_end_ms=result.window_end_unix_ms,
        )
        console.print(f"[cyan]trace explorer[/] {url}")
    title = f"whodunit: {result.compiled.expression}"
    if a.dashboard:
        console.print(
            f"[green]created dashboard[/] "
            f"{mat.create_dashboard(result.compiled, title=title)}"
        )
    if a.arm:
        console.print(
            f"[green]armed alert[/] "
            f"{mat.arm_alert(result.compiled, rule_name=title, warn_threshold=1.0, crit_threshold=5.0, channel_webhook_url=a.webhook_url)}"  # noqa: E501
        )


def main() -> int:
    a = build_args()

    if a.replay is not None:
        from whodunit.pipeline import ExplainResult

        console = make_console()
        result = ExplainResult.model_validate_json(
            a.replay.read_text(encoding="utf-8")
        )
        if a.hash_only:
            print(f"verdict hash  {result.verdict_hash}")
            return 0
        if a.quiet:
            pass
        elif a.receipt:
            _receipt(result, console)
        elif a.board:
            _board(result, console)
        else:
            render(result, console)
        if a.permalink or a.arm or a.dashboard:
            with SigNozClient() as client:
                client.login()
                _materialize(console, client, result, a)
        return 0

    bad_ids, healthy_ids, all_ids, label = resolve_cohort(a)
    start, end = window_bounds(a)

    console = make_console()
    with SigNozClient() as client:
        client.login()
        console.print(
            f"[dim]cohort[/] {len(bad_ids)} bad  |  {len(healthy_ids)} healthy   "
            f"[dim]env[/] {ENVIRONMENT}   [dim]scope[/] trace_id IN (...) "
            f"[dim](one clickhouse_sql scan)[/]\n"
            f"[dim]corpus[/] {label}   [dim]window[/] "
            f"{time.strftime('%H:%M', time.localtime(start / 1000))}"
            f"-{time.strftime('%H:%M', time.localtime(end / 1000))}"
        )
        quiet = a.as_json or a.hash_only
        t0 = time.time()
        if quiet:
            run = _run(client, bad_ids, healthy_ids, all_ids, start, end, a)
        else:
            with status(
                console,
                "[bold cyan]extract -> mine -> compile -> verify[/] "
                "(FP-growth over the full itemset lattice)",
            ):
                run = _run(client, bad_ids, healthy_ids, all_ids, start, end, a)
            console.print(f"[dim]elapsed[/] {time.time() - t0:.1f}s\n")
        result = run.result

        if a.cache is not None:
            a.cache.parent.mkdir(parents=True, exist_ok=True)
            a.cache.write_text(result.model_dump_json(indent=2), encoding="utf-8")

        if a.hash_only:
            print(f"verdict hash  {result.verdict_hash}")
            return 0
        if a.board:
            _board(result, console)
            return 0
        if a.as_json:
            payload = json.loads(result.model_dump_json())
            payload["label_recall"] = run.label_recall
            payload["label_precision_incorpus"] = run.label_precision_incorpus
            print(json.dumps(payload, indent=2))
            return 0

        render(result, console)

        if a.permalink or a.arm or a.dashboard:
            _materialize(console, client, result, a)
    return 0


def _run(client, bad_ids, healthy_ids, all_ids, start, end, a):
    return explain_scoped(
        client,
        bad_ids=bad_ids,
        healthy_ids=healthy_ids,
        window_start_ms=start,
        window_end_ms=end,
        environment=ENVIRONMENT,
        scan_config=SCAN_CONFIG,
        mine_config=MINE_CONFIG,
        do_verify=not a.no_verify,
        all_corpus_ids=set(all_ids),
    )


if __name__ == "__main__":
    raise SystemExit(main())
