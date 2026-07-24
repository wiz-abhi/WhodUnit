"""Unit tests for the pipeline: synthetic matrix -> finding -> compiled envelope.

The live network (extract_matrix) is monkeypatched to return the synthetic
matrix; mining, the edge-seam adapter, compilation, and verification all run for
real (verification against the deterministic ``FakeClient``).
"""

from __future__ import annotations

import pytest

from whodunit import pipeline
from whodunit.extract import CohortSpec, MaterializedMatrix
from whodunit.mine import MineConfig
from whodunit.pipeline import adapt_columns_for_compiler, explain
from whodunit.types import FeatureColumn, FeatureKind, Verdict

from .conftest import EDGE_NAME, FLAG_NAME, FakeClient, build_synthetic_matrix


def _spec() -> CohortSpec:
    return CohortSpec(
        window_start_unix_ms=1_000,
        window_end_unix_ms=2_000,
        ch_filter="order.completed = false",
        environment="whodunit-demo",
    )


@pytest.fixture
def patched_extract(
    monkeypatch: pytest.MonkeyPatch, synthetic_matrix: MaterializedMatrix
) -> None:
    def fake_extract_matrix(*_args: object, **_kwargs: object) -> MaterializedMatrix:
        return build_synthetic_matrix()

    monkeypatch.setattr(pipeline, "extract_matrix", fake_extract_matrix)


# --------------------------------------------------------------------------- #
# Contract-seam adapter
# --------------------------------------------------------------------------- #
def test_adapter_prefixes_edge_child_span_sentinel() -> None:
    cols = [
        FeatureColumn(
            name="e", kind=FeatureKind.EDGE, edge_parent="shop-payment", edge_child="redis-retry"
        ),
        FeatureColumn(
            name="a", kind=FeatureKind.ANCESTOR, edge_parent="shop-checkout", edge_child="db-read"
        ),
        FeatureColumn(name="s", kind=FeatureKind.SPAN_PREDICATE, service_name="shop-cart"),
    ]
    out = adapt_columns_for_compiler(cols)
    assert out[0].edge_child == "span:redis-retry"
    assert out[0].edge_parent == "shop-payment"  # parent untouched (a service)
    assert out[1].edge_child == "span:db-read"
    assert out[2].edge_child is None  # non-edge untouched
    # Column names are preserved so mined itemsets still resolve.
    assert [c.name for c in out] == ["e", "a", "s"]


def test_adapter_idempotent() -> None:
    col = FeatureColumn(
        name="e", kind=FeatureKind.EDGE, edge_parent="shop-payment", edge_child="span:redis-retry"
    )
    out = adapt_columns_for_compiler([col])
    assert out[0].edge_child == "span:redis-retry"  # not double-prefixed


# --------------------------------------------------------------------------- #
# End-to-end on the synthetic fixture
# --------------------------------------------------------------------------- #
def test_explain_finds_edge_not_flag_conjunction(
    patched_extract: None, fake_client: FakeClient
) -> None:
    result = explain(fake_client, _spec(), mine_config=MineConfig())

    assert result.verdict is Verdict.DISCRIMINATOR
    assert result.chosen_finding is not None
    itemset = set(result.chosen_finding.itemset)
    assert EDGE_NAME in itemset
    assert f"NOT {FLAG_NAME}" in itemset


def test_explain_compiles_expected_shape(
    patched_extract: None, fake_client: FakeClient
) -> None:
    result = explain(fake_client, _spec(), mine_config=MineConfig())
    assert result.compiled is not None
    # Edge folds left as (A => B); the flag negation is appended on the right.
    assert result.compiled.expression == "(A => B) && NOT C"
    # Envelope carries a builder_trace_operator plus its leaves.
    types = [q["type"] for q in result.compiled.envelope["compositeQuery"]["queries"]]
    assert "builder_trace_operator" in types


