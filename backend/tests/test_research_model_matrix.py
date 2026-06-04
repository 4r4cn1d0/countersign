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
    analyze_model_matrix_manifest,
    load_model_matrix,
    run_model_matrix,
)


def test_default_model_matrix_has_at_least_five_enabled_model_families():
    matrix = load_model_matrix()
    enabled_models = [model for model in matrix["models"] if model.get("enabled", True)]

    assert matrix["runtime"] == "ollama"
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
    model = manifest["models"][0]
    assert model["status"] == "succeeded"
    assert len(model["runs"]) == 2
    assert len(model["comparisons"]) == 1
    for run in model["runs"]:
        assert Path(run["path"]).exists()
    assert Path(model["comparisons"][0]["path"]).exists()


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

    assert report["schema_version"] == "agent-memory-model-matrix-analysis/v0.1"
    assert report["framework"] == "langgraph"
    assert report["successful_model_count"] == 1
    assert report["aggregate"]["baseline_task_rows"] == 1
    assert report["models"][0]["baseline_task_count"] == 1
    assert report["tasks"][0]["parse_status"] in {"json", "json_repaired", "unparsed"}


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
