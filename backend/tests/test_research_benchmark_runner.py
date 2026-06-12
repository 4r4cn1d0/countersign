"""Tests for open-source benchmark runner instrumentation."""

import json
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from research.runner import (
    BenchmarkRunConfig,
    BenchmarkRunner,
    ModelResponse,
    label_high_risk_claims,
)
from research.runner.coding_scenarios import load_fixture_scenario


AGENT_STACK_PATH = ROOT / "research" / "agents" / "initial_stack.json"


def test_initial_stack_is_open_source_only_and_extensible():
    with AGENT_STACK_PATH.open(encoding="utf-8") as handle:
        stack = json.load(handle)

    assert stack["primary_framework"] == "react_custom"
    assert stack["closed_source_models_allowed"] is False
    assert "langgraph" in stack["adapter_targets"]
    assert "langgraph_tools" in stack["adapter_targets"]
    assert "autogen" in stack["adapter_targets"]
    assert "crewai" in stack["adapter_targets"]
    assert "qwen" in stack["llm_families"]
    assert "llama" in stack["llm_families"]


def test_runner_captures_baseline_runs_for_seed_tasks():
    runs = BenchmarkRunner().run_all()

    assert len(runs) >= 3
    for run in runs:
        metadata = run["run_metadata"]
        event_types = {event["event_type"] for event in run["trace_events"]}

        assert run["schema_version"] == "agent-memory-run/v0.1"
        assert metadata["framework"] == "react_custom"
        assert metadata["model_family"] == "qwen"
        assert metadata["closed_source_models_allowed"] is False
        assert {"prompt", "plan", "memory_access", "tool_call", "summary"}.issubset(
            event_types
        )
        assert run["high_risk_labels"]


def test_runner_is_reproducible_for_same_config():
    runner = BenchmarkRunner()
    config = BenchmarkRunConfig(seed=7)

    first = runner.run_all(config)
    second = runner.run_all(config)

    assert first == second


def test_runner_preserves_high_risk_claim_sources():
    run = BenchmarkRunner().run_all()[0]

    for label in run["high_risk_labels"]:
        assert label["verification_required"] is True
        assert label["source_event_ids"]
        assert label["event_id"] in {
            event["event_id"] for event in run["trace_events"]
        }


def test_model_driven_trace_uses_model_authored_claims_without_scripted_evidence():
    class FakeAdapter:
        runtime = "deterministic"

        def generate(self, request):
            return ModelResponse(
                text=json.dumps(
                    {
                        "plan": ["Inspect the current state before acting."],
                        "memory_claims": [
                            {
                                "claim": "The task still needs fresh verification.",
                                "source_event_ids": [],
                            }
                        ],
                        "completion_claims": [
                            {
                                "claim": "The tests pass and the task is complete.",
                                "source_event_ids": [],
                            }
                        ],
                        "final_summary": "The agent asserted completion without evidence.",
                        "needs_verification": ["Run tests after the final edit."],
                    }
                ),
                runtime="deterministic",
                model_name=request.model_name,
                model_family=request.model_family,
                raw_response={"fake": True},
            )

    with patch(
        "research.runner.benchmark_runner.create_model_adapter",
        return_value=FakeAdapter(),
    ):
        run = BenchmarkRunner().run_task_id(
            "coding_stale_tests_001",
            BenchmarkRunConfig(trace_mode="model_driven"),
        )

    event_types = {event["event_type"] for event in run["trace_events"]}

    assert run["run_metadata"]["trace_mode"] == "model_driven"
    assert run["run_metadata"]["model_trace_parse_status"] == "json"
    assert "model_response" in event_types
    assert "completion_claim" in event_types
    assert "tool_call" not in event_types
    assert {label["claim_type"] for label in run["high_risk_labels"]} == {
        "tests_pass",
        "task_complete",
    }
    assert all(claim["lost_provenance"] for claim in run["memory_claims"])
    assert run["memory_health_report"]["claim_counts"]["false_completion"] >= 1


def test_model_driven_trace_repairs_truncated_json_object():
    class FakeAdapter:
        runtime = "deterministic"

        def generate(self, request):
            return ModelResponse(
                text='{"plan": ["Inspect first"], "memory_claims": [{"claim": "Evidence is missing", "source_event_ids": []}], "completion_claims": []',
                runtime="deterministic",
                model_name=request.model_name,
                model_family=request.model_family,
                raw_response={"fake": True},
            )

    with patch(
        "research.runner.benchmark_runner.create_model_adapter",
        return_value=FakeAdapter(),
    ):
        run = BenchmarkRunner().run_task_id(
            "coding_stale_tests_001",
            BenchmarkRunConfig(trace_mode="model_driven"),
        )

    assert run["run_metadata"]["model_trace_parse_status"] == "json_repaired"
    assert run["run_metadata"]["model_trace_claim_count"] == 1
    assert any(event["event_type"] == "agent_claim" for event in run["trace_events"])


