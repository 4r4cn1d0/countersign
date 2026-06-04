"""Trace labeling hooks for high-risk memory and completion claims."""

from __future__ import annotations

from typing import Iterable


CLAIM_PATTERNS: dict[str, tuple[str, ...]] = {
    "tests_pass": ("pass", "passed", "passing", "green", "successful"),
    "task_complete": ("complete", "completed", "done", "finished", "ready"),
    "user_approved": ("approved", "approval", "user approved"),
    "file_changed": ("changed", "modified", "updated", "edited"),
    "source_supports_claim": ("source", "supports", "citation", "cited"),
    "no_errors_present": ("no errors", "without errors", "error-free"),
}


def label_high_risk_claims(
    trace_events: Iterable[dict],
    high_risk_claims: Iterable[dict],
) -> list[dict]:
    """Return labels for high-risk claims found in trace events.

    Labels preserve the source event IDs carried by each event. This is the first
    provenance hook: later scoring can decide whether those sources are strong,
    stale, contradicted, or missing.
    """

    configured_claims = {claim["claim_type"]: claim for claim in high_risk_claims}
    labels: list[dict] = []

    for event in trace_events:
        if event.get("event_type") not in {"completion_claim", "summary", "agent_claim"}:
            continue

        text = _event_text(event)
        if not text:
            continue

        for claim_type, claim_config in configured_claims.items():
            if _matches_claim_type(text, claim_type):
                labels.append(
                    {
                        "label_id": f"{event['event_id']}:{claim_type}",
                        "event_id": event["event_id"],
                        "claim_type": claim_type,
                        "risk_level": "high",
                        "verification_required": claim_config.get(
                            "verification_required", True
                        ),
                        "minimum_source_type": claim_config.get("minimum_source_type"),
                        "freshness_rule": claim_config.get("freshness_rule"),
                        "source_event_ids": event.get("source_event_ids", []),
                        "claim_text": text,
                        "support_status": event.get("support_status"),
                    }
                )

    return labels


def _event_text(event: dict) -> str:
    text_fields = [
        event.get("prompt"),
        event.get("response"),
        event.get("summary"),
        event.get("claim"),
        event.get("content"),
    ]
    return " ".join(str(value) for value in text_fields if value).lower()


def _matches_claim_type(text: str, claim_type: str) -> bool:
    if _negates_claim(text, claim_type):
        return False
    if claim_type == "tests_pass":
        mentions_tests = any(token in text for token in ("test", "tests", "pytest"))
        mentions_success = any(pattern in text for pattern in CLAIM_PATTERNS["tests_pass"])
        return mentions_tests and mentions_success
    if claim_type == "task_complete":
        mentions_task = any(token in text for token in ("task", "work", "implementation"))
        mentions_done = any(pattern in text for pattern in CLAIM_PATTERNS["task_complete"])
        return mentions_task and mentions_done
    if claim_type == "file_changed":
        mentions_file = any(token in text for token in ("file", "files", "code"))
        mentions_change = any(pattern in text for pattern in CLAIM_PATTERNS["file_changed"])
        return mentions_file and mentions_change
    if claim_type == "source_supports_claim":
        mentions_source = any(token in text for token in ("source", "citation", "cited"))
        mentions_support = any(pattern in text for pattern in CLAIM_PATTERNS["source_supports_claim"])
        return mentions_source and mentions_support
    patterns = CLAIM_PATTERNS.get(claim_type, (claim_type.replace("_", " "),))
    return any(pattern in text for pattern in patterns)


def _negates_claim(text: str, claim_type: str) -> bool:
    negation_phrases = {
        "tests_pass": (
            "tests still need",
            "tests are required",
            "need to run tests",
            "must run tests",
            "tests not run",
            "tests have not",
            "do not claim tests",
            "without tests",
            "not sufficient",
            "insufficient evidence",
            "not sufficient evidence",
        ),
        "task_complete": (
            "not complete",
            "not done",
            "not finished",
            "still needs",
            "still need",
            "do not claim",
            "without evidence",
            "before proceeding",
            "not sufficient",
            "insufficient evidence",
        ),
    }
    return any(phrase in text for phrase in negation_phrases.get(claim_type, ()))
