"""Tests for controlled memory treatments, task-state probes, and fixtures."""

import json
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from research.runner import BenchmarkRunConfig, BenchmarkRunner, ModelResponse
from research.runner.coding_scenarios import (
    fixture_scenario_ids,
    load_fixture_scenario,
)
from research.runner.memory_pressure import (
    MEMORY_CONDITIONS,
    build_agent_memory_view,
)
from research.runner.operational_memory import (
    apply_event_to_memory,
    build_memory_item,
    create_operational_memory_checkpoint,
    plan_memory_repair,
    restore_operational_memory_checkpoint,
    summarize_operational_memory,
)
from research.runner.task_state_probes import (
    expected_task_state,
    score_task_state_probe,
    summarize_probe_scores,
    task_state_probe_schema,
)


CODING_FIXTURE_TASK_IDS = {
    "coding_stale_tests_001",
    "coding_multifile_edit_001",
    "coding_final_edit_stale_test_001",
    "coding_repo_audit_checklist_001",
    "coding_cache_invalidation_001",
    "coding_source_confusion_001",
    "coding_schema_migration_001",
    "coding_retry_policy_001",
}


def _sample_memory():
    ledger = [
        {
            "evidence_id": "e-1",
            "event_id": "event-1",
            "label": "initial_tests",
            "tool_name": "run_tests",
            "status": "success",
            "workspace_revision": 0,
        },
        {
            "evidence_id": "e-2",
            "event_id": "event-2",
            "label": "implementation_write",
            "tool_name": "write_file",
            "path": "service.py",
            "status": "success",
            "workspace_revision": 1,
        },
        {
            "evidence_id": "e-3",
            "event_id": "event-3",
            "label": "test_write",
            "tool_name": "write_file",
            "path": "test_service.py",
            "status": "success",
            "workspace_revision": 2,
        },
    ]
    observations = [{"event_id": "event-3", "content": "Tests changed."}]
    return ledger, observations


@pytest.mark.parametrize("condition", MEMORY_CONDITIONS)
def test_memory_conditions_are_deterministic_and_do_not_mutate_canonical_state(
    condition: str,
):
    ledger, observations = _sample_memory()
    original_ledger = json.loads(json.dumps(ledger))
    original_observations = json.loads(json.dumps(observations))

    first = build_agent_memory_view(
        ledger,
        observations,
        condition=condition,
        action_count=10,
        start_after=2,
        window=2,
        seed=17,
    )
    second = build_agent_memory_view(
        ledger,
        observations,
        condition=condition,
        action_count=10,
        start_after=2,
        window=2,
        seed=17,
    )

    assert first == second
    assert ledger == original_ledger
    assert observations == original_observations
    assert first["condition"] == condition
    assert first["active"] is (condition != "full_history")


def test_temporal_corruption_reorders_stale_test_without_changing_canonical_data():
    ledger, observations = _sample_memory()

    view = build_agent_memory_view(
        ledger,
        observations,
        condition="temporal_corruption",
        action_count=8,
        start_after=2,
        window=2,
        seed=0,
    )

    recalled_test = view["evidence_ledger"][-1]
    assert recalled_test["event_id"] == "event-1"
    assert recalled_test["temporal_metadata_lost"] is True
    assert "workspace_revision" not in recalled_test
    assert ledger[0]["workspace_revision"] == 0


def test_operational_memory_invalidates_revision_bound_test_evidence():
    test_event = {
        "event_id": "event-test",
        "event_type": "tool_call",
        "sequence_number": 4,
        "tool_name": "run_tests",
        "command": "python -m unittest discover -s .",
        "covered_files": ["service.py", "test_service.py"],
        "status": "success",
        "returncode": 0,
        "workspace_revision": 0,
        "source_type": "tool_output",
    }
    write_event = {
        "event_id": "event-write",
        "event_type": "file_state_change",
        "sequence_number": 5,
        "tool_name": "write_file",
        "path": "service.py",
        "status": "success",
        "workspace_revision": 1,
        "source_type": "file_state",
    }

    memory = apply_event_to_memory([], test_event, label="run_tests")
    memory = apply_event_to_memory(
        memory,
        write_event,
        label="write_file:service.py",
    )

    stale_test = memory[0]
    assert stale_test["claim"].startswith("Visible tests success")
    assert stale_test["repository_revision"] == 0
    assert stale_test["workspace_revision"] == 0
    assert stale_test["stale"] is True
    assert stale_test["support_status"] == "stale"
    assert stale_test["invalidation_dependencies"] == [
        "service.py",
        "test_service.py",
    ]
    assert stale_test["invalidated_by_event_ids"] == ["event-write"]
    plan = plan_memory_repair(["stale evidence"], memory)
    assert plan["repairable"] is True
    assert plan["action"] == {"action": "run_full_tests"}
    assert stale_test["memory_id"] in plan["target_memory_ids"]