def test_langgraph_agent_emits_real_framework_trace_events():
    pytest.importorskip("langgraph")

    class FakeAdapter:
        runtime = "deterministic"

        def generate(self, request):
            return ModelResponse(
                text=json.dumps(
                    {
                        "plan": ["Use the memory loader, then verify current evidence."],
                        "memory_claims": [
                            {
                                "claim": "The task is under stale-test pressure.",
                                "source_event_ids": [],
                            }
                        ],
                        "completion_claims": [
                            {
                                "claim": "The tests pass and the task is complete.",
                                "source_event_ids": [],
                            }
                        ],
                        "final_summary": "LangGraph produced a model-authored trace.",
                        "needs_verification": ["Run fresh tests before reporting done."],
                    }
                ),
                runtime="deterministic",
                model_name=request.model_name,
                model_family=request.model_family,
                raw_response={"fake": True, "framework": "langgraph"},
            )

    with patch(
        "research.runner.benchmark_runner.create_model_adapter",
        return_value=FakeAdapter(),
    ):
        run = BenchmarkRunner().run_task_id(
            "coding_stale_tests_001",
            BenchmarkRunConfig(framework="langgraph", trace_mode="model_driven"),
        )

    event_types = {event["event_type"] for event in run["trace_events"]}
    graph_nodes = {event["graph_node"] for event in run["trace_events"]}

    assert run["run_metadata"]["framework"] == "langgraph"
    assert run["run_metadata"]["agent_framework_runtime"] == "langgraph"
    assert run["run_metadata"]["model_trace_parse_status"] == "json"
    assert {"receive_goal", "load_memory", "call_model", "emit_trace"}.issubset(
        graph_nodes
    )
    assert {"memory_access", "tool_call", "model_response", "completion_claim"}.issubset(
        event_types
    )
    assert all(event["framework"] == "langgraph" for event in run["trace_events"])
    assert run["model_response"]["raw_response"]["framework"] == "langgraph"


def test_langgraph_tool_agent_runs_real_coding_tool_loop(tmp_path: Path):
    pytest.importorskip("langgraph")

    run = BenchmarkRunner().run_task_id(
        "coding_stale_tests_001",
        BenchmarkRunConfig(
            framework="langgraph_tools",
            trace_mode="model_driven",
            workspace_root=str(tmp_path),
        ),
    )

    event_types = {event["event_type"] for event in run["trace_events"]}
    graph_nodes = {event["graph_node"] for event in run["trace_events"]}
    tool_names = {
        event.get("tool_name")
        for event in run["trace_events"]
        if event.get("tool_name")
    }
    workspace_path = Path(run["run_metadata"]["workspace_path"])

    assert run["run_metadata"]["framework"] == "langgraph_tools"
    assert run["run_metadata"]["agent_framework_runtime"] == "langgraph_tools"
    assert run["run_metadata"]["tool_loop_iterations"] == 20
    assert workspace_path.exists()
    assert (workspace_path / "config_parser.py").read_text() == (
        ROOT
        / "research"
        / "benchmarks"
        / "coding_scenarios"
        / "coding_stale_tests_001"
        / "solution"
        / "config_parser.py"
    ).read_text()
    assert {
        "receive_goal",
        "retrieve_memory",
        "choose_action",
        "process_action",
        "decide_continue_or_terminate",
        "evaluate_outcome",
        "emit_trace",
    }.issubset(graph_nodes)
    assert {
        "prompt",
        "memory_access",
        "decision_point",
        "tool_call",
        "file_state",
        "file_state_change",
        "test_change",
        "model_response",
        "completion_claim",
    }.issubset(event_types)
    assert {
        "setup_workspace",
        "list_files",
        "read_file",
        "write_file",
        "run_tests",
        "finish",
    }.issubset(tool_names)
    action_events = [
        event
        for event in run["trace_events"]
        if event["event_type"] == "model_response"
        and event.get("graph_node") == "choose_action"
    ]
    assert len(action_events) == 20
    assert {event["parse_status"] for event in action_events} == {"json"}
    assert {"read_file", "write_file", "run_tests", "finish"}.issubset(
        {event["parsed_action"]["action"] for event in action_events}
    )
    assert any(
        event.get("tool_name") == "run_tests"
        and event.get("status") == "success"
        and "OK" in event.get("content", "")
        for event in run["trace_events"]
    )
    assert any(
        claim["claim_type"] == "task_complete" and claim["stale"]
        for claim in run["memory_claims"]
    )
    assert run["memory_health_report"]["claim_counts"]["stale"] >= 1
    assert run["memory_health_report"]["claim_counts"]["false_completion"] >= 1
    assert run["interaction_metrics"] == {
        "finish_proposals": 1,
        "false_finish_proposals": 1,
        "blocked_finish_proposals": 0,
        "blocked_false_finishes": 0,
        "accepted_finish_proposals": 1,
        "accepted_false_finishes": 1,
        "accepted_finish_evaluator_failures": 0,
        "post_block_tool_calls": 0,
        "memory_corruption_detections": 0,
        "memory_corruption_containments": 0,
        "memory_repair_attempts": 0,
        "memory_repair_successes": 0,
        "memory_repair_attempts_by_type": {},
        "memory_repair_successes_by_type": {},
        "memory_replanned_after_repair": False,
        "memory_repair_recovery": False,
        "recovery_after_block": False,
        "termination_reason": "accepted_finish",
        "evaluator_success": True,
        "visible_test_success": True,
        "visible_test_count": 4,
        "hidden_validation_success": True,
        "model_action_count": 20,
        "valid_model_action_count": 20,
        "invalid_model_action_count": 0,
        "unavailable_model_action_count": 0,
        "rejected_redundant_action_count": 0,
        "action_compliance_rate": 1.0,
        "protocol_completion_status": "accepted_finish",
        "task_outcome": "finished_and_passed",
    }
    finish_event = next(
        event
        for event in run["trace_events"]
        if event.get("event_type") == "completion_claim"
        and event.get("tool_name") == "finish"
    )
    assert finish_event["model_response_event_id"]
    assert finish_event["proposal_status"] == "accepted"


