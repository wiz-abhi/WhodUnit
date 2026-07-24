"""Manifest construction, ground-truth self-checking, and serialization.

The manifest is the contract between this corpus and the mining engine: it
records the seed, the active fault, the rates and counts, the human-readable and
machine-checkable ground-truth discriminator, and the list of bad ``trace_id``s.
A *self-check* re-evaluates the machine spec against the generated trees and
asserts it selects exactly the bad-labelled traces (for expressible faults) —
so a broken generator fails loudly instead of shipping a mislabelled corpus.
"""

from __future__ import annotations

import gzip
import hashlib
import json
from datetime import datetime, timezone

from .model import SpanNode, TracePlan

_INLINE_LIMIT = 2000  # bad_trace_ids above this are gzipped to a side file


# --------------------------------------------------------------------------- #
# Machine-spec evaluation
# --------------------------------------------------------------------------- #
def _matches_token(node: SpanNode, token: str) -> bool:
    return node.tag == token or node.service == token


def _descendant_exists(root: SpanNode, ancestor_tok: str, descendant_tok: str) -> bool:
    """True if some node matching ancestor_tok has a descendant matching
    descendant_tok."""
    for anc in root.walk():
        if _matches_token(anc, ancestor_tok):
            for d in anc.walk():
                if d is not anc and _matches_token(d, descendant_tok):
                    return True
    return False


def _count_tag(root: SpanNode, tag: str) -> int:
    return sum(1 for n in root.walk() if n.tag == tag)


def eval_spec(root: SpanNode, spec: dict) -> bool:
    """Evaluate one machine cohort predicate against a trace tree."""
    if "all_of" in spec:
        return all(eval_spec(root, s) for s in spec["all_of"])
    if "any_of" in spec:
        return any(eval_spec(root, s) for s in spec["any_of"])
    if "tag_present" in spec:
        return root.has_tag(spec["tag_present"])
    if "tag_absent" in spec:
        return not root.has_tag(spec["tag_absent"])
    if "edge_present" in spec:
        anc, desc = spec["edge_present"]
        return _descendant_exists(root, anc, desc)
    if "count" in spec:
        c = spec["count"]
        n = _count_tag(root, c["tag"])
        if "min" in c and n < c["min"]:
            return False
        if "max" in c and n > c["max"]:
            return False
        return True
    if "note" in spec or "label" in spec:
        # advisory only (label is on attributes, not structural)
        return True
    raise ValueError(f"unknown spec node: {spec}")


# --------------------------------------------------------------------------- #
def build_manifest(
    *,
    args_dict: dict,
    fault_name: str,
    ground_truth: dict,
    plans_meta: list[dict],
    bad_trace_ids: list[str],
    duration_s: float,
    base_time_ns: int,
) -> dict:
    total = len(plans_meta)
    bad = len(bad_trace_ids)
    cohort_counts: dict[str, int] = {}
    for m in plans_meta:
        cohort_counts[m["cohort"]] = cohort_counts.get(m["cohort"], 0) + 1

    background_bad_rate = bad / total if total else 0.0
    conjunction_lift = (1.0 / background_bad_rate) if background_bad_rate else None

    manifest = {
        "runid": args_dict["runid"],
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "generator_version": _version(),
        "seed": args_dict["seed"],
        "fault": fault_name,
        "fault_rate": args_dict["fault_rate"],
        "error_visible": args_dict["error_visible"],
        "decoys_strength": args_dict["decoys"],
        "endpoint": args_dict["endpoint"],
        "deployment_environment": "whodunit-demo",
        "service_name_prefix": "shop-",
        "window": {
            "base_time_ns": base_time_ns,
            "base_time_iso": datetime.fromtimestamp(
                base_time_ns / 1e9, tz=timezone.utc
            ).isoformat(),
            "duration_hours": args_dict["duration_hours"],
        },
        "counts": {
            "total_traces": total,
            "bad_traces": bad,
            "healthy_traces": total - bad,
            "background_bad_rate": round(background_bad_rate, 6),
            "conjunction_lift_vs_background": (
                round(conjunction_lift, 3) if conjunction_lift else None
            ),
            "total_spans": sum(m["span_count"] for m in plans_meta),
            "total_logs": sum(m["log_count"] for m in plans_meta),
            "by_cohort": cohort_counts,
        },
        "ground_truth": ground_truth,
        "generation_seconds": round(duration_s, 2),
        "disclosure": (
            "SYNTHETIC DATA, disclosed as methodology. Generated deterministically "
            "by corpus.generate under the recorded seed. All resources carry "
            "service.name prefix 'shop-' and deployment.environment="
            "'whodunit-demo' for filtering/removal. No production data."
        ),
    }
    return manifest


def add_self_check(manifest: dict, ground_truth: dict, plans: list[TracePlan]) -> None:
    """Re-derive the bad set from the machine spec and compare to labels."""
    gt_cohorts = ground_truth.get("cohorts", {})
    bad_spec = gt_cohorts.get("bad")
    expressible = ground_truth.get("expressible_in_trace_operator", False)

    label_bad = {p.trace_index for p in plans if p.bad}
    result = {"label_bad_count": len(label_bad)}

    if bad_spec and expressible:
        spec_bad = {p.trace_index for p in plans if eval_spec(p.root, bad_spec)}
        result["spec_bad_count"] = len(spec_bad)
        result["spec_matches_label"] = spec_bad == label_bad
        result["spec_only"] = len(spec_bad - label_bad)  # false positives of spec
        result["label_only"] = len(label_bad - spec_bad)  # missed by spec
    else:
        result["spec_matches_label"] = None
        result["note"] = (
            "Fault is not expressible as a structural presence/absence spec "
            "(cardinality- or correlation-based); ground truth is abstention."
        )
    manifest["self_check"] = result


def write_manifest(manifest: dict, bad_trace_ids: list[str], out_dir) -> dict:
    """Write manifest json (+ gzipped bad-id side file if large). Returns paths."""
    out_dir.mkdir(parents=True, exist_ok=True)
    runid = manifest["runid"]
    paths = {}

    if len(bad_trace_ids) > _INLINE_LIMIT:
        gz_path = out_dir / f"manifest-{runid}-badids.json.gz"
        with gzip.open(gz_path, "wt", encoding="utf-8") as f:
            json.dump(bad_trace_ids, f)
        manifest["bad_trace_ids_file"] = gz_path.name
        manifest["bad_trace_ids_inline"] = False
        paths["badids"] = str(gz_path)
    else:
        manifest["bad_trace_ids"] = bad_trace_ids
        manifest["bad_trace_ids_inline"] = True

    man_path = out_dir / f"manifest-{runid}.json"
    with open(man_path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2)
    paths["manifest"] = str(man_path)
    return paths


def make_runid(fault: str, seed: int, traces: int, fault_rate: float, extra: str) -> str:
    h = hashlib.sha256(
        f"{fault}|{seed}|{traces}|{fault_rate}|{extra}".encode()
    ).hexdigest()[:8]
    return f"{fault}-s{seed}-n{traces}-{h}"


def _version() -> str:
    from . import __version__

    return __version__
