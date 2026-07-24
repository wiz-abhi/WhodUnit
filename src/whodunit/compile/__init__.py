"""The Whodunit compiler + differential verifier (Stage 4/5, the crown jewel).

Public API:

* :func:`compile_finding` — a mined :class:`~whodunit.types.Finding` + the
  :class:`~whodunit.types.FeatureColumn` table -> a verifiable
  :class:`~whodunit.types.CompiledQuery` (or a loud refusal).
* :func:`build_ir` / :func:`emit_envelope` / :func:`emit_expression` — the
  lower-level normalise-and-emit steps.
* :func:`verify` — differential verification against the live SigNoz engine.
* :func:`run_conformance` / :func:`to_markdown` — the conformance table.
"""

from __future__ import annotations

from whodunit.compile.conformance import (
    ConformanceRow,
    Shape,
    default_shapes,
    run_conformance,
    to_markdown,
)
from whodunit.compile.emit import (
    build_ir,
    compile_finding,
    emit_envelope,
    emit_expression,
)
from whodunit.compile.ir import BinOp, IRBuild, Leaf, Not
from whodunit.compile.refuse import collect_refusal_reason, refusal_for
from whodunit.compile.verify import precision_recall, verify

__all__ = [
    "BinOp",
    "ConformanceRow",
    "IRBuild",
    "Leaf",
    "Not",
    "Shape",
    "build_ir",
    "collect_refusal_reason",
    "compile_finding",
    "default_shapes",
    "emit_envelope",
    "emit_expression",
    "precision_recall",
    "refusal_for",
    "run_conformance",
    "to_markdown",
    "verify",
]