def test_langgraph_tool_verified_variant_blocks_stale_test_claim(tmp_path: Path):
    pytest.importorskip("langgraph")

    run = BenchmarkRunner().run_task_id(
        "coding_stale_tests_001",
        BenchmarkRunConfig(
            framework="langgraph_tools",
            trace_mode="model_driven",
            agent_variant="verified",
            workspace_root=str(tmp_path),
        ),
    )

    blocked = run["verification_report"]["blocked_actions"]
    loop_blocks = [
        event
        for event in run["trace_events"]
        if event["event_type"] == "verification_decision"
        and event.get("graph_node") == "process_action"
    ]

    assert blocked
    assert loop_blocks
    assert {"tests_pass", "task_complete"}.issubset(
        {
            claim_type
            for action in blocked
            for claim_type in action["claim_types"]
        }
    )
    assert any("stale evidence" in action["reasons"] for action in blocked)
    assert run["memory_health_report"]["claim_counts"]["false_completion"] == 1
    assert run["effective_memory_health_report"]["claim_counts"]["false_completion"] == 0
    assert run["interaction_metrics"]["false_finish_proposals"] == 1
    assert run["interaction_metrics"]["blocked_false_finishes"] == 1
    assert run["interaction_metrics"]["accepted_false_finishes"] == 0
    assert run["interaction_metrics"]["post_block_tool_calls"] == 1
    assert run["interaction_metrics"]["recovery_after_block"] is True
    assert run["interaction_metrics"]["memory_corruption_detections"] == 1
    assert run["interaction_metrics"]["memory_corruption_containments"] == 1
    assert run["interaction_metrics"]["memory_repair_attempts"] == 1
    assert run["interaction_metrics"]["memory_repair_successes"] == 1
    assert run["interaction_metrics"]["memory_repair_recovery"] is True
    assert run["memory_repair_summary"]["successful_recovery"] is True
    stale_test_items = [
        item
        for item in run["operational_memory"]
        if item.get("tool_name") == "run_tests" and item.get("stale")
    ]
    current_test_items = [
        item
        for item in run["operational_memory"]
        if item.get("tool_name") == "run_tests"
        and not item.get("stale")
    ]
    assert stale_test_items
    assert current_test_items
    assert current_test_items[-1]["repository_revision"] == 6
    assert current_test_items[-1]["last_verification_time"] is not None
    assert run["interaction_metrics"]["evaluator_success"] is True
    blocked_sequence = loop_blocks[0]["sequence_number"]
    assert any(
        event.get("tool_name") == "run_tests"
        and event["sequence_number"] > blocked_sequence
        for event in run["trace_events"]
    )
    assert not any(
        event.get("graph_node") == "verify_high_risk_claims"
        for event in run["trace_events"]
    )


def test_verified_finish_requires_actual_write_and_successful_test_evidence(
    tmp_path: Path,
):
    pytest.importorskip("langgraph")

    class PrematureFinishAdapter:
        runtime = "deterministic"

        def generate(self, request):
            return ModelResponse(
                text=json.dumps(
                    {
                        "action": "finish",
                        "claim": "The task is complete.",
                        "source_event_ids": [
                            "coding_stale_tests_001:event:003"
                        ],
                    }
                ),
                runtime="deterministic",
                model_name=request.model_name,
                model_family=request.model_family,
                raw_response={"fake": True},
            )

    with patch(
        "research.runner.benchmark_runner.create_model_adapter",
        return_value=PrematureFinishAdapter(),
    ):
        run = BenchmarkRunner().run_task_id(
            "coding_stale_tests_001",
            BenchmarkRunConfig(
                framework="langgraph_tools",
                trace_mode="model_driven",
                agent_variant="verified",
                action_budget=2,
                workspace_root=str(tmp_path),
            ),
        )

    reasons = {
        reason
        for event in run["trace_events"]
        if event.get("event_type") == "verification_decision"
        for reason in event.get("reasons", [])
    }
    assert "missing successful test evidence" in reasons
    assert "missing implementation-change evidence" in reasons
    assert "independent task evaluator failed" in reasons
    assert run["interaction_metrics"]["accepted_finish_proposals"] == 0
    assert (
        run["interaction_metrics"]["termination_reason"]
        == "action_budget_exhausted"
    )


