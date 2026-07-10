"""Tests for the scientific figure generation layer (task 44)."""

import json
from pathlib import Path

import pytest

pytest.importorskip("matplotlib")

from research.plots import FIGURE_REGISTRY, generate_figures  # noqa: E402
from research.runner.model_matrix import run_model_matrix  # noqa: E402


EXPECTED_FIGURES = {
    "success_vs_trajectory_length",
    "accuracy_vs_action",
    "false_completion_vs_severity",
    "recovery_after_detection",
    "success_vs_verification_overhead",
    "model_task_heatmap",
    "time_to_first_corrupted_belief",
    "walkthrough_timeline",
}


@pytest.fixture(scope="module")
def matrix_manifest(tmp_path_factory) -> Path:
    pytest.importorskip("langgraph")
    tmp_path = tmp_path_factory.mktemp("plots-matrix")
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
        task_ids=["coding_easy_flag_default_001"],
        variants=["baseline", "verified"],
        seeds=[0],
        pressure_profile_ids=["control_full_history", "lossy_medium"],
        minimum_successful_models=1,
        trace_mode="model_driven",
    )
    return Path(manifest["manifest_path"])


def test_figure_registry_covers_all_task_44_figures():
    assert set(FIGURE_REGISTRY) == EXPECTED_FIGURES


def test_generate_all_figures_from_manifest(
    matrix_manifest: Path,
    tmp_path: Path,
):
    result = generate_figures(matrix_manifest, tmp_path / "figures")

    assert result["schema_version"] == "agent-memory-figures/v0.1"
    assert set(result["figures"]) == EXPECTED_FIGURES
    for path_text in result["figures"].values():
        path = Path(path_text)
        assert path.is_file()
        assert path.stat().st_size > 0
        assert path.suffix == ".png"


def test_generate_figures_subset_and_unknown_name(
    matrix_manifest: Path,
    tmp_path: Path,
):
    result = generate_figures(
        matrix_manifest,
        tmp_path / "subset",
        figures=["model_task_heatmap"],
    )
    assert list(result["figures"]) == ["model_task_heatmap"]

    with pytest.raises(ValueError):
        generate_figures(
            matrix_manifest,
            tmp_path / "invalid",
            figures=["not_a_figure"],
        )