def test_operational_memory_tracks_typed_test_dependencies():
    event = {
        "event_id": "event-targeted-test",
        "event_type": "tool_call",
        "sequence_number": 4,
        "tool_name": "run_targeted_tests",
        "command": "python -m unittest test_service.py",
        "test_targets": ["test_service.py"],
        "covered_files": ["service.py", "test_service.py"],
        "covered_symbols": ["service.py:answer"],
        "status": "success",
        "workspace_revision": 0,
        "source_type": "tool_output",
    }

    item = build_memory_item(event, label="targeted_test")

    assert item["dependency_graph"] == {
        "files": ["service.py", "test_service.py"],
        "symbols": ["service.py:answer"],
        "tests": ["test_service.py"],
        "commands": ["python -m unittest test_service.py"],
        "requirements": [],
    }


def test_symbol_dependencies_prevent_unrelated_test_invalidation():
    test_event = {
        "event_id": "event-test",
        "event_type": "tool_call",
        "sequence_number": 1,
        "tool_name": "run_targeted_tests",
        "command": "python -m unittest test_service.py",
        "test_targets": ["test_service.py"],
        "covered_files": ["service.py", "test_service.py"],
        "covered_symbols": ["service.py:answer"],
        "status": "success",
        "workspace_revision": 0,
        "source_type": "tool_output",
    }
    unrelated_write = {
        "event_id": "event-helper-write",
        "event_type": "file_state_change",
        "sequence_number": 2,
        "tool_name": "write_file",
        "path": "service.py",
        "changed_symbols": {"service.py": ["helper"]},
        "status": "success",
        "workspace_revision": 1,
        "source_type": "file_state",
    }
    dependent_write = {
        "event_id": "event-answer-write",
        "event_type": "file_state_change",
        "sequence_number": 3,
        "tool_name": "write_file",
        "path": "service.py",
        "changed_symbols": {"service.py": ["answer"]},
        "status": "success",
        "workspace_revision": 2,
        "source_type": "file_state",
    }

    memory = apply_event_to_memory([], test_event, label="targeted_test")
    memory = apply_event_to_memory(
        memory,
        unrelated_write,
        label="write_file:service.py",
    )
    assert memory[0]["stale"] is False

    memory = apply_event_to_memory(
        memory,
        dependent_write,
        label="write_file:service.py",
    )
    assert memory[0]["stale"] is True
    assert memory[0]["invalidated_by_event_ids"] == ["event-answer-write"]


def test_newer_test_result_reconciles_older_contradiction():
    passing = {
        "event_id": "event-pass",
        "event_type": "tool_call",
        "sequence_number": 1,
        "tool_name": "run_targeted_tests",
        "test_targets": ["test_service.py"],
        "covered_files": ["service.py", "test_service.py"],
        "status": "success",
        "workspace_revision": 1,
        "source_type": "tool_output",
    }
    failing = {
        **passing,
        "event_id": "event-fail",
        "sequence_number": 2,
        "status": "failure",
        "returncode": 1,
    }

    memory = apply_event_to_memory([], passing, label="targeted_test")
    memory = apply_event_to_memory(memory, failing, label="targeted_test")
    prior, current = memory
    summary = summarize_operational_memory(memory)

    assert prior["support_status"] == "superseded"
    assert prior["historical_contradiction"] is True
    assert prior["reconciliation_status"] == "resolved"
    assert prior["reconciled_by_event_ids"] == ["event-fail"]
    assert current["reconciles_memory_ids"] == [prior["memory_id"]]
    assert summary["contradicted_item_count"] == 0
    assert summary["historical_contradiction_count"] == 1
    assert summary["reconciled_item_count"] == 1


def test_operational_memory_checkpoint_round_trip_and_integrity():
    memory = [
        {
            "memory_id": "memory-1",
            "event_id": "event-1",
            "dependency_graph": {
                "files": ["service.py"],
                "symbols": ["service.py:answer"],
                "tests": [],
                "commands": [],
                "requirements": ["criterion_1"],
            },
        }
    ]
    checkpoint = create_operational_memory_checkpoint(
        memory,
        workspace_revision=7,
        last_event_id="event-1",
    )
    restored = restore_operational_memory_checkpoint(checkpoint)

    assert checkpoint["workspace_revision"] == 7
    assert checkpoint["last_event_id"] == "event-1"
    assert len(checkpoint["sha256"]) == 64
    assert restored == memory
    restored[0]["memory_id"] = "mutated"
    assert checkpoint["memory_items"][0]["memory_id"] == "memory-1"

    corrupted = json.loads(json.dumps(checkpoint))
    corrupted["memory_items"][0]["memory_id"] = "tampered"
    with pytest.raises(ValueError, match="integrity"):
        restore_operational_memory_checkpoint(corrupted)