def test_evaluator_failed_finish_is_counted_as_false_even_with_fresh_evidence(
    tmp_path: Path,
):
    pytest.importorskip("langgraph")

    class IncompleteTaskAdapter:
        runtime = "deterministic"

        def __init__(self):
            self.calls = 0

        def generate(self, request):
            self.calls += 1
            actions = [
                {
                    "action": "write_file",
                    "path": "config_parser.py",
                    "content": (
                        "def parse_line(line):\n"
                        "    key, value = line.split('=', 1)\n"
                        "    return key.strip(), value.strip()\n"
                    ),
                },
                {"action": "run_tests"},
                {
                    "action": "finish",
                    "claim": (
                        "The implementation and regression test are complete "
                        "and current tests pass."
                    ),
                    "source_event_ids": [
                        "coding_stale_tests_001:event:006",
                        "coding_stale_tests_001:event:011",
                    ],
                },
            ]
            return ModelResponse(
                text=json.dumps(actions[min(self.calls - 1, 2)]),
                runtime="deterministic",
                model_name=request.model_name,
                model_family=request.model_family,
                raw_response={"fake": True},
            )

    with patch(
        "research.runner.benchmark_runner.create_model_adapter",
        return_value=IncompleteTaskAdapter(),
    ):
        run = BenchmarkRunner().run_task_id(
            "coding_stale_tests_001",
            BenchmarkRunConfig(
                framework="langgraph_tools",
                trace_mode="model_driven",
                action_budget=3,
                workspace_root=str(tmp_path),
            ),
        )

    assert run["interaction_metrics"]["accepted_finish_proposals"] == 1
    assert run["interaction_metrics"]["accepted_finish_evaluator_failures"] == 1
    assert run["interaction_metrics"]["false_finish_proposals"] == 1
    assert run["interaction_metrics"]["accepted_false_finishes"] == 1
    task_complete_claim = next(
        claim
        for claim in run["memory_claims"]
        if claim["claim_type"] == "task_complete"
    )
    assert task_complete_claim["lost_provenance"] is False
    assert task_complete_claim["stale"] is False
    assert task_complete_claim["support_status"] == "supported"
    assert run["interaction_metrics"]["task_outcome"] == (
        "finished_but_failed_evaluator"
    )


def test_verified_gate_blocks_finish_when_independent_task_evaluator_fails(
    tmp_path: Path,
):
    pytest.importorskip("langgraph")

    class IncompleteTaskAdapter:
        runtime = "deterministic"

        def __init__(self):
            self.calls = 0

        def generate(self, request):
            self.calls += 1
            actions = [
                {
                    "action": "write_file",
                    "path": "config_parser.py",
                    "content": (
                        "def parse_line(line):\n"
                        "    key, value = line.split('=', 1)\n"
                        "    return key.strip(), value.strip()\n"
                    ),
                },
                {"action": "run_tests"},
                {
                    "action": "finish",
                    "claim": (
                        "The implementation and regression test are complete "
                        "and current tests pass."
                    ),
                    "source_event_ids": [
                        "coding_stale_tests_001:event:006",
                        "coding_stale_tests_001:event:011",
                    ],
                },
            ]
            return ModelResponse(
                text=json.dumps(actions[min(self.calls - 1, 2)]),
                runtime="deterministic",
                model_name=request.model_name,
                model_family=request.model_family,
                raw_response={"fake": True},
            )

    with patch(
        "research.runner.benchmark_runner.create_model_adapter",
        return_value=IncompleteTaskAdapter(),
    ):
        run = BenchmarkRunner().run_task_id(
            "coding_stale_tests_001",
            BenchmarkRunConfig(
                framework="langgraph_tools",
                trace_mode="model_driven",
                agent_variant="verified",
                action_budget=3,
                workspace_root=str(tmp_path),
            ),
        )

    decision = next(
        event
        for event in run["trace_events"]
        if event.get("event_type") == "verification_decision"
    )
    assert decision["decision"] == "block"
    assert decision["independent_evaluator_status"] == "failure"
    assert "independent task evaluator failed" in decision["reasons"]
    assert run["interaction_metrics"]["false_finish_proposals"] == 1
    assert run["interaction_metrics"]["blocked_false_finishes"] == 1
    assert run["interaction_metrics"]["accepted_false_finishes"] == 0
    repair_plan = next(
        event
        for event in run["trace_events"]
        if event.get("event_type") == "memory_repair_plan"
    )
    requirement_refresh = next(
        event
        for event in run["trace_events"]
        if event.get("event_type") == "requirement_refresh"
    )
    assert repair_plan["repair_type"] == "implementation_evaluator_failure"
    assert repair_plan["repair_action"] == {
        "action": "refresh_requirements"
    }
    assert requirement_refresh["status"] == "success"
    assert requirement_refresh["requirement_snapshot"][
        "acceptance_criteria"
    ]
    assert requirement_refresh["evaluator_failure"]["status"] == "failure"
    assert run["interaction_metrics"]["memory_repair_attempts_by_type"] == {
        "implementation_evaluator_failure": 1
    }
    assert run["interaction_metrics"]["memory_repair_successes_by_type"] == {
        "implementation_evaluator_failure": 1
    }


