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
    plan_memory_repair,
)
from research.runner.task_state_probes import score_task_state_probe


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
    assert stale_test["stale"] is True
    assert stale_test["support_status"] == "stale"
    assert stale_test["invalidation_dependencies"] == [
        "service.py",
        "test_service.py",
    ]
    assert stale_test["invalidated_by_event_ids"] == ["event-write"]
    plan = plan_memory_repair(["stale evidence"], memory)
    assert plan["repairable"] is True
    assert plan["action"] == {"action": "run_tests"}
    assert stale_test["memory_id"] in plan["target_memory_ids"]


def test_probe_scoring_penalizes_wrong_state_and_lost_attribution():
    expected = {
        "criterion_ids": ["criterion_1", "criterion_2"],
        "subtasks": {"inspect": "completed", "verify": "pending"},
        "latest_test": {
            "status": "passed",
            "source_event_id": "event-7",
            "workspace_revision": 1,
            "is_current": False,
        },
        "changed_files": ["service.py"],
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
        "changed_files": ["service.py", "unrelated.py"],
        "uncertainties": [],
        "next_action": "Finish.",
    }

    score = score_task_state_probe(prediction, expected)

    assert score["parse_status"] == "json"
    assert score["criterion_recall"] == 0.5
    assert score["subtask_state_accuracy"] == 0.5
    assert score["latest_test_accuracy"] < 1.0
    assert score["evidence_attribution_accuracy"] == 0.0
    assert score["overall_accuracy"] < 0.7


@pytest.mark.parametrize(
    "task_id",
    [
        "coding_cache_invalidation_001",
        "coding_source_confusion_001",
        "coding_schema_migration_001",
        "coding_retry_policy_001",
    ],
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
            action_budget=20,
            workspace_root=str(tmp_path),
        ),
    )

    scenario = load_fixture_scenario(task_id)
    assert scenario is not None
    assert set(fixture_scenario_ids()).issuperset(
        {
            "coding_cache_invalidation_001",
            "coding_source_confusion_001",
            "coding_schema_migration_001",
            "coding_retry_policy_001",
        }
    )
    for step in scenario["steps"]:
        if step.get("tool_name") == "read_file":
            assert step["path"] in scenario["initial_files"]
    assert run["interaction_metrics"]["visible_test_success"] is True
    assert run["interaction_metrics"]["hidden_validation_success"] is True
    assert run["interaction_metrics"]["evaluator_success"] is True
    assert run["run_metadata"]["tool_loop_iterations"] >= 10


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
                    "changed_files": [],
                    "uncertainties": ["Memory is incomplete."],
                    "next_action": "Inspect the workspace.",
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
                action_budget=16,
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
    assert run["task_state_probe_summary"]["eligible_probe_count"] == len(
        probe_events
    )
    assert set(adapter.probe_token_budgets) == {640}
    assert run["interaction_metrics"]["evaluator_success"] is True
