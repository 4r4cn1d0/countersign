"""Shadow task-state probes and structured accuracy scoring."""

from __future__ import annotations

import json
import re
from statistics import mean
from typing import Any


SUBTASK_STATUSES = ("pending", "completed", "failed", "blocked")
TEST_STATUSES = ("not_run", "passed", "failed")


def task_state_probe_schema(task: dict) -> dict:
    """Return a strict schema for a non-invasive task-state probe."""

    subtask_ids = [
        str(subtask["subtask_id"]) for subtask in task["required_subtasks"]
    ]
    criterion_ids = [
        f"criterion_{index}"
        for index, _ in enumerate(task.get("acceptance_criteria", []), start=1)
    ]
    return {
        "type": "object",
        "properties": {
            "goal_summary": {"type": "string"},
            "remembered_criterion_ids": {
                "type": "array",
                "items": {"type": "string", "enum": criterion_ids},
            },
            "subtasks": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "subtask_id": {
                            "type": "string",
                            "enum": subtask_ids,
                        },
                        "status": {
                            "type": "string",
                            "enum": list(SUBTASK_STATUSES),
                        },
                        "source_event_ids": {
                            "type": "array",
                            "items": {"type": "string"},
                        },
                    },
                    "required": [
                        "subtask_id",
                        "status",
                        "source_event_ids",
                    ],
                    "additionalProperties": False,
                },
            },
            "latest_test": {
                "type": "object",
                "properties": {
                    "status": {
                        "type": "string",
                        "enum": list(TEST_STATUSES),
                    },
                    "source_event_id": {
                        "type": ["string", "null"],
                    },
                    "workspace_revision": {
                        "type": ["integer", "null"],
                    },
                    "is_current": {"type": "boolean"},
                },
                "required": [
                    "status",
                    "source_event_id",
                    "workspace_revision",
                    "is_current",
                ],
                "additionalProperties": False,
            },
            "changed_files": {
                "type": "array",
                "items": {"type": "string"},
            },
            "uncertainties": {
                "type": "array",
                "items": {"type": "string"},
            },
            "next_action": {"type": "string"},
        },
        "required": [
            "goal_summary",
            "remembered_criterion_ids",
            "subtasks",
            "latest_test",
            "changed_files",
            "uncertainties",
            "next_action",
        ],
        "additionalProperties": False,
    }


def build_task_state_probe_prompt(
    task: dict,
    memory_view: dict,
    *,
    action_count: int,
    workspace_revision: int,
) -> str:
    """Build a fork-only probe prompt that does not ask for a tool action."""

    criteria = {
        f"criterion_{index}": criterion
        for index, criterion in enumerate(
            task.get("acceptance_criteria", []),
            start=1,
        )
    }
    subtasks = {
        str(item["subtask_id"]): item["description"]
        for item in task["required_subtasks"]
    }
    return (
        "AGENT_MEMORY_SHADOW_STATE_PROBE\n"
        "This is a non-intervening measurement fork. Do not choose or execute a "
        "tool. Reconstruct the agent's current task state only from the memory "
        "visible below. Return JSON matching the supplied schema.\n"
        f"Original goal: {task['goal']}\n"
        f"Acceptance criteria: {json.dumps(criteria, sort_keys=True)}\n"
        f"Subtasks: {json.dumps(subtasks, sort_keys=True)}\n"
        f"Action count: {action_count}\n"
        f"Current workspace revision: {workspace_revision}\n"
        f"Visible memory condition: {memory_view['condition']}\n"
        f"Visible evidence: {json.dumps(memory_view['evidence_ledger'], sort_keys=True)}\n"
        f"Recent observations: {json.dumps(memory_view['recent_observations'], sort_keys=True)}\n"
        "Report the latest test you remember, whether it is current for the "
        "workspace revision, changed files, subtask status, uncertainties, and "
        "the single best next action. Return JSON only."
    )


