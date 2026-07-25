"""The flat-baseline beat: run `benchmark/baseline.py` on the SAME cohort.

`baseline.py` is a library (the harness feeds it the miner's own matrix), so
this driver rebuilds that exact matrix — one `clickhouse_sql` scan over the same
trace-id-scoped cohort, same `ScanConfig` — and ranks every SINGLE feature in
both polarities by a two-proportion z-test. No mining: the point is that the
flat tool never gets to a conjunction.

Prints the baseline's top picks with their precision/recall, then the winning
conjunction from the cached whodunit run for contrast.

    uv run python tools/video/demo_baseline.py --latest conditional_dep \
        --compare docs/video/raw/explain-result.json
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "benchmark"))
sys.path.insert(0, str(REPO / "tools" / "video"))

from _console import make_console, status  # noqa: E402
from rich.panel import Panel  # noqa: E402
from rich.table import Table  # noqa: E402

from whodunit.extract import build_feature_matrix, run_scan  # noqa: E402
from whodunit.pipeline import booleanize_frame  # noqa: E402
from whodunit.signoz_client import SigNozClient  # noqa: E402

from baseline import run_baseline  # noqa: E402
from demo_explain import ENVIRONMENT, SCAN_CONFIG, resolve_cohort, window_bounds  # noqa: E402


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--manifest", type=Path)
    p.add_argument("--latest", default=None)
    p.add_argument("--seed", type=int)
    p.add_argument("--traces", type=int)
    p.add_argument("--window-h", type=float, default=2.0)
    p.add_argument("--window-end-ms", type=int, default=None)
    p.add_argument("--compare", type=Path, default=None)
    p.add_argument("--top", type=int, default=6)
    a = p.parse_args()

    bad_ids, healthy_ids, all_ids, label = resolve_cohort(a)
    start, end = window_bounds(a)
    console = make_console()
    console.print(
        f"[bold]flat BubbleUp-style baseline[/] - single-feature two-proportion "
        f"z-test, both polarities\n[dim]same cohort as whodunit:[/] "
        f"{len(bad_ids)} bad | {len(healthy_ids)} healthy  [dim]({label})[/]\n"
    )

    t0 = time.time()
    with SigNozClient() as client:
        client.login()
        with status(console, "[cyan]one scan -> trace x feature matrix[/]"):
            scan = run_scan(
                client,
                bad_ids=tuple(bad_ids),
                healthy_ids=tuple(healthy_ids),
                window_start_unix_ms=start,
                window_end_unix_ms=end,
                environment=ENVIRONMENT,
                config=SCAN_CONFIG,
            )
            mm = build_feature_matrix(
                scan,
                n_traces_bad=len(bad_ids),
                n_traces_healthy=len(healthy_ids),
                window_start_unix_ms=start,
                window_end_unix_ms=end,
            )
    frame = booleanize_frame(mm.frame, mm.meta.columns)
    top, ranking = run_baseline(frame, mm.meta.columns)

    table = Table(
        title="FLAT BASELINE - best SINGLE predicates (no conjunctions)",
        caption=(
            f"{len(mm.meta.columns)} features x 2 polarities ranked by z | "
            f"gate: precision >= 0.80 AND recall >= 0.50 | {time.time() - t0:.1f}s"
        ),
    )
    table.add_column("", style="dim", width=3)
    table.add_column("single predicate", overflow="fold")
    table.add_column("z", justify="right")
    table.add_column("precision", justify="right")
    table.add_column("recall", justify="right")
    table.add_column("verdict")
    for pick in ranking[: a.top]:
        mark = ">" if pick is top else " "
        style = "bold yellow" if pick is top else "dim"
        z = "inf" if pick.z == float("inf") else f"{pick.z:.1f}"
        table.add_row(
            mark,
            f"[{style}]{pick.predicate}[/]",
            z,
            "-" if pick.precision is None else f"{pick.precision:.2f}",
            "-" if pick.recall is None else f"{pick.recall:.2f}",
            "[green]separates[/]" if pick.found else "[red]FAILS THE GATE[/]",
        )
    console.print(table)

    if top is not None:
        console.print(
            Panel(
                f"best single predicate  [bold yellow]{top.predicate}[/]\n"
                f"precision [bold red]{top.precision:.2f}[/]   "
                f"recall {top.recall:.2f}   "
                f"-> [bold red]{'FOUND' if top.found else 'NOT A DISCRIMINATOR'}[/]",
                title="what every flat tool sees",
                border_style="red",
            )
        )

    if a.compare is not None and a.compare.exists():
        cached = json.loads(a.compare.read_text(encoding="utf-8"))
        comp = cached.get("compiled") or {}
        ver = cached.get("verification") or {}
        chosen = cached.get("chosen_finding") or {}
        console.print(
            Panel(
                f"[bold cyan]{comp.get('expression', '')}[/]  "
                f"[dim]lift[/] [bold]{chosen.get('lift', 0):.1f}x[/]\n"
                f"precision [bold green]{ver.get('precision')}[/]   "
                f"recall [bold green]{ver.get('recall')}[/]   "
                f"-> [bold green]DISCRIMINATOR[/]",
                title="whodunit's conjunction, same cohort, same matrix",
                border_style="green",
            )
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
