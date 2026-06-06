"""Tests for real-runtime model matrix workflows."""

import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from research.runner import (
    BenchmarkRunner,
    analyze_model_matrix_manifest,
    audit_model_matrix_manifest,
    build_experiment_protocol,
    build_paired_statistics,
    exact_mcnemar,
    format_model_matrix_analysis_markdown,
    load_model_matrix,
    run_model_matrix,
    sha256_file,
    wilson_interval,
)


def test_default_model_matrix_has_at_least_five_enabled_model_families():
    matrix = load_model_matrix()
    enabled_models = [model for model in matrix["models"] if model.get("enabled", True)]

    assert matrix["runtime"] == "ollama"
    assert matrix["framework"] == "langgraph_tools"
    assert len(matrix["seeds"]) >= 3
    assert matrix["constrained_actions"] is True
    assert matrix["thinking"] is False
    assert matrix["minimum_successful_models"] >= 5
    assert len(enabled_models) >= 5
    assert len({model["model_family"] for model in enabled_models}) >= 5
    assert all(model["model_name"] for model in enabled_models)
    assert all(model["pull_command"].startswith("ollama pull ") for model in enabled_models)


def test_model_matrix_skips_missing_ollama_models_without_fallback(tmp_path: Path):
    matrix_path = tmp_path / "matrix.json"
    matrix_path.write_text(
        json.dumps(
            {
                "schema_version": "agent-memory-model-matrix/v0.1",
                "runtime": "ollama",
                "minimum_successful_models": 1,
                "models": [
                    {
                        "model_family": "qwen",
                        "model_name": "missing-local-model:1b",
                        "display_name": "Missing",
                        "pull_command": "ollama pull missing-local-model:1b",
                        "enabled": True,
                    }
                ],
            }
        )
    )

    manifest = run_model_matrix(
        tmp_path / "out",
        matrix_path=matrix_path,
        task_ids=["coding_stale_tests_001"],
        variants=["baseline"],
        pull_missing=False,
        minimum_successful_models=1,
    )

    assert manifest["successful_model_count"] == 0
    assert manifest["meets_minimum_successful_models"] is False
    assert manifest["models"][0]["status"] == "skipped"
    assert manifest["failed_run_count"] == 0
    assert manifest["skipped_run_count"] == 1
    assert "not installed" in manifest["models"][0]["skip_reason"]


def test_model_matrix_writes_runs_scores_verifications_and_comparisons(tmp_path: Path):
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
                        "display_name": "Qwen deterministic test",
                        "pull_command": "ollama pull qwen2.5-coder:7b",
                        "enabled": True,
                    }
                ],
            }
        )
    )

    manifest = run_model_matrix(
        tmp_path / "out",
        matrix_path=matrix_path,
        task_ids=["coding_stale_tests_001"],
        variants=["baseline", "verified"],
        minimum_successful_models=1,
        trace_mode="scripted",
    )

    assert manifest["successful_model_count"] == 1
    assert manifest["meets_minimum_successful_models"] is True
    assert Path(manifest["manifest_path"]).exists()
    assert Path(manifest["summary_markdown"]).exists()
    assert Path(manifest["protocol_path"]).exists()
    assert Path(manifest["artifact_index_path"]).exists()
    model = manifest["models"][0]
    assert model["status"] == "succeeded"
    assert len(model["runs"]) == 2
    assert len(model["comparisons"]) == 1
    for run in model["runs"]:
        assert Path(run["path"]).exists()
    assert Path(model["comparisons"][0]["path"]).exists()


def test_model_matrix_runs_paired_multi_seed_trials_with_hashes(tmp_path: Path):
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
        task_ids=["coding_stale_tests_001"],
        variants=["baseline", "verified"],
        seeds=[3, 7, 11],
        minimum_successful_models=1,
        trace_mode="model_driven",
    )

    model = manifest["models"][0]
    assert manifest["seeds"] == [3, 7, 11]
    assert manifest["planned_run_count"] == 6
    assert manifest["completed_run_count"] == 6
    assert manifest["completed_pair_count"] == 3
    assert model["completed_pair_count"] == 3
    assert {run["seed"] for run in model["runs"]} == {3, 7, 11}
    assert len({run["trial_id"] for run in model["runs"]}) == 3
    for run in model["runs"]:
        run_path = Path(run["path"])
        assert run["sha256"] == sha256_file(run_path)
        payload = json.loads(run_path.read_text())
        assert payload["experiment_context"]["protocol_id"] == manifest["protocol_id"]

    report = analyze_model_matrix_manifest(Path(manifest["manifest_path"]))
    primary = report["paired_statistics"]["binary_outcomes"][
        "accepted_false_finish_trial"
    ]
    assert report["eligible_pair_count"] == 3
    assert primary["baseline"]["successes"] == 3
    assert primary["verified"]["successes"] == 0
    assert primary["verified"]["ci95"][1] > 0
    assert primary["mcnemar"]["p_value_two_sided_exact"] == 0.25
    assert audit_model_matrix_manifest(Path(manifest["manifest_path"]))["valid"] is True


