"""Whodunit CLI — ``whodunit explain`` and ``whodunit conformance``.

Rich, legible output built around the demo script (WHODUNIT-CONCEPT §7):

* a plain-language headline verdict;
* THE ELIMINATION BOARD — family size -> survivors, near-misses shown *with*
  their lifts beside the winner;
* the compiled operator expression + its leaf builder queries, pretty-printed;
* a verification receipt (mined N vs SigNoz N, MATCH, precision/recall, rows);
* refusals surfaced prominently;
* the verdict hash (the determinism proof) and a cost meter.

``--json`` dumps the whole :class:`~whodunit.pipeline.ExplainResult` as JSON.
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Annotated, Any

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from whodunit.extract import CohortSpec, ScanConfig
from whodunit.mine import MineConfig
from whodunit.pipeline import ExplainResult, explain, load_materializer
from whodunit.signoz_client import SigNozClient
from whodunit.types import Finding, Verdict

app = typer.Typer(
    help="Whodunit — deterministic structural root cause you can own.",
    add_completion=False,
    no_args_is_help=True,
)


# --------------------------------------------------------------------------- #
# Input resolution
# --------------------------------------------------------------------------- #
def _window_ms(window_h: float) -> tuple[int, int]:
    """The scan/verify window: the last ``window_h`` hours ending now."""
    end = int(time.time() * 1000)
    start = end - int(window_h * 3600 * 1000)
    return start, end


def _read_trace_ids(path: Path) -> tuple[str, ...]:
    text = path.read_text(encoding="utf-8").strip()
    if not text:
        return ()
    # Accept either a JSON array or newline/whitespace-separated ids.
    if text.lstrip().startswith("["):
        loaded = json.loads(text)
        return tuple(str(x) for x in loaded)
    return tuple(tok for tok in text.split() if tok)


def _spec_from_manifest(
    manifest_path: Path, window_h: float
) -> tuple[CohortSpec, dict[str, Any]]:
    data = json.loads(manifest_path.read_text(encoding="utf-8"))
    env = data.get("deployment_environment") or "whodunit-demo"
    bad_ids = data.get("bad_trace_ids")
    if not isinstance(bad_ids, list) or not bad_ids:
        raise typer.BadParameter(
            f"manifest {manifest_path} has no inline bad_trace_ids"
        )
    # Window is now-relative (--window-h). The corpus's OTLP timestamps track
    # actual send time, not the manifest's ``base_time`` metadata, so the recent
    # emission is found by a trailing window rather than the manifest's window.
    start, end = _window_ms(window_h)
    spec = CohortSpec(
        window_start_unix_ms=start,
        window_end_unix_ms=end,
        trace_ids=tuple(str(x) for x in bad_ids),
        environment=env,
    )
    return spec, data


def _build_spec(
    *,
    bad_filter: str | None,
    bad_trace_ids_file: Path | None,
    from_manifest: Path | None,
    window_h: float,
    environment: str,
) -> tuple[CohortSpec, dict[str, Any] | None]:
    provided = [bad_filter, bad_trace_ids_file, from_manifest]
    if sum(x is not None for x in provided) != 1:
        raise typer.BadParameter(
            "supply exactly one of --bad-filter, --bad-trace-ids-file, "
            "--from-manifest"
        )
    if from_manifest is not None:
        return _spec_from_manifest(from_manifest, window_h)
    start, end = _window_ms(window_h)
    if bad_trace_ids_file is not None:
        ids = _read_trace_ids(bad_trace_ids_file)
        if not ids:
            raise typer.BadParameter(f"{bad_trace_ids_file} contained no trace ids")
        spec = CohortSpec(
            window_start_unix_ms=start,
            window_end_unix_ms=end,
            trace_ids=ids,
            environment=environment,
        )
        return spec, None
    spec = CohortSpec(
        window_start_unix_ms=start,
        window_end_unix_ms=end,
        ch_filter=bad_filter,
        environment=environment,
    )
    return spec, None


# --------------------------------------------------------------------------- #
# Rendering
# --------------------------------------------------------------------------- #
def _verdict_style(verdict: Verdict) -> str:
    return {
        Verdict.DISCRIMINATOR: "bold green",
        Verdict.PARTIAL: "bold yellow",
        Verdict.ABSTAIN: "bold red",
    }[verdict]


def _fmt_itemset(itemset: list[str]) -> str:
    # ASCII-only: the Windows legacy console (cp1252) cannot encode glyphs like
    # U+2227, so rendering must stay in the ASCII range to be cross-platform.
    return " AND ".join(
        (f"NOT {i[4:]}" if i.startswith("NOT ") else i) for i in itemset
    )


def render(result: ExplainResult, console: Console) -> None:
    """Render an :class:`ExplainResult` as the demo's rich report."""
    style = _verdict_style(result.verdict)
    console.print(
        Panel(
            f"[{style}]{result.verdict.value.upper()}[/]\n{result.headline}",
            title="whodunit | verdict",
            border_style=style,
        )
    )

    _render_elimination_board(result, console)

    if result.compiled is not None and result.compiled.expression:
        _render_compiled(result, console)

    if result.verification is not None:
        _render_receipt(result, console)

    if result.refusals:
        _render_refusals(result, console)

    _render_footer(result, console)