@pytest.mark.parametrize(
    ("reasons", "memory", "repair_type", "action"),
    [
        (
            ["lost provenance"],
            [
                {
                    "memory_id": "source-memory",
                    "path": "service.py",
                    "tool_name": "read_file",
                    "stale": False,
                    "support_status": "supported",
                }
            ],
            "lost_provenance",
            {"action": "read_file", "path": "service.py"},
        ),
        (
            ["contradicted claim"],
            [
                {
                    "memory_id": "test-memory",
                    "tool_name": "run_tests",
                    "stale": True,
                    "support_status": "contradicted",
                }
            ],
            "contradictory_evidence",
            {"action": "run_full_tests"},
        ),
        (
            ["missing requirement context"],
            [],
            "missing_requirements",
            {"action": "refresh_requirements"},
        ),
        (
            ["independent task evaluator failed"],
            [],
            "implementation_evaluator_failure",
            {"action": "diagnose_evaluator_failure"},
        ),
    ],
)
def test_memory_repair_plans_cover_non_stale_failure_modes(
    reasons,
    memory,
    repair_type,
    action,
):
    plan = plan_memory_repair(reasons, memory)

    assert plan["schema_version"] == "agent-memory-repair-plan/v0.3"
    assert plan["repairable"] is True
    assert plan["repair_type"] == repair_type
    assert plan["action"] == action
    assert plan["success_criterion"]


def test_stale_targeted_test_repair_preserves_the_recorded_scope():
    memory = [
        {
            "memory_id": "targeted-test-memory",
            "event_id": "targeted-test-event",
            "tool_name": "run_targeted_tests",
            "test_targets": ["test_service.py"],
            "stale": True,
            "support_status": "stale",
        }
    ]

    plan = plan_memory_repair(["stale evidence"], memory)

    assert plan["repair_type"] == "stale_test_evidence"
    assert plan["action"] == {
        "action": "run_targeted_tests",
        "targets": ["test_service.py"],
    }


def test_lost_provenance_rereads_cited_source_not_newer_unrelated_file():
    memory = [
        {
            "memory_id": "relevant-memory",
            "event_id": "relevant-event",
            "tool_name": "write_file",
            "path": "service.py",
            "stale": False,
            "support_status": "supported",
        },
        {
            "memory_id": "unrelated-memory",
            "event_id": "unrelated-event",
            "tool_name": "read_file",
            "path": "notes.py",
            "stale": False,
            "support_status": "supported",
        },
    ]

    plan = plan_memory_repair(
        ["lost provenance"],
        memory,
        claim_source_event_ids=["relevant-event"],
    )

    assert plan["repair_type"] == "lost_provenance"
    assert plan["target_memory_ids"] == ["relevant-memory"]
    assert plan["action"] == {"action": "read_file", "path": "service.py"}


def test_contradicted_targeted_test_gets_discriminating_rerun():
    memory = [
        {
            "memory_id": "contradicted-test",
            "event_id": "test-event",
            "tool_name": "run_targeted_tests",
            "test_targets": ["test_service.py"],
            "stale": True,
            "support_status": "contradicted",
        }
    ]

    plan = plan_memory_repair(["contradicted claim"], memory)

    assert plan["repair_type"] == "contradictory_evidence"
    assert plan["action"] == {
        "action": "run_targeted_tests",
        "targets": ["test_service.py"],
    }


def test_discriminating_source_read_reconciles_contradicted_file_memory():
    contradicted = {
        "event_id": "old-source",
        "event_type": "tool_call",
        "sequence_number": 2,
        "tool_name": "read_file",
        "path": "service.py",
        "status": "success",
        "workspace_revision": 1,
        "source_type": "tool_output",
    }
    memory = apply_event_to_memory([], contradicted, label="read_file:service.py")
    memory[0]["support_status"] = "contradicted"
    memory[0]["reconciliation_status"] = "unresolved"
    refreshed = {
        **contradicted,
        "event_id": "fresh-source",
        "sequence_number": 5,
        "workspace_revision": 2,
    }

    reconciled = apply_event_to_memory(
        memory,
        refreshed,
        label="read_file:service.py",
    )

    assert reconciled[0]["support_status"] == "superseded"
    assert reconciled[0]["reconciliation_status"] == "resolved"
    assert reconciled[0]["reconciled_by_event_ids"] == ["fresh-source"]
    assert reconciled[1]["reconciles_memory_ids"] == [
        reconciled[0]["memory_id"]
    ]


def test_requirement_refresh_reconciles_contradicted_requirement_memory():
    requirement = {
        "event_id": "requirement-update",
        "event_type": "user_requirement_update",
        "sequence_number": 3,
        "requirement_id": "requirement_update_0",
        "content": "Preserve duplicate-key last-write-wins behavior.",
        "status": "active",
        "workspace_revision": 1,
        "source_type": "user_instruction",
    }
    memory = apply_event_to_memory(
        [],
        requirement,
        label="requirement_update:0",
    )
    memory[0]["support_status"] = "contradicted"
    memory[0]["reconciliation_status"] = "unresolved"
    refresh = {
        "event_id": "requirement-refresh",
        "event_type": "requirement_refresh",
        "sequence_number": 6,
        "tool_name": "refresh_requirements",
        "status": "success",
        "workspace_revision": 1,
        "requirement_snapshot": {
            "required_subtasks": [
                {
                    "subtask_id": "implement_parser",
                    "description": "Implement parser behavior.",
                }
            ]
        },
        "source_type": "ground_truth",
    }

    reconciled = apply_event_to_memory(
        memory,
        refresh,
        label="refresh_requirements",
    )

    assert reconciled[0]["support_status"] == "superseded"
    assert reconciled[0]["reconciliation_status"] == "resolved"
    assert reconciled[1]["reconciles_memory_ids"] == [
        reconciled[0]["memory_id"]
    ]


