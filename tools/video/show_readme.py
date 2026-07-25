"""Render the repo README's headline block in the terminal (beat 8).

The GitHub repo is private while the hackathon submission is in flight, so an
anonymous browser shot of the README 404s. This renders the committed
`README.md` itself — the same bytes that are pushed — with `rich`.

    uv run python tools/video/show_readme.py [--lines 34]
"""
from __future__ import annotations

import argparse
from pathlib import Path

from _console import make_console
from rich.markdown import Markdown
from rich.panel import Panel

REPO = Path(__file__).resolve().parents[2]


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--lines", type=int, default=27)
    a = p.parse_args()
    text = (REPO / "README.md").read_text(encoding="utf-8")
    # Drop the badge block (image links render as noise in a terminal).
    kept = [ln for ln in text.splitlines() if not ln.startswith("![")]
    body = "\n".join(kept[: a.lines])
    console = make_console()
    console.print(Panel(Markdown(body), title="README.md", border_style="cyan"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
