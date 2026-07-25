"""One `rich` Console factory shared by the demo drivers.

Interactively this is just `Console()`. Under `run_beat.py` (which sets
`WHODUNIT_CAPTURE=1`) stdout is a pipe, and on Windows `rich` then falls back to
the legacy-console renderer: ASCII box drawing and no colour, because it probes
the console handle for VT support and a pipe has none. Forcing `force_terminal`
and `legacy_windows=False` makes `rich` emit the same ANSI it emits in Windows
Terminal.

This only affects how output is ENCODED. No number, no ordering and no wording
changes.
"""
from __future__ import annotations

import contextlib
import os
from collections.abc import Iterator

from rich.console import Console


@contextlib.contextmanager
def status(console: Console, message: str) -> Iterator[None]:
    """`console.status`, except silent while being captured.

    A `rich` live spinner repaints itself with cursor-control sequences. Down a
    pipe those frames pile up into one long garbage line, and the capture
    renderer draws its own spinner anyway (with the real elapsed time), so under
    `WHODUNIT_CAPTURE` this is a no-op.
    """
    if os.environ.get("WHODUNIT_CAPTURE"):
        yield
        return
    with console.status(message):
        yield


def make_console(**kwargs: object) -> Console:
    if os.environ.get("WHODUNIT_CAPTURE"):
        width = int(os.environ.get("COLUMNS") or 118)
        return Console(
            force_terminal=True,
            legacy_windows=False,
            color_system="truecolor",
            width=width,
            **kwargs,  # type: ignore[arg-type]
        )
    return Console(**kwargs)  # type: ignore[arg-type]
