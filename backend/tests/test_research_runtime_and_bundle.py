"""Tests for runtime adapter path and benchmark artifact bundles."""

import json
import os
import subprocess
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
    ModelRequest,
    ModelResponse,
    compare_runs,
    create_model_adapter,
    generate_artifact_bundle,
    generate_artifact_summary,
)


def test_deterministic_model_adapter_contract():
    adapter = create_model_adapter("deterministic")
    response = adapter.generate(
        ModelRequest(
            prompt="Check memory claims.",
            model_name="qwen2.5-coder:7b",
            model_family="qwen",
            temperature=0.0,
            seed=123,
            prompt_template="test_template",
        )
    )

    assert response.runtime == "deterministic"
    assert response.model_family == "qwen"
    assert response.text
    assert response.raw_response["seed"] == 123


def test_ollama_adapter_contract_without_network():
    with patch("research.runner.model_adapters._post_json", return_value={"response": "ok"}):
        adapter = create_model_adapter("ollama", "http://127.0.0.1:11434")
        response = adapter.generate(
            ModelRequest(
                prompt="Check memory claims.",
                model_name="qwen2.5-coder:7b",
                model_family="qwen",
                temperature=0.0,
                seed=0,
                prompt_template="test_template",
            )
        )

    assert response.runtime == "ollama"
    assert response.text == "ok"


def test_runner_records_runtime_metadata_and_model_response():
    config = BenchmarkRunConfig(
        runtime="deterministic",
        prompt_template="test_template",
        temperature=0.2,
        seed=99,
    )
    run = BenchmarkRunner().run_task_id("coding_stale_tests_001", config)

    metadata = run["run_metadata"]
    assert metadata["runtime"] == "deterministic"
    assert metadata["prompt_template"] == "test_template"
    assert metadata["temperature"] == 0.2
    assert metadata["seed"] == 99
    assert run["model_response"]["runtime"] == "deterministic"


def test_verified_run_variant_attaches_verification_artifacts():
    run = BenchmarkRunner().run_task_id(
        "coding_stale_tests_001",
        BenchmarkRunConfig(agent_variant="verified"),
    )

    assert run["run_metadata"]["agent_variant"] == "verified"
    assert "verification_report" in run
    assert "effective_memory_health_report" in run
    assert "raw_memory_claims" in run
    assert any(
        event["event_type"] == "verification_decision"
        for event in run["trace_events"]
    )


def test_artifact_bundle_generation_creates_reloadable_outputs(tmp_path: Path):
    manifest = generate_artifact_bundle(
        tmp_path,
        config=BenchmarkRunConfig(seed=11),
        test_status="unit-test",
    )

    manifest_path = Path(manifest["manifest_path"])
    summary_path = Path(manifest["summary_markdown"])
    reloaded_manifest = json.loads(manifest_path.read_text())

    assert reloaded_manifest["schema_version"] == "agent-memory-artifact-bundle/v0.1"
    assert reloaded_manifest["test_status"] == "unit-test"
    assert summary_path.exists()
    assert "Agent Memory Artifact Summary" in summary_path.read_text()
    assert reloaded_manifest["tasks"]

    for task in reloaded_manifest["tasks"]:
        assert Path(task["baseline_run"]).exists()
        assert Path(task["verified_run"]).exists()
        assert Path(task["comparison_json"]).exists()
        comparison = json.loads(Path(task["comparison_json"]).read_text())
        assert comparison["schema_version"] == "agent-memory-comparison/v0.1"


def test_artifact_bundle_manifest_records_commands_and_regenerates_comparisons(
    tmp_path: Path,
):
    manifest = generate_artifact_bundle(
        tmp_path,
        config=BenchmarkRunConfig(runtime="deterministic", seed=21),
        test_status="repro-test",
    )
    reloaded_manifest = json.loads(Path(manifest["manifest_path"]).read_text())

    assert reloaded_manifest["config"]["runtime"] == "deterministic"
    assert reloaded_manifest["config"]["seed"] == 21
    assert reloaded_manifest["commands"]
    assert all(task["task_id"] for task in reloaded_manifest["tasks"])

    first_task = reloaded_manifest["tasks"][0]
    baseline = json.loads(Path(first_task["baseline_run"]).read_text())
    verified = json.loads(Path(first_task["verified_run"]).read_text())
    stored_comparison = json.loads(Path(first_task["comparison_json"]).read_text())
    regenerated_comparison = compare_runs(baseline, verified)

    assert regenerated_comparison["metric_deltas"] == stored_comparison["metric_deltas"]
    assert (
        regenerated_comparison["verification_overhead"]
        == stored_comparison["verification_overhead"]
    )


def test_artifact_summary_is_generated_from_manifest(tmp_path: Path):
    manifest = generate_artifact_bundle(tmp_path, test_status="unit-test")
    summary = generate_artifact_summary(manifest)

    assert "This summary is generated from machine-readable benchmark artifacts." in summary
    assert "Deterministic harness results are not real open-source LLM agent results." in summary
    assert "coding_stale_tests_001" in summary


def test_cli_bundle_command_creates_manifest_and_summary(tmp_path: Path):
    output_dir = tmp_path / "bundle"
    result = subprocess.run(
        [
            sys.executable,
            "scripts/agent_memory.py",
            "bundle",
            "--out",
            str(output_dir),
            "--test-status",
            "cli-test",
            "--format",
            "json",
        ],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    payload = json.loads(result.stdout)

    assert Path(payload["manifest_path"]).exists()
    assert Path(payload["summary_markdown"]).exists()
    manifest = json.loads(Path(payload["manifest_path"]).read_text())
    assert manifest["test_status"] == "cli-test"


@pytest.mark.real_runtime
def test_optional_real_open_source_runtime_smoke():
    runtime = os.environ.get("AGENT_MEMORY_REAL_RUNTIME")
    if not runtime:
        pytest.skip("Set AGENT_MEMORY_REAL_RUNTIME to ollama or llama_cpp to enable")

    run = BenchmarkRunner().run_task_id(
        "coding_stale_tests_001",
        BenchmarkRunConfig(
            runtime=runtime,
            runtime_endpoint=os.environ.get("AGENT_MEMORY_REAL_RUNTIME_ENDPOINT"),
            seed=3,
        ),
    )

    assert run["schema_version"] == "agent-memory-run/v0.1"
    assert run["run_metadata"]["runtime"] == runtime
    assert run["run_metadata"]["runtime_error"] is None
    assert run["model_response"]["runtime"] == runtime
    assert run["trace_events"]
    assert run["memory_health_report"]["schema_version"] == "agent-memory-health/v0.1"
