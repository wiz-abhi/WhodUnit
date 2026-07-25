"""The abstention beat: what the engine does when there is no answer to give.

Everything printed here is read out of the committed benchmark artifacts —
``benchmark/results.json`` (the machine-readable record of the 946.5s live run
that produced ``benchmark/REPORT.md``) and ``benchmark/ISSUES.md`` #2. Nothing
is recomputed, rounded differently, or typed by hand: if a number is on screen,
it is in one of those two files.

    uv run python tools/video/demo_abstention.py --board
    uv run python tools/video/demo_abstention.py --miss cache_bypass

``--board`` prints the six-scenario table with the two ABSTAIN rows and the one
PARTIAL row called out, plus the false-culprit count.
``--miss`` prints the scenario whodunit first got WRONG: the original ABSTAIN,
the two-engine seam that caused it, the fix, and the verified re-run.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "tools" / "video"))

from _console import make_console  # noqa: E402
from rich.panel import Panel  # noqa: E402
from rich.table import Table  # noqa: E402

RESULTS = REPO / "benchmark" / "results.json"

# How each verdict is coloured on the board. The honesty path (abstain/partial)
# is the point of the beat, so it gets the loud styles.
VERDICT_STYLE = {
    "discriminator": "green",
    "partial": "bold yellow",
    "abstain": "bold cyan",
}


def load() -> tuple[dict, list[dict]]:
    doc = json.loads(RESULTS.read_text(encoding="utf-8"))
    return doc, doc["results"]


def fmt(x: float | None, nd: int = 2) -> str:
    return "-" if x is None else f"{x:.{nd}f}"


def board(console) -> None:
    doc, rows = load()
    table = Table(
        title="BENCHMARK - 6 seeded faults, scored against the corpus manifest",
        caption=(
            f"live run {doc['generated_at']}, {doc['total_wall_clock_s']:.1f}s "
            "wall-clock | gate: precision >= 0.80 AND recall >= 0.50"
        ),
        title_style="bold",
        caption_style="dim",
    )
    table.add_column("scenario", overflow="fold")
    table.add_column("ground truth")
    table.add_column("whodunit")
    table.add_column("recall", justify="right")
    table.add_column("flat baseline p / r", justify="right")
    table.add_column("baseline")

    for r in rows:
        got = r["got"]
        style = VERDICT_STYLE.get(got, "white")
        # The honesty rows get a marker so the eye lands on them first.
        mark = "  " if got == "discriminator" else "> "
        table.add_row(
            f"[{'dim' if got == 'discriminator' else 'bold'}]{mark}{r['key']}[/]",
            f"[dim]{r['expected']}[/]",
            f"[{style}]{got.upper()}[/]",
            fmt(r["label_recall"]),
            f"{fmt(r['baseline_precision'])} / {fmt(r['baseline_recall'])}",
            "[dim]ties[/]" if r["baseline_found"] else "[red]FAILS[/]",
        )
    console.print(table)

    n = len(rows)
    passed = sum(1 for r in rows if r["passed"])
    culprits = sum(1 for r in rows if r["false_culprit"])
    abstained = [r["key"] for r in rows if r["got"] == "abstain"]
    partial = [r["key"] for r in rows if r["got"] == "partial"]
    console.print(
        Panel(
            f"[bold]{passed}/{n} pass[/]   "
            f"[bold green]{culprits} false culprits[/] [dim]across all six.[/]\n"
            f"[bold cyan]ABSTAIN[/] [dim]on[/] {', '.join(abstained)}  "
            f"[dim]- a decoy that tracks failure without causing it, and a cohort "
            f"with nothing wrong in it.[/]\n"
            f"[bold yellow]PARTIAL[/] [dim]on[/] {', '.join(partial)}"
            f"{' ' * 14}[dim]- a cardinality fault the algebra cannot phrase; "
            f"surfaced as a symptom, never claimed as a culprit.[/]",
            title="it never named a culprit that was not there",
            border_style="cyan",
        )
    )


def miss(console, key: str) -> None:
    _, rows = load()
    r = next(x for x in rows if x["key"] == key)
    refusal = r["refusals"][0].split(":", 1)[1].strip() if r["refusals"] else ""

    console.print(
        Panel(
            f"[bold red]ABSTAIN[/] [dim]- and a real answer existed. The flat "
            f"baseline found it:[/] [yellow]{r['baseline_predicate']}[/]"
            f"[dim], precision {fmt(r['baseline_precision'])} / recall "
            f"{fmt(r['baseline_recall'])}.[/]\n"
            f"[bold]why[/]   the compiler refused the winner: [dim]{refusal}[/]\n"
            f"      and the miner's MDL dominance prune had already dropped the "
            f"compilable positive-anchored superset,\n"
            f"      which shares the minimal itemset's CI floor. Neither engine is "
            f"wrong on its own.",
            title=f"the one it FIRST GOT WRONG - {key} (seed {r['seed']})",
            border_style="red",
        )
    )
    console.print(
        Panel(
            f"[bold]fix[/]     [dim]whodunit.pipeline._select_finding[/] - when every "
            f"survivor is refusable, recover the best\n"
            f"        COMPILABLE near-miss whose lift-CI floor ties the refused tier. "
            f"[dim]Sibling compiler and miner untouched.[/]\n"
            f"[bold]re-run[/]  [bold cyan]{r['expression']}[/]  =  "
            f"[cyan]{' && '.join(r['chosen_itemset'])}[/]\n"
            f"        label-recall [bold green]{fmt(r['label_recall'], 1)}[/]   "
            f"in-corpus precision [bold green]{fmt(r['label_precision'], 1)}[/]   "
            f"live verification "
            f"[bold green]{r['verify_mined']}/{r['verify_signoz']} match[/]   "
            f"[dim]original failure kept in benchmark/ISSUES.md #2[/]",
            title="found the seam, fixed it, kept the receipt",
            border_style="green",
        )
    )


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--board", action="store_true",
                    help="the six-scenario benchmark table")
    ap.add_argument("--miss", metavar="SCENARIO", default=None,
                    help="the loss-then-fix for one scenario (cache_bypass)")
    a = ap.parse_args()
    if not RESULTS.exists():
        raise SystemExit(f"missing {RESULTS} - run benchmark/run.py first")

    console = make_console()
    if a.board or not a.miss:
        board(console)
    if a.miss:
        miss(console, a.miss)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