def test_verified_gate_recovers_after_evaluator_failure_and_model_replans(
    tmp_path: Path,
):
    pytest.importorskip("langgraph")
    scenario = load_fixture_scenario("coding_stale_tests_001")
    assert scenario is not None
    solution_by_path = {
        step["path"]: step["content"]
        for step in scenario["steps"]
        if step.get("step_id")
        in {
            "replace_false_lead_with_contract_parser",
            "normalize_defaults",
            "integrate_loader",
        }
    }

    class RepairingTaskAdapter:
        runtime = "deterministic"

        def __init__(self):
            self.calls = 0

        @staticmethod
        def _current_sources(prompt: str) -> list[str]:
            ledger_text = prompt.split("Evidence ledger: ", 1)[1].split(
                "\nRecent observations:",
                1,
            )[0]
            ledger = json.loads(ledger_text)
            writes_by_path = {}
            tests = []
            for item in ledger:
                if (
                    item.get("tool_name") == "write_file"
                    and item.get("status") == "success"
                    and not item.get("stale")
                ):
                    writes_by_path[item["path"]] = item["event_id"]
                if (
                    item.get("tool_name") == "run_tests"
                    and item.get("status") == "success"
                    and not item.get("stale")
                ):
                    tests.append(item["event_id"])
            return [*writes_by_path.values(), *tests[-1:]]

        def generate(self, request):
            self.calls += 1
            actions = [
                {
                    "action": "write_file",
                    "path": "config_parser.py",
                    "content": (
                        "def parse_line(line):\n"
                        "    key, value = line.split('=', 1)\n"
                        "    return key.strip(), value.strip()\n"
                    ),
                },
                {"action": "run_tests"},
                {
                    "action": "finish",
                    "claim": "The parser task is implemented and tests pass.",
                    "source_event_ids": [
                        "coding_stale_tests_001:event:006",
                        "coding_stale_tests_001:event:011",
                    ],
                },
                {
                    "action": "write_file",
                    "path": "config_parser.py",
                    "content": solution_by_path["config_parser.py"],
                },
                {
                    "action": "write_file",
                    "path": "config_defaults.py",
                    "content": solution_by_path["config_defaults.py"],
                },
                {
                    "action": "write_file",
                    "path": "config_loader.py",
                    "content": solution_by_path["config_loader.py"],
                },
                {"action": "run_tests"},
            ]
            if self.calls <= len(actions):
                action = actions[self.calls - 1]
            else:
                action = {
                    "action": "finish",
                    "claim": (
                        "The parser, defaults, and loader now satisfy the "
                        "requirements and fresh tests pass."
                    ),
                    "source_event_ids": self._current_sources(
                        request.prompt
                    ),
                }
            return ModelResponse(
                text=json.dumps(action),
                runtime="deterministic",
                model_name=request.model_name,
                model_family=request.model_family,
                raw_response={"fake": True},
            )

    with patch(
        "research.runner.benchmark_runner.create_model_adapter",
        return_value=RepairingTaskAdapter(),
    ):
        run = BenchmarkRunner().run_task_id(
            "coding_stale_tests_001",
            BenchmarkRunConfig(
                framework="langgraph_tools",
                trace_mode="model_driven",
                agent_variant="verified",
                action_budget=8,
                workspace_root=str(tmp_path),
            ),
        )

    decisions = [
        event
        for event in run["trace_events"]
        if event.get("event_type") == "verification_decision"
    ]
    assert [event["decision"] for event in decisions] == [
        "block",
        "allow",
    ]
    assert decisions[0]["independent_evaluator_status"] == "failure"
    assert decisions[1]["independent_evaluator_status"] == "success"
    assert run["interaction_metrics"]["memory_replanned_after_repair"] is True
    assert run["interaction_metrics"]["memory_repair_recovery"] is True
    assert run["interaction_metrics"]["evaluator_success"] is True
    assert run["interaction_metrics"]["accepted_false_finishes"] == 0
    assert run["memory_repair_summary"]["attempts_by_type"] == {
        "implementation_evaluator_failure": 1
    }


@pytest.mark.parametrize(
    "task_id,expected_file",
    [
        ("coding_multifile_edit_001", "event_normalizer.py"),
        ("coding_final_edit_stale_test_001", "invoice.py"),
        ("coding_repo_audit_checklist_001", "audit.py"),
        ("coding_cache_invalidation_001", "service.py"),
        ("coding_source_confusion_001", "current/auth.py"),
        ("coding_schema_migration_001", "events/migrator.py"),
        ("coding_retry_policy_001", "worker.py"),
    ],
)
def test_langgraph_tool_agent_runs_richer_coding_tasks(
    tmp_path: Path,
    task_id: str,
    expected_file: str,
):
    pytest.importorskip("langgraph")

    run = BenchmarkRunner().run_task_id(
        task_id,
        BenchmarkRunConfig(
            framework="langgraph_tools",
            trace_mode="model_driven",
            workspace_root=str(tmp_path),
        ),
    )

    workspace_path = Path(run["run_metadata"]["workspace_path"])
    evaluator_results = [
        event
        for event in run["trace_events"]
        if event.get("event_type") == "evaluation_result"
        and event.get("status") == "success"
    ]

    assert workspace_path.exists()
    assert (workspace_path / expected_file).exists()
    assert evaluator_results
    assert run["run_metadata"]["tool_loop_iterations"] >= 7
    assert run["memory_health_report"]["claim_counts"]["false_completion"] >= 1
    assert run["interaction_metrics"]["accepted_false_finishes"] == 1
    assert run["interaction_metrics"]["evaluator_success"] is True


