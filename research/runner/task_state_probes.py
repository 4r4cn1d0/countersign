"""Shadow task-state probes and structured accuracy scoring."""

from __future__ import annotations

import json
import re
from statistics import mean
from typing import Any


SUBTASK_STATUSES = ("pending", "completed", "failed", "blocked")
TEST_STATUSES = ("not_run", "passed", "failed")
ATTEMPT_OUTCOMES = ("failed", "blocked")
REPOSITORY_STATES = ("observed", "modified")
NEXT_ACTIONS = (
    "list_files",
    "read_file",
    "write_file",
    "run_tests",
    "finish",
    "none",
)


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
            "unsuccessful_attempts": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "source_event_id": {"type": "string"},
                        "action": {"type": "string"},
                        "outcome": {
                            "type": "string",
                            "enum": list(ATTEMPT_OUTCOMES),
                        },
                        "reason": {"type": "string"},
                    },
                    "required": [
                        "source_event_id",
                        "action",
                        "outcome",
                        "reason",
                    ],
                    "additionalProperties": False,
                },
            },
            "repository_assumptions": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "path": {"type": "string"},
                        "state": {
                            "type": "string",
                            "enum": list(REPOSITORY_STATES),
                        },
                        "source_event_ids": {
                            "type": "array",
                            "items": {"type": "string"},
                        },
                    },
                    "required": ["path", "state", "source_event_ids"],
                    "additionalProperties": False,
                },
            },
            "evidence_state": {
                "type": "object",
                "properties": {
                    "current_event_ids": {
                        "type": "array",
                        "items": {"type": "string"},
                    },
                    "stale_event_ids": {
                        "type": "array",
                        "items": {"type": "string"},
                    },
                },
                "required": ["current_event_ids", "stale_event_ids"],
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
            "next_action": {
                "type": "object",
                "properties": {
                    "action": {
                        "type": "string",
                        "enum": list(NEXT_ACTIONS),
                    },
                    "path": {"type": ["string", "null"]},
                    "reason": {"type": "string"},
                },
                "required": ["action", "path", "reason"],
                "additionalProperties": False,
            },
        },
        "required": [
            "goal_summary",
            "remembered_criterion_ids",
            "subtasks",
            "latest_test",
            "unsuccessful_attempts",
            "repository_assumptions",
            "evidence_state",
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
        "Report the latest test you remember; unsuccessful failed or blocked "
        "attempts; repository paths you believe were observed or modified with "
        "their source event IDs; which evidence event IDs are current versus "
        "stale; changed files; subtask status; uncertainties caused by missing "
        "or conflicting memory; and the single best next action. Return JSON only."
    )


