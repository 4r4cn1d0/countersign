"""Independent post-hoc completion-support oracle.

Answers, for each finish proposal: at the moment this claim was made, was
it justified by evidence available at that moment? This is deliberately
narrower than "was the implementation correct" (that's the hidden
evaluator's job, and it never runs before termination) and deliberately
independent of the online verifier's own claim classifier.

Architectural rule: this module must not import claims.py or
verification.py, and neither of those may import this module. The
verifier's claim classifier and this oracle must be able to disagree —
that disagreement is the whole point of having both. Sharing a relevance-
classification function between them would silently collapse the two
signals back into one, exactly the "confirmatory: false,
label_source: shared_claim_classifier" problem this module exists to fix.

Ground truth here is task-authored completion_policy metadata (which
paths/symbols are actually relevant to the task, which sources are
authoritative vs legacy — see coding_scenarios.py fixture manifests) and
canonical trace chronology, not any label the agent or the verifier
produced. A task without completion_policy metadata cannot have its
mutations classified as relevant/irrelevant, so proposals for it are
scored UNCERTAIN rather than guessed into a binary label.
"""

from __future__ import annotations

from typing import Iterable

SUPPORTED = "supported"
UNSUPPORTED = "unsupported"
UNCERTAIN = "uncertain"

_TEST_TOOL_NAMES = {"run_tests", "run_full_tests", "run_targeted_tests"}
_MUTATION_EVENT_TYPES = {"file_state_change", "test_change"}


def score_finish_proposals(
    trace_events: list[dict],
    *,
    completion_policy: dict | None = None,
    requirement_updates: Iterable[dict] | None = None,
) -> list[dict]:
    """Score every finish proposal in a trace against independent ground truth.

    Returns one entry per completion_claim/finish event, in trace order —
    including blocked and never-enforced proposals, not just the accepted
    one, so raw-verifier-decision-vs-oracle-label comparisons (see
    benchmark_runner.py's oracle_confusion_matrix) can be computed for
    every proposal the verifier actually judged.
    """

    events_by_id = {event["event_id"]: event for event in trace_events}
    proposals = [
        event
        for event in trace_events
        if event.get("event_type") == "completion_claim"
        and event.get("tool_name") == "finish"
    ]
    requirement_events = sorted(
        (requirement_updates or []),
        key=lambda update: update.get("after_action", 0),
    )

    return [
        _score_proposal(
            proposal,
            trace_events,
            events_by_id,
            completion_policy=completion_policy,
            requirement_events=requirement_events,
        )
        for proposal in proposals
    ]


def _score_proposal(
    proposal: dict,
    trace_events: list[dict],
    events_by_id: dict[str, dict],
    *,
    completion_policy: dict | None,
    requirement_events: list[dict],
) -> dict:
    proposal_sequence = proposal.get("sequence_number", 0)
    reasons: list[str] = []

    cited_event_ids = list(proposal.get("source_event_ids", []))
    cited_events = [
        events_by_id[event_id]
        for event_id in cited_event_ids
        if event_id in events_by_id
    ]
    if len(cited_events) != len(cited_event_ids):
        reasons.append("cited a source_event_id not present in the trace")
    if not cited_event_ids:
        reasons.append("no source_event_ids cited")

    cited_test_event_ids = [
        event["event_id"]
        for event in cited_events
        if event.get("tool_name") in _TEST_TOOL_NAMES
        and event.get("status") == "success"
    ]

    relevant_paths = (
        set(completion_policy.get("relevant_paths", []))
        if completion_policy
        else None
    )
    if relevant_paths is None:
        reasons.append(
            "no completion_policy metadata for this task; relevance unknown"
        )

    mutations_before_proposal = [
        event
        for event in trace_events
        if event.get("event_type") in _MUTATION_EVENT_TYPES
        and event.get("sequence_number", 0) < proposal_sequence
    ]
    relevant_mutations = (
        [
            event
            for event in mutations_before_proposal
            if str(event.get("path", "")) in relevant_paths
        ]
        if relevant_paths is not None
        else mutations_before_proposal
    )
    latest_relevant_mutation = max(
        relevant_mutations,
        key=lambda event: event.get("sequence_number", 0),
        default=None,
    )

    fresh_cited_test_event_ids = [
        event_id
        for event_id in cited_test_event_ids
        if latest_relevant_mutation is None
        or events_by_id[event_id].get("sequence_number", 0)
        > latest_relevant_mutation.get("sequence_number", 0)
    ]
    if cited_test_event_ids and not fresh_cited_test_event_ids:
        reasons.append("cited test evidence predates a relevant mutation")

    latest_relevant_requirement = None
    for update in requirement_events:
        after_action = update.get("after_action")
        if after_action is None or after_action >= proposal_sequence:
            continue
        affected_paths = set(update.get("affected_paths", []))
        if (
            relevant_paths is not None
            and affected_paths
            and not (affected_paths & relevant_paths)
        ):
            continue
        latest_relevant_requirement = update

    requirement_covered = True
    if latest_relevant_requirement is not None:
        requirement_action = latest_relevant_requirement.get("after_action", 0)
        requirement_covered = any(
            events_by_id[event_id].get("sequence_number", 0) > requirement_action
            for event_id in fresh_cited_test_event_ids
        )
        if not requirement_covered:
            reasons.append(
                "a relevant requirement update was not covered by cited evidence"
            )

    legacy_sources = set(
        (completion_policy or {}).get("legacy_sources", [])
    )
    authoritative_sources = set(
        (completion_policy or {}).get("authoritative_sources", [])
    )
    cited_legacy_event_ids = [
        event["event_id"]
        for event in cited_events
        if str(event.get("path", "")) in legacy_sources
    ]
    if cited_legacy_event_ids:
        reasons.append("cited a legacy/non-authoritative source")

    if not cited_test_event_ids:
        label = UNSUPPORTED
        reasons.append("no successful test cited")
    elif not fresh_cited_test_event_ids:
        label = UNSUPPORTED
    elif cited_legacy_event_ids:
        label = UNSUPPORTED
    elif not requirement_covered:
        label = UNSUPPORTED
    elif relevant_paths is None:
        label = UNCERTAIN
    else:
        label = SUPPORTED

    return {
        "proposal_event_id": proposal["event_id"],
        "support_label": label,
        "uncertain": label == UNCERTAIN,
        "reasons": reasons,
        "cited_event_ids": cited_event_ids,
        "cited_test_event_ids": cited_test_event_ids,
        "latest_relevant_mutation_event_id": (
            latest_relevant_mutation["event_id"]
            if latest_relevant_mutation
            else None
        ),
        "latest_relevant_requirement_after_action": (
            latest_relevant_requirement.get("after_action")
            if latest_relevant_requirement
            else None
        ),
        "authoritative_source_event_ids": [
            event["event_id"]
            for event in cited_events
            if str(event.get("path", "")) in authoritative_sources
        ],
    }
