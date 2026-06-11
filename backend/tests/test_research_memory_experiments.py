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
    assert run["task_state_probe_summary"]["eligible_probe_count"] == len(
        probe_events
    )
    assert set(adapter.probe_token_budgets) == {640}
    assert run["interaction_metrics"]["evaluator_success"] is True