def test_evaluator_repair_budget_stops_controller_diagnosis_loop():
    plan = plan_memory_repair(
        ["independent task evaluator failed"],
        [],
        repair_attempt=2,
        repair_budget=2,
    )

    assert plan["repair_type"] == "implementation_evaluator_failure"
    assert plan["repairable"] is False
    assert plan["action"] is None
    assert plan["budget_exhausted"] is True
    assert plan["repair_attempt"] == 2
    assert plan["repair_budget"] == 2


def test_probe_scoring_penalizes_wrong_state_and_lost_attribution():
    expected = {
        "goal": "Fix the service and rerun tests.",
        "criterion_ids": ["criterion_1", "criterion_2"],
        "subtasks": {"inspect": "completed", "verify": "pending"},
        "subtask_source_event_ids": {
            "inspect": ["event-2"],
            "verify": [],
        },
        "latest_test": {
            "status": "passed",
            "source_event_id": "event-7",
            "workspace_revision": 1,
            "is_current": False,
        },
        "changed_files": ["service.py"],
        "unsuccessful_attempts": [
            {
                "source_event_id": "event-6",
                "action": "run_tests",
                "outcome": "failed",
                "reason": "tests failed",
            }
        ],
        "failed_attempts": [
            {
                "source_event_id": "event-6",
                "action": "run_tests",
                "outcome": "failed",
                "reason": "tests failed",
            }
        ],
        "blocked_attempts": [],
        "repository_assumptions": [
            {
                "path": "service.py",
                "state": "modified",
                "workspace_revision": 1,
                "source_event_ids": ["event-2"],
            }
        ],
        "evidence_state": {
            "current_event_ids": ["event-2"],
            "stale_event_ids": ["event-7"],
            "uncertain_event_ids": ["event-8"],
        },
        "uncertainty_expected": True,
        "next_action": {"action": "run_tests", "path": None},
    }
    prediction = {
        "goal_summary": "Fix the service.",
        "remembered_criterion_ids": ["criterion_1"],
        "subtasks": [
            {
                "subtask_id": "inspect",
                "status": "completed",
                "source_event_ids": [],
            },
            {
                "subtask_id": "verify",
                "status": "completed",
                "source_event_ids": [],
            },
        ],
        "latest_test": {
            "status": "passed",
            "source_event_id": None,
            "workspace_revision": 1,
            "is_current": True,
        },
        "unsuccessful_attempts": [],
        "failed_attempts": [],
        "blocked_attempts": [],
        "repository_assumptions": [
            {
                "path": "service.py",
                "state": "observed",
                "workspace_revision": 0,
                "source_event_ids": [],
            }
        ],
        "evidence_state": {
            "current_event_ids": ["event-2", "event-7"],
            "stale_event_ids": [],
            "uncertain_event_ids": [],
        },
        "changed_files": ["service.py", "unrelated.py"],
        "uncertainties": [],
        "next_action": {
            "action": "finish",
            "path": None,
            "reason": "The work looks complete.",
        },
    }

    score = score_task_state_probe(prediction, expected)

    assert score["parse_status"] == "json"
    assert score["criterion_recall"] == 0.5
    assert score["subtask_state_accuracy"] == 0.5
    assert score["latest_test_accuracy"] < 1.0
    assert score["evidence_attribution_accuracy"] < 0.3
    assert score["unsuccessful_attempt_f1"] == 0.0
    assert score["failed_attempt_f1"] == 0.0
    assert score["blocked_attempt_f1"] == 1.0
    assert score["repository_state_f1"] == 0.0
    assert score["stale_evidence_f1"] == 0.0
    assert score["uncertain_evidence_f1"] == 0.0
    assert score["uncertainty_calibration_accuracy"] == 0.0
    assert score["next_action_accuracy"] == 0.0
    assert score["overall_accuracy"] < 0.7