def expected_task_state(
    task: dict,
    evidence_ledger: list[dict],
    *,
    workspace_revision: int,
    trace_events: list[dict] | None = None,
    expected_next_action: dict | None = None,
    uncertainty_expected: bool = False,
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
    unsuccessful_attempts = _unsuccessful_attempts(trace_events or [])
    blocked_finish = any(
        attempt["action"] == "finish"
        and attempt["outcome"] == "blocked"
        for attempt in unsuccessful_attempts
    )
    latest_test_failed = bool(
        latest_test and latest_test.get("status") != "success"
    )
    subtasks = {}
    subtask_source_event_ids = {}
    for index, subtask in enumerate(task["required_subtasks"]):
        completed = completion_flags[min(index, len(completion_flags) - 1)]
        subtask_id = str(subtask["subtask_id"])
        status = "completed" if completed else "pending"
        sources: list[str] = []
        if index == 0:
            sources = [
                str(entry["event_id"])
                for entry in reads
                if entry.get("event_id")
            ]
        elif index == 1:
            sources = [
                str(entry["event_id"])
                for entry in source_writes
                if entry.get("event_id")
            ]
        elif index == 2:
            sources = [
                str(entry["event_id"])
                for entry in test_writes
                if entry.get("event_id")
            ]
        else:
            sources = (
                [str(latest_test["event_id"])]
                if latest_test and latest_test.get("event_id")
                else []
            )
            if latest_test_failed:
                status = "failed"
            elif blocked_finish and not fresh_success:
                status = "blocked"
        subtasks[subtask_id] = status
        subtask_source_event_ids[subtask_id] = sources

    repository_assumptions = _repository_assumptions(
        [*reads, *source_writes, *test_writes]
    )
    stale_event_ids = sorted(
        {
            str(entry["event_id"])
            for entry in evidence_ledger
            if entry.get("event_id") and entry.get("stale")
        }
    )
    current_event_ids = sorted(
        {
            str(entry["event_id"])
            for entry in evidence_ledger
            if entry.get("event_id") and not entry.get("stale")
        }
    )

    return {
        "goal": task["goal"],
        "criterion_ids": [
            f"criterion_{index}"
            for index, _ in enumerate(
                task.get("acceptance_criteria", []),
                start=1,
            )
        ],
        "subtasks": subtasks,
        "subtask_source_event_ids": subtask_source_event_ids,
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
        "unsuccessful_attempts": unsuccessful_attempts,
        "repository_assumptions": repository_assumptions,
        "evidence_state": {
            "current_event_ids": current_event_ids,
            "stale_event_ids": stale_event_ids,
        },
        "uncertainty_expected": bool(uncertainty_expected),
        "next_action": _normalize_next_action(expected_next_action),
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
                "source_event_ids": expected[
                    "subtask_source_event_ids"
                ].get(subtask_id, []),
            }
            for subtask_id, status in expected["subtasks"].items()
        ],
        "latest_test": expected["latest_test"],
        "unsuccessful_attempts": expected["unsuccessful_attempts"],
        "repository_assumptions": expected["repository_assumptions"],
        "evidence_state": expected["evidence_state"],
        "changed_files": expected["changed_files"],
        "uncertainties": (
            ["Visible memory is incomplete or contains stale evidence."]
            if expected["uncertainty_expected"]
            else []
        ),
        "next_action": {
            **expected["next_action"],
            "reason": "Follow the canonical next executable action.",
        },
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
            "objective_fidelity": 0.0,
            "unsuccessful_attempt_f1": 0.0,
            "repository_state_f1": 0.0,
            "current_evidence_f1": 0.0,
            "stale_evidence_f1": 0.0,
            "uncertainty_calibration_accuracy": 0.0,
            "next_action_accuracy": 0.0,
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
    attribution_components = [
        float(
            predicted_test.get("source_event_id")
            == expected_test["source_event_id"]
        )
    ]
    subtask_attribution = _mean_optional(
        [
            _set_f1(
                set(
                    str(event_id)
                    for event_id in item.get("source_event_ids", [])
                ),
                set(
                    expected.get("subtask_source_event_ids", {}).get(
                        str(item.get("subtask_id")),
                        [],
                    )
                ),
            )
            for item in payload.get("subtasks", [])
            if isinstance(item, dict)
            and str(item.get("subtask_id")) in expected_subtasks
        ]
    )
    if (
        subtask_attribution is not None
        and "subtask_source_event_ids" in expected
    ):
        attribution_components.append(subtask_attribution)
    criterion_recall = _set_recall(
        set(payload.get("remembered_criterion_ids", [])),
        set(expected["criterion_ids"]),
    )
    changed_file_f1 = _set_f1(
        set(payload.get("changed_files", [])),
        set(expected["changed_files"]),
    )
    objective_fidelity = _text_f1(
        str(payload.get("goal_summary", "")),
        str(expected.get("goal", "")),
    )
    unsuccessful_attempt_f1 = _record_set_f1(
        payload.get("unsuccessful_attempts", []),
        expected.get("unsuccessful_attempts", []),
        fields=("source_event_id", "action", "outcome"),
    )
    repository_state_f1 = _record_set_f1(
        payload.get("repository_assumptions", []),
        expected.get("repository_assumptions", []),
        fields=("path", "state"),
    )
    repository_attribution = _repository_attribution_accuracy(
        payload.get("repository_assumptions", []),
        expected.get("repository_assumptions", []),
    )
    if "repository_assumptions" in expected:
        attribution_components.append(repository_attribution)
    attribution_accuracy = mean(attribution_components)
    predicted_evidence = payload.get("evidence_state", {})
    current_evidence_f1 = _set_f1(
        set(predicted_evidence.get("current_event_ids", [])),
        set(
            expected.get("evidence_state", {}).get(
                "current_event_ids",
                [],
            )
        ),
    )
    stale_evidence_f1 = _set_f1(
        set(predicted_evidence.get("stale_event_ids", [])),
        set(
            expected.get("evidence_state", {}).get(
                "stale_event_ids",
                [],
            )
        ),
    )
    uncertainty_calibration = float(
        bool(payload.get("uncertainties"))
        is bool(expected.get("uncertainty_expected", False))
    )
    predicted_next_action = _normalize_next_action(
        payload.get("next_action")
    )
    expected_next_action = _normalize_next_action(
        expected.get("next_action")
    )
    next_action_accuracy = _accuracy(
        [
            predicted_next_action["action"]
            == expected_next_action["action"],
            predicted_next_action["path"]
            == expected_next_action["path"],
        ]
    )
    components = [
        objective_fidelity,
        criterion_recall,
        subtask_accuracy,
        latest_evidence_selection_accuracy,
        temporal_ordering_accuracy,
        changed_file_f1,
        attribution_accuracy,
        unsuccessful_attempt_f1,
        repository_state_f1,
        current_evidence_f1,
        stale_evidence_f1,
        uncertainty_calibration,
        next_action_accuracy,
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
        "objective_fidelity": round(objective_fidelity, 4),
        "unsuccessful_attempt_f1": round(
            unsuccessful_attempt_f1,
            4,
        ),
        "repository_state_f1": round(repository_state_f1, 4),
        "current_evidence_f1": round(current_evidence_f1, 4),
        "stale_evidence_f1": round(stale_evidence_f1, 4),
        "uncertainty_calibration_accuracy": round(
            uncertainty_calibration,
            4,
        ),
        "next_action_accuracy": round(next_action_accuracy, 4),
    }


