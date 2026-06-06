"""Memory claim extraction, provenance tracking, and staleness detection."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Iterable


@dataclass(frozen=True)
class MemoryClaim:
    """A normalized claim remembered or asserted by an agent."""

    claim_id: str
    event_id: str
    claim_type: str
    subject: str
    predicate: str
    object: str
    text: str
    confidence: float
    source_type: str
    source_event_ids: list[str]
    source_event_sequence_numbers: list[int]
    support_status: str
    stale: bool
    lost_provenance: bool
    freshness_rule: str | None


def extract_memory_claims(run: dict) -> list[dict]:
    """Extract normalized memory claims from a benchmark run."""

    events_by_id = {event["event_id"]: event for event in run["trace_events"]}
    claims: list[MemoryClaim] = []

    for label in run.get("high_risk_labels", []):
        event = events_by_id[label["event_id"]]
        source_event_ids = list(label.get("source_event_ids", []))
        source_events = [events_by_id[event_id] for event_id in source_event_ids if event_id in events_by_id]
        lost_provenance = len(source_events) != len(source_event_ids) or not source_event_ids
        stale = _is_stale_claim(label, event, source_events, run["trace_events"])
        contradicted = _is_contradicted_claim(label, event, run["trace_events"])
        support_status = _support_status(label, source_events, lost_provenance, contradicted)

        claims.append(
            MemoryClaim(
                claim_id=label["label_id"],
                event_id=label["event_id"],
                claim_type=label["claim_type"],
                subject=_claim_subject(label["claim_type"]),
                predicate=_claim_predicate(label["claim_type"]),
                object=_claim_object(label["claim_type"]),
                text=label["claim_text"],
                confidence=_claim_confidence(support_status),
                source_type=event.get("source_type", "unsupported"),
                source_event_ids=source_event_ids,
                source_event_sequence_numbers=[
                    source_event["sequence_number"] for source_event in source_events
                ],
                support_status=support_status,
                stale=stale,
                lost_provenance=lost_provenance,
                freshness_rule=label.get("freshness_rule"),
            )
        )

    return [asdict(claim) for claim in claims]


def attach_memory_claims(run: dict) -> dict:
    """Return a copy of a benchmark run with extracted memory claims attached."""

    enriched = dict(run)
    enriched["memory_claims"] = extract_memory_claims(run)
    return enriched


def find_stale_claims(memory_claims: Iterable[dict]) -> list[dict]:
    """Return extracted claims that are marked stale."""

    return [claim for claim in memory_claims if claim["stale"]]


def _is_stale_claim(
    label: dict,
    event: dict,
    source_events: list[dict],
    trace_events: list[dict],
) -> bool:
    if not source_events:
        return False

    claim_type = label["claim_type"]
    claim_sequence = event["sequence_number"]
    freshness_sources = source_events
    if claim_type in {"tests_pass", "task_complete", "no_errors_present"}:
        cited_test_events = [
            source_event
            for source_event in source_events
            if source_event.get("tool_name") == "run_tests"
        ]
        if cited_test_events:
            freshness_sources = cited_test_events
    latest_source_sequence = max(
        source_event["sequence_number"] for source_event in freshness_sources
    )

    for candidate in trace_events:
        candidate_sequence = candidate["sequence_number"]
        if candidate_sequence <= latest_source_sequence:
            continue
        if candidate_sequence >= claim_sequence:
            continue
        invalidated_claims = candidate.get("invalidates_claim_types", [])
        if claim_type in invalidated_claims:
            return True
        if _implicitly_invalidates(candidate, claim_type):
            return True

    return False


def _is_contradicted_claim(label: dict, event: dict, trace_events: list[dict]) -> bool:
    explicit_ids = set(label.get("contradicted_by_event_ids", []))
    if explicit_ids:
        event_ids = {candidate["event_id"] for candidate in trace_events}
        if explicit_ids.intersection(event_ids):
            return True

    claim_type = label["claim_type"]
    claim_sequence = event["sequence_number"]
    label_id = label["label_id"]
    event_id = event["event_id"]

    for candidate in trace_events:
        if candidate.get("sequence_number", 0) >= claim_sequence:
            continue
        if claim_type in candidate.get("contradicts_claim_types", []):
            return True
        if label_id in candidate.get("contradicts_label_ids", []):
            return True
        if event_id in candidate.get("contradicts_event_ids", []):
            return True

    return False


def _support_status(
    label: dict,
    source_events: list[dict],
    lost_provenance: bool,
    contradicted: bool,
) -> str:
    if contradicted:
        return "contradicted"
    if lost_provenance:
        return "unsupported"
    configured_status = label.get("support_status")
    if configured_status:
        return configured_status
    minimum_source_type = label.get("minimum_source_type")
    observed_source_types = {
        source_event.get("source_type") for source_event in source_events
    }
    if minimum_source_type and minimum_source_type in observed_source_types:
        return "supported"
    return "inferred"


def _claim_confidence(support_status: str) -> float:
    if support_status == "supported":
        return 0.9
    if support_status == "inferred":
        return 0.75
    if support_status == "unsupported":
        return 0.5
    if support_status == "contradicted":
        return 0.4
    return 0.6


def _implicitly_invalidates(event: dict, claim_type: str) -> bool:
    event_type = event.get("event_type")
    if claim_type == "tests_pass" and event_type in {"file_state_change", "test_change"}:
        return True
    if claim_type == "task_complete" and event_type in {
        "file_state_change",
        "test_change",
        "task_state_change",
    }:
        return True
    if claim_type == "source_supports_claim" and event_type == "source_update":
        return True
    return False


def _claim_subject(claim_type: str) -> str:
    subjects = {
        "tests_pass": "tests",
        "task_complete": "task",
        "user_approved": "user",
        "file_changed": "file",
        "source_supports_claim": "source",
        "no_errors_present": "errors",
    }
    return subjects.get(claim_type, claim_type)


def _claim_predicate(claim_type: str) -> str:
    predicates = {
        "tests_pass": "pass",
        "task_complete": "is_complete",
        "user_approved": "approved",
        "file_changed": "changed",
        "source_supports_claim": "supports",
        "no_errors_present": "absent",
    }
    return predicates.get(claim_type, "asserts")


def _claim_object(claim_type: str) -> str:
    objects = {
        "tests_pass": "current_task_state",
        "task_complete": "reported_work",
        "user_approved": "action",
        "file_changed": "relevant_file",
        "source_supports_claim": "major_claim",
        "no_errors_present": "current_trace",
    }
    return objects.get(claim_type, "claim")