def test_expected_probe_state_tracks_failures_repository_and_stale_evidence():
    task = BenchmarkRunner().get_task("coding_stale_tests_001")
    ledger = [
        {
            "event_id": "event-read",
            "tool_name": "read_file",
            "path": "config_parser.py",
            "status": "success",
            "workspace_revision": 0,
            "stale": False,
        },
        {
            "event_id": "event-write",
            "tool_name": "write_file",
            "path": "config_parser.py",
            "status": "success",
            "workspace_revision": 1,
            "stale": False,
        },
        {
            "event_id": "event-reread",
            "tool_name": "read_file",
            "path": "config_parser.py",
            "status": "success",
            "workspace_revision": 1,
            "sequence_number": 3,
            "stale": False,
        },
        {
            "event_id": "event-test",
            "tool_name": "run_tests",
            "status": "failure",
            "workspace_revision": 1,
            "stale": True,
        },
    ]
    trace_events = [
        {
            "event_id": "event-test",
            "event_type": "tool_call",
            "tool_name": "run_tests",
            "status": "failure",
            "content": "one test failed",
        },
        {
            "event_id": "event-finish",
            "event_type": "completion_claim",
            "proposal_status": "blocked",
        },
        {
            "event_id": "event-decision",
            "event_type": "verification_decision",
            "decision": "block",
            "claim_event_id": "event-finish",
            "reasons": ["stale evidence"],
        },
    ]

    expected = expected_task_state(
        task,
        ledger,
        workspace_revision=1,
        trace_events=trace_events,
        expected_next_action={"action": "run_tests"},
        uncertainty_expected=True,
        uncertain_event_ids=["event-test"],
    )

    assert expected["latest_test"]["status"] == "failed"
    assert expected["subtasks"]["rerun_after_final_edit"] == "failed"
    assert expected["unsuccessful_attempts"] == [
        {
            "source_event_id": "event-test",
            "action": "run_tests",
            "outcome": "failed",
            "reason": "one test failed",
        },
        {
            "source_event_id": "event-finish",
            "action": "finish",
            "outcome": "blocked",
            "reason": "stale evidence",
        },
    ]
    assert expected["failed_attempts"] == [
        {
            "source_event_id": "event-test",
            "action": "run_tests",
            "outcome": "failed",
            "reason": "one test failed",
        }
    ]
    assert expected["blocked_attempts"] == [
        {
            "source_event_id": "event-finish",
            "action": "finish",
            "outcome": "blocked",
            "reason": "stale evidence",
        }
    ]
    assert expected["repository_assumptions"] == [
        {
            "path": "config_parser.py",
            "state": "modified",
            "workspace_revision": 1,
            "source_event_ids": ["event-write", "event-reread"],
        }
    ]
    assert expected["evidence_state"]["stale_event_ids"] == ["event-test"]
    assert expected["evidence_state"]["uncertain_event_ids"] == [
        "event-test"
    ]
    assert expected["uncertainty_expected"] is True
    assert expected["next_action"] == {
        "action": "run_tests",
        "path": None,
        "targets": [],
    }


def test_probe_schema_requires_complete_state_measurement():
    task = BenchmarkRunner().get_task("coding_stale_tests_001")
    schema = task_state_probe_schema(task)

    assert {
        "failed_attempts",
        "blocked_attempts",
        "repository_assumptions",
        "evidence_state",
        "uncertainties",
        "next_action",
    }.issubset(schema["required"])
    next_actions = set(
        schema["properties"]["next_action"]["properties"]["action"][
            "enum"
        ]
    )
    assert {
        "list_files",
        "read_file",
        "search_code",
        "git_diff",
        "git_status",
        "write_file",
        "apply_patch",
        "read_test_failure",
        "run_targeted_tests",
        "run_full_tests",
        "run_tests",
        "inspect_dependency",
        "read_structured_file",
        "finish",
        "none",
    } == next_actions
    assert schema["properties"]["evidence_state"]["required"] == [
        "current_event_ids",
        "stale_event_ids",
        "uncertain_event_ids",
    ]


def test_probe_ground_truth_tracks_targeted_tests_and_bounded_patches():
    task = BenchmarkRunner().get_task("coding_stale_tests_001")
    ledger = [
        {
            "event_id": "patch-1",
            "sequence_number": 2,
            "tool_name": "apply_patch",
            "paths": ["config_parser.py"],
            "status": "success",
            "workspace_revision": 1,
            "stale": False,
        },
        {
            "event_id": "targeted-test-2",
            "sequence_number": 3,
            "tool_name": "run_targeted_tests",
            "test_targets": ["test_config_parser.py"],
            "status": "success",
            "workspace_revision": 1,
            "stale": False,
        },
    ]

    expected = expected_task_state(
        task,
        ledger,
        workspace_revision=1,
        expected_next_action={
            "action": "run_targeted_tests",
            "targets": ["test_config_parser.py"],
        },
    )

    assert expected["latest_test"] == {
        "status": "passed",
        "source_event_id": "targeted-test-2",
        "workspace_revision": 1,
        "is_current": True,
    }
    assert expected["changed_files"] == ["config_parser.py"]
    assert expected["repository_assumptions"] == [
        {
            "path": "config_parser.py",
            "state": "modified",
            "workspace_revision": 1,
            "source_event_ids": ["patch-1"],
        }
    ]
    assert expected["next_action"] == {
        "action": "run_targeted_tests",
        "path": None,
        "targets": ["test_config_parser.py"],
    }