def test_explain_edge_leaf_uses_span_name_not_service(
    patched_extract: None, fake_client: FakeClient
) -> None:
    result = explain(fake_client, _spec(), mine_config=MineConfig())
    assert result.compiled is not None
    exprs = " || ".join(
        str(leaf.filters.get("expression", "")) for leaf in result.compiled.leaf_queries
    )
    # The child endpoint must be a span-name match, never service.name.
    assert "name = 'redis-retry'" in exprs
    assert "service.name = 'redis-retry'" not in exprs
    # The cohort scope is ANDed in.
    assert "deployment.environment = 'whodunit-demo'" in exprs


def test_explain_verifies_match(patched_extract: None, fake_client: FakeClient) -> None:
    result = explain(fake_client, _spec(), mine_config=MineConfig())
    assert result.verification is not None
    assert result.verification.mined_count == 40
    assert result.verification.signoz_count == 40
    assert result.verification.match is True


def test_explain_no_verify_skips_network(patched_extract: None) -> None:
    client = FakeClient(scalar_count=999)
    result = explain(client, _spec(), mine_config=MineConfig(), do_verify=False)
    assert result.verification is None
    assert client.calls == []  # never touched the network


def test_explain_result_json_roundtrips(
    patched_extract: None, fake_client: FakeClient
) -> None:
    result = explain(fake_client, _spec(), mine_config=MineConfig())
    blob = result.model_dump_json()
    assert '"verdict_hash"' in blob
    assert result.verdict_hash  # non-empty


# --------------------------------------------------------------------------- #
# Absence-only recovery (ISSUES.md #2 — the cache_bypass regression)
# --------------------------------------------------------------------------- #
def _build_cache_bypass_matrix() -> MaterializedMatrix:
    """A matrix mirroring the corpus ``cache_bypass`` fault.

    Bad traces are exactly those *missing* the ``cache-get`` span; an always-
    present ``shop-db`` service anchors every trace. So the only sound structural
    discriminator is the trace-scoped absence ``NOT cache-get`` — which the
    compiler refuses on its own (absence-only) — while the statistically
    identical, *compilable* superset ``shop-db AND NOT cache-get`` is the phrasing
    the pipeline must recover instead of abstaining.
    """
    import polars as pl

    from whodunit.types import FeatureMatrix

    cache = "svc__shop_cache__cache_get"
    anchor = "svc__shop_db"
    noise = "svc__shop_cart"
    columns = [
        FeatureColumn(
            name=cache,
            kind=FeatureKind.SPAN_PREDICATE,
            description="trace contains the 'cache-get' span",
            service_name="shop-cache",
            span_name="cache-get",
        ),
        FeatureColumn(
            name=anchor,
            kind=FeatureKind.SPAN_PREDICATE,
            description="trace contains a 'shop-db' span (present in every trace)",
            service_name="shop-db",
        ),
        FeatureColumn(
            name=noise,
            kind=FeatureKind.SPAN_PREDICATE,
            description="trace contains a 'shop-cart' span",
            service_name="shop-cart",
        ),
    ]

    n_bad, n_healthy = 60, 140
    tids: list[str] = []
    labels: list[int] = []
    cache_col: list[int] = []
    anchor_col: list[int] = []
    noise_col: list[int] = []
    for i in range(n_bad + n_healthy):
        is_bad = i < n_bad
        tids.append(f"trace{i:05d}")
        labels.append(1 if is_bad else 0)
        cache_col.append(0 if is_bad else 1)  # bad traces MISS cache-get
        anchor_col.append(1)  # shop-db in every trace
        noise_col.append(i % 2)  # decorrelated from the label

    frame = pl.DataFrame(
        {
            "trace_id": tids,
            "label": pl.Series(labels, dtype=pl.Int8),
            cache: pl.Series(cache_col, dtype=pl.Int8),
            anchor: pl.Series(anchor_col, dtype=pl.Int8),
            noise: pl.Series(noise_col, dtype=pl.Int8),
        }
    )
    meta = FeatureMatrix(
        columns=columns,
        n_traces_bad=n_bad,
        n_traces_healthy=n_healthy,
        window_start_unix_ms=1_000,
        window_end_unix_ms=2_000,
    )
    return MaterializedMatrix(frame=frame, meta=meta)


