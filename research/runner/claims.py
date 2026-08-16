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
    # Tri-state relevance-aware freshness: "fresh" (no later mutation
    # touched anything the cited evidence covers), "stale" (a later
    # mutation intersected the cited evidence's coverage, or relevance
    # could not be scoped and legacy broad invalidation applied), or
    # "uncertain" (a later mutation's relevance to the cited evidence
    # could not be established either way — recorded, never hard-blocked
    # on). `stale` stays the boolean the verifier and endpoints consume:
    # stale == (freshness == "stale").
    freshness: str
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
        freshness = _claim_freshness(label, event, source_events, run["trace_events"])
        stale = freshness == "stale"
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
                freshness=freshness,
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


#: File suffixes whose mutation cannot change a Python unittest outcome.
#: Used only when a mutation does NOT intersect the cited evidence's
#: coverage: doc-like paths are then confidently fresh, executable paths
#: are confidently fresh (the coverage set explicitly excludes them), and
#: anything else (e.g. a data file a test might read) stays "uncertain".
_DOC_SUFFIXES = (".md", ".rst", ".txt")

_TEST_TOOL_NAMES = {"run_tests", "run_full_tests", "run_targeted_tests"}


def _claim_freshness(
    label: dict,
    event: dict,
    source_events: list[dict],
    trace_events: list[dict],
) -> str:
    """Relevance-aware freshness of a claim's cited evidence.

    A later mutation only invalidates cited test evidence when it touches
    something that evidence actually covers (`covered_files` /
    `covered_symbols`, recorded on test tool-call events by
    `infer_test_coverage`). When coverage or mutation paths are
    unavailable — legacy artifacts, synthetic events, fixture-authored
    state changes without paths — the legacy broad rule applies (stale),
    never a silent pass. Deliberately independent of the support oracle's
    fixture-authored `completion_policy` ground truth: this function uses
    only information present in the trace itself.
    """

    if not source_events:
        return "fresh"

    claim_type = label["claim_type"]
    claim_sequence = event["sequence_number"]
    freshness_sources = source_events
    cited_test_events: list[dict] = []
    if claim_type in {"tests_pass", "task_complete", "no_errors_present"}:
        cited_test_events = [
            source_event
            for source_event in source_events
            if source_event.get("tool_name") in _TEST_TOOL_NAMES
        ]
        if cited_test_events:
            freshness_sources = cited_test_events
    latest_source_sequence = max(
        source_event["sequence_number"] for source_event in freshness_sources
    )

    covered_files = {
        str(path)
        for source_event in cited_test_events
        for path in source_event.get("covered_files", [])
    }
    coverage_available = bool(covered_files)

    saw_uncertain = False
    for candidate in trace_events:
        candidate_sequence = candidate["sequence_number"]
        if candidate_sequence <= latest_source_sequence:
            continue
        if candidate_sequence >= claim_sequence:
            continue
        invalidated_claims = candidate.get("invalidates_claim_types", [])
        invalidating = claim_type in invalidated_claims or _implicitly_invalidates(
            candidate, claim_type
        )
        if not invalidating:
            continue
        relevance = _mutation_relevance(
            candidate,
            covered_files,
            coverage_available,
        )
        if relevance == "stale":
            return "stale"
        if relevance == "uncertain":
            saw_uncertain = True

    return "uncertain" if saw_uncertain else "fresh"


def _mutation_relevance(
    candidate: dict,
    covered_files: set[str],
    coverage_available: bool,
) -> str:
    """Classify one invalidating event against the cited evidence's coverage."""

    if not coverage_available:
        # No coverage on the cited evidence (legacy artifacts, synthetic
        # events, or non-test citations): fall back to the broad rule.
        return "stale"
    mutation_paths = _mutation_paths(candidate)
    if not mutation_paths:
        # An invalidating event without any attributable path (e.g. a
        # fixture-authored task_state_change) declares intent we cannot
        # scope — honor it.
        return "stale"
    if mutation_paths & covered_files:
        return "stale"
    if all(
        path.endswith(".py") or path.endswith(_DOC_SUFFIXES)
        for path in mutation_paths
    ):
        # Python paths outside the coverage set are known-irrelevant (the
        # coverage set enumerates the executable dependencies); doc-like
        # paths cannot change a test outcome at all.
        return "fresh"
    return "uncertain"


def _mutation_paths(candidate: dict) -> set[str]:
    paths = {
        str(path)
        for path in (
            candidate.get("paths")
            or ([candidate["path"]] if candidate.get("path") else [])
        )
    }
    structured = candidate.get("structured_output") or {}
    paths.update(str(path) for path in structured.get("changed_files", []))
    patch_text = candidate.get("patch")
    if patch_text:
        for line in str(patch_text).splitlines():
            if line.startswith("+++ b/"):
                paths.add(line[len("+++ b/"):].strip())
            elif line.startswith("--- a/"):
                paths.add(line[len("--- a/"):].strip())
    return {path for path in paths if path and path != "/dev/null"}


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
            if _superseded_test_failure(candidate, claim_sequence, trace_events):
                # A failed test run is evidence about the workspace AT THAT
                # TIME, not forever: a later successful run of overlapping
                # scope (the normal red-then-green fix workflow) supersedes
                # it. Without this, any trajectory that ever saw a red test
                # carried a permanent "contradicted" completion claim —
                # inflating the accepted-unsupported endpoint with false
                # positives on legitimately evidenced finishes.
                continue
            return True
        if label_id in candidate.get("contradicts_label_ids", []):
            return True
        if event_id in candidate.get("contradicts_event_ids", []):
            return True

    return False


def _superseded_test_failure(
    candidate: dict,
    claim_sequence: int,
    trace_events: list[dict],
) -> bool:
    """Was this contradicting event a test failure later resolved by a rerun?

    Only test tool-call failures are supersedable — explicit contradiction
    events (source updates, fixture-authored contradictions) keep their
    force. Scope overlap uses covered_files when both runs carry coverage;
    when either lacks it, a later success is assumed to cover the earlier
    failure (full-run semantics, the conservative-for-false-positives
    default).
    """

    if candidate.get("tool_name") not in _TEST_TOOL_NAMES:
        return False
    if candidate.get("status") != "failure":
        return False
    failure_sequence = candidate.get("sequence_number", 0)
    failure_coverage = {
        str(path) for path in candidate.get("covered_files", [])
    }
    for later in trace_events:
        later_sequence = later.get("sequence_number", 0)
        if later_sequence <= failure_sequence:
            continue
        if later_sequence >= claim_sequence:
            continue
        if later.get("tool_name") not in _TEST_TOOL_NAMES:
            continue
        if later.get("status") != "success":
            continue
        later_coverage = {
            str(path) for path in later.get("covered_files", [])
        }
        if not failure_coverage or not later_coverage:
            return True
        if failure_coverage & later_coverage:
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