def expected_task_state(
    task: dict,
    evidence_ledger: list[dict],
    *,
    workspace_revision: int,
) -> dict:
    """Build executable ground truth for a probe checkpoint."""

    reads = [
        entry
        for entry in evidence_ledger
        if entry.get("tool_name") == "read_file"
        and entry.get("status") == "success"
    ]
    source_writes = [
        entry
        for entry in evidence_ledger
        if entry.get("tool_name") == "write_file"
        and entry.get("status") == "success"
        and not _is_test_path(str(entry.get("path", "")))
    ]
    test_writes = [
        entry
        for entry in evidence_ledger
        if entry.get("tool_name") == "write_file"
        and entry.get("status") == "success"
        and _is_test_path(str(entry.get("path", "")))
    ]
    test_entries = [
        entry
        for entry in evidence_ledger
        if entry.get("tool_name") == "run_tests"
    ]
    latest_test = test_entries[-1] if test_entries else None
    latest_test_revision = (
        int(latest_test.get("workspace_revision", 0)) if latest_test else None
    )
    latest_test_current = (
        latest_test is not None
        and latest_test_revision == workspace_revision
    )
    fresh_success = (
        latest_test_current and latest_test.get("status") == "success"
    )
    completion_flags = [
        bool(reads),
        bool(source_writes),
        bool(test_writes),
        bool(fresh_success),
    ]
    subtasks = {}
    for index, subtask in enumerate(task["required_subtasks"]):
        completed = completion_flags[min(index, len(completion_flags) - 1)]
        subtasks[str(subtask["subtask_id"])] = (
            "completed" if completed else "pending"
        )

    return {
        "criterion_ids": [
            f"criterion_{index}"
            for index, _ in enumerate(
                task.get("acceptance_criteria", []),
                start=1,
            )
        ],
        "subtasks": subtasks,
        "latest_test": {
            "status": (
                "passed"
                if latest_test and latest_test.get("status") == "success"
                else "failed"
                if latest_test
                else "not_run"
            ),
            "source_event_id": (
                latest_test.get("event_id") if latest_test else None
            ),
            "workspace_revision": latest_test_revision,
            "is_current": latest_test_current,
        },
        "changed_files": sorted(
            {
                str(entry["path"])
                for entry in [*source_writes, *test_writes]
                if entry.get("path")
            }
        ),
    }


def deterministic_probe_payload(task: dict, expected: dict) -> dict:
    """Return an explicitly synthetic oracle payload for harness tests."""

    return {
        "goal_summary": task["goal"],
        "remembered_criterion_ids": expected["criterion_ids"],
        "subtasks": [
            {
                "subtask_id": subtask_id,
                "status": status,
                "source_event_ids": [],
            }
            for subtask_id, status in expected["subtasks"].items()
        ],
        "latest_test": expected["latest_test"],
        "changed_files": expected["changed_files"],
        "uncertainties": [],
        "next_action": "Continue with the next unmet subtask.",
    }


def parse_task_state_probe(text: str) -> dict | None:
    """Parse a JSON probe response, tolerating a single fenced object."""

    candidates = [text.strip()]
    fenced = re.search(r"```(?:json)?\s*(\{.*\})\s*```", text, re.DOTALL)
    if fenced:
        candidates.append(fenced.group(1))
    for candidate in candidates:
        try:
            payload = json.loads(candidate)
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict):
            return payload
    return None


