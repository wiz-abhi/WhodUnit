"""CLI smoke tests via typer's CliRunner.

Network is neutralised two ways: ``whodunit.cli.SigNozClient`` is replaced with
the :class:`FakeClient`, and ``whodunit.pipeline.extract_matrix`` returns the
synthetic matrix, so ``whodunit explain`` runs the real pipeline offline.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest
from typer.testing import CliRunner

from whodunit import cli, pipeline

from .conftest import EDGE_NAME, FakeClient, build_synthetic_matrix

runner = CliRunner()

_ANSI = re.compile(r"\x1b\[[0-9;]*[A-Za-z]")


def _help_text(*args: str) -> str:
    """`--help` output rendered at a fixed width with colour off.

    Rich lays help out to the terminal width and interleaves ANSI codes. On a CI
    runner (80 columns, no TTY) long option names wrap mid-string, so a plain
    substring assertion passes locally and fails there. Pinning COLUMNS and
    stripping ANSI keeps these assertions about the CLI rather than the terminal.
    """
    result = runner.invoke(
        cli.app,
        [*args, "--help"],
        env={"COLUMNS": "200", "TERM": "dumb", "NO_COLOR": "1"},
    )
    assert result.exit_code == 0, result.output
    return _ANSI.sub("", result.output)


@pytest.fixture
def offline(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        pipeline, "extract_matrix", lambda *a, **k: build_synthetic_matrix()
    )
    monkeypatch.setattr(cli, "SigNozClient", lambda *a, **k: FakeClient(scalar_count=40))


def test_help() -> None:
    out = _help_text()
    assert "explain" in out
    assert "conformance" in out


def test_explain_help() -> None:
    out = _help_text("explain")
    assert "--bad-filter" in out
    assert "--from-manifest" in out
    assert "--arm" in out


def test_explain_requires_exactly_one_source(offline: None) -> None:
    result = runner.invoke(cli.app, ["explain"])
    assert result.exit_code != 0


def test_explain_json_on_fixture(offline: None) -> None:
    result = runner.invoke(
        cli.app, ["explain", "--bad-filter", "order.completed = false", "--json"]
    )
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["verdict"] == "discriminator"
    assert payload["verdict_hash"]
    assert payload["compiled"]["expression"] == "(A => B) && NOT C"
    itemset = set(payload["chosen_finding"]["itemset"])
    assert EDGE_NAME in itemset


def test_explain_human_render(offline: None) -> None:
    result = runner.invoke(cli.app, ["explain", "--bad-filter", "order.completed = false"])
    assert result.exit_code == 0, result.output
    assert "ELIMINATION BOARD" in result.output
    assert "DISCRIMINATOR" in result.output.upper()
    assert "verdict hash" in result.output


def test_explain_from_manifest(offline: None, tmp_path: Path) -> None:
    manifest = tmp_path / "manifest.json"
    manifest.write_text(
        json.dumps(
            {
                "deployment_environment": "whodunit-demo",
                "bad_trace_ids": [f"trace{i:05d}" for i in range(40)],
            }
        ),
        encoding="utf-8",
    )
    result = runner.invoke(
        cli.app, ["explain", "--from-manifest", str(manifest), "--json"]
    )
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["environment"] == "whodunit-demo"


def test_explain_arm_without_materializer(offline: None, monkeypatch: pytest.MonkeyPatch) -> None:
    # Force the lazy import to fail so the graceful message path runs.
    monkeypatch.setattr(cli, "load_materializer", lambda client: None)
    result = runner.invoke(
        cli.app, ["explain", "--bad-filter", "order.completed = false", "--arm"]
    )
    assert result.exit_code == 0, result.output
    assert "materializer not yet installed" in result.output


def test_bad_trace_ids_file(offline: None, tmp_path: Path) -> None:
    ids_file = tmp_path / "ids.txt"
    ids_file.write_text("\n".join(f"trace{i:05d}" for i in range(40)), encoding="utf-8")
    result = runner.invoke(
        cli.app, ["explain", "--bad-trace-ids-file", str(ids_file), "--json"]
    )
    assert result.exit_code == 0, result.output
    assert json.loads(result.output)["verdict"] == "discriminator"


def test_read_ids_from_json_array(tmp_path: Path) -> None:
    f = tmp_path / "ids.json"
    f.write_text('["aaa", "bbb", "ccc"]', encoding="utf-8")
    assert cli._read_trace_ids(f) == ("aaa", "bbb", "ccc")
