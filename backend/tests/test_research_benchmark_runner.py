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
    interaction_metrics = dict(run["interaction_metrics"])
    # oracle_proposal_scores is a detailed per-proposal structure (see
    # support_oracle.py) — checked separately below rather than folded
    # into the exact-equality comparison of the simpler scalar fields.
    oracle_proposal_scores = interaction_metrics.pop("oracle_proposal_scores")
    assert interaction_metrics == {
        "finish_proposals": 1,
        "false_finish_proposals": 1,
        "blocked_finish_proposals": 0,
        "blocked_false_finishes": 0,
        "accepted_finish_proposals": 1,
        "accepted_false_finishes": 1,
        "accepted_finish_evaluator_failures": 0,
        "accepted_unsupported_finish": True,
        "accepted_incorrect_finish": False,
        "supported_but_incorrect_finish": False,
        "unsupported_but_correct_finish": True,
        # accepted_unsupported_finish under another name — see
        # _oracle_interaction_metrics's docstring for why both exist.
        "accepted_classifier_unsupported_finish": True,
        # This fixture's completion_policy makes the cited-test-predates-
        # a-relevant-mutation staleness detectable independently of the
        # shared claim classifier, so the oracle agrees it's unsupported.
        "accepted_oracle_unsupported_finish": True,
        "accepted_oracle_uncertain_finish": False,
        "accepted_oracle_supported_finish": False,
        "post_block_tool_calls": 0,
        "memory_corruption_detections": 0,
        "memory_corruption_containments": 0,
        "memory_repair_attempts": 0,
        "memory_repair_successes": 0,
        "memory_repair_attempts_by_type": {},
        "memory_repair_successes_by_type": {},
        "memory_replanned_after_repair": False,
        "memory_replans_required": 0,
        "memory_replans_completed": 0,
        "memory_replans_invalid": 0,
        "memory_repair_recovery": False,
        "detected_corruption": False,
        "attempted_recovery": False,
        "contained_recovery": False,
        "recovery_level": 0,
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
        "prevented_unsafe_actions": 0,
        "prevented_unsafe_claims": 0,
        "action_compliance_rate": 1.0,
        "protocol_completion_status": "accepted_finish",
        "task_outcome": "finished_and_passed",
    }
    assert len(oracle_proposal_scores) == 1
    assert oracle_proposal_scores[0]["support_label"] == "unsupported"
    assert (
        "cited test evidence predates a relevant mutation"
        in oracle_proposal_scores[0]["reasons"]
    )
    finish_event = next(
        event
        for event in run["trace_events"]
        if event.get("event_type") == "completion_claim"
        and event.get("tool_name") == "finish"
    )
    assert finish_event["model_response_event_id"]
    assert finish_event["proposal_status"] == "accepted"
    assert all(event.get("observed_at") for event in run["trace_events"])
    artifacts = run["coding_environment_artifacts"]
    assert artifacts["schema_version"] == (
        "agent-coding-environment-artifacts/v0.1"
    )
    assert len(artifacts["base_commit"]) == 40
    assert run["run_metadata"]["base_commit"] == artifacts["base_commit"]
    assert artifacts["initial_repository_hash"]
    assert artifacts["final_repository_hash"]
    assert artifacts["final_git_status"]["clean"] is False
    assert artifacts["final_diff"]["changed_files"]
    assert artifacts["latest_test_result"]["status"] == "success"
    assert artifacts["hidden_evaluator_result"]["status"] == "success"
    checkpoint = run["operational_memory_checkpoint"]
    assert checkpoint["schema_version"] == (
        "agent-operational-memory-checkpoint/v0.1"
    )
    assert checkpoint["workspace_revision"] == 6
    assert len(checkpoint["sha256"]) == 64


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
    assert run["interaction_metrics"]["detected_corruption"] is True
    assert run["interaction_metrics"]["attempted_recovery"] is True
    assert run["interaction_metrics"]["contained_recovery"] is True
    assert run["interaction_metrics"]["recovery_level"] == 4
    assert run["memory_repair_summary"]["successful_recovery"] is True
    assert run["memory_repair_summary"]["contained_recovery"] is True
    assert run["memory_repair_summary"]["recovery_level"] == 4
    stale_test_items = [
        item
        for item in run["operational_memory"]
        if item.get("tool_name") == "run_tests" and item.get("stale")
    ]
    current_test_items = [
        item
        for item in run["operational_memory"]
        if item.get("tool_name")
        in {"run_tests", "run_full_tests", "run_targeted_tests"}
        and not item.get("stale")
    ]
    assert stale_test_items
    assert current_test_items
    assert current_test_items[-1]["repository_revision"] == 6
    assert current_test_items[-1]["last_verification_time"] is not None
    assert run["interaction_metrics"]["evaluator_success"] is True
    blocked_sequence = loop_blocks[0]["sequence_number"]
    assert any(
        event.get("tool_name") == "run_full_tests"
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
    # The hidden/ground-truth evaluator must never gate the online finish
    # decision (see _evaluate_finish_proposal) — only trace-based evidence
    # checks do.
    assert "independent task evaluator failed" not in reasons
    assert run["interaction_metrics"]["accepted_finish_proposals"] == 0
    assert (
        run["interaction_metrics"]["termination_reason"]
        == "action_budget_exhausted"
    )


def test_evaluator_failure_with_fresh_evidence_is_supported_but_incorrect(
    tmp_path: Path,
):
    """A well-supported claim that the hidden evaluator rejects is not

    counted as unsupported/false — support and correctness are separate
    failure classes. It must instead land in supported_but_incorrect_finish,
    since the relevant defect wasn't visible in the evidence available
    before termination.
    """
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
    assert run["interaction_metrics"]["accepted_incorrect_finish"] is True
    assert run["interaction_metrics"]["false_finish_proposals"] == 0
    assert run["interaction_metrics"]["accepted_false_finishes"] == 0
    assert run["interaction_metrics"]["accepted_unsupported_finish"] is False
    assert run["interaction_metrics"]["supported_but_incorrect_finish"] is True
    assert run["interaction_metrics"]["unsupported_but_correct_finish"] is False
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


def test_verified_gate_allows_finish_when_only_hidden_validation_fails(
    tmp_path: Path,
):
    """The online finish gate must not consult hidden/ground-truth validation.

    A finish backed by real trace evidence (a successful write and a
    successful visible test run) is allowed even when the hidden validator
    would fail it — that failure only becomes visible post-termination,
    identically to how the baseline agent is scored.
    """
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
    assert decision["decision"] == "allow"
    assert decision["independent_hidden_validation_status"] == "not_run"
    assert "independent task evaluator failed" not in decision["reasons"]
    # No repair/diagnosis is triggered pre-termination, since nothing was
    # blocked and the hidden evaluator was never consulted.
    assert not [
        event
        for event in run["trace_events"]
        if event.get("event_type") in {"memory_repair_plan", "evaluator_diagnosis"}
    ]
    # The claim was well-supported (real write/test citations), so this is
    # supported_but_incorrect, not unsupported/false — the hidden-evaluator
    # failure is only caught by post-termination scoring, identically to
    # how a baseline agent's finish is scored.
    assert run["interaction_metrics"]["accepted_finish_proposals"] == 1
    assert run["interaction_metrics"]["accepted_finish_evaluator_failures"] == 1
    assert run["interaction_metrics"]["accepted_incorrect_finish"] is True
    assert run["interaction_metrics"]["false_finish_proposals"] == 0
    assert run["interaction_metrics"]["accepted_false_finishes"] == 0
    assert run["interaction_metrics"]["accepted_unsupported_finish"] is False
    assert run["interaction_metrics"]["supported_but_incorrect_finish"] is True
    assert run["interaction_metrics"]["task_outcome"] == (
        "finished_but_failed_evaluator"
    )


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
                # Premature finish: no write or test has actually happened
                # yet, so this is blocked by the trace-based
                # "missing implementation-change evidence"/"missing
                # successful test evidence" checks — never by hidden
                # validation, which the online gate never consults.
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
    # Neither decision ever consults hidden/ground-truth validation online.
    assert decisions[0]["independent_hidden_validation_status"] == "not_run"
    assert decisions[1]["independent_hidden_validation_status"] == "not_run"
    assert run["interaction_metrics"]["memory_replanned_after_repair"] is True
    assert run["interaction_metrics"]["memory_replans_required"] == 1
    assert run["interaction_metrics"]["memory_replans_completed"] == 1
    assert run["interaction_metrics"]["memory_replans_invalid"] == 0
    assert run["interaction_metrics"]["memory_repair_recovery"] is True
    assert run["interaction_metrics"]["evaluator_success"] is True
    assert run["interaction_metrics"]["accepted_false_finishes"] == 0
    assert run["memory_repair_summary"]["attempts_by_type"] == {
        "implementation_evaluator_failure": 1
    }
    replan = next(
        event
        for event in run["trace_events"]
        if event.get("event_type") == "memory_replan"
        and event.get("status") == "completed"
    )
    repair_result = next(
        event
        for event in run["trace_events"]
        if event.get("event_type") == "memory_repair_result"
    )
    assert replan["repair_result_event_id"] == repair_result["event_id"]
    assert replan["repaired_memory_id"] == repair_result[
        "repaired_memory_id"
    ]
    assert replan["model_response_event_id"]


def test_evaluator_diagnosis_loop_stops_at_controller_repair_budget(
    tmp_path: Path,
):
    pytest.importorskip("langgraph")

    class RepeatedFalseFinishAdapter:
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
                    "claim": "The incomplete implementation is complete.",
                    "source_event_ids": [],
                },
            ]
            action = actions[min(self.calls - 1, len(actions) - 1)]
            return ModelResponse(
                text=json.dumps(action),
                runtime="deterministic",
                model_name=request.model_name,
                model_family=request.model_family,
                raw_response={"fake": True},
            )

    with patch(
        "research.runner.benchmark_runner.create_model_adapter",
        return_value=RepeatedFalseFinishAdapter(),
    ):
        run = BenchmarkRunner().run_task_id(
            "coding_stale_tests_001",
            BenchmarkRunConfig(
                framework="langgraph_tools",
                trace_mode="model_driven",
                agent_variant="verified",
                action_budget=5,
                workspace_root=str(tmp_path),
            ),
        )

    repair_plans = [
        event
        for event in run["trace_events"]
        if event.get("event_type") == "memory_repair_plan"
        and event.get("repair_type")
        == "implementation_evaluator_failure"
    ]
    diagnoses = [
        event
        for event in run["trace_events"]
        if event.get("event_type") == "evaluator_diagnosis"
    ]
    exhausted = [
        event
        for event in run["trace_events"]
        if event.get("event_type") == "memory_corruption_detection"
        and event.get("repair_type")
        == "implementation_evaluator_failure"
        and event.get("repairable") is False
    ]

    assert [event["repair_attempt"] for event in repair_plans] == [1, 2]
    assert all(event["repair_budget"] == 2 for event in repair_plans)
    assert len(diagnoses) == 2
    assert len(exhausted) == 1
    assert exhausted[0]["repair_attempt"] == 2
    assert exhausted[0]["repair_budget"] == 2
    assert exhausted[0]["budget_exhausted"] is True
    assert run["interaction_metrics"]["memory_replans_required"] == 2
    assert run["interaction_metrics"]["memory_replans_completed"] == 2
    assert run["interaction_metrics"]["termination_reason"] == (
        "action_budget_exhausted"
    )