def test_artifact_audit_detects_tampering(tmp_path: Path):
    matrix_path = tmp_path / "matrix.json"
    matrix_path.write_text(
        json.dumps(
            {
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
        task_ids=["coding_stale_tests_001"],
        variants=["baseline"],
        seeds=[0],
        minimum_successful_models=1,
    )
    run_path = Path(manifest["models"][0]["runs"][0]["path"])
    run_path.write_text(run_path.read_text() + "\n")

    audit = audit_model_matrix_manifest(Path(manifest["manifest_path"]))

    assert audit["valid"] is False
    assert audit["hash_mismatches"][0]["path"].endswith(
        "coding_stale_tests_001.json"
    )


def test_frozen_protocol_rejects_changed_experiment_in_same_output_dir(
    tmp_path: Path,
):
    matrix_path = tmp_path / "matrix.json"
    matrix_path.write_text(
        json.dumps(
            {
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
    output_dir = tmp_path / "out"
    run_model_matrix(
        output_dir,
        matrix_path=matrix_path,
        task_ids=["coding_stale_tests_001"],
        variants=["baseline"],
        seeds=[0],
        minimum_successful_models=1,
    )

    with pytest.raises(RuntimeError, match="different frozen experiment protocol"):
        run_model_matrix(
            output_dir,
            matrix_path=matrix_path,
            task_ids=["coding_stale_tests_001"],
            variants=["baseline"],
            seeds=[1],
            minimum_successful_models=1,
        )


def test_runtime_failure_is_recorded_and_does_not_abort_remaining_trials(
    tmp_path: Path,
):
    class OneFailureRunner(BenchmarkRunner):
        def run_task_id(self, task_id, config=None):
            if config.seed == 0 and config.agent_variant == "baseline":
                raise RuntimeError("deliberate runtime failure")
            return super().run_task_id(task_id, config)

    matrix_path = tmp_path / "matrix.json"
    matrix_path.write_text(
        json.dumps(
            {
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
        task_ids=["coding_stale_tests_001"],
        variants=["baseline", "verified"],
        seeds=[0, 1],
        minimum_successful_models=1,
        trace_mode="model_driven",
        runner=OneFailureRunner(),
    )

    model = manifest["models"][0]
    assert model["status"] == "partial"
    assert model["completed_run_count"] == 3
    assert model["failed_run_count"] == 1
    assert model["completed_pair_count"] == 1
    assert any(
        run["seed"] == 1 and run["variant"] == "baseline"
        for run in model["runs"]
    )

    report = analyze_model_matrix_manifest(Path(manifest["manifest_path"]))
    stats = report["paired_statistics"]
    assert stats["planned_pair_count"] == 2
    assert stats["eligible_pair_count"] == 1
    assert stats["excluded_pair_count"] == 1
    assert "deliberate runtime failure" in stats["exclusion_ledger"][0]["reason"]


def test_protocol_identifier_is_stable_but_changes_with_generation_settings(
    tmp_path: Path,
):
    runner = BenchmarkRunner()
    matrix_path = tmp_path / "matrix.json"
    matrix_path.write_text('{"models":[]}')
    model = {"model_family": "qwen", "model_name": "qwen2.5-coder:7b"}
    task = runner.get_task("coding_stale_tests_001")
    kwargs = {
        "matrix_path": matrix_path,
        "benchmark_path": runner.benchmark_path,
        "selected_models": [model],
        "selected_tasks": [task],
        "runtime": "deterministic",
        "framework": "langgraph_tools",
        "variants": ["baseline", "verified"],
        "seeds": [0, 1, 2],
        "temperature": 0.0,
        "max_tokens": 256,
        "action_budget": 20,
        "trace_mode": "model_driven",
        "prompt_template": "default_react_memory_v0",
        "constrained_actions": True,
        "thinking": False,
    }

    first = build_experiment_protocol(**kwargs)
    second = build_experiment_protocol(**kwargs)
    changed = build_experiment_protocol(**{**kwargs, "action_budget": 21})

    assert first["protocol_id"] == second["protocol_id"]
    assert first["created_at"] != ""
    assert first["protocol_id"] != changed["protocol_id"]
    changed_thinking = build_experiment_protocol(
        **{**kwargs, "thinking": True}
    )
    assert first["protocol_id"] != changed_thinking["protocol_id"]


def test_predeclared_statistics_report_zero_rate_uncertainty_and_exact_pairing():
    interval = wilson_interval(0, 5)
    paired = exact_mcnemar(
        [True, True, True, False],
        [False, False, False, False],
    )

    assert interval["rate"] == 0.0
    assert interval["ci95"][1] > 0.4
    assert paired["baseline_only"] == 3
    assert paired["verified_only"] == 0
    assert paired["p_value_two_sided_exact"] == 0.25


def test_budget_exhaustion_is_analyzed_not_excluded():
    row = {
        "model_name": "qwen",
        "task_id": "task",
        "seed": 0,
        "pair_eligible": True,
        "exclusion_reason": None,
        "baseline_accepted_false_finishes": 0,
        "verified_accepted_false_finishes": 0,
        "baseline_false_finish_proposals": 0,
        "verified_false_finish_proposals": 0,
        "baseline_accepted_finish_evaluator_failures": 0,
        "verified_accepted_finish_evaluator_failures": 0,
        "baseline_evaluator_success": False,
        "verified_evaluator_success": False,
        "baseline_protocol_completion_status": "action_budget_exhausted",
        "verified_protocol_completion_status": "action_budget_exhausted",
        "baseline_action_compliance_rate": 0.5,
        "verified_action_compliance_rate": 0.5,
        "baseline_model_action_count": 20,
        "verified_model_action_count": 20,
    }

    stats = build_paired_statistics([row])

    assert stats["eligible_pair_count"] == 1
    assert stats["excluded_pair_count"] == 0
    exhausted = stats["binary_outcomes"]["action_budget_exhaustion"]
    assert exhausted["baseline"]["successes"] == 1
    assert exhausted["verified"]["successes"] == 1


def test_model_matrix_records_model_driven_trace_mode(tmp_path: Path):
    matrix_path = tmp_path / "matrix.json"
    matrix_path.write_text(
        json.dumps(
            {
                "schema_version": "agent-memory-model-matrix/v0.1",
                "runtime": "deterministic",
                "trace_mode": "model_driven",
                "prompt_template": "memory_pressure_v0",
                "minimum_successful_models": 1,
                "models": [
                    {
                        "model_family": "qwen",
                        "model_name": "qwen2.5-coder:7b",
                        "display_name": "Qwen deterministic test",
                        "pull_command": "ollama pull qwen2.5-coder:7b",
                        "enabled": True,
                    }
                ],
            }
        )
    )

    manifest = run_model_matrix(
        tmp_path / "out",
        matrix_path=matrix_path,
        task_ids=["coding_stale_tests_001"],
        variants=["baseline"],
        minimum_successful_models=1,
    )
    run_path = Path(manifest["models"][0]["runs"][0]["path"])
    run = json.loads(run_path.read_text())

    assert manifest["trace_mode"] == "model_driven"
    assert manifest["prompt_template"] == "memory_pressure_v0"
    assert run["run_metadata"]["trace_mode"] == "model_driven"
    assert run["run_metadata"]["prompt_template"] == "memory_pressure_v0"
    assert "model_response" in {event["event_type"] for event in run["trace_events"]}


def test_model_matrix_can_run_langgraph_framework(tmp_path: Path):
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
                        "display_name": "Qwen deterministic test",
                        "pull_command": "ollama pull qwen2.5-coder:7b",
                        "enabled": True,
                    }
                ],
            }
        )
    )

    manifest = run_model_matrix(
        tmp_path / "out",
        matrix_path=matrix_path,
        framework="langgraph",
        task_ids=["coding_stale_tests_001"],
        variants=["baseline"],
        minimum_successful_models=1,
        trace_mode="model_driven",
    )
    run_path = Path(manifest["models"][0]["runs"][0]["path"])
    run = json.loads(run_path.read_text())

    assert manifest["framework"] == "langgraph"
    assert run["run_metadata"]["framework"] == "langgraph"
    assert run["run_metadata"]["agent_framework_runtime"] == "langgraph"
    assert {event["framework"] for event in run["trace_events"]} == {"langgraph"}


def test_model_matrix_can_filter_to_one_configured_model(tmp_path: Path):
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
                        "display_name": "Qwen deterministic test",
                        "pull_command": "ollama pull qwen2.5-coder:7b",
                        "enabled": True,
                    },
                    {
                        "model_family": "gemma",
                        "model_name": "gemma4:12b-mlx",
                        "display_name": "Gemma 4 12B deterministic test",
                        "pull_command": "ollama pull gemma4:12b-mlx",
                        "enabled": True,
                    },
                ],
            }
        )
    )

    manifest = run_model_matrix(
        tmp_path / "out",
        matrix_path=matrix_path,
        task_ids=["coding_stale_tests_001"],
        model_names=["gemma4:12b-mlx"],
        variants=["baseline"],
        minimum_successful_models=1,
    )

    assert manifest["model_names"] == ["gemma4:12b-mlx"]
    assert manifest["successful_model_count"] == 1
    assert len(manifest["models"]) == 1
    assert manifest["models"][0]["model_name"] == "gemma4:12b-mlx"


