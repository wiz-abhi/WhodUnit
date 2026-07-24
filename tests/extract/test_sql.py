"""Unit tests for the low-level clickhouse_sql helpers."""

from __future__ import annotations

from whodunit.extract.sql import (
    ExecStats,
    _extract_rows,
    build_envelope,
    env_predicate,
    id_list_predicate,
    quote_ident,
    sql_str,
)


def test_quote_ident_handles_dollar_columns() -> None:
    assert quote_ident("resource_string_service$$name") == "`resource_string_service$$name`"


def test_quote_ident_doubles_backticks() -> None:
    assert quote_ident("a`b") == "`a``b`"


def test_sql_str_escapes_quotes_and_backslashes() -> None:
    assert sql_str("O'Brien") == "'O\\'Brien'"
    assert sql_str("a\\b") == "'a\\\\b'"


def test_env_predicate() -> None:
    assert env_predicate(None) == "1 = 1"
    assert (
        env_predicate("whodunit-demo")
        == "resources_string['deployment.environment'] = 'whodunit-demo'"
    )


def test_id_list_predicate() -> None:
    assert id_list_predicate("trace_id", []) == "0 = 1"
    assert id_list_predicate("trace_id", ["a", "b"]) == "trace_id IN ('a', 'b')"


def test_build_envelope_shape() -> None:
    env = build_envelope("SELECT 1", 100, 200, "Q")
    assert env["requestType"] == "raw"
    q = env["compositeQuery"]["queries"][0]
    assert q["type"] == "clickhouse_sql"
    assert q["spec"]["name"] == "Q"
    assert q["spec"]["query"] == "SELECT 1"


def test_execstats_from_meta() -> None:
    s = ExecStats.from_meta({"rowsScanned": 10, "bytesScanned": 20, "durationMs": 3})
    assert (s.rows_scanned, s.bytes_scanned, s.duration_ms) == (10, 20, 3.0)
    empty = ExecStats.from_meta(None)
    assert empty.rows_scanned is None


def test_extract_rows_unwraps_data() -> None:
    payload = {
        "data": {
            "data": {"results": [{"rows": [{"data": {"x": 1}}, {"data": {"x": 2}}]}]}
        }
    }
    assert _extract_rows(payload) == [{"x": 1}, {"x": 2}]
    assert _extract_rows({"data": {}}) == []
