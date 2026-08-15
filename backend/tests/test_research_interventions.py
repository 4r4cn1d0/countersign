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
from research.runner.matrix_analysis import analyze_model_matrix_manifest
from research.runner.model_adapters import ModelResponse
from research.runner.model_matrix import run_model_matrix


def test_resolve_intervention_specs():
    assert INTERVENTION_CONDITIONS == (
        "memory_baseline",
        "observe_only",
        "verification_only",
        "repair_only",
        "verification_and_repair",
    )

    baseline = resolve_intervention("memory_baseline")
    assert baseline.agent_variant == "baseline"
    assert baseline.memory_repair is False
    assert baseline.verification_blocking is False

    observe_only = resolve_intervention("observe_only")
    assert observe_only.agent_variant == "verified"
    assert observe_only.memory_repair is False
    assert observe_only.verification_blocking is False

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
    assert manifest["planned_run_count"] == 5
    assert manifest["completed_run_count"] == 5
    # Each non-baseline condition pairs against memory_baseline.
    assert manifest["completed_pair_count"] == 4

    model = manifest["models"][0]
    run_ids = set()
    interventions_seen = set()
    for run_info in model["runs"]:
        payload = json.loads(Path(run_info["path"]).read_text())
        run_ids.add(payload["run_id"])
        interventions_seen.add(
            payload["run_metadata"]["intervention"]
        )
    assert len(run_ids) == 5
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


def test_tool_workspace_paths_are_isolated_per_intervention(tmp_path: Path):
    """Every intervention condition must resolve to a distinct workspace.

    observe_only/verification_only/repair_only/verification_and_repair all
    share agent_variant="verified" — if the workspace slug keyed on
    agent_variant alone, they would collide on the same workspace, trace
    journal, and checkpoint path and silently overwrite each other when
    run in the same matrix sweep.
    """
    runner = BenchmarkRunner()
    task = runner.get_task("coding_stale_tests_001")
    workspace_paths = []
    for intervention in INTERVENTION_CONDITIONS:
        spec = resolve_intervention(intervention)
        config = BenchmarkRunConfig(
            framework="langgraph_tools",
            agent_variant=spec.agent_variant,
            verifier_enabled=spec.verifier_enabled,
            intervention=intervention,
            workspace_root=str(tmp_path),
            seed=0,
        )
        workspace_paths.append(runner._tool_workspace_path(task, config))

    assert len(set(workspace_paths)) == len(INTERVENTION_CONDITIONS)

    # Different pressure profiles must also isolate, independent of
    # intervention/agent_variant.
    baseline_config = BenchmarkRunConfig(
        framework="langgraph_tools",
        agent_variant="baseline",
        intervention="memory_baseline",
        workspace_root=str(tmp_path),
        seed=0,
        pressure_profile_id="full_history",
    )
    corrupted_config = BenchmarkRunConfig(
        framework="langgraph_tools",
        agent_variant="baseline",
        intervention="memory_baseline",
        workspace_root=str(tmp_path),
        seed=0,
        pressure_profile_id="lossy_medium",
    )
    assert runner._tool_workspace_path(
        task, baseline_config
    ) != runner._tool_workspace_path(task, corrupted_config)


def test_intervention_mode_manifest_analysis_pairs_every_treatment_condition(
    tmp_path: Path,
):
    """analyze_model_matrix_manifest must not silently produce empty pairs.

    Intervention-mode run artifacts record their "variant" as the actual
    intervention name (e.g. "observe_only"), never the literal strings
    "baseline"/"verified" that the legacy two-arm analysis path looks for.
    Every non-baseline condition must be paired against memory_baseline as
    its own reference/treatment comparison, not silently dropped.
    """
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

    report = analyze_model_matrix_manifest(Path(manifest["manifest_path"]))

    assert report["reference_condition"] == "memory_baseline"
    assert set(report["treatment_conditions"]) == {
        "observe_only",
        "verification_only",
        "repair_only",
        "verification_and_repair",
    }
    # One full set of paired rows per treatment condition.
    assert len(report["tasks"]) == len(report["treatment_conditions"])
    for row in report["tasks"]:
        assert row["reference_condition"] == "memory_baseline"
        assert row["treatment_condition"] in report["treatment_conditions"]
        # The core bug: these were always None/empty because the analysis
        # looked for pair["baseline"]/pair["verified"] literally.
        assert row["pair_complete"] is True
        assert row["exclusion_reason"] is None
    # A multi-arm manifest has no single valid pooled statistic — pooling
    # the same memory_baseline observation across four treatment
    # comparisons would violate McNemar's independence assumption.
    assert report["paired_statistics"] is None
    expected_comparisons = {
        f"memory_baseline__vs__{treatment}"
        for treatment in report["treatment_conditions"]
    } | {"verification_only__vs__verification_and_repair"}
    assert set(report["pairwise_statistics"]) == expected_comparisons
    for comparison, stats in report["pairwise_statistics"].items():
        assert stats["eligible_pair_count"] == 1, comparison
    assert report["model_count"] == 1
    assert report["model_treatment_summary_count"] == len(
        report["treatment_conditions"]
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
