"""Tests for real-runtime model matrix workflows."""

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from research.runner import load_model_matrix, run_model_matrix


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
