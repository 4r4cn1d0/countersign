"""Baseline-vs-verified comparison reports."""

from __future__ import annotations

from .metrics import build_memory_health_report


def compare_runs(baseline_run: dict, verified_run: dict) -> dict:
    """Compare raw claims and observable intervention behavior."""

    baseline_report = baseline_run.get("memory_health_report") or build_memory_health_report(
        baseline_run
    )
    verified_raw_report = (
        verified_run.get("raw_memory_health_report")
        or verified_run.get("memory_health_report")
        or build_memory_health_report(verified_run)
    )

    baseline_metrics = baseline_report["metrics"]
    verified_metrics = verified_raw_report["metrics"]
    metric_deltas = {
        metric: round(verified_metrics.get(metric, 0.0) - baseline_metrics.get(metric, 0.0), 4)
        for metric in sorted(set(baseline_metrics) | set(verified_metrics))
    }
    baseline_interaction = baseline_run.get("interaction_metrics")
    verified_interaction = verified_run.get("interaction_metrics")
    behavioral_evidence_available = bool(
        baseline_interaction is not None and verified_interaction is not None
    )
    behavioral_outcomes = _behavioral_outcomes(
        baseline_interaction or {},
        verified_interaction or {},
        behavioral_evidence_available,
    )
    effective_report = verified_run.get("effective_memory_health_report")

    return {
        "schema_version": "agent-memory-comparison/v0.2",
        "baseline_run_id": baseline_run.get("run_id"),
        "verified_run_id": verified_run.get("run_id"),
        "task_id": baseline_run.get("task_id") or verified_run.get("task_id"),
        "interpretation": (
            "Raw metrics count every model-authored finish proposal. Behavioral "
            "outcomes separately count which proposals the agent accepted, which "
            "the verifier blocked, whether the independent evaluator rejected an "
            "accepted claim, and whether the agent gathered new evidence."
        ),
        "baseline_metrics": baseline_metrics,
        "verified_raw_metrics": verified_metrics,
        "metric_deltas": metric_deltas,
        "baseline_claim_counts": baseline_report["claim_counts"],
        "verified_raw_claim_counts": verified_raw_report["claim_counts"],
        "verified_accepted_claim_metrics": (
            effective_report.get("metrics") if effective_report else None
        ),
        "verified_accepted_claim_counts": (
            effective_report.get("claim_counts") if effective_report else None
        ),
        "behavioral_evidence_available": behavioral_evidence_available,
        "behavioral_outcomes": behavioral_outcomes,
        "verification_decision_counts": verified_run.get(
            "verification_report", {}
        ).get("decision_counts", {}),
        "verification_overhead": {
            "extra_trace_events": (
                len(verified_run.get("trace_events", []))
                - len(baseline_run.get("trace_events", []))
            ),
            "verification_events": _verification_event_count(verified_run),
            "blocked_actions": len(verified_run.get("blocked_actions", [])),
            "extra_model_actions": _model_action_count(verified_run)
            - _model_action_count(baseline_run),
            "post_block_tool_calls": (
                verified_interaction or {}
            ).get("post_block_tool_calls"),
        },
    }


def _behavioral_outcomes(
    baseline: dict,
    verified: dict,
    available: bool,
) -> dict:
    if not available:
        return {
            "available": False,
            "reason": (
                "These runs do not contain in-loop interaction metrics; post-hoc "
                "claim filtering cannot establish a behavioral intervention effect."
            ),
        }

    baseline_accepted_false = int(baseline.get("accepted_false_finishes", 0))
    verified_accepted_false = int(verified.get("accepted_false_finishes", 0))
    return {
        "available": True,
        "baseline_finish_proposals": int(baseline.get("finish_proposals", 0)),
        "baseline_false_finish_proposals": int(
            baseline.get("false_finish_proposals", 0)
        ),
        "baseline_accepted_false_finishes": baseline_accepted_false,
        "baseline_accepted_finish_evaluator_failures": int(
            baseline.get("accepted_finish_evaluator_failures", 0)
        ),
        "verified_finish_proposals": int(verified.get("finish_proposals", 0)),
        "verified_false_finish_proposals": int(
            verified.get("false_finish_proposals", 0)
        ),
        "verified_blocked_false_finishes": int(
            verified.get("blocked_false_finishes", 0)
        ),
        "verified_accepted_false_finishes": verified_accepted_false,
        "verified_accepted_finish_evaluator_failures": int(
            verified.get("accepted_finish_evaluator_failures", 0)
        ),
        "accepted_false_finish_delta": (
            verified_accepted_false - baseline_accepted_false
        ),
        "verified_recovery_after_block": bool(
            verified.get("recovery_after_block", False)
        ),
        "baseline_evaluator_success": bool(
            baseline.get("evaluator_success", False)
        ),
        "verified_evaluator_success": bool(
            verified.get("evaluator_success", False)
        ),
        "baseline_termination_reason": baseline.get("termination_reason"),
        "verified_termination_reason": verified.get("termination_reason"),
    }


def _verification_event_count(run: dict) -> int:
    return sum(
        1
        for event in run.get("trace_events", [])
        if event.get("event_type") == "verification_decision"
    )


def _model_action_count(run: dict) -> int:
    return sum(
        1
        for event in run.get("trace_events", [])
        if event.get("event_type") == "model_response"
        and event.get("graph_node") == "choose_action"
    )
