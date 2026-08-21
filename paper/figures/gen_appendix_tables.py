#!/usr/bin/env python3
"""Appendix numbers for the Countersign paper, recomputed from AUDITED artifacts.

Same discipline as gen_figures.py: every value the paper prints is derived
here from the frozen run artifacts at build time, so a table cannot drift
from the data it claims to describe. Prints a report and emits
`appendix_numbers.json` next to this file for the pinning test.

Answers three questions the campaign never reported:
  1. WHICH of the four advertised audit checks actually produced blocks?
  2. What did a blocked worker DO next - gather evidence, or re-cite it?
  3. Did unsupported proposals lack evidence, or merely fail to cite it?
"""
import json
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RUNS = ROOT / "runs" / "pod-sync"
OUT = Path(__file__).resolve().parent

TEST_TOOLS = {"run_tests", "run_full_tests", "run_targeted_tests"}
WRITE_TOOLS = {"write_file", "apply_patch"}
BLOCKING_ARMS = {"verification_only", "verification_and_repair"}

# The no-citation bundle: these reasons fire together when a completion claim
# cites nothing at all, so the bundle is one event, not six findings.
NO_CITATION_BUNDLE = frozenset({
    "lost provenance", "low retrieval consistency",
    "missing implementation-change evidence", "missing required source type",
    "missing successful test evidence", "unsupported claim",
})


# The frozen campaign is exactly these seven directories (490 runs). Other
# directories under pod-sync are earlier probes and are NOT campaign data;
# including them would silently inflate every denominator below.
CAMPAIGNS = ("final-matrix", "fm-negctrl-qwen", "pressure-a", "pressure-b",
             "substrate-b40", "substrate-resume", "e5-observe")


def runs():
    """Yield (campaign, run). The campaign name is part of a cell's identity:
    substrate-b40 re-executed 50 final-matrix cells at action budget 40 vs 24,
    so merging them by (task, profile, seed) alone would silently pair runs
    from different conditions."""
    for campaign in CAMPAIGNS:
        directory = RUNS / campaign / "runs"
        if not directory.exists():
            continue
        for f in sorted(directory.rglob("*.json")):
            yield campaign, json.loads(f.read_text())


def blocks_of(run):
    for ev in run.get("trace_events", []):
        if ev.get("event_type") != "verification_decision":
            continue
        if (ev.get("verifier_decision") or ev.get("decision")) == "block":
            yield ev


