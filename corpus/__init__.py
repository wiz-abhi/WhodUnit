"""Whodunit demo corpus + seeded fault engine (SigNoz Track 2).

A single Python process emits OTLP traces + logs for a synthetic 8-service
"shop", at volume, with a switchable library of *structural* faults. Every run
records machine-checkable ground truth in a manifest so the mining engine can be
scored honestly. Fully deterministic under ``--seed``.

Disclosed synthetic data is methodology; hidden synthetic data is fatal. See
``corpus/README.md`` for the disclosure statement.
"""

__version__ = "0.1.0"

# All emitted resources carry these so demo data is filterable / removable.
SERVICE_PREFIX = "shop-"
DEPLOYMENT_ENVIRONMENT = "whodunit-demo"

# The eight logical services of the shop.
SERVICES = (
    "checkout",
    "cart",
    "payment",
    "inventory",
    "flag-service",
    "cache",
    "db",
    "notification",
)
