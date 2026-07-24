"""Smoke test: emit 50 traces of the flagship fault and print counts.

    python -m corpus.smoke                       # emit to localhost:4318
    python -m corpus.smoke --no-emit             # offline, manifest only
    python -m corpus.smoke --endpoint http://ingester:4318

Exits non-zero if the ground-truth self-check fails.
"""

from __future__ import annotations

import sys

from .generate import run


def main(argv: list[str] | None = None) -> int:
    argv = list(argv if argv is not None else sys.argv[1:])
    base = ["--traces", "50", "--seed", "42", "--fault", "conditional_dep", "--fault-rate", "0.2"]
    result = run(base + argv)
    m = result["manifest"]
    c = m["counts"]
    sc = m["self_check"]
    print("=== whodunit corpus smoke ===")
    print(f"runid            : {m['runid']}")
    print(f"fault            : {m['fault']}  rate={m['fault_rate']}")
    print(f"total traces     : {c['total_traces']}")
    print(f"bad / healthy    : {c['bad_traces']} / {c['healthy_traces']}")
    print(f"spans / logs     : {c['total_spans']} / {c['total_logs']}")
    print(f"by cohort        : {c['by_cohort']}")
    print(f"conjunction lift : {c['conjunction_lift_vs_background']}")
    print(f"self-check       : spec_matches_label={sc.get('spec_matches_label')} "
          f"(spec_bad={sc.get('spec_bad_count')}, label_bad={sc.get('label_bad_count')})")
    print(f"manifest         : {result['paths']['manifest']}")
    ok = sc.get("spec_matches_label") in (True, None)
    print(f"RESULT           : {'OK' if ok else 'FAIL'}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