def _render_elimination_board(result: ExplainResult, console: Console) -> None:
    table = Table(
        title="THE ELIMINATION BOARD",
        caption=(
            f"{result.family_size} candidate itemsets enumerated | "
            f"{result.cost.n_features} features | "
            f"{len(result.mine_result_findings)} survivor(s)"
        ),
        show_lines=False,
    )
    table.add_column("", style="dim", width=3)
    table.add_column("candidate", overflow="fold")
    table.add_column("lift", justify="right")
    table.add_column("95% CI", justify="right")
    table.add_column("bad", justify="right")
    table.add_column("healthy", justify="right")
    table.add_column("verdict")

    chosen = result.chosen_finding

    def _row(mark: str, f: Finding, style: str) -> None:
        ci = f"[{f.ci_low:.1f}, {f.ci_high:.1f}]"
        table.add_row(
            mark,
            f"[{style}]{_fmt_itemset(f.itemset)}[/]",
            f"{f.lift:.1f}x",
            ci,
            str(f.support_bad),
            str(f.support_healthy),
            f.verdict.value,
        )

    for f in result.mine_result_findings:
        is_winner = chosen is not None and f.itemset == chosen.itemset
        _row(">" if is_winner else " ", f, "bold green" if is_winner else "green")

    if result.near_misses:
        table.add_section()
        for f in result.near_misses:
            _row("x", f, "yellow")

    console.print(table)
    if result.near_misses and chosen is not None:
        console.print(
            f"[dim]Winner survives on lift {chosen.lift:.1f}x where every "
            f"single-predicate near-miss above was eliminated — that is the "
            f"conjunction earning its keep.[/]"
        )


def _render_compiled(result: ExplainResult, console: Console) -> None:
    compiled = result.compiled
    assert compiled is not None
    lines = [f"[bold cyan]{compiled.expression}[/]", ""]
    lines.append(f"[dim]returnSpansFrom[/] = {compiled.return_spans_from}")
    lines.append("")
    lines.append("[bold]leaf builder queries[/]")
    for leaf in compiled.leaf_queries:
        expr = leaf.filters.get("expression", "")
        lines.append(f"  [green]{leaf.name}[/] : {expr}")
    console.print(
        Panel(
            "\n".join(lines),
            title="compiled trace-operator query (yours to keep)",
            border_style="cyan",
        )
    )


def _render_receipt(result: ExplainResult, console: Console) -> None:
    v = result.verification
    assert v is not None
    match_txt = "[bold green]MATCH[/]" if v.match else "[bold red]MISMATCH[/]"
    parts = [
        f"mined [bold]{v.mined_count}[/]",
        f"SigNoz [bold]{v.signoz_count}[/]",
        match_txt,
    ]
    if v.precision is not None:
        parts.append(f"precision {v.precision:.2f}")
    if v.recall is not None:
        parts.append(f"recall {v.recall:.2f}")
    if v.rows_scanned is not None:
        parts.append(f"{v.rows_scanned:,} rows scanned")
    console.print(
        Panel(
            "  |  ".join(parts),
            title="verification receipt (differential)",
            border_style="green" if v.match else "red",
        )
    )


def _render_refusals(result: ExplainResult, console: Console) -> None:
    lines = []
    for r in result.refusals:
        lines.append(f"[yellow]x {_fmt_itemset(r.itemset)}[/]")
        lines.append(f"   [dim]{r.reason}[/]")
    console.print(
        Panel(
            "\n".join(lines),
            title="REFUSALS (surfaced, never swallowed)",
            border_style="yellow",
        )
    )


def _render_footer(result: ExplainResult, console: Console) -> None:
    c = result.cost
    cost_bits = []
    if c.scan_rows_scanned is not None:
        cost_bits.append(f"scan {c.scan_rows_scanned:,} rows")
    if c.scan_duration_ms is not None:
        cost_bits.append(f"{c.scan_duration_ms:.0f} ms")
    if c.verify_rows_scanned is not None:
        cost_bits.append(f"verify {c.verify_rows_scanned:,} rows")
    cost_str = "  |  ".join(cost_bits) if cost_bits else "n/a"
    console.print(
        f"[dim]verdict hash[/] [bold]{result.verdict_hash}[/]\n"
        f"[dim]cost meter[/] {cost_str}  "
        f"[dim](cached buckets may over-report)[/]"
    )