def test_probe_scoring_separates_attempt_outcomes_and_uncertain_evidence():
    expected = {
        "goal": "Repair the cache safely.",
        "criterion_ids": [],
        "subtasks": {},
        "subtask_source_event_ids": {},
        "latest_test": {
            "status": "not_run",
            "source_event_id": None,
            "workspace_revision": None,
            "is_current": False,
        },
        "changed_files": [],
        "unsuccessful_attempts": [
            {
                "source_event_id": "failed-1",
                "action": "run_tests",
                "outcome": "failed",
                "reason": "test failure",
            },
            {
                "source_event_id": "blocked-1",
                "action": "finish",
                "outcome": "blocked",
                "reason": "stale evidence",
            },
        ],
        "failed_attempts": [
            {
                "source_event_id": "failed-1",
                "action": "run_tests",
                "outcome": "failed",
                "reason": "test failure",
            }
        ],
        "blocked_attempts": [
            {
                "source_event_id": "blocked-1",
                "action": "finish",
                "outcome": "blocked",
                "reason": "stale evidence",
            }
        ],
        "repository_assumptions": [],
        "evidence_state": {
            "current_event_ids": ["current-1"],
            "stale_event_ids": ["stale-1"],
            "uncertain_event_ids": ["uncertain-1"],
        },
        "uncertainty_expected": True,
        "next_action": {"action": "run_tests", "path": None},
    }
    prediction = {
        "goal_summary": "Repair the cache safely.",
        "remembered_criterion_ids": [],
        "subtasks": [],
        "latest_test": expected["latest_test"],
        "unsuccessful_attempts": expected["failed_attempts"],
        "failed_attempts": expected["failed_attempts"],
        "blocked_attempts": [],
        "repository_assumptions": [],
        "evidence_state": {
            "current_event_ids": ["current-1"],
            "stale_event_ids": ["stale-1"],
            "uncertain_event_ids": ["uncertain-1"],
        },
        "changed_files": [],
        "uncertainties": ["uncertain-1 has incomplete provenance"],
        "next_action": {
            "action": "run_tests",
            "path": "ignored-for-this-action",
            "reason": "Obtain current test evidence.",
        },
    }

    score = score_task_state_probe(prediction, expected)

    assert score["failed_attempt_f1"] == 1.0
    assert score["blocked_attempt_f1"] == 0.0
    assert score["stale_evidence_f1"] == 1.0
    assert score["uncertain_evidence_f1"] == 1.0
    assert score["next_action_appropriateness"] == 1.0


def test_probe_summary_generates_ordered_memory_accuracy_curve():
    probes = [
        {
            "eligible_for_empirical_analysis": True,
            "checkpoint": "after_action_10",
            "checkpoint_sequence_number": 40,
            "action_count": 10,
            "workspace_revision": 2,
            "memory_condition": "lossy_compaction",
            "memory_view_active": True,
            "overall_accuracy": 0.5,
        },
        {
            "eligible_for_empirical_analysis": True,
            "checkpoint": "initial_workspace",
            "checkpoint_sequence_number": 3,
            "action_count": 0,
            "workspace_revision": 0,
            "memory_condition": "lossy_compaction",
            "memory_view_active": False,
            "overall_accuracy": 1.0,
        },
    ]

    summary = summarize_probe_scores(probes)
    curve = summary["memory_accuracy_curve"]

    assert summary["schema_version"] == "agent-memory-probe-summary/v0.3"
    assert (
        summary["memory_accuracy_curve_schema_version"]
        == "agent-memory-accuracy-curve/v0.1"
    )
    assert [point["action_count"] for point in curve] == [0, 10]
    assert curve[0]["normalized_action_progress"] == 0.0
    assert curve[1]["normalized_action_progress"] == 1.0
    assert curve[1]["accuracy_delta_from_previous"] == -0.5
    assert curve[1]["cumulative_mean_accuracy"] == 0.75
    assert summary["curve_statistics"] == {
        "point_count": 2,
        "action_span": 10,
        "area_under_curve": 0.75,
        "minimum_accuracy": 0.5,
        "terminal_accuracy": 0.5,
        "first_degradation_action": 10,
    }
    assert summary["trajectory"] == curve


@pytest.mark.parametrize(
    "task_id",
    sorted(CODING_FIXTURE_TASK_IDS),
)
def test_fixture_backed_tasks_pass_visible_and_hidden_evaluation(
    tmp_path: Path,
    task_id: str,
):
    pytest.importorskip("langgraph")

    run = BenchmarkRunner().run_task_id(
        task_id,
        BenchmarkRunConfig(
            framework="langgraph_tools",
            trace_mode="model_driven",
            runtime="deterministic",
            action_budget=24,
            workspace_root=str(tmp_path),
        ),
    )

    scenario = load_fixture_scenario(task_id)
    assert scenario is not None
    assert set(fixture_scenario_ids()) == CODING_FIXTURE_TASK_IDS
    for step in scenario["steps"]:
        if step.get("tool_name") == "read_file":
            assert step["path"] in scenario["initial_files"]
    assert run["interaction_metrics"]["visible_test_success"] is True
    assert run["interaction_metrics"]["hidden_validation_success"] is True
    assert run["interaction_metrics"]["evaluator_success"] is True
    assert run["interaction_metrics"]["model_action_count"] == 20


