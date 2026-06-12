"""Revision-aware operational memory for coding-agent evidence."""

from __future__ import annotations

import copy
import hashlib
import json
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
    reconciled_memory_ids = []

    changed_paths, changed_symbols = _event_changes(event)
    if changed_paths:
        for item in items:
            if item.get("stale") or not _depends_on_change(
                item,
                changed_paths,
                changed_symbols,
            ):
                continue
            _invalidate_item(
                item,
                event_id=event_id,
                reason=(
                    "dependent repository state changed: "
                    + ", ".join(sorted(changed_paths))
                ),
            )

    if tool_name in {"run_tests", "run_full_tests", "run_targeted_tests"}:
        for item in items:
            if (
                item.get("tool_name")
                not in {"run_tests", "run_full_tests", "run_targeted_tests"}
                or not _test_scopes_overlap(item, event)
            ):
                continue
            previous_status = item.get("status")
            current_status = event.get("status")
            _reconcile_item(
                item,
                event_id=event_id,
                contradictory=previous_status != current_status,
            )
            reconciled_memory_ids.append(str(item["memory_id"]))

    memory_item = build_memory_item(event, label=label)
    memory_item["reconciles_memory_ids"] = reconciled_memory_ids
    items.append(memory_item)
    return items


def build_memory_item(event: dict, *, label: str) -> dict:
    """Create a complete operational-memory record from a trace event."""

    event_id = str(event["event_id"])
    tool_name = event.get("tool_name")
    status = str(event.get("status", "observed"))
    path = event.get("path")
    dependency_graph = _dependency_graph(event)
    dependencies = list(dependency_graph["files"])
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
        "dependency_graph": dependency_graph,
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
        "reconciliation_status": "current",
        "reconciled_by_event_ids": [],
        "reconciles_memory_ids": [],
        "event_type": event.get("event_type"),
        "tool_name": tool_name,
        "status": status,
    }
    for key in [
        "path",
        "returncode",
        "command",
        "covered_files",
        "covered_symbols",
        "coverage_mode",
        "files",
        "paths",
        "changed_symbols",
        "content",
        "structured_output",
        "test_targets",
        "test_count",
        "base_commit",
        "repository_hash",
        "observed_at",
        "requirement_snapshot",
        "evaluator_failure",
    ]:
        if event.get(key) is not None:
            item[key] = copy.deepcopy(event[key])
    if (
        path
        and path not in dependencies
        and tool_name in {"read_file", "write_file"}
    ):
        item["invalidation_dependencies"].append(str(path))
        item["dependency_graph"]["files"].append(str(path))
    return item


def summarize_operational_memory(memory_items: list[dict]) -> dict:
    """Return auditable counts for the final operational-memory state."""

    stale = [item for item in memory_items if item.get("stale")]
    unresolved_contradictions = [
        item
        for item in memory_items
        if item.get("support_status") == "contradicted"
    ]
    reconciled = [
        item
        for item in memory_items
        if item.get("reconciliation_status") == "resolved"
    ]
    historical_contradictions = [
        item for item in memory_items if item.get("historical_contradiction")
    ]
    current = [item for item in memory_items if not item.get("stale")]
    return {
        "schema_version": "agent-operational-memory-summary/v0.2",
        "item_count": len(memory_items),
        "current_item_count": len(current),
        "stale_item_count": len(stale),
        "contradicted_item_count": len(unresolved_contradictions),
        "historical_contradiction_count": len(historical_contradictions),
        "reconciled_item_count": len(reconciled),
        "mean_confidence": (
            round(mean(float(item["confidence"]) for item in memory_items), 4)
            if memory_items
            else None
        ),
        "stale_memory_ids": [item["memory_id"] for item in stale],
        "contradicted_memory_ids": [
            item["memory_id"] for item in unresolved_contradictions
        ],
        "reconciled_memory_ids": [
            item["memory_id"] for item in reconciled
        ],
    }


def create_operational_memory_checkpoint(
    memory_items: list[dict],
    *,
    workspace_revision: int,
    last_event_id: str,
) -> dict:
    """Serialize canonical memory with an integrity hash for run resumption."""

    payload = {
        "schema_version": "agent-operational-memory-checkpoint/v0.1",
        "workspace_revision": int(workspace_revision),
        "last_event_id": str(last_event_id),
        "memory_items": copy.deepcopy(memory_items),
    }
    payload["sha256"] = _checkpoint_sha256(payload)
    return payload


def restore_operational_memory_checkpoint(checkpoint: dict) -> list[dict]:
    """Validate and restore a checkpoint without sharing mutable state."""

    if checkpoint.get("schema_version") != (
        "agent-operational-memory-checkpoint/v0.1"
    ):
        raise ValueError("Unsupported operational-memory checkpoint schema")
    expected = str(checkpoint.get("sha256", ""))
    if not expected or expected != _checkpoint_sha256(checkpoint):
        raise ValueError("Operational-memory checkpoint integrity check failed")
    memory_items = checkpoint.get("memory_items")
    if not isinstance(memory_items, list):
        raise ValueError("Operational-memory checkpoint has no memory list")
    return copy.deepcopy(memory_items)


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
        if item.get("tool_name")
        in {"run_tests", "run_full_tests", "run_targeted_tests"}
        and item.get("stale")
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
        if item.get("tool_name") == "run_targeted_tests" and item.get(
            "test_targets"
        ):
            return {
                "action": "run_targeted_tests",
                "targets": list(item["test_targets"]),
            }
        if item.get("tool_name") == "run_full_tests":
            return {"action": "run_full_tests"}
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