def test_observe_only_never_blocks_and_records_raw_would_block_decision(
    tmp_path: Path,
):
    """observe_only must be genuinely passive.

    The verifier still scores every finish proposal and its raw decision
    (verifier_decision/would_block) must be recorded even when it wanted to
    block — but the enforced decision is always "allow" and no repair ever
    executes. This is what makes verifier precision/recall computable from
    observe_only runs without any behavioral feedback loop confounding it.
    """
    pytest.importorskip("langgraph")

    class UnsupportedFinishAdapter:
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
                    # No source_event_ids: unsupported by construction.
                    "action": "finish",
                    "claim": "The task is complete.",
                    "source_event_ids": [],
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
        return_value=UnsupportedFinishAdapter(),
    ):
        run = BenchmarkRunner().run_task_id(
            "coding_stale_tests_001",
            BenchmarkRunConfig(
                framework="langgraph_tools",
                trace_mode="model_driven",
                intervention="observe_only",
                action_budget=3,
                workspace_root=str(tmp_path),
            ),
        )

    decision = next(
        event
        for event in run["trace_events"]
        if event.get("event_type") == "verification_decision"
    )
    # The verifier's raw judgment wanted to block this unsupported claim...
    assert decision["verifier_decision"] == "block"
    assert decision["would_block"] is True
    # ...but observe_only never enforces it.
    assert decision["enforced_decision"] == "allow"
    assert decision["decision"] == "allow"
    assert decision["gate_mode"] == "non_blocking"
    # No repair ever executes in observe_only.
    assert not [
        event
        for event in run["trace_events"]
        if event.get("event_type") == "memory_repair_plan"
    ]
    assert run["interaction_metrics"]["accepted_finish_proposals"] == 1
    assert run["interaction_metrics"]["accepted_unsupported_finish"] is True
    assert run["run_metadata"]["verifier_enabled"] is True
    assert run["run_metadata"]["verification_blocking"] is False
    assert run["run_metadata"]["memory_repair"] is False