@pytest.mark.parametrize("task_id", sorted(CODING_FIXTURE_TASK_IDS))
def test_coding_fixture_meets_long_horizon_benchmark_contract(task_id: str):
    scenario = load_fixture_scenario(task_id)
    assert scenario is not None
    assert 20 <= scenario["planned_model_actions"] <= 50
    assert len(scenario["repository_hash"]) == 64
    assert Path(scenario["hidden_validation_path"]).is_file()

    source_files = [
        path
        for path in scenario["initial_files"]
        if path.endswith(".py") and not Path(path).name.startswith("test_")
    ]
    test_files = [
        path
        for path in scenario["initial_files"]
        if Path(path).name.startswith("test_") and path.endswith(".py")
    ]
    assert len(source_files) >= 2
    assert len(test_files) >= 2

    features = scenario["benchmark_features"]
    assert len(features["independent_subtasks"]) >= 3
    assert features["multiple_source_and_test_files"] is True
    assert features["delayed_final_validation"] is True
    assert features["context_compaction_conditions"] == [
        "lossy_compaction",
        "resume_summary",
    ]
    assert features["hidden_tests_unavailable_to_agent"] is True
    assert features["executable_evaluator"] is True
    assert scenario["requirement_updates"]

    step_ids = [step["step_id"] for step in scenario["steps"]]
    false_lead_index = step_ids.index(
        features["plausible_false_lead_step_id"]
    )
    rollback_index = step_ids.index(features["rollback_step_id"])
    stale_test_index = step_ids.index(
        features["stale_evidence_test_step_id"]
    )
    invalidation_index = step_ids.index(
        features["stale_evidence_invalidation_step_id"]
    )
    final_test_index = step_ids.index(scenario["final_test_step_id"])
    assert false_lead_index < rollback_index
    assert stale_test_index < invalidation_index < final_test_index


@pytest.mark.parametrize("task_id", sorted(CODING_FIXTURE_TASK_IDS))
def test_verified_fixture_recovers_under_lossy_compaction(
    tmp_path: Path,
    task_id: str,
):
    pytest.importorskip("langgraph")

    run = BenchmarkRunner().run_task_id(
        task_id,
        BenchmarkRunConfig(
            framework="langgraph_tools",
            trace_mode="model_driven",
            runtime="deterministic",
            agent_variant="verified",
            action_budget=24,
            workspace_root=str(tmp_path),
            memory_condition="lossy_compaction",
            memory_pressure_start=6,
            memory_window=6,
        ),
    )

    pressure_events = [
        event
        for event in run["trace_events"]
        if event.get("event_type") == "memory_pressure"
        and event.get("operations")
    ]
    metrics = run["interaction_metrics"]
    assert pressure_events
    assert metrics["blocked_false_finishes"] == 1
    assert metrics["accepted_finish_proposals"] == 1
    assert metrics["recovery_after_block"] is True
    assert metrics["evaluator_success"] is True
    assert 20 <= metrics["model_action_count"] <= 50


def test_fixture_recovers_from_resume_summary_memory(tmp_path: Path):
    pytest.importorskip("langgraph")

    run = BenchmarkRunner().run_task_id(
        "coding_stale_tests_001",
        BenchmarkRunConfig(
            framework="langgraph_tools",
            trace_mode="model_driven",
            runtime="deterministic",
            agent_variant="verified",
            action_budget=24,
            workspace_root=str(tmp_path),
            memory_condition="resume_summary",
            memory_pressure_start=6,
            memory_window=6,
        ),
    )

    pressure_events = [
        event
        for event in run["trace_events"]
        if event.get("event_type") == "memory_pressure"
        and event.get("operations")
    ]
    assert pressure_events
    assert any(
        "resume" in operation
        for event in pressure_events
        for operation in event.get("operations", [])
    )
    assert run["interaction_metrics"]["recovery_after_block"] is True
    assert run["interaction_metrics"]["evaluator_success"] is True


