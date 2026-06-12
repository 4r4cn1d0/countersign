"""Decision-linked repository belief extraction and temporal support scoring."""

from __future__ import annotations

from collections import Counter
from typing import Any


BELIEF_TYPES = {
    "file_state",
    "test_state",
    "requirement_state",
    "task_state",
    "repository_state",
    "source_support",
}


def extract_decision_beliefs(run: dict) -> list[dict]:
    """Extract beliefs explicitly consumed by model-authored tool decisions."""

    trace_events = list(run.get("trace_events", []))
    events_by_id = {
        str(event["event_id"]): event
        for event in trace_events
        if event.get("event_id")
    }
    sequence_by_id = {
        event_id: int(event.get("sequence_number", 0))
        for event_id, event in events_by_id.items()
    }
    memory_by_event_id = {
        str(item["event_id"]): item
        for item in run.get("operational_memory", [])
        if item.get("event_id")
    }
    beliefs = []
    for decision in trace_events:
        if (
            decision.get("event_type") != "model_response"
            or decision.get("graph_node") != "choose_action"
            or not isinstance(decision.get("parsed_action"), dict)
        ):
            continue
        action = decision["parsed_action"]
        action_name = str(action.get("action", ""))
        if not action_name:
            continue
        decision_id = str(decision.get("event_id", ""))
        decision_sequence = int(decision.get("sequence_number", 0))
        declared = _declared_beliefs(action)
        if declared:
            candidates = declared
        else:
            candidates = _citation_derived_beliefs(
                action,
                memory_by_event_id,
                events_by_id,
            )
        for index, candidate in enumerate(candidates, start=1):
            source_event_ids = [
                str(event_id)
                for event_id in candidate.get("source_event_ids", [])
                if str(event_id)
            ]
            support = _support_at_decision(
                source_event_ids,
                decision_sequence=decision_sequence,
                memory_by_event_id=memory_by_event_id,
                events_by_id=events_by_id,
                sequence_by_id=sequence_by_id,
            )
            beliefs.append(
                {
                    "schema_version": "agent-decision-belief/v0.1",
                    "belief_id": f"{decision_id}:belief:{index:02d}",
                    "decision_event_id": decision_id,
                    "decision_sequence_number": decision_sequence,
                    "decision_action": action_name,
                    "tool_decision": action_name != "finish",
                    "belief_type": _normalize_belief_type(
                        candidate.get("belief_type")
                    ),
                    "claim": str(candidate.get("claim", "")).strip(),
                    "source_event_ids": source_event_ids,
                    "declared_by_model": bool(candidate.get("declared_by_model")),
                    **support,
                }
            )
    return beliefs


def summarize_decision_beliefs(
    beliefs: list[dict],
    *,
    trace_events: list[dict] | None = None,
) -> dict:
    """Summarize decision coverage and corruption at the point of use."""

    decision_ids = {
        str(event["event_id"])
        for event in trace_events or []
        if event.get("event_id")
        and event.get("event_type") == "model_response"
        and event.get("graph_node") == "choose_action"
        and isinstance(event.get("parsed_action"), dict)
    }
    trace_tool_decision_ids = {
        str(event["event_id"])
        for event in trace_events or []
        if event.get("event_id")
        and event.get("event_type") == "model_response"
        and event.get("graph_node") == "choose_action"
        and isinstance(event.get("parsed_action"), dict)
        and event["parsed_action"].get("action") != "finish"
    }
    if not decision_ids:
        decision_ids = {
            str(belief["decision_event_id"])
            for belief in beliefs
            if belief.get("decision_event_id")
        }
    tool_decision_ids = trace_tool_decision_ids or {
        str(belief["decision_event_id"])
        for belief in beliefs
        if belief.get("tool_decision")
    }
    decisions_with_beliefs = {
        str(belief["decision_event_id"])
        for belief in beliefs
        if belief.get("decision_event_id")
    }
    unsupported = [
        belief
        for belief in beliefs
        if belief.get("support_status") == "unsupported"
    ]
    stale = [belief for belief in beliefs if belief.get("stale")]
    contradicted = [
        belief
        for belief in beliefs
        if belief.get("support_status") == "contradicted"
    ]
    corrupted_ids = {
        str(belief["belief_id"])
        for belief in [*unsupported, *stale, *contradicted]
    }
    tool_beliefs = [
        belief for belief in beliefs if belief.get("tool_decision")
    ]
    type_counts = Counter(
        str(belief.get("belief_type", "repository_state"))
        for belief in beliefs
    )
    return {
        "schema_version": "agent-decision-belief-summary/v0.1",
        "decision_count": len(decision_ids),
        "tool_decision_count": len(tool_decision_ids),
        "decisions_with_beliefs": len(decisions_with_beliefs),
        "decision_belief_coverage": _rate(
            len(decisions_with_beliefs),
            len(decision_ids),
        ),
        "belief_count": len(beliefs),
        "tool_decision_belief_count": len(tool_beliefs),
        "declared_belief_count": sum(
            bool(belief.get("declared_by_model")) for belief in beliefs
        ),
        "citation_derived_belief_count": sum(
            not belief.get("declared_by_model") for belief in beliefs
        ),
        "supported_belief_count": sum(
            belief.get("support_status") == "supported"
            for belief in beliefs
        ),
        "unsupported_belief_count": len(unsupported),
        "stale_belief_count": len(stale),
        "contradicted_belief_count": len(contradicted),
        "corrupted_belief_count": len(corrupted_ids),
        "unsupported_belief_use_rate": _rate(
            len(unsupported),
            len(beliefs),
        ),
        "stale_belief_use_rate": _rate(len(stale), len(beliefs)),
        "contradicted_belief_use_rate": _rate(
            len(contradicted),
            len(beliefs),
        ),
        "corrupted_belief_use_rate": _rate(
            len(corrupted_ids),
            len(beliefs),
        ),
        "belief_counts_by_type": dict(sorted(type_counts.items())),
    }


