"""Baseline-vs-verified comparison reports."""

from __future__ import annotations

from .metrics import build_memory_health_report


def compare_runs(baseline_run: dict, verified_run: dict) -> dict:
    """Compare baseline memory health against verified effective behavior."""

    baseline_report = baseline_run.get("memory_health_report") or build_memory_health_report(
        baseline_run
    )
    verified_report = (
        verified_run.get("effective_memory_health_report")
        or verified_run.get("memory_health_report")
        or build_memory_health_report(verified_run)
    )

    baseline_metrics = baseline_report["metrics"]
    verified_metrics = verified_report["metrics"]
    metric_deltas = {
        metric: round(verified_metrics.get(metric, 0.0) - baseline_metrics.get(metric, 0.0), 4)
        for metric in sorted(set(baseline_metrics) | set(verified_metrics))
    }

    return {
        "schema_version": "agent-memory-comparison/v0.1",
        "baseline_run_id": baseline_run.get("run_id"),
        "verified_run_id": verified_run.get("run_id"),
        "task_id": baseline_run.get("task_id") or verified_run.get("task_id"),
        "baseline_metrics": baseline_metrics,
        "verified_metrics": verified_metrics,
        "metric_deltas": metric_deltas,
        "baseline_claim_counts": baseline_report["claim_counts"],
        "verified_claim_counts": verified_report["claim_counts"],
        "verification_decision_counts": verified_run.get(
            "verification_report", {}
        ).get("decision_counts", {}),
        "verification_overhead": {
            "extra_trace_events": _verification_event_count(verified_run),
            "blocked_actions": len(verified_run.get("blocked_actions", [])),
        },
    }


def _verification_event_count(run: dict) -> int:
    return sum(
        1
        for event in run.get("trace_events", [])
        if event.get("event_type") == "verification_decision"
    )