def test_model_matrix_analysis_summarizes_artifact_rows(tmp_path: Path):
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
                        "display_name": "Qwen deterministic test",
                        "pull_command": "ollama pull qwen2.5-coder:7b",
                        "enabled": True,
                    }
                ],
            }
        )
    )
    manifest = run_model_matrix(
        tmp_path / "out",
        matrix_path=matrix_path,
        framework="langgraph",
        task_ids=["coding_stale_tests_001"],
        variants=["baseline", "verified"],
        minimum_successful_models=1,
        trace_mode="model_driven",
    )

    report = analyze_model_matrix_manifest(Path(manifest["manifest_path"]))

    assert report["schema_version"] == "agent-memory-model-matrix-analysis/v0.2"
    assert report["framework"] == "langgraph"
    assert report["successful_model_count"] == 1
    assert report["aggregate"]["baseline_task_rows"] == 1
    assert report["models"][0]["baseline_task_count"] == 1
    assert report["tasks"][0]["parse_status"] in {"json", "json_repaired", "unparsed"}


def test_model_matrix_analysis_reports_langgraph_tool_reality_columns(tmp_path: Path):
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
                        "display_name": "Qwen deterministic test",
                        "pull_command": "ollama pull qwen2.5-coder:7b",
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
        task_ids=["coding_stale_tests_001"],
        variants=["baseline", "verified"],
        minimum_successful_models=1,
        trace_mode="model_driven",
    )

    report = analyze_model_matrix_manifest(Path(manifest["manifest_path"]))
    model = report["models"][0]
    row = report["tasks"][0]
    markdown = format_model_matrix_analysis_markdown(report)

    assert row["used_stale_evidence"] is True
    assert row["baseline_evaluator_success"] is True
    assert row["verified_evaluator_success"] is True
    assert row["false_completion_claim_count"] >= 1
    assert row["baseline_false_finish_proposals"] == 1
    assert row["baseline_accepted_false_finishes"] == 1
    assert row["verified_false_finish_proposals"] == 1
    assert row["verified_blocked_false_finishes"] == 1
    assert row["verified_accepted_false_finishes"] == 0
    assert row["verified_recovery_after_block"] is True
    assert row["tool_action_parse_status_counts"] == {"json": 6}
    assert model["verified_recovery_count"] == 1
    assert model["baseline_evaluator_success_count"] == 1
    assert model["verified_evaluator_success_count"] == 1
    assert report["aggregate"]["total_false_completion_claims"] >= 1
    assert report["aggregate"]["verified_blocked_false_finishes"] == 1
    assert "Coding-Agent Intervention Matrix" in markdown


