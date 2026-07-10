"""Tests for the four-condition intervention ablation axis."""

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from research.runner.benchmark_runner import (
    BenchmarkRunConfig,
    BenchmarkRunner,
)
from research.runner.interventions import (
    INTERVENTION_CONDITIONS,
    resolve_intervention,
)
from research.runner.model_adapters import ModelResponse
from research.runner.model_matrix import run_model_matrix


def test_resolve_intervention_specs():
    assert INTERVENTION_CONDITIONS == (
        "memory_baseline",
        "verification_only",
        "repair_only",
        "verification_and_repair",
    )

    baseline = resolve_intervention("memory_baseline")
    assert baseline.agent_variant == "baseline"
    assert baseline.memory_repair is False
    assert baseline.verification_blocking is False

    verify_only = resolve_intervention("verification_only")
    assert verify_only.agent_variant == "verified"
    assert verify_only.memory_repair is False
    assert verify_only.verification_blocking is True

    repair_only = resolve_intervention("repair_only")
    assert repair_only.agent_variant == "verified"
    assert repair_only.memory_repair is True
    assert repair_only.verification_blocking is False

    full = resolve_intervention("verification_and_repair")
    assert full.agent_variant == "verified"
    assert full.memory_repair is True
    assert full.verification_blocking is True

    with pytest.raises(ValueError):
        resolve_intervention("oracle_memory")


def test_memory_baseline_runs_without_gate_or_repair(tmp_path: Path):
    pytest.importorskip("langgraph")

    run = BenchmarkRunner().run_task_id(
        "coding_stale_tests_001",
        BenchmarkRunConfig(
            framework="langgraph_tools",
            trace_mode="model_driven",
            intervention="memory_baseline",
            workspace_root=str(tmp_path),
        ),
    )

    assert run["run_metadata"]["intervention"] == "memory_baseline"
    assert run["run_metadata"]["agent_variant"] == "baseline"
    assert run["run_metadata"]["memory_repair"] is False
    assert not [
        event
        for event in run["trace_events"]
        if event.get("event_type") == "verification_decision"
    ]
    assert not [
        event
        for event in run["trace_events"]
        if event.get("event_type") == "memory_repair_plan"
    ]
    assert run["interaction_metrics"]["termination_reason"] == (
        "accepted_finish"
    )


def test_verification_only_blocks_without_repair(tmp_path: Path):
    pytest.importorskip("langgraph")

    run = BenchmarkRunner().run_task_id(
        "coding_stale_tests_001",
        BenchmarkRunConfig(
            framework="langgraph_tools",
            trace_mode="model_driven",
            intervention="verification_only",
            workspace_root=str(tmp_path),
        ),
    )

    decisions = [
        event
        for event in run["trace_events"]
        if event.get("event_type") == "verification_decision"
    ]
    assert run["run_metadata"]["intervention"] == "verification_only"
    assert run["run_metadata"]["agent_variant"] == "verified"
    assert run["run_metadata"]["memory_repair"] is False
    assert decisions
    assert all(event["gate_mode"] == "blocking" for event in decisions)
    assert run["interaction_metrics"]["blocked_false_finishes"] >= 1
    assert run["interaction_metrics"]["memory_repair_attempts"] == 0
    assert run["interaction_metrics"]["accepted_false_finishes"] == 0


def test_repair_only_repairs_but_never_issues_terminal_veto(tmp_path: Path):
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
                intervention="repair_only",
                action_budget=8,
                workspace_root=str(tmp_path),
            ),
        )

    metrics = run["interaction_metrics"]
    decisions = [
        event
        for event in run["trace_events"]
        if event.get("event_type") == "verification_decision"
    ]
    assert run["run_metadata"]["intervention"] == "repair_only"
    assert run["run_metadata"]["verification_blocking"] is False
    assert all(event["gate_mode"] == "non_blocking" for event in decisions)
    # Repair still runs while the bounded budget lasts.
    assert metrics["memory_repair_attempts"] >= 1
    # Once the repair budget is exhausted, the gate lets the proposal
    # through instead of issuing a terminal veto.
    assert metrics["termination_reason"] == "accepted_finish"
    assert metrics["accepted_false_finishes"] >= 1
    assert metrics["detected_corruption"] is True
    assert metrics["contained_recovery"] is False
    allowed_unverified = [
        event
        for event in decisions
        if event.get("decision") == "allow"
        and "unverified" in event.get("content", "")
    ]
    assert allowed_unverified


