"""Verification gates and action-risk policy for memory claims."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from .metrics import build_memory_health_report


HIGH_RISK_CLAIMS = {
    "tests_pass",
    "task_complete",
    "user_approved",
    "file_changed",
    "source_supports_claim",
    "no_errors_present",
}

REQUIRED_SOURCE_TYPES = {
    "tests_pass": {"tool_output"},
    "task_complete": {"tool_output", "file_state"},
    "user_approved": {"user_instruction"},
    "file_changed": {"file_state", "tool_output"},
    "source_supports_claim": {"retrieved_source"},
    "no_errors_present": {"tool_output"},
}


@dataclass(frozen=True)
class VerificationPolicy:
    """Policy thresholds for high-risk claim verification."""

    mode: str = "strict"
    min_confidence: float = 0.75
    min_consistency_score: float = 0.75


def verify_run(
    run: dict,
    policy: VerificationPolicy | None = None,
) -> dict:
    """Return a copy of a benchmark run with verification decisions attached."""

    active_policy = policy or VerificationPolicy()
    trace_events = list(run.get("trace_events", []))
    memory_claims = list(run.get("memory_claims", []))
    decisions = [
        verify_claim(claim, trace_events, active_policy) for claim in memory_claims
    ]

    verified = dict(run)
    verified["verification_policy"] = {
        "mode": active_policy.mode,
        "min_confidence": active_policy.min_confidence,
        "min_consistency_score": active_policy.min_consistency_score,
    }
    verified["verification_decisions"] = decisions
    verified["blocked_actions"] = [
        _blocked_action(decision)
        for decision in decisions
        if decision["decision"] == "block"
    ]
    verified["trace_events"] = trace_events + _decision_trace_events(
        run, trace_events, decisions
    )

    blocked_claim_ids = {
        decision["claim_id"]
        for decision in decisions
        if decision["decision"] == "block"
    }
    effective_run = dict(verified)
    effective_run["memory_claims"] = [
        claim for claim in memory_claims if claim["claim_id"] not in blocked_claim_ids
    ]
    verified["effective_memory_health_report"] = build_memory_health_report(
        effective_run
    )
    verified["verification_report"] = build_verification_report(verified)
    return verified


def verify_claim(
    claim: dict,
    trace_events: Iterable[dict],
    policy: VerificationPolicy | None = None,
) -> dict:
    """Verify a single memory claim against provenance and risk policy."""

    active_policy = policy or VerificationPolicy()
    events_by_id = {event["event_id"]: event for event in trace_events}
    provenance_chain = _resolve_provenance_chain(claim, events_by_id)
    inspected_event_ids = [event["event_id"] for event in provenance_chain]
    required_sources = REQUIRED_SOURCE_TYPES.get(claim["claim_type"], set())
    observed_sources = {
        event.get("source_type")
        for event in provenance_chain
        if event.get("source_type")
    }

    consistency_score = retrieval_consistency_score(
        claim,
        provenance_chain,
        required_sources,
        active_policy,
    )
    reasons = _verification_reasons(
        claim,
        consistency_score,
        required_sources,
        observed_sources,
        active_policy,
    )
    decision = _verification_decision(claim, consistency_score, reasons, active_policy)

    return {
        "decision_id": f"{claim['claim_id']}:verification",
        "claim_id": claim["claim_id"],
        "event_id": claim["event_id"],
        "claim_type": claim["claim_type"],
        "risk_level": "high"
        if claim["claim_type"] in HIGH_RISK_CLAIMS
        else "normal",
        "decision": decision,
        "consistency_score": consistency_score,
        "reasons": reasons,
        "required_source_types": sorted(required_sources),
        "observed_source_types": sorted(observed_sources),
        "source_event_ids": claim.get("source_event_ids", []),
        "inspected_event_ids": inspected_event_ids,
        "recommended_action": _recommended_action(claim),
    }


def retrieval_consistency_score(
    claim: dict,
    provenance_chain: Iterable[dict],
    required_sources: set[str],
    policy: VerificationPolicy | None = None,
) -> float:
    """Score whether recalled claim provenance is consistent with evidence."""

    active_policy = policy or VerificationPolicy()
    chain = list(provenance_chain)
    if not chain:
        return 0.0

    observed_sources = {
        event.get("source_type") for event in chain if event.get("source_type")
    }
    score = 0.0

    if not required_sources or required_sources.issubset(observed_sources):
        score += 0.4
    elif observed_sources.intersection(required_sources):
        score += 0.2
    if not claim.get("stale", False):
        score += 0.25
    if claim.get("support_status") not in {"unsupported", "contradicted"}:
        score += 0.2
    if not claim.get("lost_provenance", False):
        score += 0.1
    if claim.get("confidence", 0.0) >= active_policy.min_confidence:
        score += 0.05

    return round(min(score, 1.0), 4)


def build_verification_report(verified_run: dict) -> dict:
    """Build a compact report from verification decisions."""

    decisions = verified_run.get("verification_decisions", [])
    counts = {
        "allow": sum(1 for decision in decisions if decision["decision"] == "allow"),
        "needs_verification": sum(
            1 for decision in decisions if decision["decision"] == "needs_verification"
        ),
        "block": sum(1 for decision in decisions if decision["decision"] == "block"),
    }
    return {
        "schema_version": "agent-memory-verification/v0.1",
        "run_id": verified_run.get("run_id"),
        "task_id": verified_run.get("task_id"),
        "policy": verified_run.get("verification_policy", {}),
        "decision_counts": counts,
        "decisions": decisions,
        "blocked_actions": verified_run.get("blocked_actions", []),
        "effective_memory_health_report": verified_run.get(
            "effective_memory_health_report"
        ),
    }


def _verification_reasons(
    claim: dict,
    consistency_score: float,
    required_sources: set[str],
    observed_sources: set[str],
    policy: VerificationPolicy,
) -> list[str]:
    reasons = []
    if claim.get("lost_provenance"):
        reasons.append("lost provenance")
    if claim.get("stale"):
        reasons.append("stale evidence")
    if claim.get("support_status") in {"unsupported", "contradicted"}:
        reasons.append(f"{claim['support_status']} claim")
    if claim.get("confidence", 0.0) < policy.min_confidence:
        reasons.append("low confidence")
    if required_sources and not required_sources.issubset(observed_sources):
        reasons.append("missing required source type")
    if consistency_score < policy.min_consistency_score:
        reasons.append("low retrieval consistency")
    return reasons


def _verification_decision(
    claim: dict,
    consistency_score: float,
    reasons: list[str],
    policy: VerificationPolicy,
) -> str:
    high_risk = claim["claim_type"] in HIGH_RISK_CLAIMS
    blocking_reasons = {
        "lost provenance",
        "stale evidence",
        "unsupported claim",
        "contradicted claim",
        "missing required source type",
    }

    if policy.mode == "strict" and high_risk and blocking_reasons.intersection(reasons):
        return "block"
    if consistency_score < policy.min_consistency_score or reasons:
        return "needs_verification"
    return "allow"


def _resolve_provenance_chain(claim: dict, events_by_id: dict[str, dict]) -> list[dict]:
    chain: list[dict] = []
    seen: set[str] = set()
    stack = list(claim.get("source_event_ids", []))

    while stack:
        event_id = stack.pop()
        if event_id in seen:
            continue
        seen.add(event_id)
        event = events_by_id.get(event_id)
        if not event:
            continue
        chain.append(event)
        stack.extend(event.get("source_event_ids", []))

    return chain


def _decision_trace_events(
    run: dict,
    existing_events: list[dict],
    decisions: list[dict],
) -> list[dict]:
    start_sequence = max(
        [event.get("sequence_number", 0) for event in existing_events],
        default=0,
    )
    task_id = run.get("task_id", "run")
    events = []
    for index, decision in enumerate(decisions, start=1):
        events.append(
            {
                "event_id": f"{task_id}:verification:{index:03d}",
                "event_type": "verification_decision",
                "sequence_number": start_sequence + index,
                "source_type": "verification_policy",
                "source_event_ids": [decision["event_id"]],
                "decision": decision["decision"],
                "claim_id": decision["claim_id"],
                "claim_type": decision["claim_type"],
                "reasons": decision["reasons"],
                "consistency_score": decision["consistency_score"],
            }
        )
    return events


def _blocked_action(decision: dict) -> dict:
    return {
        "claim_id": decision["claim_id"],
        "claim_type": decision["claim_type"],
        "blocked_action": _action_name(decision["claim_type"]),
        "reasons": decision["reasons"],
        "recommended_action": decision["recommended_action"],
    }


def _action_name(claim_type: str) -> str:
    actions = {
        "tests_pass": "report_tests_pass",
        "task_complete": "mark_task_complete",
        "user_approved": "act_on_user_approval",
        "file_changed": "report_file_changed",
        "source_supports_claim": "cite_source_support",
        "no_errors_present": "report_no_errors",
    }
    return actions.get(claim_type, f"use_{claim_type}")


def _recommended_action(claim: dict) -> str:
    if claim["claim_type"] == "tests_pass":
        return "rerun relevant tests and attach fresh tool output"
    if claim["claim_type"] == "task_complete":
        return "collect implementation evidence and fresh verification output"
    if claim["claim_type"] == "source_supports_claim":
        return "re-read the cited source and attach provenance"
    if claim["claim_type"] == "user_approved":
        return "confirm approval in the user instruction history"
    return "verify the claim against current evidence"
