"""Conservative attribution of coding-agent failures to memory evidence."""

from __future__ import annotations

from typing import Any

from .memory_pressure import INDUCED_CORRUPTION_CONDITIONS


MUTATION_TOOLS = {"write_file", "apply_patch"}
TEST_TOOLS = {"run_tests", "run_full_tests", "run_targeted_tests"}
READ_TOOLS = {
    "list_files",
    "read_file",
    "read_structured_file",
    "search_code",
    "inspect_dependency",
    "git_diff",
    "git_status",
}


def classify_run_failure(run: dict) -> dict:
    """Classify failure evidence without equating every task failure with memory."""

    metadata = run.get("run_metadata", {})
    interaction = run.get("interaction_metrics", {})
    trace_events = list(run.get("trace_events", []))
    condition = str(metadata.get("memory_condition", "full_history"))
    successful_tools = [
        event
        for event in trace_events
        if event.get("status") == "success"
        and (
            event.get("event_type") == "tool_call"
            or event.get("event_type") == "file_state_change"
        )
    ]
    successful_tool_names = {
        str(event.get("tool_name"))
        for event in successful_tools
        if event.get("tool_name")
    }
    action_count = int(interaction.get("model_action_count", 0))
    valid_action_count = int(
        interaction.get("valid_model_action_count", action_count)
    )
    compliance_rate = float(
        interaction.get(
            "action_compliance_rate",
            valid_action_count / action_count if action_count else 0.0,
        )
    )
    demonstrated_tool_competence = bool(
        successful_tool_names & READ_TOOLS
        and successful_tool_names & MUTATION_TOOLS
        and successful_tool_names & TEST_TOOLS
        and valid_action_count >= 5
        and compliance_rate >= 0.8
    )

    belief_summary = run.get("decision_belief_summary", {})
    corrupted_belief_count = sum(
        int(belief_summary.get(key, 0))
        for key in (
            "unsupported_belief_count",
            "stale_belief_count",
            "contradicted_belief_count",
        )
    )
    first_corrupted_belief_sequence = min(
        (
            int(belief.get("decision_sequence_number", 0))
            for belief in run.get("decision_beliefs", [])
            if belief.get("support_status")
            in {"unsupported", "stale", "contradicted"}
        ),
        default=None,
    )
    stale_finish_pattern = _stale_finish_pattern(trace_events)
    memory_signal_sequence = _minimum_sequence(
        first_corrupted_belief_sequence,
        stale_finish_pattern.get("finish_sequence"),
    )
    memory_signal_types = []
    if corrupted_belief_count:
        memory_signal_types.append("corrupted_decision_belief")
    if stale_finish_pattern["detected"]:
        memory_signal_types.append("stale_verification_at_finish")

    runtime_error = metadata.get("runtime_error")
    evaluator_success = bool(
        interaction.get(
            "evaluator_success",
            metadata.get("evaluator_success", False),
        )
    )
    accepted_false_finish = int(
        interaction.get("accepted_false_finishes", 0)
    ) > 0
    task_failed = not evaluator_success
    memory_contributed = bool(
        task_failed
        and demonstrated_tool_competence
        and memory_signal_types
        and (
            accepted_false_finish
            or stale_finish_pattern["detected"]
            or corrupted_belief_count
        )
    )

    pressure_sequences = [
        int(event.get("sequence_number", 0))
        for event in trace_events
        if event.get("event_type") == "memory_pressure"
        and event.get("induced_corruption")
    ]
    first_induced_pressure_sequence = (
        min(pressure_sequences) if pressure_sequences else None
    )
    origin = _corruption_origin(
        condition=condition,
        memory_contributed=memory_contributed,
        memory_signal_sequence=memory_signal_sequence,
        first_induced_pressure_sequence=first_induced_pressure_sequence,
    )

    if runtime_error:
        outcome_class = "runtime_failure"
    elif evaluator_success and memory_signal_types:
        outcome_class = "task_success_with_memory_warning"
    elif evaluator_success:
        outcome_class = "task_success"
    elif memory_contributed:
        outcome_class = "memory_contributed_failure"
    elif not demonstrated_tool_competence:
        outcome_class = "capability_or_action_failure"
    else:
        outcome_class = "coding_or_task_failure_without_memory_evidence"

    return {
        "schema_version": "agent-run-failure-attribution/v0.1",
        "outcome_class": outcome_class,
        "task_failed": task_failed,
        "runtime_error": runtime_error,
        "memory_contributed": memory_contributed,
        "corruption_origin": origin,
        "causal_claim_supported": False,
        "demonstrated_tool_competence": demonstrated_tool_competence,
        "action_count": action_count,
        "valid_action_count": valid_action_count,
        "action_compliance_rate": round(compliance_rate, 4),
        "successful_tool_names": sorted(successful_tool_names),
        "memory_signal_types": memory_signal_types,
        "corrupted_decision_belief_count": corrupted_belief_count,
        "first_memory_signal_sequence": memory_signal_sequence,
        "first_induced_pressure_sequence": first_induced_pressure_sequence,
        "stale_finish_pattern": stale_finish_pattern,
        "interpretation": (
            "Memory-contributed requires demonstrated read/edit/test competence "
            "plus decision-linked corrupted evidence or a finish that relied on "
            "test evidence invalidated by a later mutation. It does not prove "
            "memory was the sole cause of task failure."
        ),
    }


