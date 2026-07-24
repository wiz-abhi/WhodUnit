"""The shop topology: builds a realistic base trace tree.

One checkout request fans out across cart / flag-service / inventory / payment /
notification, each of which may touch cache and db. Optional structural elements
are toggled by keyword flags so that faults (:mod:`corpus.faults`) can express
their mutations as small, auditable parameter changes rather than tree surgery.
"""

from __future__ import annotations

import random

from .model import SpanNode

# Log-normal duration params (mu, sigma) in log-nanoseconds, per span archetype.
# exp(mu) is the geometric-mean duration; ~exp(15)=3.3ms, exp(17)=24ms, etc.
_DUR = {
    "checkout": (17.2, 0.45),
    "flag": (13.5, 0.35),
    "cart": (16.0, 0.5),
    "cache": (12.8, 0.4),
    "db": (15.4, 0.55),
    "inventory": (15.8, 0.5),
    "payment": (16.6, 0.5),
    "redis": (14.2, 0.4),
    "notify": (14.8, 0.45),
    "sync": (15.0, 0.45),
}

_FEATURE_FLAGS = ("checkout_v2", "express_pay", "new_cart_ui", "risk_v3")


def build_base_trace(
    rng: random.Random,
    *,
    flag_present: bool = True,
    redis_retry_present: bool = False,
    redis_retry_count: int = 1,
    cache_get_present: bool = True,
    cache_hit: bool | None = None,
    inventory_sync_present: bool = False,
    db_read_inflation: float = 0.0,
    error_visible: bool = False,
    bad: bool = False,
    decoy_attrs: dict[str, object] | None = None,
) -> SpanNode:
    """Build one checkout trace tree.

    Parameters mirror the structural degrees of freedom the fault library
    exercises. ``db_read_inflation`` is added to the cart db-read ``dur_mu``
    (cache-bypass makes the db work heavier). When ``error_visible`` and ``bad``,
    the culprit spans carry ERROR status.
    """
    d = decoy_attrs or {}

    checkout = SpanNode(
        service="checkout",
        name="POST /api/checkout",
        kind="SERVER",
        attrs={
            "http.route": "/api/checkout",
            "http.method": "POST",
            "http.status_code": 500 if (bad and error_visible) else 200,
            # Business label: surfaced always; the *polite* failure signal.
            "order.completed": not bad,
            **d,
        },
        dur_mu=_DUR["checkout"][0],
        dur_sigma=_DUR["checkout"][1],
        error=bad and error_visible,
    )

    # flag-service: present in healthy traffic; its ABSENCE is the flagship
    # fault's second conjunct.
    if flag_present:
        flags = {f"feature.flag.{name}": rng.random() < 0.5 for name in _FEATURE_FLAGS}
        checkout.add(
            SpanNode(
                service="flag-service",
                name="GET /flags/evaluate",
                kind="CLIENT",
                tag="flag-service",
                attrs={"http.route": "/flags/evaluate", **flags},
                dur_mu=_DUR["flag"][0],
                dur_sigma=_DUR["flag"][1],
            )
        )

    # cart -> cache -> db
    cart = checkout.add(
        SpanNode(
            service="cart",
            name="cart.load",
            kind="CLIENT",
            attrs={"cart.item_count": rng.randint(1, 8)},
            dur_mu=_DUR["cart"][0],
            dur_sigma=_DUR["cart"][1],
        )
    )
    hit = cache_hit if cache_hit is not None else (rng.random() < 0.7)
    if cache_get_present:
        cart.add(
            SpanNode(
                service="cache",
                name="cache-get",
                kind="CLIENT",
                tag="cache-get",
                attrs={"cache.hit": hit, "db.system": "redis", "cache.key": "cart:items"},
                dur_mu=_DUR["cache"][0],
                dur_sigma=_DUR["cache"][1],
            )
        )
    cart.add(
        SpanNode(
            service="db",
            name="SELECT cart_items",
            kind="CLIENT",
            tag="db-read",
            attrs={"db.system": "postgresql", "db.operation": "SELECT", "db.sql.table": "cart_items"},
            dur_mu=_DUR["db"][0] + db_read_inflation,
            dur_sigma=_DUR["db"][1],
        )
    )
    # new_edge fault: cart gains an inventory-sync child post-deploy.
    if inventory_sync_present:
        cart.add(
            SpanNode(
                service="inventory",
                name="inventory-sync",
                kind="CLIENT",
                tag="inventory-sync",
                attrs={"http.route": "/inventory/sync", "sync.async": True},
                dur_mu=_DUR["sync"][0],
                dur_sigma=_DUR["sync"][1],
            )
        )

    # inventory branch (occasionally dropped for span-count variety)
    if rng.random() < 0.9:
        inv = checkout.add(
            SpanNode(
                service="inventory",
                name="inventory.check",
                kind="CLIENT",
                attrs={"http.route": "/inventory/check"},
                dur_mu=_DUR["inventory"][0],
                dur_sigma=_DUR["inventory"][1],
            )
        )
        inv.add(
            SpanNode(
                service="db",
                name="SELECT stock",
                kind="CLIENT",
                attrs={"db.system": "postgresql", "db.operation": "SELECT", "db.sql.table": "stock"},
                dur_mu=_DUR["db"][0],
                dur_sigma=_DUR["db"][1],
            )
        )

    # payment branch: the flagship fault's redis-retry lives here.
    payment = checkout.add(
        SpanNode(
            service="payment",
            name="payment.charge",
            kind="CLIENT",
            attrs={
                "http.route": "/payment/charge",
                "payment.amount": round(rng.uniform(5, 500), 2),
                "payment.currency": "USD",
            },
            dur_mu=_DUR["payment"][0],
            dur_sigma=_DUR["payment"][1],
            error=bad and error_visible,
        )
    )
    if redis_retry_present:
        for i in range(max(1, redis_retry_count)):
            payment.add(
                SpanNode(
                    service="payment",
                    name="redis-retry",
                    kind="INTERNAL",
                    tag="redis-retry",
                    attrs={"db.system": "redis", "retry.attempt": i + 1},
                    dur_mu=_DUR["redis"][0],
                    dur_sigma=_DUR["redis"][1],
                )
            )
    payment.add(
        SpanNode(
            service="db",
            name="UPDATE ledger",
            kind="CLIENT",
            attrs={"db.system": "postgresql", "db.operation": "UPDATE", "db.sql.table": "ledger"},
            dur_mu=_DUR["db"][0],
            dur_sigma=_DUR["db"][1],
        )
    )

    # notification (occasionally dropped)
    if rng.random() < 0.85:
        checkout.add(
            SpanNode(
                service="notification",
                name="notify.enqueue",
                kind="PRODUCER",
                attrs={"messaging.system": "kafka", "messaging.operation": "publish"},
                dur_mu=_DUR["notify"][0],
                dur_sigma=_DUR["notify"][1],
            )
        )

    return checkout