def test_explain_recovers_anchored_superset_for_absence_only(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """cache_bypass regression: the top discriminator is absence-only (refused),
    and the statistically-tied compilable superset was dominance-pruned into
    near_misses. The pipeline must recover it and return a DISCRIMINATOR — never
    ABSTAIN — with a compiled ``... && NOT ...`` expression."""
    mm = _build_cache_bypass_matrix()
    monkeypatch.setattr(pipeline, "extract_matrix", lambda *a, **k: mm)

    # 60 bad traces, all matched by the recovered discriminator.
    result = explain(FakeClient(scalar_count=60), _spec(), mine_config=MineConfig())

    assert result.verdict is Verdict.DISCRIMINATOR
    assert result.chosen_finding is not None
    itemset = set(result.chosen_finding.itemset)
    # Absence conjunct on cache-get, plus a positive anchor so it compiles.
    assert "NOT svc__shop_cache__cache_get" in itemset
    assert any(not tok.startswith("NOT ") for tok in itemset)
    assert result.compiled is not None
    assert result.compiled.envelope  # actually compiled, not refused
    assert "NOT" in result.compiled.expression


# --------------------------------------------------------------------------- #
# Determinism — the "run twice, hashes identical" proof
# --------------------------------------------------------------------------- #
def test_verdict_hash_is_deterministic(
    patched_extract: None,
) -> None:
    r1 = explain(FakeClient(scalar_count=40), _spec(), mine_config=MineConfig())
    r2 = explain(FakeClient(scalar_count=40), _spec(), mine_config=MineConfig())
    assert r1.verdict_hash == r2.verdict_hash
    assert r1.compiled is not None and r2.compiled is not None
    assert r1.compiled.expression == r2.compiled.expression


def test_verdict_hash_changes_with_findings() -> None:
    from whodunit.pipeline import compute_verdict_hash
    from whodunit.types import Finding

    f = Finding(
        itemset=["a", "NOT b"],
        lift=4.0,
        ci_low=3.0,
        ci_high=5.0,
        support_bad=40,
        support_healthy=0,
        verdict=Verdict.DISCRIMINATOR,
    )
    h1 = compute_verdict_hash([f], "(A => B) && NOT C", {"mined": 40, "signoz": 40})
    h2 = compute_verdict_hash([f], "(A => B) && NOT C", {"mined": 41, "signoz": 40})
    assert h1 != h2


# --------------------------------------------------------------------------- #
# Abstention path
# --------------------------------------------------------------------------- #
def test_explain_abstains_on_noise(monkeypatch: pytest.MonkeyPatch) -> None:
    import random

    import polars as pl

    from whodunit.types import FeatureMatrix

    # Pure noise: every feature independent of the label -> ABSTAIN. Built with
    # Int8 columns to also exercise the booleanize seam.
    rng = random.Random(3)
    n = 400
    labels = [1 if rng.random() < 0.5 else 0 for _ in range(n)]
    cols = [
        FeatureColumn(name=f"f{i}", kind=FeatureKind.SPAN_PREDICATE, service_name=f"svc-{i}")
        for i in range(6)
    ]
    data: dict[str, object] = {
        "trace_id": [f"t{i:05d}" for i in range(n)],
        "label": pl.Series(labels, dtype=pl.Int8),
    }
    for c in cols:
        data[c.name] = pl.Series(
            [1 if rng.random() < 0.4 else 0 for _ in range(n)], dtype=pl.Int8
        )
    frame = pl.DataFrame(data)
    meta = FeatureMatrix(columns=cols, n_traces_bad=sum(labels), n_traces_healthy=n - sum(labels))
    mm = MaterializedMatrix(frame=frame, meta=meta)

    monkeypatch.setattr(pipeline, "extract_matrix", lambda *a, **k: mm)

    result = explain(FakeClient(scalar_count=0), _spec(), mine_config=MineConfig())
    assert result.verdict is Verdict.ABSTAIN
    assert result.chosen_finding is None
    assert result.compiled is None
    assert "ABSTAIN" in result.headline