def main():
    all_pairs = list(runs())
    all_runs = [run for _, run in all_pairs]

    # ---- 1. Which checks fired? -------------------------------------
    signatures = Counter()
    for run in all_runs:
        for ev in blocks_of(run):
            signatures[frozenset(ev.get("reasons", ()))] += 1

    trivial = sum(n for sig, n in signatures.items() if sig == NO_CITATION_BUNDLE)
    requirement = sum(n for sig, n in signatures.items()
                      if sig == {"unresolved requirement update newer than "
                                 "the latest successful test evidence"})
    missing_test = sum(n for sig, n in signatures.items()
                       if sig == {"missing successful test evidence"})
    staleness = sum(n for sig, n in signatures.items()
                    if any("stale" in r.lower() for r in sig))
    total_blocks = sum(signatures.values())

    # ---- 2. What did a blocked worker do next? -----------------------
    recovery = {"episodes": 0, "gathered_evidence": 0, "recited_only": 0}
    for run in all_runs:
        if run.get("experiment_context", {}).get("variant") not in BLOCKING_ARMS:
            continue
        blks = list(blocks_of(run))
        if not blks:
            continue
        recovery["episodes"] += 1
        first = min(e.get("sequence_number", 0) for e in blks)
        after = [e for e in run.get("trace_events", [])
                 if e.get("sequence_number", 0) > first
                 and e.get("event_type") == "tool_call"
                 and e.get("status") == "success"
                 and e.get("tool_name") in (TEST_TOOLS | WRITE_TOOLS)]
        if after:
            recovery["gathered_evidence"] += 1
        else:
            recovery["recited_only"] += 1

    # ---- 3. Did unsupported proposals lack evidence, or just cite none? --
    had_evidence = uncited = unsupported = 0
    for run in all_runs:
        metrics = run.get("interaction_metrics", {})
        scores = metrics.get("oracle_proposal_scores", [])
        events = run.get("trace_events", [])
        for score in scores:
            if score.get("support_label") != "unsupported":
                continue
            unsupported += 1
            pid = score.get("proposal_event_id")
            seq = next((e.get("sequence_number", 0) for e in events
                        if e.get("event_id") == pid), None)
            if seq is None:
                continue
            prior = [e for e in events if e.get("sequence_number", 0) < seq
                     and e.get("event_type") == "tool_call"
                     and e.get("status") == "success"]
            last_edit = max((e.get("sequence_number", 0) for e in prior
                             if e.get("tool_name") in WRITE_TOOLS), default=0)
            fresh_green = [e for e in prior if e.get("tool_name") in TEST_TOOLS
                           and e.get("sequence_number", 0) > last_edit]
            if fresh_green:
                had_evidence += 1
            if "no source_event_ids cited" in tuple(score.get("reasons", ())):
                uncited += 1

    # ---- 4. What did halting authority cost? -------------------------
    # The introduction promises "what that authority costs" and the
    # responsible-use statement promises counter-metrics; both are priced
    # here, on matched cells, as predeclared secondary endpoints.
    cells = {}
    latencies = []
    for campaign, run in all_pairs:
        ctx = run.get("experiment_context", {})
        metrics = run.get("interaction_metrics", {})
        key = (campaign, run.get("task_id"), ctx.get("pressure_profile_id"),
               ctx.get("seed"))
        cells.setdefault(key, {})[ctx.get("variant")] = {
            "actions": metrics.get("model_action_count"),
            "hidden_ok": bool(metrics.get("hidden_validation_success")
                              or metrics.get("evaluator_success")),
            "exhausted": "budget" in str(metrics.get("termination_reason", "")).lower(),
        }
        for ev in run.get("trace_events", []):
            if ev.get("event_type") == "verification_decision" \
                    and ev.get("gate_latency_ms") is not None:
                latencies.append(ev["gate_latency_ms"])

    pairs = [(v["memory_baseline"], v["verification_only"]) for v in cells.values()
             if "memory_baseline" in v and "verification_only" in v]
    deltas = [t["actions"] - b["actions"] for b, t in pairs
              if b["actions"] is not None and t["actions"] is not None]
    latencies.sort()
    cost = {
        "matched_cells": len(pairs),
        "mean_extra_actions": round(sum(deltas) / len(deltas), 3) if deltas else None,
        "hidden_eval_success_baseline": sum(b["hidden_ok"] for b, _ in pairs),
        "hidden_eval_success_gated": sum(t["hidden_ok"] for _, t in pairs),
        "budget_exhaustion_baseline": sum(b["exhausted"] for b, _ in pairs),
        "budget_exhaustion_gated": sum(t["exhausted"] for _, t in pairs),
        "gate_decisions": len(latencies),
        "gate_latency_median_ms": round(latencies[len(latencies) // 2], 2) if latencies else None,
        "gate_latency_max_ms": round(max(latencies), 1) if latencies else None,
    }

    report = {
        "cost_of_authority": cost,
        "blocks": {
            "total": total_blocks,
            "no_citation_bundle": trivial,
            "requirement_recency_alone": requirement,
            "missing_test_alone": missing_test,
            "staleness": staleness,
            "distinct_signatures": len(signatures),
        },
        "recovery": recovery,
        "unsupported_proposals": {
            "total": unsupported,
            "had_fresh_green_test_in_trace": had_evidence,
            "cited_nothing_at_all": uncited,
        },
        "runs_scanned": len(all_runs),
    }
    (OUT / "appendix_numbers.json").write_text(json.dumps(report, indent=2, sort_keys=True))

    print(f"runs scanned: {len(all_runs)}")
    print(f"\nBLOCKS ({total_blocks} total, {len(signatures)} distinct signatures)")
    print(f"  claim cited nothing (6-reason bundle) : {trivial}")
    print(f"  requirement recency, alone            : {requirement}")
    print(f"  missing successful test, alone        : {missing_test}")
    print(f"  STALENESS (freshness check)           : {staleness}")
    print(f"\nPOST-BLOCK BEHAVIOUR ({recovery['episodes']} blocked episodes)")
    print(f"  gathered new evidence (test/edit)     : {recovery['gathered_evidence']}")
    print(f"  re-cited existing evidence only       : {recovery['recited_only']}")
    print(f"\nUNSUPPORTED PROPOSALS ({unsupported})")
    print(f"  already had a fresh green test        : {had_evidence}")
    print(f"  cited nothing at all                  : {uncited}")
    print(f"\nCOST OF AUTHORITY ({cost['matched_cells']} matched cells)")
    print(f"  mean extra model actions              : {cost['mean_extra_actions']:+}")
    print(f"  hidden-eval success  base -> gated    : "
          f"{cost['hidden_eval_success_baseline']} -> {cost['hidden_eval_success_gated']}")
    print(f"  budget exhaustion    base -> gated    : "
          f"{cost['budget_exhaustion_baseline']} -> {cost['budget_exhaustion_gated']}")
    print(f"  gate latency (n={cost['gate_decisions']})            : "
          f"median {cost['gate_latency_median_ms']} ms, max {cost['gate_latency_max_ms']} ms")


if __name__ == "__main__":
    main()
