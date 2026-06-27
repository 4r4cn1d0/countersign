"""Validation tests for the long-horizon memory corruption seed benchmark."""

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
BENCHMARK_DIR = ROOT / "research" / "benchmarks"


def _load_json(name: str) -> dict:
    with (BENCHMARK_DIR / name).open(encoding="utf-8") as handle:
        return json.load(handle)


def test_seed_benchmark_matches_schema_contract():
    schema = _load_json("ground_truth_schema.json")
    dataset = _load_json("seed_tasks.json")

    assert dataset["schema_version"] == schema["schema_version"]
    assert dataset["tasks"], "seed benchmark must include at least one task"

    allowed_families = set(schema["families"])
    allowed_failure_modes = set(schema["failure_modes"])
    required_fields = set(schema["task_fields"])

    seen_task_ids = set()
    for task in dataset["tasks"]:
        assert required_fields.issubset(task)
        assert task["task_id"] not in seen_task_ids
        seen_task_ids.add(task["task_id"])
        assert task["family"] in allowed_families
        assert set(task["failure_modes_targeted"]).issubset(allowed_failure_modes)
        assert task["open_source_constraints"]["closed_source_models_allowed"] is False


def test_seed_tasks_are_long_horizon_and_memory_hostile():
    dataset = _load_json("seed_tasks.json")

    for task in dataset["tasks"]:
        horizon = task["horizon"]
        assert horizon["expected_steps_min"] >= 18
        assert horizon["expected_tool_calls_min"] >= 10
        assert horizon["requires_context_compression"] is True
        assert len(task["drift_inducers"]) >= 3
        assert len(task["required_subtasks"]) >= 4
        assert len(task["ground_truth_checkpoints"]) >= 3
        assert len(task["high_risk_claims"]) >= 2


def test_ground_truth_checkpoints_and_risk_claims_are_verifiable():
    schema = _load_json("ground_truth_schema.json")
    dataset = _load_json("seed_tasks.json")

    support_labels = set(schema["claim_support_labels"])
    source_types = set(schema["source_types"])
    high_risk_claim_types = set(schema["high_risk_claim_types"])

    for task in dataset["tasks"]:
        for checkpoint in task["ground_truth_checkpoints"]:
            assert checkpoint["support_label"] in support_labels
            assert checkpoint["source_type"] in source_types
            assert checkpoint["expected_evidence"]

        for claim in task["high_risk_claims"]:
            assert claim["claim_type"] in high_risk_claim_types
            assert claim["verification_required"] is True
            assert claim["minimum_source_type"] in source_types
            assert claim["freshness_rule"]


def test_seed_dataset_targets_core_research_failures():
    dataset = _load_json("seed_tasks.json")
    targeted = {
        mode
        for task in dataset["tasks"]
        for mode in task["failure_modes_targeted"]
    }

    assert "semantic_drift" in targeted
    assert "source_confusion" in targeted
    assert "temporal_disordering" in targeted
    assert "false_completion" in targeted


def test_stale_parser_task_discloses_the_independent_evaluator_contract():
    dataset = _load_json("seed_tasks.json")
    task = next(
        item
        for item in dataset["tasks"]
        if item["task_id"] == "coding_stale_tests_001"
    )
    disclosed_contract = " ".join(
        [task["goal"], *task["acceptance_criteria"]]
    ).lower()

    for required_behavior in [
        "blank",
        "comment",
        "malformed",
        "normalize",
        "default",
        "later",
        "override",
    ]:
        assert required_behavior in disclosed_contract