def test_verification_and_repair_matches_legacy_verified(tmp_path: Path):
    pytest.importorskip("langgraph")

    legacy = BenchmarkRunner().run_task_id(
        "coding_stale_tests_001",
        BenchmarkRunConfig(
            framework="langgraph_tools",
            trace_mode="model_driven",
            agent_variant="verified",
            workspace_root=str(tmp_path / "legacy"),
        ),
    )
    intervention = BenchmarkRunner().run_task_id(
        "coding_stale_tests_001",
        BenchmarkRunConfig(
            framework="langgraph_tools",
            trace_mode="model_driven",
            intervention="verification_and_repair",
            workspace_root=str(tmp_path / "intervention"),
        ),
    )

    assert intervention["run_metadata"]["agent_variant"] == "verified"
    assert intervention["run_metadata"]["memory_repair"] is True
    assert intervention["run_metadata"]["verification_blocking"] is True
    assert (
        intervention["interaction_metrics"]
        == legacy["interaction_metrics"]
    )
    assert intervention["run_id"] != legacy["run_id"]


def test_matrix_interventions_axis_produces_distinct_paired_runs(
    tmp_path: Path,
):
    pytest.importorskip("langgraph")
    matrix_path = tmp_path / "matrix.json"
    matrix_path.write_text(
        json.dumps(
            {
                "schema_version": "agent-memory-model-matrix/v0.1",
                "runtime": "deterministic",
                "minimum_successful_models": 1,
                "models": [
                    {
                        "model_family": "qwen",
                        "model_name": "qwen2.5-coder:7b",
                        "enabled": True,
                    }
                ],
            }
        )
    )

    manifest = run_model_matrix(
        tmp_path / "out",
        matrix_path=matrix_path,
        framework="langgraph_tools",
        task_ids=["coding_easy_flag_default_001"],
        interventions=list(INTERVENTION_CONDITIONS),
        seeds=[0],
        minimum_successful_models=1,
        trace_mode="model_driven",
    )

    assert manifest["interventions"] == list(INTERVENTION_CONDITIONS)
    assert manifest["variants"] == list(INTERVENTION_CONDITIONS)
    assert manifest["planned_run_count"] == 4
    assert manifest["completed_run_count"] == 4
    # Each non-baseline condition pairs against memory_baseline.
    assert manifest["completed_pair_count"] == 3

    model = manifest["models"][0]
    run_ids = set()
    interventions_seen = set()
    for run_info in model["runs"]:
        payload = json.loads(Path(run_info["path"]).read_text())
        run_ids.add(payload["run_id"])
        interventions_seen.add(
            payload["run_metadata"]["intervention"]
        )
    assert len(run_ids) == 4
    assert interventions_seen == set(INTERVENTION_CONDITIONS)

    with pytest.raises(ValueError):
        run_model_matrix(
            tmp_path / "invalid",
            matrix_path=matrix_path,
            framework="langgraph_tools",
            task_ids=["coding_easy_flag_default_001"],
            interventions=["memory_baseline"],
            variants=["baseline"],
            seeds=[0],
            trace_mode="model_driven",
        )


def test_unsafe_mutation_gate_blocks_corrupted_file_basis():
    fresh_ledger = [
        {"path": "config_parser.py", "stale": False},
    ]
    stale_ledger = [
        {"path": "config_parser.py", "stale": False},
        {"path": "config_parser.py", "stale": True},
    ]
    contradicted_ledger = [
        {"path": "config_parser.py", "support_status": "contradicted"},
    ]
    write_action = {"action": "write_file", "path": "config_parser.py"}

    assert (
        BenchmarkRunner._unsafe_mutation_reason(write_action, fresh_ledger)
        is None
    )
    assert (
        BenchmarkRunner._unsafe_mutation_reason(
            {"action": "read_file", "path": "config_parser.py"},
            stale_ledger,
        )
        is None
    )
    assert (
        BenchmarkRunner._unsafe_mutation_reason(
            {"action": "write_file", "path": "other.py"},
            stale_ledger,
        )
        is None
    )
    stale_reason = BenchmarkRunner._unsafe_mutation_reason(
        write_action,
        stale_ledger,
    )
    assert stale_reason and "stale" in stale_reason
    contradicted_reason = BenchmarkRunner._unsafe_mutation_reason(
        write_action,
        contradicted_ledger,
    )
    assert contradicted_reason and "contradicted" in contradicted_reason