def _declared_beliefs(action: dict) -> list[dict]:
    beliefs = action.get("beliefs")
    if not isinstance(beliefs, list):
        return []
    normalized = []
    for belief in beliefs:
        if not isinstance(belief, dict):
            continue
        normalized.append(
            {
                "belief_type": belief.get("belief_type"),
                "claim": belief.get("claim", ""),
                "source_event_ids": belief.get("source_event_ids", []),
                "declared_by_model": True,
            }
        )
    return normalized


def _citation_derived_beliefs(
    action: dict,
    memory_by_event_id: dict[str, dict],
    events_by_id: dict[str, dict],
) -> list[dict]:
    beliefs = []
    for event_id in action.get("source_event_ids", []):
        source_id = str(event_id)
        item = memory_by_event_id.get(source_id)
        event = events_by_id.get(source_id, {})
        beliefs.append(
            {
                "belief_type": _belief_type_for_source(item or event),
                "claim": str(
                    (item or {}).get("claim")
                    or event.get("content")
                    or event.get("claim")
                    or f"Decision relied on evidence {source_id}."
                ),
                "source_event_ids": [source_id],
                "declared_by_model": False,
            }
        )
    return beliefs


def _support_at_decision(
    source_event_ids: list[str],
    *,
    decision_sequence: int,
    memory_by_event_id: dict[str, dict],
    events_by_id: dict[str, dict],
    sequence_by_id: dict[str, int],
) -> dict:
    valid_source_ids = [
        event_id
        for event_id in source_event_ids
        if event_id in events_by_id
        and sequence_by_id.get(event_id, decision_sequence + 1)
        < decision_sequence
    ]
    invalid_source_ids = [
        event_id for event_id in source_event_ids if event_id not in valid_source_ids
    ]
    if not valid_source_ids:
        return {
            "support_status": "unsupported",
            "stale": False,
            "lost_provenance": True,
            "valid_source_event_ids": [],
            "invalid_source_event_ids": invalid_source_ids,
            "invalidated_by_event_ids_at_decision": [],
            "contradicted_by_event_ids_at_decision": [],
        }

    invalidators = []
    contradictions = []
    for event_id in valid_source_ids:
        item = memory_by_event_id.get(event_id, {})
        invalidators.extend(
            _prior_event_ids(
                item.get("invalidated_by_event_ids", []),
                decision_sequence,
                sequence_by_id,
            )
        )
        contradictions.extend(
            _prior_event_ids(
                item.get("contradictions", []),
                decision_sequence,
                sequence_by_id,
            )
        )
        if (
            item.get("support_status") == "contradicted"
            and not item.get("contradictions")
        ):
            contradictions.append(event_id)
        if (
            item.get("stale")
            and not item.get("invalidated_by_event_ids")
            and not item.get("contradictions")
            and item.get("support_status") != "contradicted"
        ):
            invalidators.append(event_id)

    unique_invalidators = sorted(set(invalidators))
    unique_contradictions = sorted(set(contradictions))
    stale = bool(unique_invalidators)
    if unique_contradictions:
        support_status = "contradicted"
    elif invalid_source_ids:
        support_status = "unsupported"
    elif stale:
        support_status = "stale"
    else:
        support_status = "supported"
    return {
        "support_status": support_status,
        "stale": stale,
        "lost_provenance": bool(invalid_source_ids),
        "valid_source_event_ids": valid_source_ids,
        "invalid_source_event_ids": invalid_source_ids,
        "invalidated_by_event_ids_at_decision": unique_invalidators,
        "contradicted_by_event_ids_at_decision": unique_contradictions,
    }


def _prior_event_ids(
    event_ids: list[str],
    decision_sequence: int,
    sequence_by_id: dict[str, int],
) -> list[str]:
    return [
        str(event_id)
        for event_id in event_ids
        if sequence_by_id.get(str(event_id), decision_sequence + 1)
        < decision_sequence
    ]


def _belief_type_for_source(source: dict) -> str:
    tool_name = source.get("tool_name")
    if tool_name in {"run_tests", "run_full_tests", "run_targeted_tests"}:
        return "test_state"
    if tool_name in {"read_file", "write_file", "apply_patch"}:
        return "file_state"
    if tool_name in {"refresh_requirements", "diagnose_evaluator_failure"}:
        return "requirement_state"
    if source.get("event_type") == "user_requirement_update":
        return "requirement_state"
    return "repository_state"


def _normalize_belief_type(value: Any) -> str:
    belief_type = str(value or "repository_state")
    return (
        belief_type
        if belief_type in BELIEF_TYPES
        else "repository_state"
    )


def _rate(count: int, total: int) -> float:
    return round(count / total, 4) if total else 0.0
