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
        "repository_revision": int(event.get("workspace_revision", 0)),
        "confidence": _confidence_for_event(event),
        "support_status": "supported",
        "invalidation_dependencies": dependencies,
        "last_verification_time": (
            int(event.get("sequence_number", 0))
            if event.get("source_type") in {
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
) -> dict:
    """Choose the smallest executable repair for a blocked finish claim."""

    normalized_reasons = {str(reason).lower() for reason in reasons}
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
    if any("lost provenance" in reason for reason in normalized_reasons):
        detections.append("lost provenance")
    if any(
        "missing successful test evidence" in reason
        for reason in normalized_reasons
    ):
        detections.append("missing current test evidence")

    if missing_or_stale_tests:
        return {
            "schema_version": "agent-memory-repair-plan/v0.1",
            "detected": True,
            "detections": sorted(set(detections)),
            "repairable": True,
            "action": {"action": "run_tests"},
            "target_memory_ids": [
                item["memory_id"] for item in stale_tests
            ],
            "rationale": (
                "Refresh test evidence at the current repository revision."
            ),
        }
    return {
        "schema_version": "agent-memory-repair-plan/v0.1",
        "detected": bool(reasons),
        "detections": sorted(set(detections or reasons)),
        "repairable": False,
        "action": None,
        "target_memory_ids": [],
        "rationale": (
            "No bounded evidence-refresh action can repair the implementation; "
            "return the precise failure to the model for replanning."
        ),
    }


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
    return str(event.get("content") or label)


def _confidence_for_event(event: dict) -> float:
    source_type = event.get("source_type")
    if source_type in {"tool_output", "file_state", "user_instruction"}:
        return 1.0
    if source_type == "independent_evaluator":
        return 1.0
    if source_type == "agent_summary":
        return 0.65
    return 0.75