def summarize_probe_scores(probes: list[dict]) -> dict:
    """Summarize empirical probe events for one run."""

    eligible = [
        probe
        for probe in probes
        if probe.get("eligible_for_empirical_analysis")
    ]
    return {
        "schema_version": "agent-memory-probe-summary/v0.2",
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
        "mean_objective_fidelity": _mean_metric(
            eligible,
            "objective_fidelity",
        ),
        "mean_unsuccessful_attempt_f1": _mean_metric(
            eligible,
            "unsuccessful_attempt_f1",
        ),
        "mean_repository_state_f1": _mean_metric(
            eligible,
            "repository_state_f1",
        ),
        "mean_current_evidence_f1": _mean_metric(
            eligible,
            "current_evidence_f1",
        ),
        "mean_stale_evidence_f1": _mean_metric(
            eligible,
            "stale_evidence_f1",
        ),
        "mean_uncertainty_calibration_accuracy": _mean_metric(
            eligible,
            "uncertainty_calibration_accuracy",
        ),
        "mean_next_action_accuracy": _mean_metric(
            eligible,
            "next_action_accuracy",
        ),
        "trajectory": [
            {
                "action_count": probe.get("action_count"),
                "workspace_revision": probe.get("workspace_revision"),
                "memory_condition": probe.get("memory_condition"),
                "overall_accuracy": probe.get("overall_accuracy"),
                "objective_fidelity": probe.get("objective_fidelity"),
                "subtask_state_accuracy": probe.get(
                    "subtask_state_accuracy"
                ),
                "unsuccessful_attempt_f1": probe.get(
                    "unsuccessful_attempt_f1"
                ),
                "repository_state_f1": probe.get(
                    "repository_state_f1"
                ),
                "stale_evidence_f1": probe.get(
                    "stale_evidence_f1"
                ),
                "next_action_accuracy": probe.get(
                    "next_action_accuracy"
                ),
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


def _unsuccessful_attempts(trace_events: list[dict]) -> list[dict]:
    attempts = []
    decisions_by_claim = {
        str(event.get("claim_event_id")): event
        for event in trace_events
        if event.get("event_type") == "verification_decision"
        and event.get("decision") == "block"
    }
    for event in trace_events:
        event_id = event.get("event_id")
        if not event_id:
            continue
        if (
            event.get("event_type") == "tool_call"
            and event.get("status") == "failure"
        ):
            attempts.append(
                {
                    "source_event_id": str(event_id),
                    "action": str(event.get("tool_name") or "tool"),
                    "outcome": "failed",
                    "reason": str(event.get("content") or "tool failed"),
                }
            )
        elif event.get("event_type") == "action_error":
            rejected = event.get("rejected_action") or {}
            attempts.append(
                {
                    "source_event_id": str(event_id),
                    "action": str(
                        rejected.get("action")
                        or event.get("parse_status")
                        or "invalid_action"
                    ),
                    "outcome": "blocked",
                    "reason": str(event.get("content") or "action rejected"),
                }
            )
        elif (
            event.get("event_type") == "completion_claim"
            and event.get("proposal_status") == "blocked"
        ):
            decision = decisions_by_claim.get(str(event_id), {})
            attempts.append(
                {
                    "source_event_id": str(event_id),
                    "action": "finish",
                    "outcome": "blocked",
                    "reason": "; ".join(decision.get("reasons", []))
                    or "finish proposal blocked",
                }
            )
    return attempts


def _repository_assumptions(entries: list[dict]) -> list[dict]:
    latest_by_path: dict[str, dict] = {}
    for entry in entries:
        path = str(entry.get("path", ""))
        if path:
            latest_by_path[path] = entry
    return [
        {
            "path": path,
            "state": (
                "modified"
                if entry.get("tool_name") == "write_file"
                else "observed"
            ),
            "source_event_ids": [str(entry["event_id"])]
            if entry.get("event_id")
            else [],
        }
        for path, entry in sorted(latest_by_path.items())
    ]


def _normalize_next_action(action: Any) -> dict:
    if not isinstance(action, dict):
        return {"action": "none", "path": None}
    action_name = str(action.get("action", "none"))
    if action_name not in NEXT_ACTIONS:
        action_name = "none"
    path = action.get("path")
    return {
        "action": action_name,
        "path": str(path) if path is not None else None,
    }


def _record_set_f1(
    predicted: Any,
    expected: Any,
    *,
    fields: tuple[str, ...],
) -> float:
    predicted_records = {
        tuple(str(item.get(field, "")) for field in fields)
        for item in predicted
        if isinstance(item, dict)
    }
    expected_records = {
        tuple(str(item.get(field, "")) for field in fields)
        for item in expected
        if isinstance(item, dict)
    }
    return _set_f1(predicted_records, expected_records)


def _repository_attribution_accuracy(
    predicted: Any,
    expected: Any,
) -> float:
    expected_by_key = {
        (str(item.get("path")), str(item.get("state"))): set(
            item.get("source_event_ids", [])
        )
        for item in expected
        if isinstance(item, dict)
    }
    scores = []
    for item in predicted:
        if not isinstance(item, dict):
            continue
        key = (str(item.get("path")), str(item.get("state")))
        if key not in expected_by_key:
            continue
        scores.append(
            _set_f1(
                set(item.get("source_event_ids", [])),
                expected_by_key[key],
            )
        )
    if not expected_by_key:
        return 1.0 if not predicted else 0.0
    return sum(scores) / len(expected_by_key)


def _text_f1(predicted: str, expected: str) -> float:
    predicted_tokens = set(re.findall(r"[a-z0-9_]+", predicted.lower()))
    expected_tokens = set(re.findall(r"[a-z0-9_]+", expected.lower()))
    return _set_f1(predicted_tokens, expected_tokens)


def _mean_optional(values: list[float]) -> float | None:
    return mean(values) if values else None
