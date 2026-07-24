"""CLI entry point placeholder.

The full ``whodunit explain`` command lands in Wave 3; this stub keeps the
console-script wiring honest and importable.
"""

from __future__ import annotations

import typer

app = typer.Typer(help="Whodunit — deterministic structural root cause.")


@app.command()
def version() -> None:
    """Print the installed version."""
    from whodunit import __version__

    typer.echo(__version__)


def main() -> None:
    app()


if __name__ == "__main__":
    main()