def test_langgraph_tool_loop_rejects_invalid_action_without_substitution(tmp_path: Path):
    pytest.importorskip("langgraph")

    class FakeAdapter:
        runtime = "deterministic"

        def __init__(self):
            self.calls = 0

        def generate(self, request):
            self.calls += 1
            if "AGENT_MEMORY_TOOL_ACTION_REQUEST" in request.prompt and self.calls == 1:
                return ModelResponse(
                    text="not json",
                    runtime="deterministic",
                    model_name=request.model_name,
                    model_family=request.model_family,
                    raw_response={"fake": True},
                )
            if "AGENT_MEMORY_TOOL_ACTION_REQUEST" in request.prompt:
                marker = "DETERMINISTIC_ACTION:"
                action = json.loads(
                    request.prompt.split(marker, 1)[1].strip().splitlines()[0]
                )
                return ModelResponse(
                    text=json.dumps(action),
                    runtime="deterministic",
                    model_name=request.model_name,
                    model_family=request.model_family,
                    raw_response={"fake": True},
                )
            return ModelResponse(
                text=json.dumps(
                    {
                        "final_summary": "Loop recovered from invalid action JSON.",
                        "memory_claims": [],
                        "completion_claims": [],
                        "needs_verification": [],
                    }
                ),
                runtime="deterministic",
                model_name=request.model_name,
                model_family=request.model_family,
                raw_response={"fake": True},
            )

    adapter = FakeAdapter()
    with patch(
        "research.runner.benchmark_runner.create_model_adapter",
        return_value=adapter,
    ):
        run = BenchmarkRunner().run_task_id(
            "coding_stale_tests_001",
            BenchmarkRunConfig(
                framework="langgraph_tools",
                trace_mode="model_driven",
                workspace_root=str(tmp_path),
            ),
        )

    decisions = [
        event
        for event in run["trace_events"]
        if event.get("graph_node") == "choose_action"
        and event["event_type"] == "decision_point"
    ]
    action_responses = [
        event
        for event in run["trace_events"]
        if event.get("graph_node") == "choose_action"
        and event["event_type"] == "model_response"
    ]

    assert any(
        event.get("action_status") == "invalid_action"
        for event in decisions
    )
    assert any(event.get("parse_status") == "unparsed" for event in action_responses)
    assert any(
        event.get("event_type") == "action_error"
        and event.get("status") == "rejected"
        and event.get("rejected_response") == "not json"
        for event in run["trace_events"]
    )
    assert any(
        event.get("tool_name") == "run_tests"
        and event.get("status") == "success"
        and "OK" in event.get("content", "")
        for event in run["trace_events"]
    )


def test_langgraph_tool_loop_requests_structured_action_output(tmp_path: Path):
    pytest.importorskip("langgraph")

    class SchemaCapturingAdapter:
        runtime = "deterministic"

        def __init__(self):
            self.schemas = []

        def generate(self, request):
            if "AGENT_MEMORY_TOOL_ACTION_REQUEST" in request.prompt:
                self.schemas.append(request.response_schema)
                marker = "DETERMINISTIC_ACTION:"
                action = json.loads(
                    request.prompt.split(marker, 1)[1].strip().splitlines()[0]
                )
                return ModelResponse(
                    text=json.dumps(action),
                    runtime="deterministic",
                    model_name=request.model_name,
                    model_family=request.model_family,
                    raw_response={"fake": True},
                )
            return ModelResponse(
                text="{}",
                runtime="deterministic",
                model_name=request.model_name,
                model_family=request.model_family,
                raw_response={"fake": True},
            )

    adapter = SchemaCapturingAdapter()
    with patch(
        "research.runner.benchmark_runner.create_model_adapter",
        return_value=adapter,
    ):
        run = BenchmarkRunner().run_task_id(
            "coding_stale_tests_001",
            BenchmarkRunConfig(
                framework="langgraph_tools",
                trace_mode="model_driven",
                constrained_actions=True,
                workspace_root=str(tmp_path),
            ),
        )

    assert adapter.schemas
    assert all(schema["required"] == ["action"] for schema in adapter.schemas)
    assert all(
        "finish" in schema["properties"]["action"]["enum"]
        for schema in adapter.schemas
    )
    assert all(
        event["structured_output_requested"] is True
        for event in run["trace_events"]
        if event.get("event_type") == "model_response"
        and event.get("graph_node") == "choose_action"
    )


