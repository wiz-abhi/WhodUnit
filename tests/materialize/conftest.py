"""Shared fixtures for the materializer tests.

The ``compiled`` fixture rebuilds a :class:`CompiledQuery` from the compiler's own
golden envelope (``tests/compile/golden/ground_truth_conjunction.json``) so the
materializer is exercised against the real ground-truth conjunction
``(A => B) && NOT C`` rather than a hand-invented shape.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

import httpx
import pytest

from whodunit.signoz_client import SigNozClient, SigNozConfig
from whodunit.types import CompiledQuery, LeafQuery, Verification

Handler = Callable[[httpx.Request], httpx.Response]

_COMPILE_GOLDEN = (
    Path(__file__).resolve().parents[1]
    / "compile"
    / "golden"
    / "ground_truth_conjunction.json"
)
GOLDEN_DIR = Path(__file__).resolve().parent / "golden"


def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line(
        "markers",
        "live: hits a real SigNoz instance; requires SIGNOZ_LIVE=1 and creds.",
    )


def load_golden(name: str) -> Any:
    return json.loads((GOLDEN_DIR / name).read_text(encoding="utf-8"))


@pytest.fixture
def compiled() -> CompiledQuery:
    """The ground-truth compiled query, reconstructed from the compiler golden."""
    raw = json.loads(_COMPILE_GOLDEN.read_text(encoding="utf-8"))
    envelope = raw["envelope"]
    leaves: list[LeafQuery] = []
    for query in envelope["compositeQuery"]["queries"]:
        if query["type"] != "builder_query":
            continue
        spec = query["spec"]
        # Skip the independently-executed denominator duplicate (ADenom, …).
        if spec["name"].endswith("Denom"):
            continue
        leaves.append(
            LeafQuery(
                name=spec["name"],
                filters={"expression": spec["filter"]["expression"]},
            )
        )
    return CompiledQuery(
        envelope=envelope,
        expression=raw["expression"],
        return_spans_from=raw["return_spans_from"],
        leaf_queries=leaves,
        verification=Verification(
            mined_count=1284,
            signoz_count=1284,
            match=True,
            precision=0.98,
            recall=0.95,
        ),
        signoz_version="v0.132.2",
    )


def make_client(handler: Handler) -> SigNozClient:
    """A SigNozClient wired to a mock transport that auto-answers login."""
    config = SigNozConfig(
        url="http://signoz.test",
        email="user@example.com",
        password="secret",
        org_id="org-123",
    )
    return SigNozClient(config, transport=httpx.MockTransport(handler))