def test_verification_only_enforces_block_and_matches_raw_decision(
    tmp_path: Path,
):
    """When blocking is enabled, the enforced decision matches the raw one."""
    pytest.importorskip("langgraph")

    class UnsupportedFinishAdapter:
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
                    "claim": "The task is complete.",
                    "source_event_ids": [],
                },
            ]
            action = actions[min(self.calls - 1, len(actions) - 1)]
            return ModelResponse(
                text=json.dumps(action),
                runtime="deterministic",
                model_name=request.model_name,
                model_family=request.model_family,
                raw_response={"fake": True},
            )

    with patch(
        "research.runner.benchmark_runner.create_model_adapter",
        return_value=UnsupportedFinishAdapter(),
    ):
        run = BenchmarkRunner().run_task_id(
            "coding_stale_tests_001",
            BenchmarkRunConfig(
                framework="langgraph_tools",
                trace_mode="model_driven",
                intervention="verification_only",
                action_budget=3,
                workspace_root=str(tmp_path),
            ),
        )

    decision = next(
        event
        for event in run["trace_events"]
        if event.get("event_type") == "verification_decision"
    )
    assert decision["verifier_decision"] == "block"
    assert decision["would_block"] is True
    assert decision["enforced_decision"] == "block"
    assert decision["decision"] == "block"
    assert decision["gate_mode"] == "blocking"
    assert run["interaction_metrics"]["accepted_finish_proposals"] == 0


def test_verification_report_confusion_matrix_uses_raw_not_enforced_decision(
    tmp_path: Path,
):
    """Verifier precision/recall must be computable from observe_only runs.

    The verification report's decision_counts/blocked_actions reflect the
    enforced action (always "allow" in observe_only), but
    raw_decision_counts and confusion_matrix must reflect the verifier's
    own raw judgment against ground-truth support — otherwise observe_only
    would look like a verifier that never finds anything to flag.
    """
    pytest.importorskip("langgraph")

    class UnsupportedFinishAdapter:
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
                    "claim": "The task is complete.",
                    "source_event_ids": [],
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
        return_value=UnsupportedFinishAdapter(),
    ):
        run = BenchmarkRunner().run_task_id(
            "coding_stale_tests_001",
            BenchmarkRunConfig(
                framework="langgraph_tools",
                trace_mode="model_driven",
                intervention="observe_only",
                action_budget=3,
                workspace_root=str(tmp_path),
            ),
        )

    report = run["verification_report"]
    # Enforced: observe_only never blocks.
    assert report["decision_counts"]["block"] == 0
    assert report["blocked_actions"] == []
    # Raw: the verifier still recognized the unsupported claim.
    assert report["raw_decision_counts"]["block"] == 1
    assert len(report["raw_blocked_proposals"]) == 1
    assert report["raw_blocked_proposals"][0]["enforced_decision"] == "allow"
    confusion = report["confusion_matrix"]
    # Not independent evidence — ground truth here is the same claim
    # classifier the verifier itself consumes. Must be labeled as such so
    # it can't be mistaken for external precision/recall in the paper.
    assert confusion["confirmatory"] is False
    assert confusion["label_source"] == "shared_claim_classifier"
    assert confusion["true_positive"] == 1
    assert confusion["false_positive"] == 0
    assert confusion["false_negative"] == 0
    assert confusion["precision"] == 1.0
    assert confusion["recall"] == 1.0


def test_verification_report_includes_oracle_confusion_matrix(
    tmp_path: Path,
):
    """oracle_confusion_matrix uses independent ground truth, not the classifier.

    Ground truth here is support_oracle.py's label (fixture-authored
    completion_policy metadata), which is why it's a distinct block from
    confusion_matrix (label_source: shared_claim_classifier) even though
    both happen to agree in this scenario.
    """
    pytest.importorskip("langgraph")

    class UnsupportedFinishAdapter:
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
                    "claim": "The task is complete.",
                    "source_event_ids": [],
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
        return_value=UnsupportedFinishAdapter(),
    ):
        run = BenchmarkRunner().run_task_id(
            "coding_stale_tests_001",
            BenchmarkRunConfig(
                framework="langgraph_tools",
                trace_mode="model_driven",
                intervention="observe_only",
                action_budget=3,
                workspace_root=str(tmp_path),
            ),
        )

    oracle_confusion = run["verification_report"]["oracle_confusion_matrix"]
    assert oracle_confusion["confirmatory"] is False
    assert oracle_confusion["label_source"] == "support_oracle"
    # No source_event_ids cited at all — the oracle's own trace-based
    # reasoning (not the claim classifier) calls this unsupported too.
    assert oracle_confusion["true_positive"] == 1
    assert oracle_confusion["false_positive"] == 0
    assert run["interaction_metrics"]["accepted_oracle_unsupported_finish"] is True