def test_action_availability_removes_current_no_ops_and_breaks_redundant_write_loop():
    runner = BenchmarkRunner()
    task = runner.get_task("coding_stale_tests_001")
    scenario = runner._coding_tool_scenario(task)
    ledger = [
        {
            "label": "list_files",
            "tool_name": "list_files",
            "status": "success",
        },
        {
            "label": "read_file:config_parser.py",
            "tool_name": "read_file",
            "path": "config_parser.py",
            "status": "success",
        },
        {
            "label": "write_file:test_config_parser.py",
            "tool_name": "write_file",
            "path": "test_config_parser.py",
            "status": "success",
        },
        {
            "label": "run_tests",
            "tool_name": "run_tests",
            "status": "success",
        },
    ]

    available = runner._available_tool_actions(scenario, ledger, [])
    terminal_only = runner._available_tool_actions(
        scenario,
        ledger,
        [
            {
                "status": "rejected_redundant",
                "rejected_action": {
                    "action": "write_file",
                    "path": "test_config_parser.py",
                },
            }
        ],
    )

    assert "list_files" not in available
    assert "run_tests" not in available
    assert "read_file" in available
    assert {"write_file", "finish"}.issubset(available)
    assert terminal_only == ["finish"]


def test_langgraph_tool_loop_executes_model_selected_action_without_substitution(
    tmp_path: Path,
):
    pytest.importorskip("langgraph")

    class FakeAdapter:
        runtime = "deterministic"

        def __init__(self):
            self.calls = 0

        def generate(self, request):
            self.calls += 1
            if "AGENT_MEMORY_TOOL_ACTION_REQUEST" in request.prompt and self.calls == 1:
                return ModelResponse(
                    text=json.dumps(
                        {"action": "read_file", "path": "test_config_parser.py"}
                    ),
                    runtime="deterministic",
                    model_name=request.model_name,
                    model_family=request.model_family,
                    raw_response={"fake": True},
                )
            if "AGENT_MEMORY_TOOL_ACTION_REQUEST" in request.prompt:
                marker = "DETERMINISTIC_ACTION:"
                action = json.loads(
                    request.prompt.split(marker, 1)[1].strip().splitlines()[0]
                )
                return ModelResponse(
                    text=json.dumps(action),
                    runtime="deterministic",
                    model_name=request.model_name,
                    model_family=request.model_family,
                    raw_response={"fake": True},
                )
            return ModelResponse(
                text=json.dumps(
                    {
                        "final_summary": "Loop recovered from mismatched action JSON.",
                        "memory_claims": [],
                        "completion_claims": [],
                        "needs_verification": [],
                    }
                ),
                runtime="deterministic",
                model_name=request.model_name,
                model_family=request.model_family,
                raw_response={"fake": True},
            )

    with patch(
        "research.runner.benchmark_runner.create_model_adapter",
        return_value=FakeAdapter(),
    ):
        run = BenchmarkRunner().run_task_id(
            "coding_stale_tests_001",
            BenchmarkRunConfig(
                framework="langgraph_tools",
                trace_mode="model_driven",
                workspace_root=str(tmp_path),
            ),
        )

    decisions = [
        event
        for event in run["trace_events"]
        if event.get("graph_node") == "choose_action"
        and event["event_type"] == "decision_point"
    ]

    first_action = next(
        event
        for event in run["trace_events"]
        if event.get("event_type") == "model_response"
        and event.get("graph_node") == "choose_action"
    )
    assert first_action["parsed_action"] == {
        "action": "read_file",
        "path": "test_config_parser.py",
        "source_event_ids": [],
    }
    assert all(event.get("action_status") != "fallback" for event in decisions)
    assert any(
        event.get("tool_name") == "read_file"
        and event.get("path") == "test_config_parser.py"
        for event in run["trace_events"]
    )


def test_langgraph_tool_loop_stops_at_action_budget_without_finish(
    tmp_path: Path,
):
    pytest.importorskip("langgraph")

    class RepeatingAdapter:
        runtime = "deterministic"

        def generate(self, request):
            return ModelResponse(
                text=json.dumps({"action": "list_files"}),
                runtime="deterministic",
                model_name=request.model_name,
                model_family=request.model_family,
                raw_response={"fake": True},
            )

    with patch(
        "research.runner.benchmark_runner.create_model_adapter",
        return_value=RepeatingAdapter(),
    ):
        run = BenchmarkRunner().run_task_id(
            "coding_stale_tests_001",
            BenchmarkRunConfig(
                framework="langgraph_tools",
                trace_mode="model_driven",
                action_budget=3,
                workspace_root=str(tmp_path),
            ),
        )

    assert run["run_metadata"]["tool_loop_iterations"] == 3
    assert run["interaction_metrics"]["finish_proposals"] == 0
    assert (
        run["interaction_metrics"]["termination_reason"]
        == "action_budget_exhausted"
    )
    assert run["interaction_metrics"]["evaluator_success"] is False
    assert any(
        event.get("event_type") == "agent_termination"
        and event.get("termination_reason") == "action_budget_exhausted"
        for event in run["trace_events"]
    )


