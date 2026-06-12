"""Revision-aware operational memory for coding-agent evidence."""

from __future__ import annotations

import copy
from statistics import mean
from typing import Any


def apply_event_to_memory(
    memory_items: list[dict],
    event: dict,
    *,
    label: str,
) -> list[dict]:
    """Reconcile prior beliefs against an event and append its memory item."""

    items = copy.deepcopy(memory_items)
    event_id = str(event["event_id"])
    tool_name = event.get("tool_name")

    if tool_name == "write_file":
        changed_path = str(event.get("path", ""))
        for item in items:
            if item.get("stale") or not _depends_on_path(item, changed_path):
                continue
            _invalidate_item(
                item,
                event_id=event_id,
                reason=f"dependency changed: {changed_path}",
            )

    if tool_name == "run_tests":
        for item in items:
            if item.get("tool_name") != "run_tests" or item.get("stale"):
                continue
            previous_status = item.get("status")
            current_status = event.get("status")
            _invalidate_item(
                item,
                event_id=event_id,
                reason="superseded by a newer test result",
            )
            if previous_status != current_status:
                item["support_status"] = "contradicted"
                item["contradictions"].append(event_id)

    items.append(build_memory_item(event, label=label))
    return items


def build_memory_item(event: dict, *, label: str) -> dict:
    """Create a complete operational-memory record from a trace event."""

    event_id = str(event["event_id"])
    tool_name = event.get("tool_name")
    status = str(event.get("status", "observed"))
    path = event.get("path")
    dependencies = _invalidation_dependencies(event)
    repository_revision = int(event.get("workspace_revision", 0))
    item = {
        "memory_id": f"{event_id}:memory",
        "evidence_id": f"{event_id}:evidence",
        "event_id": event_id,
        "claim": _claim_for_event(event, label),
        "label": label,
        "source_event_ids": [event_id],
        "source_type": event.get("source_type", "unknown"),
        "observation_time": int(event.get("sequence_number", 0)),
        "sequence_number": int(event.get("sequence_number", 0)),
        "repository_revision": repository_revision,
        "workspace_revision": repository_revision,
        "confidence": _confidence_for_event(event),
        "support_status": "supported",
        "invalidation_dependencies": dependencies,
        "last_verification_time": (
            int(event.get("sequence_number", 0))
            if event.get("source_type") in {
                "ground_truth",
                "tool_output",
                "file_state",
                "user_instruction",
            }
            else None
        ),
        "contradictions": [],
        "stale": False,
        "invalidation_reasons": [],
        "invalidated_by_event_ids": [],
        "event_type": event.get("event_type"),
        "tool_name": tool_name,
        "status": status,
    }
    for key in [
        "path",
        "returncode",
        "command",
        "covered_files",
        "files",
        "requirement_snapshot",
        "evaluator_failure",
    ]:
        if event.get(key) is not None:
            item[key] = copy.deepcopy(event[key])
    if path and path not in dependencies and tool_name in {"read_file", "write_file"}:
        item["invalidation_dependencies"].append(str(path))
    return item


def summarize_operational_memory(memory_items: list[dict]) -> dict:
    """Return auditable counts for the final operational-memory state."""

    stale = [item for item in memory_items if item.get("stale")]
    contradicted = [
        item
        for item in memory_items
        if item.get("support_status") == "contradicted"
    ]
    current = [item for item in memory_items if not item.get("stale")]
    return {
        "schema_version": "agent-operational-memory-summary/v0.1",
        "item_count": len(memory_items),
        "current_item_count": len(current),
        "stale_item_count": len(stale),
        "contradicted_item_count": len(contradicted),
        "mean_confidence": (
            round(mean(float(item["confidence"]) for item in memory_items), 4)
            if memory_items
            else None
        ),
        "stale_memory_ids": [item["memory_id"] for item in stale],
        "contradicted_memory_ids": [
            item["memory_id"] for item in contradicted
        ],
    }