def test_cli_matrix_report_outputs_analysis(tmp_path: Path):
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
                        "display_name": "Qwen deterministic test",
                        "pull_command": "ollama pull qwen2.5-coder:7b",
                        "enabled": True,
                    }
                ],
            }
        )
    )
    manifest = run_model_matrix(
        tmp_path / "out",
        matrix_path=matrix_path,
        task_ids=["coding_stale_tests_001"],
        variants=["baseline", "verified"],
        minimum_successful_models=1,
        trace_mode="model_driven",
    )
    output_path = tmp_path / "analysis.md"

    result = subprocess.run(
        [
            sys.executable,
            "scripts/agent_memory.py",
            "matrix-report",
            "--manifest",
            manifest["manifest_path"],
            "--out",
            str(output_path),
            "--format",
            "markdown",
        ],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )

    assert "Agent Memory Model Matrix Analysis" in result.stdout
    assert "qwen2.5-coder:7b" in output_path.read_text()


def test_cli_matrix_list_outputs_configured_models():
    result = subprocess.run(
        [
            sys.executable,
            "scripts/agent_memory.py",
            "matrix-list",
            "--format",
            "table",
        ],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )

    assert "qwen2.5-coder:7b" in result.stdout
    assert "deepseek-r1:8b" in result.stdout