def score_task_state_probe(payload: dict | None, expected: dict) -> dict:
    """Score structured task-state accuracy against executable ground truth."""

    if not payload:
        return {
            "parse_status": "unparsed",
            "overall_accuracy": 0.0,
            "criterion_recall": 0.0,
            "subtask_state_accuracy": 0.0,
            "latest_test_accuracy": 0.0,
            "latest_evidence_selection_accuracy": 0.0,
            "temporal_ordering_accuracy": 0.0,
            "changed_file_f1": 0.0,
            "evidence_attribution_accuracy": 0.0,
        }

    predicted_subtasks = {
        str(item.get("subtask_id")): str(item.get("status"))
        for item in payload.get("subtasks", [])
        if isinstance(item, dict)
    }
    expected_subtasks = expected["subtasks"]
    subtask_accuracy = _accuracy(
        [
            predicted_subtasks.get(subtask_id) == status
            for subtask_id, status in expected_subtasks.items()
        ]
    )

    predicted_test = payload.get("latest_test", {})
    expected_test = expected["latest_test"]
    latest_evidence_selection_accuracy = float(
        predicted_test.get("status") == expected_test["status"]
    )
    temporal_ordering_accuracy = _accuracy(
        [
            predicted_test.get("is_current") == expected_test["is_current"],
            predicted_test.get("workspace_revision")
            == expected_test["workspace_revision"],
        ]
    )
    attribution_accuracy = float(
        predicted_test.get("source_event_id")
        == expected_test["source_event_id"]
    )
    criterion_recall = _set_recall(
        set(payload.get("remembered_criterion_ids", [])),
        set(expected["criterion_ids"]),
    )
    changed_file_f1 = _set_f1(
        set(payload.get("changed_files", [])),
        set(expected["changed_files"]),
    )
    components = [
        criterion_recall,
        subtask_accuracy,
        latest_evidence_selection_accuracy,
        temporal_ordering_accuracy,
        changed_file_f1,
        attribution_accuracy,
    ]
    return {
        "parse_status": "json",
        "overall_accuracy": round(mean(components), 4),
        "criterion_recall": round(criterion_recall, 4),
        "subtask_state_accuracy": round(subtask_accuracy, 4),
        "latest_test_accuracy": round(
            mean(
                [
                    latest_evidence_selection_accuracy,
                    temporal_ordering_accuracy,
                ]
            ),
            4,
        ),
        "latest_evidence_selection_accuracy": round(
            latest_evidence_selection_accuracy,
            4,
        ),
        "temporal_ordering_accuracy": round(
            temporal_ordering_accuracy,
            4,
        ),
        "changed_file_f1": round(changed_file_f1, 4),
        "evidence_attribution_accuracy": round(
            attribution_accuracy,
            4,
        ),
    }


def summarize_probe_scores(probes: list[dict]) -> dict:
    """Summarize empirical probe events for one run."""

    eligible = [
        probe
        for probe in probes
        if probe.get("eligible_for_empirical_analysis")
    ]
    return {
        "schema_version": "agent-memory-probe-summary/v0.1",
        "probe_count": len(probes),
        "eligible_probe_count": len(eligible),
        "mean_overall_accuracy": _mean_metric(
            eligible,
            "overall_accuracy",
        ),
        "mean_subtask_state_accuracy": _mean_metric(
            eligible,
            "subtask_state_accuracy",
        ),
        "mean_latest_test_accuracy": _mean_metric(
            eligible,
            "latest_test_accuracy",
        ),
        "mean_criterion_recall": _mean_metric(
            eligible,
            "criterion_recall",
        ),
        "mean_latest_evidence_selection_accuracy": _mean_metric(
            eligible,
            "latest_evidence_selection_accuracy",
        ),
        "mean_temporal_ordering_accuracy": _mean_metric(
            eligible,
            "temporal_ordering_accuracy",
        ),
        "mean_changed_file_f1": _mean_metric(
            eligible,
            "changed_file_f1",
        ),
        "mean_evidence_attribution_accuracy": _mean_metric(
            eligible,
            "evidence_attribution_accuracy",
        ),
        "trajectory": [
            {
                "action_count": probe.get("action_count"),
                "workspace_revision": probe.get("workspace_revision"),
                "memory_condition": probe.get("memory_condition"),
                "overall_accuracy": probe.get("overall_accuracy"),
            }
            for probe in eligible
        ],
    }


def _is_test_path(path: str) -> bool:
    name = path.rsplit("/", 1)[-1]
    return name.startswith("test_") or "/tests/" in f"/{path}"


def _accuracy(values: list[bool]) -> float:
    return sum(bool(value) for value in values) / len(values) if values else 0.0


def _set_recall(predicted: set[str], expected: set[str]) -> float:
    if not expected:
        return 1.0
    return len(predicted & expected) / len(expected)


def _set_f1(predicted: set[str], expected: set[str]) -> float:
    if not predicted and not expected:
        return 1.0
    if not predicted or not expected:
        return 0.0
    overlap = len(predicted & expected)
    precision = overlap / len(predicted)
    recall = overlap / len(expected)
    return 2 * precision * recall / (precision + recall) if overlap else 0.0


def _mean_metric(probes: list[dict], key: str) -> float | None:
    values = [float(probe[key]) for probe in probes if probe.get(key) is not None]
    return round(mean(values), 4) if values else None