def plan_memory_repair(
    reasons: list[str],
    memory_items: list[dict],
    *,
    recommended_actions: list[str] | None = None,
) -> dict:
    """Choose the smallest executable repair for a blocked finish claim."""

    normalized_reasons = {str(reason).lower() for reason in reasons}
    normalized_recommendations = {
        str(action).lower() for action in (recommended_actions or [])
    }
    stale_tests = [
        item
        for item in memory_items
        if item.get("tool_name") == "run_tests" and item.get("stale")
    ]
    contradicted = [
        item
        for item in memory_items
        if item.get("support_status") == "contradicted"
    ]
    lost_provenance = any(
        "lost provenance" in reason for reason in normalized_reasons
    )
    missing_requirements = any(
        "missing requirement" in reason
        or "acceptance criteria" in reason
        for reason in normalized_reasons | normalized_recommendations
    )
    implementation_failure = any(
        "independent task evaluator failed" in reason
        or "missing implementation-change evidence" in reason
        for reason in normalized_reasons
    )
    contradicted_claim = any(
        "contradicted" in reason for reason in normalized_reasons
    )
    missing_or_stale_tests = bool(stale_tests) or any(
        "stale evidence" in reason
        or "missing successful test evidence" in reason
        for reason in normalized_reasons
    )
    detections = []
    if stale_tests:
        detections.append("stale test evidence")
    if contradicted:
        detections.append("contradicted operational memory")
    if lost_provenance:
        detections.append("lost provenance")
    if missing_requirements:
        detections.append("missing or forgotten requirements")
    if implementation_failure:
        detections.append("implementation or evaluator failure")
    if any(
        "missing successful test evidence" in reason
        for reason in normalized_reasons
    ):
        detections.append("missing current test evidence")

    repair_type = None
    action = None
    targets: list[str] = []
    rationale = ""

    if implementation_failure:
        repair_type = "implementation_evaluator_failure"
        action = {"action": "refresh_requirements"}
        rationale = (
            "Refresh the authoritative goal, acceptance criteria, active requirement "
            "updates, and evaluator failure before returning control to the model."
        )
    elif missing_requirements:
        repair_type = "missing_requirements"
        action = {"action": "refresh_requirements"}
        rationale = (
            "Restore the authoritative task requirements before the model replans."
        )
    elif contradicted_claim or contradicted:
        repair_type = "contradictory_evidence"
        targets = [item["memory_id"] for item in contradicted]
        action = _evidence_refresh_action(contradicted)
        rationale = (
            "Refresh the evidence source whose newer observation contradicted the "
            "completion belief."
        )
    elif lost_provenance:
        repair_type = "lost_provenance"
        provenance_targets = [
            item
            for item in reversed(memory_items)
            if item.get("path") and not item.get("stale")
        ]
        targets = [
            item["memory_id"] for item in provenance_targets[:1]
        ]
        action = _evidence_refresh_action(provenance_targets)
        rationale = (
            "Re-observe the latest relevant repository source and attach fresh "
            "provenance before another completion claim."
        )
    elif missing_or_stale_tests:
        repair_type = "stale_test_evidence"
        action = {"action": "run_tests"}
        targets = [item["memory_id"] for item in stale_tests]
        rationale = "Refresh test evidence at the current repository revision."

    if action:
        return {
            "schema_version": "agent-memory-repair-plan/v0.2",
            "detected": True,
            "detections": sorted(set(detections)),
            "repair_type": repair_type,
            "repairable": True,
            "action": action,
            "target_memory_ids": targets,
            "rationale": rationale,
            "success_criterion": _repair_success_criterion(repair_type),
        }
    return {
        "schema_version": "agent-memory-repair-plan/v0.2",
        "detected": bool(reasons),
        "detections": sorted(set(detections or reasons)),
        "repair_type": "unclassified",
        "repairable": False,
        "action": None,
        "target_memory_ids": [],
        "success_criterion": None,
        "rationale": (
            "No bounded evidence-refresh action can repair the implementation; "
            "return the precise failure to the model for replanning."
        ),
    }


def _evidence_refresh_action(memory_items: list[dict]) -> dict:
    for item in memory_items:
        if item.get("tool_name") == "run_tests":
            return {"action": "run_tests"}
        if item.get("path"):
            return {"action": "read_file", "path": str(item["path"])}
    return {"action": "list_files"}


def _repair_success_criterion(repair_type: str | None) -> str:
    if repair_type == "stale_test_evidence":
        return "A new test result is recorded at the current repository revision."
    if repair_type == "lost_provenance":
        return "A current repository observation is stored with an exact event ID."
    if repair_type == "contradictory_evidence":
        return "The contradicted evidence source is re-observed and superseded."
    if repair_type in {
        "missing_requirements",
        "implementation_evaluator_failure",
    }:
        return (
            "The authoritative task snapshot is restored and the model performs a "
            "new planning step before any completion claim."
        )
    return "A current evidence item is stored before replanning."


def _invalidate_item(item: dict, *, event_id: str, reason: str) -> None:
    item["stale"] = True
    if item.get("support_status") != "contradicted":
        item["support_status"] = "stale"
    if event_id not in item["invalidated_by_event_ids"]:
        item["invalidated_by_event_ids"].append(event_id)
    if reason not in item["invalidation_reasons"]:
        item["invalidation_reasons"].append(reason)


def _depends_on_path(item: dict, path: str) -> bool:
    dependencies = {
        str(value) for value in item.get("invalidation_dependencies", [])
    }
    return "*" in dependencies or path in dependencies


def _invalidation_dependencies(event: dict) -> list[str]:
    tool_name = event.get("tool_name")
    if tool_name == "run_tests":
        covered = [str(path) for path in event.get("covered_files", [])]
        return covered or ["*"]
    if tool_name in {"read_file", "write_file"} and event.get("path"):
        return [str(event["path"])]
    return []


def _claim_for_event(event: dict, label: str) -> str:
    tool_name = event.get("tool_name")
    revision = int(event.get("workspace_revision", 0))
    if tool_name == "run_tests":
        return (
            f"Visible tests {event.get('status')} at repository revision "
            f"{revision} using {event.get('command', 'the recorded command')}."
        )
    if tool_name == "read_file":
        return f"Observed {event.get('path')} at repository revision {revision}."
    if tool_name == "write_file":
        return f"Wrote {event.get('path')} at repository revision {revision}."
    if tool_name == "list_files":
        return f"Observed the workspace file list at repository revision {revision}."
    if tool_name == "setup_workspace":
        return f"Initialized the workspace at repository revision {revision}."
    if tool_name == "refresh_requirements":
        return (
            "Restored authoritative requirements and evaluator feedback at "
            f"repository revision {revision}."
        )
    return str(event.get("content") or label)


def _confidence_for_event(event: dict) -> float:
    source_type = event.get("source_type")
    if source_type in {
        "ground_truth",
        "tool_output",
        "file_state",
        "user_instruction",
    }:
        return 1.0
    if source_type == "independent_evaluator":
        return 1.0
    if source_type == "agent_summary":
        return 0.65
    return 0.75