def test_requirement_snapshot_recovers_task_and_changed_user_history():
    task = BenchmarkRunner().get_task("coding_stale_tests_001")
    scenario = load_fixture_scenario("coding_stale_tests_001")
    assert scenario is not None
    trace_events = [
        {
            "event_id": "goal-event",
            "event_type": "prompt",
            "sequence_number": 1,
            "prompt": task["goal"],
            "source_type": "user_instruction",
        },
        {
            "event_id": "update-event",
            "event_type": "user_requirement_update",
            "sequence_number": 9,
            "requirement_id": "requirement_update_0",
            "content": scenario["requirement_updates"][0]["content"],
            "status": "active",
            "source_type": "user_instruction",
        },
    ]

    snapshot = BenchmarkRunner._requirement_history_snapshot(
        task,
        scenario,
        [0],
        trace_events,
    )

    assert snapshot["goal"] == task["goal"]
    assert snapshot["acceptance_criteria"] == task["acceptance_criteria"]
    assert snapshot["active_requirement_updates"] == [
        scenario["requirement_updates"][0]
    ]
    assert [item["event_id"] for item in snapshot["history"]] == [
        "goal-event",
        "update-event",
    ]
    assert snapshot["history"][-1]["content"] == (
        scenario["requirement_updates"][0]["content"]
    )


