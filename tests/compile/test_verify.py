"""Unit tests for the differential verifier, using a mocked transport."""

from __future__ import annotations

import json

import httpx
import pytest

from whodunit.compile.emit import compile_finding
from whodunit.compile.verify import (
    operator_query_name,
    precision_recall,
    scalar_value,
    verify,
)
from whodunit.signoz_client import SigNozClient, SigNozConfig
from whodunit.types import FeatureColumn, FeatureKind, Finding, Verdict


def _columns() -> list[FeatureColumn]:
    return [
        FeatureColumn(
            name="edge",
            kind=FeatureKind.EDGE,
            edge_parent="shop-payment",
            edge_child="span:redis-retry",
        ),
        FeatureColumn(name="flag", kind=FeatureKind.SPAN_PREDICATE, service_name="flag"),
    ]


def _finding() -> Finding:
    return Finding(
        itemset=["edge", "NOT flag"],
        lift=41.0,
        ci_low=30.0,
        ci_high=55.0,
        support_bad=55,
        support_healthy=1,
        verdict=Verdict.DISCRIMINATOR,
    )


def _scalar_response(op_name: str, value: int) -> dict[str, object]:
    return {
        "status": "success",
        "data": {
            "meta": {"rowsScanned": 12345},
            "data": {
                "results": [
                    {"queryName": op_name, "data": [[value]], "columns": []}
                ]
            },
        },
    }


def _trace_response(op_name: str, trace_ids: list[str]) -> dict[str, object]:
    return {
        "status": "success",
        "data": {
            "meta": {"rowsScanned": 999},
            "data": {
                "results": [
                    {
                        "queryName": op_name,
                        "nextCursor": "",
                        "rows": [{"data": {"trace_id": t}} for t in trace_ids],
                    }
                ]
            },
        },
    }


def _client(handler: object) -> SigNozClient:
    config = SigNozConfig(
        url="http://signoz.test", email="e@x.com", password="p", org_id="o"
    )
    return SigNozClient(config, transport=httpx.MockTransport(handler))  # type: ignore[arg-type]


# --------------------------------------------------------------------------- #
# pure helpers
# --------------------------------------------------------------------------- #


def test_scalar_value_extraction() -> None:
    resp = _scalar_response("T1", 55)
    assert scalar_value(resp, "T1") == 55


def test_scalar_value_empty_result_is_zero_not_error() -> None:
    """A query that ran but matched nothing (empty ``data``) is a genuine zero —
    a legitimately-empty discriminator must not crash verification."""
    resp: dict[str, object] = {
        "status": "success",
        "data": {"meta": {}, "data": {"results": [{"queryName": "T1", "data": []}]}},
    }
    assert scalar_value(resp, "T1") == 0


def test_scalar_value_absent_query_still_raises() -> None:
    """A truly missing query name is a malformed response, not a zero."""
    resp = _scalar_response("T1", 55)
    with pytest.raises(ValueError):
        scalar_value(resp, "NOPE")


def test_precision_recall() -> None:
    matched = {"a", "b", "c"}
    bad = {"a", "b", "d", "e"}
    precision, recall = precision_recall(matched, bad)
    assert precision == 2 / 3
    assert recall == 2 / 4


def test_operator_query_name() -> None:
    compiled = compile_finding(_finding(), _columns())
    assert operator_query_name(compiled.envelope) == "T1"


# --------------------------------------------------------------------------- #
# full verify orchestration
# --------------------------------------------------------------------------- #


def test_verify_match_with_precision_recall() -> None:
    compiled = compile_finding(_finding(), _columns())
    matched_ids = [f"t{i}" for i in range(55)]

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("email_password"):
            return httpx.Response(200, content=json.dumps({"data": {"accessToken": "t"}}))
        body = json.loads(request.content)
        if body.get("requestType") == "trace":
            return httpx.Response(200, content=json.dumps(_trace_response("T1", matched_ids)))
        return httpx.Response(200, content=json.dumps(_scalar_response("T1", 55)))

    with _client(handler) as client:
        result = verify(
            client,
            compiled,
            mined_count=55,
            start=0,
            end=1,
            bad_trace_ids=set(matched_ids),
        )

    assert result.signoz_count == 55
    assert result.match is True
    assert result.precision == 1.0
    assert result.recall == 1.0
    assert result.rows_scanned == 12345


def test_verify_mismatch_is_reported_not_hidden() -> None:
    compiled = compile_finding(_finding(), _columns())

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("email_password"):
            return httpx.Response(200, content=json.dumps({"data": {"accessToken": "t"}}))
        return httpx.Response(200, content=json.dumps(_scalar_response("T1", 40)))

    with _client(handler) as client:
        result = verify(
            client, compiled, mined_count=55, start=0, end=1, with_precision_recall=False
        )

    assert result.signoz_count == 40
    assert result.mined_count == 55
    assert result.match is False
