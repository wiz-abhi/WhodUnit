"""Unit tests for scan SQL generation, pruning, and a full mocked run_scan."""

from __future__ import annotations

from typing import Any

from whodunit.extract.scan import (
    ScanConfig,
    _build_scan_sql,
    _prune,
    _ScanFeature,
    _slug,
    run_scan,
)
from whodunit.extract.sql import env_predicate, id_list_predicate
from whodunit.types import FeatureColumn, FeatureKind


def _feat(name: str, mode: str, gap: float, **kw: Any) -> _ScanFeature:
    col = FeatureColumn(name=name, kind=FeatureKind.SPAN_PREDICATE)
    return _ScanFeature(column=col, mode=mode, gap=gap, **kw)  # type: ignore[arg-type]


def test_slug() -> None:
    assert _slug("shop-payment") == "shop_payment"
    assert _slug("GET /flags/evaluate") == "GET_flags_evaluate"
    assert _slug("") == "x"


def test_prune_caps_and_ranks_by_gap() -> None:
    cands = [
        _feat("a", "agg", 0.1, agg_expr="1"),
        _feat("b", "agg", 0.9, agg_expr="1"),
        _feat("c", "agg", 0.5, agg_expr="1"),
        _feat("a", "agg", 0.9, agg_expr="1"),  # duplicate name dropped
    ]
    kept = _prune(cands, ScanConfig(max_features=2))
    assert [f.column.name for f in kept] == ["b", "c"]


def test_prune_min_gap_filter() -> None:
    cands = [_feat("a", "agg", 0.01, agg_expr="1"), _feat("b", "agg", 0.4, agg_expr="1")]
    kept = _prune(cands, ScanConfig(min_prevalence_gap=0.1))
    assert [f.column.name for f in kept] == ["b"]


def test_build_scan_sql_includes_all_families() -> None:
    env = env_predicate("whodunit-demo")
    scope = id_list_predicate("trace_id", ["t1", "t2"])
    badlist = id_list_predicate("trace_id", ["t1"])
    feats = [
        _feat("span__a__b", "agg", 0.5, agg_expr="svc = 'shop-a' AND name = 'b'"),
        _feat("edge__a__b", "edge", 0.5, parent_pred="p.svc = 'shop-a'",
              child_pred="c.name = 'b'"),
        _feat("anc__a__b", "ancestor", 0.5, parent_pred="anc_svc = 'shop-a'",
              child_pred="cur_name = 'b'"),
        _feat("log__err", "log", 0.5, log_pred="body ILIKE '%err%'"),
    ]
    sql = _build_scan_sql(
        env=env, scope=scope, badlist=badlist, environment="whodunit-demo",
        features=feats, ancestor_max_depth=10,
    )
    # Recursive closure present because an ancestor feature exists.
    assert sql.startswith("WITH RECURSIVE")
    assert "closure AS (" in sql
    assert "WHERE r.depth < 10" in sql
    # Self-join edge semantics.
    assert "p.span_id = c.parent_span_id" in sql
    # per-trace aggregation + label.
    assert "maxIf(toUInt8(1), svc = 'shop-a' AND name = 'b') AS span__a__b" in sql
    assert "AS label" in sql
    # Log CTE joined by trace_id.
    assert "log_0 AS (" in sql
    assert "body ILIKE '%err%'" in sql
    # Row order is pinned: the feature matrix packs columns positionally and the
    # bootstrap indexes rows positionally, so a stable scan order is what makes the
    # verdict hash reproducible across ClickHouse's otherwise-unordered scans.
    assert "ORDER BY pt.trace_id" in sql


def test_build_scan_sql_no_recursive_without_ancestors() -> None:
    sql = _build_scan_sql(
        env="1 = 1", scope="1 = 1", badlist="trace_id IN ('t1')",
        environment=None,
        features=[_feat("span__a__b", "agg", 0.5, agg_expr="has_error")],
        ancestor_max_depth=10,
    )
    assert sql.startswith("WITH ")
    assert "WITH RECURSIVE" not in sql
    assert "closure" not in sql


# --------------------------------------------------------------------------- #
# Full run_scan against a routing fake client
# --------------------------------------------------------------------------- #
def _payload(rows: list[dict[str, Any]], meta: dict[str, Any] | None = None) -> dict[str, Any]:
    return {
        "data": {
            "meta": meta or {"rowsScanned": 7, "bytesScanned": 8, "durationMs": 1},
            "data": {"results": [{"rows": [{"data": r} for r in rows]}]},
        }
    }


class RoutingClient:
    """Answers each discovery/scan query with canned rows based on the SQL text."""

    def query_range(self, payload: dict[str, Any]) -> dict[str, Any]:
        spec = payload["compositeQuery"]["queries"][0]["spec"]
        name, sql = spec["name"], spec["query"]
        if name == "SCAN":
            rows: list[dict[str, Any]] = [
                {"trace_id": "t1", "label": 1, "span__shop_payment__redis_retry": 1,
                 "edge__shop_payment__redis_retry": 1, "log__error_template": 1},
                {"trace_id": "t2", "label": 0, "span__shop_payment__redis_retry": 0,
                 "edge__shop_payment__redis_retry": 0, "log__error_template": 0},
            ]
            return _payload(rows)
        if "GROUP BY svc, name" in sql:
            return _payload([
                {"svc": "shop-payment", "name": "redis-retry", "nb": 1, "nh": 0}
            ])
        if "GROUP BY svc" in sql:
            return _payload([{"svc": "shop-payment", "nb": 1, "nh": 1}])
        if "has_error" in sql and "quantiles" not in sql:
            return _payload([{"nb": 1, "nh": 0}])
        if "quantilesExact" in sql:
            return _payload([{"q": [100, 200, 300]}])
        if "GROUP BY psvc, cname" in sql:
            return _payload([
                {"psvc": "shop-payment", "cname": "redis-retry", "nb": 1, "nh": 0}
            ])
        if "attributes_string[" in sql and "GROUP BY val" in sql:
            return _payload([])
        if "distributed_dependency_graph_minutes_v2" in sql:
            return _payload([{"src": "shop-checkout", "dest": "shop-payment"}])
        if "distributed_logs_v2" in sql:  # log-token discovery counts
            return _payload([{"nb": 1, "nh": 0}])
        return _payload([])


def test_run_scan_end_to_end_mocked() -> None:
    result = run_scan(
        RoutingClient(),  # type: ignore[arg-type]
        bad_ids=("t1",),
        healthy_ids=("t2",),
        window_start_unix_ms=1,
        window_end_unix_ms=2,
        environment="whodunit-demo",
        config=ScanConfig(include_attributes=True, attribute_keys=("cache.hit",)),
    )
    names = {c.name for c in result.columns}
    assert "edge__shop_payment__redis_retry" in names
    assert "log__error_template" in names
    assert result.exec_stats.rows_scanned == 7
    assert len(result.rows) == 2
    # SQL is the real generated scan.
    assert "per_trace" in result.sql