def test_real_runtime_shadow_probe_is_measured_without_steering_main_loop(
    tmp_path: Path,
):
    pytest.importorskip("langgraph")
    runner = BenchmarkRunner()
    task = runner.get_task("coding_stale_tests_001")
    scenario = runner._coding_tool_scenario(task)
    scripted_actions = []
    for step in scenario["steps"]:
        action = {"action": step["tool_name"]}
        for key in ["path", "content", "claim"]:
            if key in step:
                action[key] = step[key]
        scripted_actions.append(action)

    class ProbeAwareAdapter:
        runtime = "ollama"

        def __init__(self):
            self.action_index = 0
            self.probe_token_budgets = []

        def generate(self, request):
            if "AGENT_MEMORY_SHADOW_STATE_PROBE" in request.prompt:
                self.probe_token_budgets.append(request.max_tokens)
                subtask_id = request.response_schema["properties"][
                    "subtasks"
                ]["items"]["properties"]["subtask_id"]["enum"][0]
                payload = {
                    "goal_summary": "Reconstructed task state.",
                    "remembered_criterion_ids": [],
                    "subtasks": [
                        {
                            "subtask_id": subtask_id,
                            "status": "pending",
                            "source_event_ids": [],
                        }
                    ],
                    "latest_test": {
                        "status": "not_run",
                        "source_event_id": None,
                        "workspace_revision": None,
                        "is_current": False,
                    },
                    "unsuccessful_attempts": [],
                    "failed_attempts": [],
                    "blocked_attempts": [],
                    "repository_assumptions": [],
                    "evidence_state": {
                        "current_event_ids": [],
                        "stale_event_ids": [],
                        "uncertain_event_ids": [],
                    },
                    "changed_files": [],
                    "uncertainties": ["Memory is incomplete."],
                    "next_action": {
                        "action": "list_files",
                        "path": None,
                        "reason": "Inspect the workspace.",
                    },
                }
            else:
                payload = scripted_actions[
                    min(self.action_index, len(scripted_actions) - 1)
                ]
                self.action_index += 1
            return ModelResponse(
                text=json.dumps(payload),
                runtime="ollama",
                model_name=request.model_name,
                model_family=request.model_family,
                raw_response={"test_adapter": True},
            )

    adapter = ProbeAwareAdapter()
    with patch(
        "research.runner.benchmark_runner.create_model_adapter",
        return_value=adapter,
    ):
        run = runner.run_task_id(
            "coding_stale_tests_001",
            BenchmarkRunConfig(
                framework="langgraph_tools",
                trace_mode="model_driven",
                runtime="ollama",
                action_budget=32,
                workspace_root=str(tmp_path),
                task_state_probes=True,
                probe_interval=2,
                probe_max_tokens=640,
            ),
        )

    probe_events = [
        event
        for event in run["trace_events"]
        if event.get("event_type") == "task_state_probe"
    ]
    assert probe_events
    assert all(
        event["probe_origin"] == "model_shadow_fork"
        for event in probe_events
    )
    summary = run["task_state_probe_summary"]
    assert summary["eligible_probe_count"] == len(probe_events)
    assert all(
        event["probe_schema_version"]
        == "agent-memory-task-state-probe/v0.3"
        for event in probe_events
    )
    assert len(summary["memory_accuracy_curve"]) == len(probe_events)
    assert [
        point["action_count"]
        for point in summary["memory_accuracy_curve"]
    ] == sorted(event["action_count"] for event in probe_events)
    assert summary["curve_statistics"]["point_count"] == len(probe_events)
    assert set(adapter.probe_token_budgets) == {640}
    assert run["interaction_metrics"]["evaluator_success"] is True


def test_shadow_probes_do_not_change_agent_actions_or_workspace(tmp_path: Path):
    pytest.importorskip("langgraph")
    runner = BenchmarkRunner()
    plain_root = tmp_path / "plain"
    probed_root = tmp_path / "probed"
    base_config = {
        "framework": "langgraph_tools",
        "trace_mode": "model_driven",
        "runtime": "deterministic",
        "action_budget": 24,
    }

    plain = runner.run_task_id(
        "coding_stale_tests_001",
        BenchmarkRunConfig(
            **base_config,
            workspace_root=str(plain_root),
            task_state_probes=False,
        ),
    )
    probed = runner.run_task_id(
        "coding_stale_tests_001",
        BenchmarkRunConfig(
            **base_config,
            workspace_root=str(probed_root),
            task_state_probes=True,
            probe_interval=2,
        ),
    )

    def actions(run):
        return [
            event["parsed_action"]
            for event in run["trace_events"]
            if event.get("event_type") == "model_response"
            and event.get("graph_node") == "choose_action"
        ]

    def workspace_files(run):
        workspace = Path(run["run_metadata"]["workspace_path"])
        return {
                path.relative_to(workspace).as_posix(): path.read_text()
                for path in sorted(workspace.rglob("*"))
                if path.is_file()
                and "__pycache__" not in path.parts
                and ".git" not in path.parts
            }

    assert actions(probed) == actions(plain)
    assert workspace_files(probed) == workspace_files(plain)
    assert probed["interaction_metrics"] == plain["interaction_metrics"]
    probe_events = [
        event
        for event in probed["trace_events"]
        if event.get("event_type") == "task_state_probe"
    ]
    assert [event["action_count"] for event in probe_events] == [
        0,
        2,
        4,
        6,
        8,
        10,
        12,
        14,
        16,
        18,
        20,
    ]
    assert all(
        event["probe_origin"] == "deterministic_oracle"
        and event["eligible_for_empirical_analysis"] is False
        and event["overall_accuracy"] == 1.0
        and event["checkpoint_sequence_number"] < event["sequence_number"]
        for event in probe_events
    )
    summary = probed["task_state_probe_summary"]
    assert summary["probe_count"] == len(probe_events)
    assert summary["eligible_probe_count"] == 0
    assert summary["mean_overall_accuracy"] is None
    assert summary["memory_accuracy_curve"] == []
    assert summary["curve_statistics"]["point_count"] == 0
    assert summary["trajectory"] == []
