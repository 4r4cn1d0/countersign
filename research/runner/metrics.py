"""Memory corruption metrics for benchmark runs."""

from __future__ import annotations

import re
from statistics import mean
from typing import Iterable

from .claims import extract_memory_claims


WORD_PATTERN = re.compile(r"[a-z0-9_]+")


def build_memory_health_report(run: dict, task: dict | None = None) -> dict:
    """Build a per-run memory health report."""

    memory_claims = (
        run["memory_claims"] if "memory_claims" in run else extract_memory_claims(run)
    )
    trace_events = run.get("trace_events", [])

    semantic_drift_score = compute_semantic_drift_score(run, task)
    task_state_accuracy = compute_task_state_accuracy(memory_claims)
    attribution_accuracy = compute_attribution_accuracy(memory_claims)
    temporal_accuracy = compute_temporal_accuracy(memory_claims)

    metrics = {
        "semantic_drift_score": semantic_drift_score,
        "goal_fidelity": 1.0 - semantic_drift_score,
        "task_state_accuracy": task_state_accuracy,
        "attribution_accuracy": attribution_accuracy,
        "temporal_accuracy": temporal_accuracy,
        "false_completion_rate": compute_false_completion_rate(memory_claims),
        "memory_health_score": mean(
            [
                1.0 - semantic_drift_score,
                task_state_accuracy,
                attribution_accuracy,
                temporal_accuracy,
            ]
        ),
    }

    unsupported_claims = [
        claim for claim in memory_claims if claim["support_status"] == "unsupported"
    ]
    stale_claims = [claim for claim in memory_claims if claim["stale"]]
    contradicted_claims = [
        claim for claim in memory_claims if claim["support_status"] == "contradicted"
    ]

    return {
        "schema_version": "agent-memory-health/v0.1",
        "run_id": run.get("run_id"),
        "task_id": run.get("task_id") or (task or {}).get("task_id"),
        "metrics": metrics,
        "claim_counts": {
            "total": len(memory_claims),
            "unsupported": len(unsupported_claims),
            "stale": len(stale_claims),
            "contradicted": len(contradicted_claims),
            "lost_provenance": sum(
                1 for claim in memory_claims if claim["lost_provenance"]
            ),
            "false_completion": _count_false_completion_claims(memory_claims),
        },
        "unsupported_claims": unsupported_claims,
        "stale_claims": stale_claims,
        "contradicted_claims": contradicted_claims,
        "recovery_opportunities": _build_recovery_opportunities(memory_claims),
        "trace_event_count": len(trace_events),
    }


def compute_semantic_drift_score(run: dict, task: dict | None = None) -> float:
    """Score drift between the original goal and the latest agent summary/claim."""

    goal_text = _original_goal_text(run, task)
    current_text = _latest_agent_state_text(run)
    if not goal_text or not current_text:
        return 0.0

    alignment = _jaccard_similarity(goal_text, current_text)

    checkpoint_text = " ".join(
        checkpoint.get("claim", "")
        for checkpoint in _ground_truth_checkpoints(run, task)
    )
    if checkpoint_text:
        alignment = max(alignment, _jaccard_similarity(checkpoint_text, current_text))

    return _round_score(1.0 - alignment)


def compute_task_state_accuracy(memory_claims: Iterable[dict]) -> float:
    """Score whether completion-related claims are supported and fresh."""

    completion_claims = [
        claim for claim in memory_claims if claim["claim_type"] == "task_complete"
    ]
    if not completion_claims:
        return 1.0

    false_completion_count = _count_false_completion_claims(completion_claims)
    return _round_score(1.0 - false_completion_count / len(completion_claims))


def compute_attribution_accuracy(memory_claims: Iterable[dict]) -> float:
    """Score whether claims retain provenance."""

    claims = list(memory_claims)
    if not claims:
        return 1.0

    attributed = [
        claim
        for claim in claims
        if claim["source_event_ids"] and not claim["lost_provenance"]
    ]
    return _round_score(len(attributed) / len(claims))


def compute_temporal_accuracy(memory_claims: Iterable[dict]) -> float:
    """Score whether claims are backed by fresh enough evidence."""

    claims = list(memory_claims)
    if not claims:
        return 1.0

    fresh = [claim for claim in claims if not claim["stale"]]
    return _round_score(len(fresh) / len(claims))


def compute_false_completion_rate(memory_claims: Iterable[dict]) -> float:
    """Return the rate of completion claims lacking fresh support."""

    completion_claims = [
        claim for claim in memory_claims if claim["claim_type"] == "task_complete"
    ]
    if not completion_claims:
        return 0.0
    return _round_score(
        _count_false_completion_claims(completion_claims) / len(completion_claims)
    )


def _count_false_completion_claims(memory_claims: Iterable[dict]) -> int:
    return sum(
        1
        for claim in memory_claims
        if claim["claim_type"] == "task_complete"
        and (
            claim["stale"]
            or claim["lost_provenance"]
            or claim["support_status"] in {"unsupported", "contradicted"}
        )
    )


def _build_recovery_opportunities(memory_claims: Iterable[dict]) -> list[dict]:
    opportunities: list[dict] = []
    for claim in memory_claims:
        reasons = []
        if claim["lost_provenance"]:
            reasons.append("verify provenance")
        if claim["stale"]:
            reasons.append("refresh stale evidence")
        if claim["support_status"] in {"unsupported", "contradicted"}:
            reasons.append(f"resolve {claim['support_status']} claim")
        if reasons:
            opportunities.append(
                {
                    "claim_id": claim["claim_id"],
                    "claim_type": claim["claim_type"],
                    "reasons": reasons,
                    "recommended_action": _recommended_action(claim),
                }
            )
    return opportunities


def _recommended_action(claim: dict) -> str:
    if claim["claim_type"] == "tests_pass":
        return "rerun relevant tests after the latest state change"
    if claim["claim_type"] == "task_complete":
        return "collect implementation evidence and fresh verification evidence"
    if claim["claim_type"] == "source_supports_claim":
        return "re-read the cited source and attach exact provenance"
    return "verify the claim against current trace evidence"


def _original_goal_text(run: dict, task: dict | None) -> str:
    if task and task.get("goal"):
        return task["goal"]
    if run.get("task_goal"):
        return run["task_goal"]
    for event in run.get("trace_events", []):
        if event.get("event_type") == "prompt":
            return event.get("prompt", "")
    return ""


def _ground_truth_checkpoints(run: dict, task: dict | None) -> list[dict]:
    if task and task.get("ground_truth_checkpoints"):
        return task["ground_truth_checkpoints"]
    return run.get("ground_truth_checkpoints", [])


def _latest_agent_state_text(run: dict) -> str:
    for event in reversed(run.get("trace_events", [])):
        if event.get("event_type") in {"summary", "completion_claim", "agent_claim"}:
            return " ".join(
                str(value)
                for value in [
                    event.get("summary"),
                    event.get("claim"),
                    event.get("content"),
                ]
                if value
            )
    return ""


def _jaccard_similarity(left: str, right: str) -> float:
    left_words = set(WORD_PATTERN.findall(left.lower()))
    right_words = set(WORD_PATTERN.findall(right.lower()))
    if not left_words and not right_words:
        return 1.0
    if not left_words or not right_words:
        return 0.0
    return len(left_words & right_words) / len(left_words | right_words)


def _round_score(value: float) -> float:
    return round(max(0.0, min(1.0, value)), 4)
