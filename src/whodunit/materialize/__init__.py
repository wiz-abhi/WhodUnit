"""The Whodunit materializer (Stage 6): a verified :class:`CompiledQuery` becomes
owned SigNoz artifacts — a Trace Explorer permalink, a native v6 dashboard, and
an armed v2alpha1 alert rule.

Public surface:

* :class:`Materializer` — the interface the pipeline/CLI drives.
* :mod:`permalink`, :mod:`dashboard`, :mod:`alert` — the tested builders + the
  create/get/delete helpers used for live materialisation and cleanup.

Empirical schema findings live in ``NOTES.md`` next to this package.
"""

from __future__ import annotations

from whodunit.materialize.materializer import Materializer

__all__ = ["Materializer"]