def _stale_finish_pattern(trace_events: list[dict]) -> dict[str, Any]:
    accepted_finishes = [
        event
        for event in trace_events
        if event.get("event_type") == "completion_claim"
        and event.get("tool_name") == "finish"
        and event.get("proposal_status") == "accepted"
    ]
    if not accepted_finishes:
        return {
            "detected": False,
            "test_event_id": None,
            "invalidating_event_id": None,
            "finish_event_id": None,
            "finish_sequence": None,
        }
    finish = accepted_finishes[-1]
    finish_sequence = int(finish.get("sequence_number", 0))
    successful_tests = [
        event
        for event in trace_events
        if event.get("tool_name") in TEST_TOOLS
        and event.get("status") == "success"
        and int(event.get("sequence_number", 0)) < finish_sequence
    ]
    if not successful_tests:
        return {
            "detected": False,
            "test_event_id": None,
            "invalidating_event_id": None,
            "finish_event_id": finish.get("event_id"),
            "finish_sequence": finish_sequence,
        }
    latest_test = max(
        successful_tests,
        key=lambda event: int(event.get("sequence_number", 0)),
    )
    test_sequence = int(latest_test.get("sequence_number", 0))
    later_mutations = [
        event
        for event in trace_events
        if event.get("tool_name") in MUTATION_TOOLS
        and event.get("status") == "success"
        and test_sequence < int(event.get("sequence_number", 0))
        < finish_sequence
    ]
    invalidator = later_mutations[-1] if later_mutations else {}
    return {
        "detected": bool(invalidator),
        "test_event_id": latest_test.get("event_id"),
        "invalidating_event_id": invalidator.get("event_id"),
        "finish_event_id": finish.get("event_id"),
        "finish_sequence": finish_sequence,
    }


def _corruption_origin(
    *,
    condition: str,
    memory_contributed: bool,
    memory_signal_sequence: int | None,
    first_induced_pressure_sequence: int | None,
) -> str:
    if not memory_contributed:
        return "not_observed"
    if (
        condition in INDUCED_CORRUPTION_CONDITIONS
        and first_induced_pressure_sequence is not None
        and memory_signal_sequence is not None
        and memory_signal_sequence >= first_induced_pressure_sequence
    ):
        return "induced_associated"
    return "natural_or_preexisting"


def _minimum_sequence(*values: int | None) -> int | None:
    present = [value for value in values if value is not None]
    return min(present) if present else None