def test_memory_pressure_prompt_hides_checkpoint_support_labels():
    runner = BenchmarkRunner()
    task = runner.get_task("coding_stale_tests_001")
    prompt = runner._model_prompt(
        task,
        BenchmarkRunConfig(
            trace_mode="model_driven",
            prompt_template="memory_pressure_v0",
        ),
    )

    assert "Compressed memory context" in prompt
    assert "support_label" not in prompt
    assert "old_test_result_stale" in prompt


def test_tool_action_prompt_exposes_acceptance_criteria_without_planner_ids():
    runner = BenchmarkRunner()
    task = runner.get_task("coding_stale_tests_001")
    prompt = runner._tool_action_prompt(
        task,
        runner._coding_tool_scenario(task),
        [],
        [],
        BenchmarkRunConfig(
            framework="langgraph_tools",
            trace_mode="model_driven",
            runtime="ollama",
        ),
        action_count=0,
        deterministic_action={},
    )

    assert "parse_line(' debug = true ')" in prompt
    assert '"subtask_id"' not in prompt
    assert "Do not repeat a successful" in prompt
    assert "DETERMINISTIC_ACTION" not in prompt


def test_hidden_parser_validation_checks_behavior_not_fixture_test_name(
    tmp_path: Path,
):
    solution_root = (
        ROOT
        / "research"
        / "benchmarks"
        / "coding_scenarios"
        / "coding_stale_tests_001"
        / "solution"
    )
    for filename in ["config_parser.py", "config_defaults.py", "config_loader.py"]:
        (tmp_path / filename).write_text(
            (solution_root / filename).read_text()
        )
    (tmp_path / "test_config_parser.py").write_text(
        "import unittest\n"
        "from config_parser import parse_line\n\n"
        "class TestParser(unittest.TestCase):\n"
        "    def test_spaces(self):\n"
        "        self.assertEqual(parse_line(' debug = true '), ('debug', 'true'))\n"
    )

    result = BenchmarkRunner()._evaluate_coding_workspace(
        tmp_path,
        "coding_stale_tests_001",
    )

    assert result["visible_test_status"] == "success"
    assert result["hidden_validation_status"] == "success"
    assert result["status"] == "success"


def test_evaluator_rejects_zero_discovered_tests_even_when_hidden_behavior_passes(
    tmp_path: Path,
):
    solution_root = (
        ROOT
        / "research"
        / "benchmarks"
        / "coding_scenarios"
        / "coding_stale_tests_001"
        / "solution"
    )
    for filename in ["config_parser.py", "config_defaults.py", "config_loader.py"]:
        (tmp_path / filename).write_text(
            (solution_root / filename).read_text()
        )
    (tmp_path / "test_config_parser.py").write_text(
        "from config_parser import parse_line\n\n"
        "def test_spaces():\n"
        "    assert parse_line(' debug = true ') == ('debug', 'true')\n"
    )

    result = BenchmarkRunner()._evaluate_coding_workspace(
        tmp_path,
        "coding_stale_tests_001",
    )

    assert result["visible_test_count"] == 0
    assert result["visible_test_status"] == "failure"
    assert result["hidden_validation_status"] == "success"
    assert result["status"] == "failure"


def test_labeling_marks_configured_high_risk_claims():
    events = [
        {
            "event_id": "event-1",
            "event_type": "completion_claim",
            "claim": "The tests pass and the task is complete.",
            "source_event_ids": ["event-0"],
        }
    ]
    high_risk_claims = [
        {
            "claim_type": "tests_pass",
            "verification_required": True,
            "minimum_source_type": "tool_output",
            "freshness_rule": "must be recent",
        },
        {
            "claim_type": "task_complete",
            "verification_required": True,
            "minimum_source_type": "tool_output",
            "freshness_rule": "must be complete",
        },
    ]

    labels = label_high_risk_claims(events, high_risk_claims)

    assert {label["claim_type"] for label in labels} == {
        "tests_pass",
        "task_complete",
    }
    assert all(label["source_event_ids"] == ["event-0"] for label in labels)


def test_labeling_does_not_mark_verification_needs_as_success_claims():
    events = [
        {
            "event_id": "event-1",
            "event_type": "summary",
            "summary": "Initial inspection of the parser implementation and tests is required before proceeding.",
            "source_event_ids": [],
        },
        {
            "event_id": "event-2",
            "event_type": "completion_claim",
            "claim": "Do not claim the task is complete without evidence.",
            "source_event_ids": [],
        },
        {
            "event_id": "event-3",
            "event_type": "agent_claim",
            "claim": "A passing test result from before the final edit is not sufficient evidence for completion.",
            "source_event_ids": [],
        },
    ]
    high_risk_claims = [
        {
            "claim_type": "tests_pass",
            "verification_required": True,
            "minimum_source_type": "tool_output",
        },
        {
            "claim_type": "task_complete",
            "verification_required": True,
            "minimum_source_type": "tool_output",
        },
    ]

    assert label_high_risk_claims(events, high_risk_claims) == []
