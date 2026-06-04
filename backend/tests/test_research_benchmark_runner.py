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


AGENT_STACK_PATH = ROOT / "research" / "agents" / "initial_stack.json"


def test_initial_stack_is_open_source_only_and_extensible():
    with AGENT_STACK_PATH.open(encoding="utf-8") as handle:
        stack = json.load(handle)

    assert stack["primary_framework"] == "react_custom"
    assert stack["closed_source_models_allowed"] is False
    assert "langgraph" in stack["adapter_targets"]
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