# --------------------------------------------------------------------------- #
# explain command
# --------------------------------------------------------------------------- #
@app.command("explain")
def explain_cmd(
    bad_filter: Annotated[
        str | None,
        typer.Option("--bad-filter", help="ClickHouse bool filter defining the bad cohort."),
    ] = None,
    bad_trace_ids_file: Annotated[
        Path | None,
        typer.Option(
            "--bad-trace-ids-file",
            help="File of bad trace ids (JSON array or whitespace-separated).",
            exists=True,
            dir_okay=False,
        ),
    ] = None,
    from_manifest: Annotated[
        Path | None,
        typer.Option(
            "--from-manifest",
            help="A corpus manifest whose bad_trace_ids define the cohort.",
            exists=True,
            dir_okay=False,
        ),
    ] = None,
    window_h: Annotated[
        float, typer.Option("--window-h", help="Window size in hours (ending now).")
    ] = 24.0,
    environment: Annotated[
        str,
        typer.Option("--environment", help="deployment.environment scope."),
    ] = "whodunit-demo",
    seed: Annotated[
        int | None,
        typer.Option("--seed", help="Deterministic mining seed override."),
    ] = None,
    max_itemset_size: Annotated[
        int, typer.Option("--max-k", help="Max itemset size (FP-growth k).")
    ] = 3,
    as_json: Annotated[
        bool, typer.Option("--json", help="Emit the full ExplainResult as JSON.")
    ] = False,
    arm: Annotated[
        bool, typer.Option("--arm", help="Arm an alert from the compiled query.")
    ] = False,
    dashboard: Annotated[
        bool, typer.Option("--dashboard", help="Create a dashboard from the query.")
    ] = False,
    no_verify: Annotated[
        bool, typer.Option("--no-verify", help="Skip live differential verification.")
    ] = False,
    ancestors: Annotated[
        bool,
        typer.Option(
            "--ancestors/--no-ancestors",
            help="Include transitive-ancestor (->) features, not just direct edges (=>).",
        ),
    ] = False,
) -> None:
    """Explain a bad cohort: extract -> mine -> compile -> verify."""
    spec, _manifest = _build_spec(
        bad_filter=bad_filter,
        bad_trace_ids_file=bad_trace_ids_file,
        from_manifest=from_manifest,
        window_h=window_h,
        environment=environment,
    )
    mine_config = MineConfig(
        max_itemset_size=max_itemset_size,
        **({"seed": seed} if seed is not None else {}),
    )
    scan_config = ScanConfig(include_ancestors=ancestors)

    console = Console()
    with SigNozClient() as client:
        result = explain(
            client,
            spec,
            scan_config=scan_config,
            mine_config=mine_config,
            do_verify=not no_verify,
        )
        if as_json:
            typer.echo(result.model_dump_json(indent=2))
        else:
            render(result, console)
        if arm or dashboard:
            _do_materialize(client, result, console, arm=arm, dashboard=dashboard)


def _do_materialize(
    client: SigNozClient,
    result: ExplainResult,
    console: Console,
    *,
    arm: bool,
    dashboard: bool,
) -> None:
    if result.compiled is None or not result.compiled.envelope:
        console.print("[yellow]nothing compiled to materialize (abstained/refused)[/]")
        return
    mat = load_materializer(client)
    if mat is None:
        console.print("materializer not yet installed")
        return
    title = f"whodunit: {result.compiled.expression}"
    try:
        # Best-effort Trace Explorer permalink (nice-to-have; ignore if the
        # materializer does not expose it).
        permalink = getattr(mat, "permalink", None)
        if permalink is not None and result.window_start_unix_ms is not None:
            url = permalink(
                result.compiled,
                window_start_ms=result.window_start_unix_ms,
                window_end_ms=result.window_end_unix_ms,
            )
            console.print(f"[cyan]trace explorer[/] {url}")
        if dashboard:
            ref = mat.create_dashboard(result.compiled, title=title)
            console.print(f"[green]created dashboard[/] {ref}")
        if arm:
            ref = mat.arm_alert(
                result.compiled,
                rule_name=title,
                warn_threshold=1.0,
                crit_threshold=1.0,
                channel_webhook_url=None,
            )
            console.print(f"[green]armed alert[/] {ref}")
    except Exception as exc:
        console.print(f"[red]materialization failed:[/] {exc}")


# --------------------------------------------------------------------------- #
# conformance command
# --------------------------------------------------------------------------- #
@app.command()
def conformance(
    window_h: Annotated[
        float, typer.Option("--window-h", help="Window size in hours (ending now).")
    ] = 24.0,
    environment: Annotated[
        str, typer.Option("--environment", help="deployment.environment scope.")
    ] = "whodunit-demo",
    parent_service: Annotated[
        str, typer.Option("--parent", help="Edge parent service (leaf A).")
    ] = "shop-payment",
    child_span: Annotated[
        str, typer.Option("--child", help="Edge child span name (leaf B).")
    ] = "redis-retry",
    absent_service: Annotated[
        str, typer.Option("--absent", help="Negated service (leaf C).")
    ] = "shop-flag-service",
) -> None:
    """Replay the trace-operator conformance battery; print the Markdown table."""
    from whodunit.compile import run_conformance, to_markdown

    start, end = _window_ms(window_h)
    base_filter = f"deployment.environment = '{environment}'"
    leaves = {
        "A": f"service.name = '{parent_service}'",
        "B": f"name = '{child_span}'",
        "C": f"service.name = '{absent_service}'",
    }
    with SigNozClient() as client:
        rows = run_conformance(
            client, leaves, base_filter=base_filter, start=start, end=end
        )
    typer.echo(to_markdown(rows))


def main() -> None:
    app()


if __name__ == "__main__":
    main()
