"""Unit tests for Trace Explorer permalink construction."""

from __future__ import annotations

import json
from urllib.parse import parse_qs, unquote, urlparse

from whodunit.materialize import permalink
from whodunit.types import CompiledQuery

from .conftest import load_golden


def test_composite_state_matches_golden(compiled: CompiledQuery) -> None:
    state = permalink.composite_query_state(compiled)
    golden = load_golden("permalink_composite.json")
    # the id is a fresh uuid per call; compare everything else exactly.
    state.pop("id")
    golden.pop("id")
    assert state == golden


def test_permalink_encodes_operator_and_leaves(compiled: CompiledQuery) -> None:
    url = permalink.build_permalink(
        compiled,
        ui_base_url="http://signoz.test",
        window_start_ms=1000,
        window_end_ms=2000,
    )
    assert url.startswith("http://signoz.test/traces-explorer?compositeQuery=")
    parsed = urlparse(url)
    params = parse_qs(parsed.query)
    # window recorded for provenance
    assert params["startTime"] == ["1000"]
    assert params["endTime"] == ["2000"]
    # DOUBLE-encoded: parse_qs decodes once, leaving %-escapes; decode again for JSON.
    once_decoded = params["compositeQuery"][0]
    assert once_decoded.startswith("%7B")  # still encoded after a single decode
    decoded = json.loads(unquote(once_decoded))
    op = decoded["builder"]["queryTraceOperator"]
    assert len(op) == 1
    assert op[0]["expression"] == "(A => B) && NOT C"
    assert op[0]["returnSpansFrom"] == "A"
    names = [q["queryName"] for q in decoded["builder"]["queryData"]]
    assert names == ["A", "B", "C"]
    # every leaf carries its v5 filter expression and is a disabled operand.
    for leaf in decoded["builder"]["queryData"]:
        assert leaf["filter"]["expression"]
        assert leaf["disabled"] is True


def test_permalink_ui_base_trailing_slash_normalised(compiled: CompiledQuery) -> None:
    url = permalink.build_permalink(
        compiled,
        ui_base_url="http://signoz.test/",
        window_start_ms=0,
        window_end_ms=0,
    )
    assert "signoz.test//traces-explorer" not in url