def _reconcile_item(
    item: dict,
    *,
    event_id: str,
    contradictory: bool,
) -> None:
    item.setdefault("reconciled_by_event_ids", [])
    item.setdefault("invalidated_by_event_ids", [])
    item.setdefault("invalidation_reasons", [])
    item.setdefault("contradictions", [])
    item["stale"] = True
    item["support_status"] = "superseded"
    item["reconciliation_status"] = "resolved"
    if event_id not in item["reconciled_by_event_ids"]:
        item["reconciled_by_event_ids"].append(event_id)
    if event_id not in item["invalidated_by_event_ids"]:
        item["invalidated_by_event_ids"].append(event_id)
    reason = "superseded by a newer observation of the same evidence scope"
    if reason not in item["invalidation_reasons"]:
        item["invalidation_reasons"].append(reason)
    if contradictory:
        item["historical_contradiction"] = True
        if event_id not in item["contradictions"]:
            item["contradictions"].append(event_id)


def _event_changes(event: dict) -> tuple[set[str], dict[str, set[str]]]:
    tool_name = event.get("tool_name")
    if tool_name not in {"write_file", "apply_patch"}:
        return set(), {}
    paths = {
        str(path)
        for path in (
            event.get("paths")
            or ([event["path"]] if event.get("path") else [])
        )
    }
    changed_symbols = {
        str(path): {str(symbol) for symbol in symbols}
        for path, symbols in dict(
            event.get("changed_symbols") or {}
        ).items()
    }
    return paths, changed_symbols


def _depends_on_change(
    item: dict,
    changed_paths: set[str],
    changed_symbols: dict[str, set[str]],
) -> bool:
    graph = item.get("dependency_graph") or {
        "files": item.get("invalidation_dependencies", [])
    }
    file_dependencies = {str(value) for value in graph.get("files", [])}
    if "*" in file_dependencies:
        return True
    symbol_dependencies = {
        str(value) for value in graph.get("symbols", [])
    }
    for path in changed_paths:
        if path not in file_dependencies:
            continue
        item_symbols = {
            value.split(":", 1)[1]
            for value in symbol_dependencies
            if value.startswith(f"{path}:")
        }
        event_symbols = changed_symbols.get(path, set())
        if item_symbols and event_symbols:
            if "*" in event_symbols or item_symbols & event_symbols:
                return True
            continue
        return True
    return False


def _dependency_graph(event: dict) -> dict[str, list[str]]:
    tool_name = event.get("tool_name")
    files = set()
    symbols = set()
    tests = set()
    commands = set()
    requirements = set()

    if event.get("path"):
        files.add(str(event["path"]))
    files.update(str(path) for path in event.get("paths", []))
    files.update(str(path) for path in event.get("covered_files", []))
    symbols.update(str(symbol) for symbol in event.get("covered_symbols", []))
    if tool_name == "inspect_dependency" and event.get("symbol"):
        symbols.add(f"{event.get('path')}:{event['symbol']}")
    structured = event.get("structured_output") or {}
    if tool_name == "search_code":
        files.update(
            str(match["path"])
            for match in structured.get("matches", [])
            if match.get("path")
        )
    if tool_name in {"git_status", "git_diff"}:
        files.add("*")
    test_targets = event.get("test_targets", [])
    if tool_name in {"run_tests", "run_full_tests"} and not test_targets:
        tests.add("*")
    else:
        tests.update(str(target) for target in test_targets)
    if event.get("command"):
        commands.add(str(event["command"]))
    if event.get("requirement_id"):
        requirements.add(str(event["requirement_id"]))
    if event.get("event_type") == "user_requirement_update":
        requirements.add(str(event.get("requirement_id") or "active_task"))
    requirement_snapshot = event.get("requirement_snapshot") or {}
    requirements.update(
        str(item.get("subtask_id"))
        for item in requirement_snapshot.get("required_subtasks", [])
        if item.get("subtask_id")
    )
    return {
        "files": sorted(files),
        "symbols": sorted(symbols),
        "tests": sorted(tests),
        "commands": sorted(commands),
        "requirements": sorted(requirements),
    }


def _test_scopes_overlap(item: dict, event: dict) -> bool:
    previous = set((item.get("dependency_graph") or {}).get("tests", []))
    if not previous:
        previous = {
            str(target) for target in item.get("test_targets", [])
        }
        if (
            item.get("tool_name") in {"run_tests", "run_full_tests"}
            and not previous
        ):
            previous.add("*")
    current = set(_dependency_graph(event)["tests"])
    return "*" in previous or "*" in current or previous == current


def _checkpoint_sha256(checkpoint: dict) -> str:
    content = {
        key: value
        for key, value in checkpoint.items()
        if key != "sha256"
    }
    return hashlib.sha256(
        json.dumps(
            content,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
        ).encode("utf-8")
    ).hexdigest()


def _claim_for_event(event: dict, label: str) -> str:
    tool_name = event.get("tool_name")
    revision = int(event.get("workspace_revision", 0))
    if tool_name in {"run_tests", "run_full_tests", "run_targeted_tests"}:
        return (
            f"Visible tests {event.get('status')} at repository revision "
            f"{revision} using {event.get('command', 'the recorded command')}."
        )
    if tool_name == "read_file":
        return f"Observed {event.get('path')} at repository revision {revision}."
    if tool_name == "write_file":
        return f"Wrote {event.get('path')} at repository revision {revision}."
    if tool_name == "apply_patch":
        return (
            "Applied a bounded patch to "
            f"{', '.join(event.get('paths', []))} at repository revision "
            f"{revision}."
        )
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