def test_failing_fresh_test_is_a_successful_memory_observation():
    assert BenchmarkRunner._memory_repair_observation_succeeded(
        {"action": "run_targeted_tests", "targets": ["test_service.py"]},
        {"status": "failure", "returncode": 1},
    )
    assert not BenchmarkRunner._memory_repair_observation_succeeded(
        {"action": "run_targeted_tests", "targets": ["test_service.py"]},
        {"status": "tool_error"},
    )


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
    assert all(
        schema["oneOf"]
        for schema in adapter.schemas
    )
    assert all(
        schema["$defs"]["beliefs"]["maxItems"] == 4
        for schema in adapter.schemas
    )
    assert all(
        all(
            variant["properties"]["beliefs"] == {
                "$ref": "#/$defs/beliefs"
            }
            for variant in schema["oneOf"]
        )
        for schema in adapter.schemas
    )
    assert all(
        len(json.dumps(schema)) < 6_000
        for schema in adapter.schemas
    )
    assert all(
        "finish"
        in {
            variant["properties"]["action"]["const"]
            for variant in schema["oneOf"]
        }
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
    search_cooldown = runner._available_tool_actions(
        scenario,
        ledger,
        [
            {
                "status": "rejected_redundant",
                "rejected_action": {
                    "action": "search_code",
                    "query": "parse_line",
                },
            }
        ],
    )
    progress_only = runner._available_tool_actions(
        scenario,
        ledger,
        [
            {"status": "tool_error", "rejected_action": {"action": "read_file"}},
            {
                "status": "rejected_redundant",
                "rejected_action": {"action": "search_code"},
            },
            {"status": "rejected", "rejected_action": {"action": "git_status"}},
        ],
        enforce_no_progress_guard=True,
    )
    stalled_after_write = runner._available_tool_actions(
        scenario,
        ledger,
        [],
        no_progress_action_count=3,
        enforce_no_progress_guard=True,
    )
    stalled_before_write = runner._available_tool_actions(
        scenario,
        ledger[:2],
        [],
        no_progress_action_count=6,
        enforce_no_progress_guard=True,
    )

    assert "list_files" not in available
    assert "run_tests" not in available
    assert "read_file" in available
    assert {"write_file", "finish"}.issubset(available)
    assert terminal_only == ["finish"]
    assert "search_code" not in search_cooldown
    assert {"read_file", "write_file", "finish"}.issubset(search_cooldown)
    assert set(progress_only) <= {
        "write_file",
        "apply_patch",
        "run_targeted_tests",
        "run_tests",
        "run_full_tests",
        "read_test_failure",
        "finish",
    }
    assert {"write_file", "apply_patch", "finish"}.issubset(progress_only)
    assert set(stalled_after_write) <= {
        "write_file",
        "apply_patch",
        "run_targeted_tests",
        "run_tests",
        "run_full_tests",
        "read_test_failure",
        "finish",
    }
    assert "run_targeted_tests" not in stalled_after_write
    assert {"write_file", "apply_patch", "finish"}.issubset(
        stalled_after_write
    )
    assert set(stalled_before_write) == {
        "write_file",
        "apply_patch",
        "finish",
    }
    assert "read_structured_file" not in available


def test_action_availability_only_exposes_supported_structured_reads():
    runner = BenchmarkRunner()
    scenario = {
        "initial_files": {
            "agent.py": "print('ok')\n",
            "settings.json": '{"enabled": true}\n',
        }
    }

    available = runner._available_tool_actions(scenario, [], [])
    schema = runner._tool_action_response_schema(
        available,
        workspace_files=sorted(scenario["initial_files"]),
    )
    variants = {
        variant["properties"]["action"]["const"]: variant
        for variant in schema["oneOf"]
    }

    assert "read_structured_file" in available
    assert variants["read_structured_file"]["properties"]["path"]["enum"] == [
        "settings.json"
    ]
    assert variants["inspect_dependency"]["properties"]["path"]["enum"] == [
        "agent.py"
    ]


def test_tool_action_schema_excludes_redundant_read_paths_only():
    schema = BenchmarkRunner._tool_action_response_schema(
        ["read_file", "write_file"],
        workspace_files=[
            "config_loader.py",
            "config_parser.py",
            "test_config_parser.py",
        ],
        readable_files=["config_parser.py"],
    )
    variants = {
        variant["properties"]["action"]["const"]: variant
        for variant in schema["oneOf"]
    }

    assert variants["read_file"]["properties"]["path"]["enum"] == [
        "config_parser.py"
    ]
    assert variants["write_file"]["properties"]["path"]["enum"] == [
        "config_loader.py",
        "config_parser.py",
        "test_config_parser.py",
    ]


def test_read_test_failure_is_available_once_per_new_failure():
    runner = BenchmarkRunner()
    scenario = {"initial_files": {"agent.py": "", "test_agent.py": ""}}
    ledger = [
        {
            "label": "run_tests",
            "tool_name": "run_tests",
            "status": "failure",
        }
    ]

    assert "read_test_failure" in runner._available_tool_actions(
        scenario,
        ledger,
        [],
    )
    ledger.append(
        {
            "label": "read_test_failure",
            "tool_name": "read_test_failure",
            "status": "success",
        }
    )
    assert "read_test_failure" not in runner._available_tool_actions(
        scenario,
        ledger,
        [],
    )
    ledger.append(
        {
            "label": "run_tests",
            "tool_name": "run_tests",
            "status": "failure",
        }
    )
    assert "read_test_failure" in runner._available_tool_actions(
        scenario,
        ledger,
        [],
    )


@pytest.mark.parametrize(
    "action",
    [
        {"action": "search_code", "query": "parse_line", "path": "."},
        {"action": "git_diff"},
        {"action": "git_status"},
        {
            "action": "inspect_dependency",
            "path": "config_parser.py",
            "symbol": "parse_line",
        },
        {
            "action": "read_structured_file",
            "path": "config.json",
        },
        {
            "action": "run_targeted_tests",
            "targets": ["test_config_parser.py"],
        },
    ],
)
def test_exact_observational_actions_are_redundant_until_a_write(action):
    runner = BenchmarkRunner()
    ledger = [
        {
            "label": runner._action_label(action),
            "tool_name": action["action"],
            "status": "success",
        }
    ]

    assert runner._redundant_action_reason(action, ledger)

    ledger.append(
        {
            "label": (
                "write_file:"
                + (
                    action["path"]
                    if action["action"]
                    in {"read_structured_file", "inspect_dependency"}
                    else "config_parser.py"
                )
            ),
            "tool_name": "write_file",
            "path": (
                action["path"]
                if action["action"]
                in {"read_structured_file", "inspect_dependency"}
                else "config_parser.py"
            ),
            "status": "success",
        }
    )
    assert runner._redundant_action_reason(action, ledger) is None


def test_tool_action_schema_requires_action_specific_fields():
    schema = BenchmarkRunner._tool_action_response_schema(
        ["write_file", "run_targeted_tests", "finish"]
    )
    requirements = {
        variant["properties"]["action"]["const"]:
        set(variant["required"])
        for variant in schema["oneOf"]
    }

    assert requirements == {
        "write_file": {"action", "path", "content", "beliefs"},
        "run_targeted_tests": {"action", "targets", "beliefs"},
        "finish": {"action", "claim", "beliefs"},
    }
    targeted = next(
        variant
        for variant in schema["oneOf"]
        if variant["properties"]["action"]["const"]
        == "run_targeted_tests"
    )
    assert targeted["properties"]["targets"]["minItems"] == 1


def test_tool_action_schema_constrains_model_selected_workspace_paths():
    schema = BenchmarkRunner._tool_action_response_schema(
        [
            "read_file",
            "write_file",
            "read_structured_file",
            "inspect_dependency",
            "run_targeted_tests",
        ],
        workspace_files=[
            "agent.py",
            "test_agent.py",
            "settings.json",
            "README.md",
        ],
    )
    variants = {
        variant["properties"]["action"]["const"]: variant
        for variant in schema["oneOf"]
    }

    assert variants["read_file"]["properties"]["path"]["enum"] == [
        "README.md",
        "agent.py",
        "settings.json",
        "test_agent.py",
    ]
    assert variants["write_file"]["properties"]["path"]["enum"] == [
        "README.md",
        "agent.py",
        "settings.json",
        "test_agent.py",
    ]
    assert variants["read_structured_file"]["properties"]["path"]["enum"] == [
        "settings.json"
    ]
    assert variants["inspect_dependency"]["properties"]["path"]["enum"] == [
        "agent.py",
        "test_agent.py",
    ]
    assert variants["run_targeted_tests"]["properties"]["targets"]["items"][
        "enum"
    ] == ["test_agent.py"]


def test_invalid_tool_action_schema_preserves_attempted_action():
    parsed = BenchmarkRunner._parse_tool_action_response(
        json.dumps(
            {
                "action": "run_targeted_tests",
                "beliefs": [],
                "source_event_ids": [],
            }
        )
    )

    assert parsed == {
        "parse_status": "invalid_schema",
        "attempted_action": "run_targeted_tests",
    }


def test_langgraph_tool_loop_persists_incremental_trace_journal(tmp_path: Path):
    pytest.importorskip("langgraph")

    run = BenchmarkRunner().run_task_id(
        "coding_stale_tests_001",
        BenchmarkRunConfig(
            framework="langgraph_tools",
            trace_mode="model_driven",
            action_budget=3,
            workspace_root=str(tmp_path),
        ),
    )

    journal_path = Path(run["run_metadata"]["trace_journal_path"])
    checkpoint_path = Path(run["run_metadata"]["run_checkpoint_path"])
    workspace_path = Path(run["run_metadata"]["workspace_path"])
    journal_events = [
        json.loads(line)
        for line in journal_path.read_text(encoding="utf-8").splitlines()
    ]
    checkpoint = json.loads(checkpoint_path.read_text(encoding="utf-8"))

    assert journal_path.exists()
    assert checkpoint_path.exists()
    assert checkpoint["status"] == "completed"
    assert checkpoint["next_node"] == "__end__"
    assert checkpoint["workspace_path"] == str(workspace_path.resolve())
    assert journal_path.parent == workspace_path.parent
    assert journal_path.parent != workspace_path
    assert [event["event_id"] for event in journal_events] == [
        event["event_id"] for event in run["trace_events"]
    ]


def test_langgraph_tool_loop_resumes_after_durable_model_action_without_replay(
    tmp_path: Path,
):
    pytest.importorskip("langgraph")

    class CountingAdapter:
        runtime = "deterministic"

        def __init__(self):
            self.requests = []

        def generate(self, request):
            self.requests.append(request)
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

    class InterruptingRunner(BenchmarkRunner):
        def __init__(self):
            super().__init__()
            self.interrupted = False

        def _after_tool_run_checkpoint(self, checkpoint):
            if (
                not self.interrupted
                and checkpoint["next_node"] == "process_action"
            ):
                self.interrupted = True
                raise RuntimeError("simulated process interruption")

    interrupted_adapter = CountingAdapter()
    runner = InterruptingRunner()
    config = BenchmarkRunConfig(
        framework="langgraph_tools",
        trace_mode="model_driven",
        action_budget=8,
        workspace_root=str(tmp_path / "interrupted"),
    )
    with patch(
        "research.runner.benchmark_runner.create_model_adapter",
        return_value=interrupted_adapter,
    ):
        with pytest.raises(RuntimeError, match="simulated process interruption"):
            runner.run_task_id("coding_stale_tests_001", config)

        checkpoint_path = next(
            (tmp_path / "interrupted").glob("*.run-checkpoint.json")
        )
        checkpoint = BenchmarkRunner._load_tool_run_checkpoint(
            checkpoint_path
        )
        assert checkpoint["next_node"] == "process_action"
        assert checkpoint["state"]["action_count"] == 0
        assert len(interrupted_adapter.requests) == 1

        resumed = runner.resume_task(checkpoint_path)

    baseline_adapter = CountingAdapter()
    with patch(
        "research.runner.benchmark_runner.create_model_adapter",
        return_value=baseline_adapter,
    ):
        baseline = BenchmarkRunner().run_task_id(
            "coding_stale_tests_001",
            BenchmarkRunConfig(
                framework="langgraph_tools",
                trace_mode="model_driven",
                action_budget=8,
                workspace_root=str(tmp_path / "baseline"),
            ),
        )

    assert len(interrupted_adapter.requests) == len(baseline_adapter.requests)
    assert resumed["interaction_metrics"]["model_action_count"] == (
        baseline["interaction_metrics"]["model_action_count"]
    )
    assert resumed["run_metadata"]["resumed_from_checkpoint"] is True
    assert resumed["run_metadata"]["resume_count"] == 1
    assert sum(
        event.get("event_type") == "run_resume"
        for event in resumed["trace_events"]
    ) == 1
    assert (
        resumed["run_metadata"]["final_repository_hash"]
        == baseline["run_metadata"]["final_repository_hash"]
    )


def test_tool_run_resume_rejects_workspace_changed_after_checkpoint(
    tmp_path: Path,
):
    pytest.importorskip("langgraph")

    class InterruptingRunner(BenchmarkRunner):
        def __init__(self):
            super().__init__()
            self.interrupted = False

        def _after_tool_run_checkpoint(self, checkpoint):
            if (
                not self.interrupted
                and checkpoint["next_node"] == "choose_action"
            ):
                self.interrupted = True
                raise RuntimeError("simulated process interruption")

    runner = InterruptingRunner()
    with pytest.raises(RuntimeError, match="simulated process interruption"):
        runner.run_task_id(
            "coding_stale_tests_001",
            BenchmarkRunConfig(
                framework="langgraph_tools",
                trace_mode="model_driven",
                workspace_root=str(tmp_path),
            ),
        )

    checkpoint_path = next(tmp_path.glob("*.run-checkpoint.json"))
    checkpoint = BenchmarkRunner._load_tool_run_checkpoint(checkpoint_path)
    workspace = Path(checkpoint["workspace_path"])
    (workspace / "config_parser.py").write_text(
        "def parse_line(line):\n    return ('tampered', line)\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="workspace hash does not match"):
        runner.resume_task(checkpoint_path)


def test_tool_run_resume_rejects_tampered_checkpoint_and_config(
    tmp_path: Path,
):
    pytest.importorskip("langgraph")

    run = BenchmarkRunner().run_task_id(
        "coding_stale_tests_001",
        BenchmarkRunConfig(
            framework="langgraph_tools",
            trace_mode="model_driven",
            action_budget=3,
            workspace_root=str(tmp_path),
        ),
    )
    checkpoint_path = Path(run["run_metadata"]["run_checkpoint_path"])
    checkpoint = BenchmarkRunner._load_tool_run_checkpoint(checkpoint_path)
    mismatched_config = {
        **checkpoint["config"],
        "temperature": 0.5,
        "resume_from": str(checkpoint_path),
    }

    with pytest.raises(ValueError, match="configuration does not match"):
        BenchmarkRunner().run_task_id(
            "coding_stale_tests_001",
            BenchmarkRunConfig(**mismatched_config),
        )

    checkpoint["state"]["action_count"] = 999
    checkpoint_path.write_text(
        json.dumps(checkpoint),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="integrity check failed"):
        BenchmarkRunner().resume_task(checkpoint_path)


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
        "beliefs": [],
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


def test_tool_action_prompt_is_identical_across_conditions():
    """Every primary condition shares the exact same prompt text.

    The treatment under study is the online gate and repair — not prompt
    coaching — so instrumentation (evidence ledger, citation requirements,
    freshness reminder) must not vary across conditions. The baseline is
    an "instrumented baseline", not a naive agent: only what happens after
    the agent proposes an action should differ between conditions.
    """
    runner = BenchmarkRunner()
    task = runner.get_task("coding_stale_tests_001")
    scenario = runner._coding_tool_scenario(task)
    common_kwargs = dict(
        action_count=0,
        deterministic_action={},
    )
    baseline_prompt = runner._tool_action_prompt(
        task,
        scenario,
        [],
        [],
        BenchmarkRunConfig(
            framework="langgraph_tools",
            trace_mode="model_driven",
            runtime="ollama",
            agent_variant="baseline",
        ),
        **common_kwargs,
    )
    verified_prompt = runner._tool_action_prompt(
        task,
        scenario,
        [],
        [],
        BenchmarkRunConfig(
            framework="langgraph_tools",
            trace_mode="model_driven",
            runtime="ollama",
            agent_variant="verified",
        ),
        **common_kwargs,
    )

    freshness_text = (
        "There is no successful visible test run newer than the latest "
        "write. Do not claim verified completion without current evidence."
    )
    assert freshness_text in baseline_prompt
    assert freshness_text in verified_prompt

    # Citation/schema instructions stay identical — post-hoc claim scoring
    # depends on them for both conditions equally.
    assert "cite exact evidence event IDs" in baseline_prompt
    assert "cite exact evidence event IDs" in verified_prompt

    # Controller mechanics (redundant-action guidance) are variant-independent.
    unavailable_guidance = runner._unavailable_action_guidance(scenario, [])
    assert unavailable_guidance in baseline_prompt
    assert unavailable_guidance in verified_prompt

    assert baseline_prompt == verified_prompt


def test_model_visible_evidence_projection_is_bounded_without_mutating_memory():
    runner = BenchmarkRunner()
    canonical = [
        {
            "memory_id": f"memory-{index}",
            "event_id": f"event-{index}",
            "label": f"read_file:file_{index}.py",
            "event_type": "tool_call",
            "tool_name": "read_file",
            "status": "success",
            "source_type": "tool_output",
            "workspace_revision": 0,
            "support_status": "supported",
            "stale": False,
            "path": f"file_{index}.py",
            "claim": f"Observed file_{index}.py.",
            "content": f"payload-{index}-" + ("x" * 5_000),
            "structured_output": {
                "path": f"file_{index}.py",
                "content": "x" * 5_000,
                "content_sha256": "a" * 64,
            },
        }
        for index in range(8)
    ]
    canonical_before = json.loads(json.dumps(canonical))

    projected = runner._model_visible_evidence_ledger(canonical)

    assert len(json.dumps(projected, sort_keys=True)) <= 8_000
    assert [item["event_id"] for item in projected] == [
        f"event-{index}" for index in range(8)
    ]
    assert canonical == canonical_before
    assert all(
        len(item.get("content", "")) <= 1_600
        for item in projected
    )
    assert all(
        "content" not in item.get("structured_output", {})
        for item in projected
    )


def test_model_visible_evaluator_diagnosis_preserves_replan_evidence():
    failing_assertion = 'assert parse_line(" retries = 3 ") == ("retries", "3")'
    entry = {
        "memory_id": "repair-event:memory",
        "event_id": "repair-event",
        "label": "diagnose_evaluator_failure",
        "event_type": "evaluator_diagnosis",
        "tool_name": "diagnose_evaluator_failure",
        "status": "success",
        "source_type": "tool_output",
        "workspace_revision": 0,
        "support_status": "supported",
        "content": "Diagnosed the independent evaluator failure.",
        "requirement_snapshot": {
            "goal": "large duplicated requirement",
            "history": [{"content": "y" * 4_000}],
        },
        "evaluator_failure": {
            "visible_test_status": "success",
            "hidden_validation_status": "failure",
            "content": "duplicated evaluator output",
        },
        "structured_output": {
            "failed_components": ["hidden_validation"],
            "changed_files": [],
            "current_diff": "",
            "evaluator_output": (
                ("traceback frame\n" * 200)
                + failing_assertion
                + "\nAssertionError"
            ),
            "latest_test_failure": None,
            "requirement_snapshot": {
                "goal": "large duplicated requirement",
            },
        },
    }

    projected = BenchmarkRunner._model_visible_evidence_entry(entry)

    assert projected["memory_id"] == "repair-event:memory"
    assert projected["diagnosis"]["failed_components"] == [
        "hidden_validation"
    ]
    assert projected["diagnosis"]["visible_test_status"] == "success"
    assert projected["diagnosis"]["hidden_validation_status"] == "failure"
    assert failing_assertion in projected["diagnosis"]["evaluator_output"]
    assert "requirement_snapshot" not in projected
    assert "evaluator_failure" not in projected
    assert "structured_output" not in projected


def test_model_visible_ledger_never_evicts_evaluator_diagnosis():
    failing_assertion = 'assert parse_line(" # ignored") is None'
    entries = [
        {
            "memory_id": f"memory-{index}",
            "event_id": f"event-{index}",
            "tool_name": "read_file",
            "status": "success",
            "source_type": "tool_output",
            "workspace_revision": index,
            "support_status": "supported",
            "path": f"file_{index}.py",
            "content": "x" * 1_500,
        }
        for index in range(20)
    ]
    entries.insert(
        8,
        {
            "memory_id": "diagnosis-event:memory",
            "event_id": "diagnosis-event",
            "tool_name": "diagnose_evaluator_failure",
            "status": "success",
            "source_type": "tool_output",
            "workspace_revision": 3,
            "support_status": "supported",
            "content": "Diagnosed hidden validation.",
            "evaluator_failure": {
                "visible_test_status": "success",
                "hidden_validation_status": "failure",
            },
            "structured_output": {
                "failed_components": ["hidden_validation"],
                "changed_files": ["config_parser.py"],
                "current_diff": "diff line\n" * 300,
                "evaluator_output": (
                    ("traceback frame\n" * 200)
                    + failing_assertion
                    + "\nValueError: ignored line"
                ),
            },
        },
    )

    projected = BenchmarkRunner._model_visible_evidence_ledger(entries)
    diagnosis = next(
        item for item in projected if item.get("event_id") == "diagnosis-event"
    )

    assert len(json.dumps(projected, sort_keys=True)) <= 8_000
    assert diagnosis["diagnosis"]["failed_components"] == [
        "hidden_validation"
    ]
    assert failing_assertion in diagnosis["diagnosis"]["evaluator_output"]


def test_tool_action_prompt_uses_bounded_evidence_projection():
    runner = BenchmarkRunner()
    task = runner.get_task("coding_stale_tests_001")
    ledger = [
        {
            "memory_id": f"memory-{index}",
            "event_id": f"event-{index}",
            "label": f"read_file:file_{index}.py",
            "event_type": "tool_call",
            "tool_name": "read_file",
            "status": "success",
            "source_type": "tool_output",
            "workspace_revision": 0,
            "support_status": "supported",
            "path": f"file_{index}.py",
            "content": f"UNBOUNDED-{index}-" + ("z" * 6_000),
        }
        for index in range(8)
    ]

    prompt = runner._tool_action_prompt(
        task,
        runner._coding_tool_scenario(task),
        ledger,
        [],
        BenchmarkRunConfig(
            framework="langgraph_tools",
            trace_mode="model_driven",
            runtime="ollama",
        ),
        action_count=8,
        deterministic_action={},
    )
    ledger_text = prompt.split("Evidence ledger: ", 1)[1].split(
        "\nRecent observations:",
        1,
    )[0]
    projected = json.loads(ledger_text)

    assert len(json.dumps(projected, sort_keys=True)) <= 8_000
    assert len(projected) == len(ledger)
    assert prompt.count("UNBOUNDED-") == len(ledger)
    assert "z" * 6_000 not in prompt


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


def test_hidden_validation_runs_exactly_once_after_termination(tmp_path: Path):
    """Hidden validation must never run as part of an agent-visible tool call.

    Spies on _run_hidden_validation across a complete deterministic
    coding_stale_tests_001 episode. Only evaluate_outcome (post-
    termination) may call it — never _execute_coding_tool's run_tests
    handling, online or deterministic. Guards against reintroducing the
    now-removed (and, on inspection, already-unreachable)
    step.get("hidden_validation") branch.
    """
    pytest.importorskip("langgraph")
    calls: list[tuple[str, str]] = []
    original = BenchmarkRunner._run_hidden_validation

    def spy(self, workspace, task_id):
        calls.append((str(workspace), task_id))
        return original(self, workspace, task_id)

    with patch.object(BenchmarkRunner, "_run_hidden_validation", spy):
        run = BenchmarkRunner().run_task_id(
            "coding_stale_tests_001",
            BenchmarkRunConfig(
                framework="langgraph_tools",
                trace_mode="model_driven",
                intervention="verification_only",
                action_budget=20,
                workspace_root=str(tmp_path),
            ),
        )

    assert len(calls) == 1
    events = run["trace_events"]
    termination_sequence = next(
        (
            event["sequence_number"]
            for event in events
            if event.get("event_type") in {"agent_termination", "decision_point"}
            and event.get("termination_reason")
        ),
        None,
    )
    evaluation_event = next(
        event
        for event in events
        if event.get("event_type") == "evaluation_result"
    )
    if termination_sequence is not None:
        assert evaluation_event["sequence_number"] > termination_sequence
    assert not [
        event
        for event in events
        if event.get("structured_output", {}).get("hidden_validation_included")
    ]
    assert not [
        event
        for event in events
        if event.get("event_type") == "tool_call"
        and event.get("tool_name")
        in {"run_tests", "run_full_tests", "run_targeted_tests"}
        and "hidden" in json.dumps(event.get("structured_output", {})).lower()
    ]


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


def test_labeling_force_labels_finish_as_task_complete_regardless_of_wording():
    """A `finish` action must always register as a task_complete claim.

    Keyword-based detection alone would miss claim text that never says
    "complete"/"done"/"finished"/etc., but a `finish` call is itself the
    highest-risk completion claim there is — it terminates the episode.
    """
    events = [
        {
            "event_id": "event-1",
            "event_type": "completion_claim",
            "tool_name": "finish",
            "claim": "Nothing further remains on the acceptance checklist.",
            "source_event_ids": ["event-0"],
        }
    ]
    high_risk_claims = [
        {
            "claim_type": "task_complete",
            "verification_required": True,
            "minimum_source_type": "tool_output",
            "freshness_rule": "must be complete",
        },
    ]

    labels = label_high_risk_claims(events, high_risk_claims)

    assert {label["claim_type"] for label in labels} == {"task_complete"}
    assert labels[0]["source_event_ids"] == ["event-0"]


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


def test_graded_recovery_levels_are_ordered_and_monotonic():
    def metrics(events, claims=()):
        return BenchmarkRunner._interaction_metrics(
            {"trace_events": list(events), "memory_claims": list(claims)}
        )

    evaluation_success = {
        "event_type": "evaluation_result",
        "sequence_number": 90,
        "status": "success",
    }
    evaluation_failure = {
        "event_type": "evaluation_result",
        "sequence_number": 90,
        "status": "failure",
    }
    termination = {
        "event_type": "agent_termination",
        "sequence_number": 95,
        "termination_reason": "action_budget_exhaustion",
    }
    blocked_finish = {
        "event_type": "completion_claim",
        "tool_name": "finish",
        "event_id": "finish-blocked",
        "proposal_status": "blocked",
        "sequence_number": 10,
    }
    stale_claim = {
        "event_id": "finish-blocked",
        "claim_type": "task_complete",
        "stale": True,
        "lost_provenance": False,
        "support_status": "supported",
    }
    block_decision = {
        "event_type": "verification_decision",
        "decision": "block",
        "claim_event_id": "finish-blocked",
        "sequence_number": 10,
    }
    post_block_tool = {"event_type": "tool_call", "sequence_number": 20}
    repair_plan = {
        "event_type": "memory_repair_plan",
        "repair_type": "stale_evidence",
        "sequence_number": 30,
    }
    repair_result = {
        "event_type": "memory_repair_result",
        "status": "repaired",
        "repair_type": "stale_evidence",
        "replan_required": True,
        "sequence_number": 31,
    }
    replan = {
        "event_type": "memory_replan",
        "status": "completed",
        "sequence_number": 32,
    }
    accepted_finish = {
        "event_type": "completion_claim",
        "tool_name": "finish",
        "event_id": "finish-accepted",
        "proposal_status": "accepted",
        "sequence_number": 40,
    }
    supported_claim = {
        "event_id": "finish-accepted",
        "claim_type": "task_complete",
        "stale": False,
        "lost_provenance": False,
        "support_status": "supported",
    }

    observed = [
        metrics([accepted_finish, evaluation_success], [supported_claim]),
        metrics(
            [blocked_finish, block_decision, termination, evaluation_failure],
            [stale_claim],
        ),
        metrics(
            [
                blocked_finish,
                block_decision,
                post_block_tool,
                termination,
                evaluation_failure,
            ],
            [stale_claim],
        ),
        metrics(
            [
                blocked_finish,
                block_decision,
                post_block_tool,
                repair_plan,
                repair_result,
                replan,
                termination,
                evaluation_failure,
            ],
            [stale_claim],
        ),
        metrics(
            [
                blocked_finish,
                block_decision,
                post_block_tool,
                repair_plan,
                repair_result,
                replan,
                accepted_finish,
                evaluation_success,
            ],
            [stale_claim, supported_claim],
        ),
    ]

    assert [run["recovery_level"] for run in observed] == [0, 1, 2, 3, 4]
    for run in observed:
        level = run["recovery_level"]
        assert run["detected_corruption"] is (level >= 1)
        assert run["attempted_recovery"] is (level >= 2)
        assert run["contained_recovery"] is (level >= 3)
        assert run["memory_repair_recovery"] is (level >= 4)

    contained_only = observed[3]
    assert contained_only["contained_recovery"] is True
    assert contained_only["memory_repair_recovery"] is False
    assert contained_only["evaluator_success"] is False
