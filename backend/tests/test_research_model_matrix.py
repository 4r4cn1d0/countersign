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


def test_multi_seed_real_runtime_matrix_rejects_greedy_decoding(tmp_path: Path):
    """Seeds must be genuine replicates, not copies of one greedy episode.

    At temperature 0.0 the sampler seed is inert, so a multi-seed
    real-runtime matrix would enter the same deterministic episode into
    paired statistics once per seed — pseudoreplication. The runner must
    refuse that configuration outright rather than silently produce
    triplicate data. Deterministic-runtime instrumentation matrices are
    exempt (their trajectories are scripted; seeds are bookkeeping).
    """
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
                        "enabled": True,
                    }
                ],
            }
        )
    )

    with pytest.raises(ValueError, match="temperature 0.0"):
        run_model_matrix(
            tmp_path / "out",
            matrix_path=matrix_path,
            task_ids=["coding_stale_tests_001"],
            variants=["baseline"],
            seeds=[0, 1, 2],
            temperature=0.0,
            pull_missing=False,
            minimum_successful_models=1,
        )

    # Sampling makes the same configuration legitimate (the run itself is
    # then skipped for the missing model, which is fine — the guard must
    # not fire).
    manifest = run_model_matrix(
        tmp_path / "out",
        matrix_path=matrix_path,
        task_ids=["coding_stale_tests_001"],
        variants=["baseline"],
        seeds=[0, 1, 2],
        temperature=0.7,
        pull_missing=False,
        minimum_successful_models=1,
    )
    assert manifest["models"][0]["status"] == "skipped"


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
    markdown = format_model_matrix_analysis_markdown(report)
    assert "`accepted_false_finish_trial`" in markdown
    assert "`{name}`" not in markdown
    assert audit_model_matrix_manifest(Path(manifest["manifest_path"]))["valid"] is True


def test_model_matrix_treats_memory_condition_as_a_paired_experiment_axis(
    tmp_path: Path,
):
    pytest.importorskip("langgraph")
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
        seeds=[5],
        memory_conditions=["full_history", "temporal_corruption"],
        memory_pressure_start=2,
        task_state_probes=True,
        probe_interval=2,
        probe_max_tokens=640,
        minimum_successful_models=1,
        trace_mode="model_driven",
    )

    model = manifest["models"][0]
    assert manifest["memory_conditions"] == [
        "full_history",
        "temporal_corruption",
    ]
    assert manifest["planned_run_count"] == 4
    assert manifest["probe_max_tokens"] == 640
    assert model["completed_pair_count"] == 2
    assert {
        run["memory_condition"] for run in model["runs"]
    } == {"full_history", "temporal_corruption"}
    assert len({run["trial_id"] for run in model["runs"]}) == 2
    assert all(
        run["memory_condition"] in run["relative_path"]
        for run in model["runs"]
    )

    report = analyze_model_matrix_manifest(Path(manifest["manifest_path"]))
    assert report["planned_pair_count"] == 2
    assert {
        row["memory_condition"] for row in report["tasks"]
    } == {"full_history", "temporal_corruption"}
    assert (
        report["paired_statistics"]["analysis_unit"]
        == "model-task-pressure-profile-seed pair"
    )
    assert {
        row["pressure_profile_id"] for row in report["tasks"]
    } == {"full_history", "temporal_corruption"}
    assert report["pressure_analysis"]["profile_summaries"]


def test_pressure_study_produces_dose_response_curves(tmp_path: Path):
    pytest.importorskip("langgraph")
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
        pressure_profile_ids=[
            "control_full_history",
            "lossy_low",
            "lossy_medium",
            "lossy_high",
        ],
        task_state_probes=True,
        probe_interval=4,
        probe_max_tokens=640,
        minimum_successful_models=1,
        trace_mode="model_driven",
    )

    assert manifest["planned_run_count"] == 8
    assert manifest["completed_run_count"] == 8

    report = analyze_model_matrix_manifest(Path(manifest["manifest_path"]))
    dose_response = report["dose_response"]
    assert dose_response["schema_version"] == (
        "agent-memory-dose-response/v0.1"
    )
    severities = dose_response["severities"]
    assert [
        entry["pressure_severity_ordinal"] for entry in severities
    ] == [0, 1, 2, 3]
    for entry in severities:
        assert entry["row_count"] == 1
        assert 0.0 <= entry["baseline_accepted_false_finish_rate"] <= 1.0
        assert 0.0 <= entry["verified_contained_recovery_rate"] <= 1.0
        # Deterministic adapters cannot answer task-state probes, so the
        # per-action accuracy curve is empty here; real-model runs fill it.
        assert entry["mean_probe_accuracy_by_action"] == []


def test_cohens_h_effect_size():
    from research.runner.statistics import cohens_h

    assert cohens_h(0.5, 0.5) == 0.0
    assert cohens_h(None, 0.5) is None
    # Known value: h(0.75, 0.50) = 2*asin(sqrt(.75)) - 2*asin(sqrt(.5))
    assert cohens_h(0.75, 0.5) == pytest.approx(0.5236, abs=1e-4)
    assert cohens_h(0.5, 0.75) == pytest.approx(-0.5236, abs=1e-4)


def test_survival_curve_kaplan_meier_with_censoring():
    from research.runner.statistics import survival_curve

    curve = survival_curve(
        [4, 6, 6, 10, 12],
        [True, True, True, False, True],
    )
    assert curve["subjects"] == 5
    assert curve["events"] == 4
    points = {point["time"]: point for point in curve["points"]}
    # t=4: 5 at risk, 1 event -> S = 0.8
    assert points[4]["survival"] == pytest.approx(0.8)
    # t=6: 4 at risk, 2 events -> S = 0.8 * 0.5 = 0.4
    assert points[6]["survival"] == pytest.approx(0.4)
    # t=10 censored; t=12: 1 at risk, 1 event -> S = 0
    assert points[12]["survival"] == pytest.approx(0.0)
    assert curve["median_time"] == 6

    empty = survival_curve([], [])
    assert empty["subjects"] == 0
    assert empty["median_time"] is None


def test_cohens_kappa_agreement():
    from research.runner.statistics import cohens_kappa

    perfect = cohens_kappa(["a", "b", "a"], ["a", "b", "a"])
    assert perfect["kappa"] == 1.0

    result = cohens_kappa(
        ["yes", "yes", "no", "no"],
        ["yes", "no", "no", "no"],
    )
    assert result["items"] == 4
    assert result["observed_agreement"] == 0.75
    assert 0.0 < result["kappa"] < 1.0

    with pytest.raises(ValueError):
        cohens_kappa(["a"], ["a", "b"])


def test_dose_response_curves_aggregates_probe_trajectories():
    from research.runner.matrix_analysis import dose_response_curves

    def row(ordinal, accuracy, first_stale, false_finish):
        return {
            "pressure_severity_ordinal": ordinal,
            "pressure_severity": ["control", "low", "medium", "high"][
                ordinal
            ],
            "baseline_accepted_false_finishes": false_finish,
            "verified_accepted_false_finishes": 0,
            "verified_contained_recovery": ordinal >= 2,
            "baseline_probe_trajectory": [
                {"action_count": 4, "overall_accuracy": accuracy},
                {"action_count": 8, "overall_accuracy": accuracy - 0.1},
            ],
            "baseline_first_stale_claim_sequence": first_stale,
        }

    curves = dose_response_curves(
        [
            row(0, 0.9, None, 0),
            row(0, 0.8, None, 0),
            row(2, 0.6, 14, 1),
            row(2, 0.5, 10, 1),
        ]
    )

    severities = {
        entry["pressure_severity_ordinal"]: entry
        for entry in curves["severities"]
    }
    control = severities[0]
    medium = severities[2]
    assert control["baseline_accepted_false_finish_rate"] == 0.0
    assert medium["baseline_accepted_false_finish_rate"] == 1.0
    assert medium["verified_contained_recovery_rate"] == 1.0
    assert control["first_corrupted_belief_sequences"] == []
    assert medium["first_corrupted_belief_sequences"] == [10, 14]
    control_points = {
        point["action_count"]: point
        for point in control["mean_probe_accuracy_by_action"]
    }
    assert control_points[4]["mean_overall_accuracy"] == pytest.approx(
        0.85
    )
    assert control_points[4]["sample_count"] == 2
    assert control_points[8]["mean_overall_accuracy"] == pytest.approx(
        0.75
    )


def test_model_matrix_rejects_probe_budget_too_small(tmp_path: Path):
    matrix_path = tmp_path / "matrix.json"
    matrix_path.write_text(
        json.dumps(
            {
                "runtime": "deterministic",
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

    with pytest.raises(ValueError, match="probe_max_tokens"):
        run_model_matrix(
            tmp_path / "out",
            matrix_path=matrix_path,
            task_ids=["coding_stale_tests_001"],
            variants=["baseline"],
            probe_max_tokens=64,
        )


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
    pytest.importorskip("langgraph")

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


def test_protocol_integrity_section_hashes_fixtures_and_policy(
    tmp_path: Path,
):
    runner = BenchmarkRunner()
    matrix_path = tmp_path / "matrix.json"
    matrix_path.write_text('{"models":[]}')
    model = {"model_family": "qwen", "model_name": "qwen2.5-coder:7b"}
    task = runner.get_task("coding_stale_tests_001")
    protocol = build_experiment_protocol(
        matrix_path=matrix_path,
        benchmark_path=runner.benchmark_path,
        selected_models=[model],
        selected_tasks=[task],
        runtime="deterministic",
        framework="langgraph_tools",
        variants=["memory_baseline", "observe_only", "verification_only"],
        seeds=[0, 1, 2],
        temperature=0.0,
        max_tokens=256,
        action_budget=20,
        trace_mode="model_driven",
        prompt_template="default_react_memory_v0",
        constrained_actions=True,
        thinking=False,
        controller_policy_version="test-policy-v1",
        model_names_for_digest=["qwen2.5-coder:7b"],
    )

    integrity = protocol["integrity"]
    assert integrity["scenario_tree_sha256"] is not None
    assert integrity["verifier_policy_hashes"]
    assert all(
        value is not None
        for value in integrity["verifier_policy_hashes"].values()
    )
    assert integrity["intervention_spec_hash"]
    assert integrity["controller_policy_version"] == "test-policy-v1"
    # Absent/unreachable Ollama must yield None per model, not raise.
    assert set(integrity["model_digests"]) == {"qwen2.5-coder:7b"}
    assert integrity["hidden_validation_scope"]

    # Counterbalanced order is a deterministic per-seed rotation of the
    # exact variant list, not the fixed declared order.
    order = protocol["design"]["counterbalanced_order_by_seed"]
    variants = ["memory_baseline", "observe_only", "verification_only"]
    assert order["0"] == variants
    assert order["1"] == [*variants[1:], *variants[:1]]
    assert order["2"] == [*variants[2:], *variants[:2]]
    for rotated in order.values():
        assert sorted(rotated) == sorted(variants)

    assert protocol["predeclared_outcomes"]["primary"]["name"] == (
        "accepted_unsupported_finish_trial"
    )
    assert "accepted_incorrect_finish_trial" in (
        protocol["predeclared_outcomes"]["secondary"]
    )

    # Changing the intervention-spec content changes the protocol identity.
    from research.runner.interventions import _SPECS
    from dataclasses import replace as dc_replace

    original = _SPECS["observe_only"]
    try:
        _SPECS["observe_only"] = dc_replace(
            original, verification_blocking=True
        )
        mutated_protocol = build_experiment_protocol(
            matrix_path=matrix_path,
            benchmark_path=runner.benchmark_path,
            selected_models=[model],
            selected_tasks=[task],
            runtime="deterministic",
            framework="langgraph_tools",
            variants=["memory_baseline", "observe_only", "verification_only"],
            seeds=[0, 1, 2],
            temperature=0.0,
            max_tokens=256,
            action_budget=20,
            trace_mode="model_driven",
            prompt_template="default_react_memory_v0",
            constrained_actions=True,
            thinking=False,
        )
    finally:
        _SPECS["observe_only"] = original
    assert (
        mutated_protocol["integrity"]["intervention_spec_hash"]
        != integrity["intervention_spec_hash"]
    )


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
        variants=["baseline", "verified"],
        minimum_successful_models=1,
        trace_mode="model_driven",
    )

    report = analyze_model_matrix_manifest(Path(manifest["manifest_path"]))

    assert report["schema_version"] == "agent-memory-model-matrix-analysis/v0.4"
    assert report["framework"] == "langgraph"
    assert report["successful_model_count"] == 1
    assert report["aggregate"]["baseline_task_rows"] == 1
    assert report["models"][0]["baseline_task_count"] == 1
    assert report["tasks"][0]["parse_status"] in {"json", "json_repaired", "unparsed"}
    assert "verified_contained_recovery" in report["tasks"][0]
    assert report["tasks"][0]["verified_recovery_level"] in range(5)
    assert "verified_contained_recovery_count" in report["models"][0]
    assert "verified_contained_recovery_rows" in report["aggregate"]
    assert "execution_accounting" in report
    assert "pressure_analysis" in report
    assert report["tasks"][0]["pressure_profile_id"] == "full_history"


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
    assert row["tool_action_parse_status_counts"] == {"json": 20}
    assert 0.0 <= row["baseline_decision_belief_coverage"] <= 1.0
    assert 0.0 <= row["verified_decision_belief_coverage"] <= 1.0
    # None (not a forced 0.0) when there were no tool-decision beliefs to
    # compute a rate over — see metrics.py:_rate.
    baseline_unsupported_rate = row["baseline_unsupported_tool_decision_use_rate"]
    assert baseline_unsupported_rate is None or 0.0 <= baseline_unsupported_rate <= 1.0
    verified_stale_rate = row["verified_stale_tool_decision_use_rate"]
    assert verified_stale_rate is None or 0.0 <= verified_stale_rate <= 1.0
    verified_contradicted_rate = row["verified_contradicted_tool_decision_use_rate"]
    assert (
        verified_contradicted_rate is None
        or 0.0 <= verified_contradicted_rate <= 1.0
    )
    assert model["verified_recovery_count"] == 1
    assert model["baseline_evaluator_success_count"] == 1
    assert model["verified_evaluator_success_count"] == 1
    assert (
        model["avg_baseline_decision_belief_coverage"]
        == row["baseline_decision_belief_coverage"]
    )
    # When the single row's rate is None (no tool-decision beliefs to
    # measure), the aggregate falls back to _mean's empty-input default
    # (0.0) rather than equaling the row's None.
    assert model["avg_verified_stale_tool_decision_use_rate"] == (
        row["verified_stale_tool_decision_use_rate"]
        if row["verified_stale_tool_decision_use_rate"] is not None
        else 0.0
    )
    assert report["aggregate"]["total_false_completion_claims"] >= 1
    assert report["aggregate"]["verified_blocked_false_finishes"] == 1
    assert report["aggregate"][
        "avg_verified_contradicted_tool_decision_use_rate"
    ] == (
        row["verified_contradicted_tool_decision_use_rate"]
        if row["verified_contradicted_tool_decision_use_rate"] is not None
        else 0.0
    )
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


def test_strict_freeze_violations_enumerates_each_defect():
    from research.runner.experiment_protocol import strict_freeze_violations

    broken = {
        "source_revision": None,
        "integrity": {
            "clean_working_tree": {
                "checked": True,
                "clean": False,
                "dirty_paths": ["research/runner/claims.py"],
            },
            "verifier_policy_hashes": {
                "research/runner/verification.py": "abc",
                "research/runner/benchmark_runner.py": None,
            },
            "scenario_tree_sha256": None,
            "controller_policy_version": None,
            "model_digests": {"qwen2.5-coder:14b": None},
        },
    }
    violations = strict_freeze_violations(broken, runtime="ollama")
    text = "\n".join(violations)
    assert "no git revision" in text
    assert "working tree is dirty" in text
    assert "research/runner/claims.py" in text
    assert "benchmark_runner.py" in text
    assert "scenario tree hash missing" in text
    assert "controller_policy_version" in text
    assert "qwen2.5-coder:14b" in text

    clean = {
        "source_revision": "deadbeef",
        "integrity": {
            "clean_working_tree": {
                "checked": True,
                "clean": True,
                "dirty_paths": [],
            },
            "verifier_policy_hashes": {
                "research/runner/verification.py": "abc",
            },
            "scenario_tree_sha256": "def",
            "controller_policy_version": "v4-oracle-arm-flag",
            "model_digests": {"qwen2.5-coder:14b": "sha256:123"},
        },
    }
    assert strict_freeze_violations(clean, runtime="ollama") == []
    # A deterministic runtime has no weights to pin, so absent digests
    # are not a violation there.
    clean["integrity"]["model_digests"] = {}
    assert strict_freeze_violations(clean, runtime="deterministic") == []
    assert strict_freeze_violations(clean, runtime="ollama") != []


def test_model_matrix_strict_freeze_refuses_dirty_tree(
    tmp_path: Path, monkeypatch
):
    """Strict mode must refuse BEFORE writing a protocol or running
    anything — a frozen bundle whose own integrity block says 'dirty
    tree' is not a freeze record at all."""
    import research.runner.experiment_protocol as protocol_module

    monkeypatch.setattr(
        protocol_module,
        "clean_working_tree_status",
        lambda: {
            "checked": True,
            "clean": False,
            "dirty_paths": ["research/runner/claims.py"],
        },
    )
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
    out_dir = tmp_path / "out"
    with pytest.raises(RuntimeError, match="strict freeze mode refused"):
        run_model_matrix(
            out_dir,
            matrix_path=matrix_path,
            task_ids=["coding_stale_tests_001"],
            variants=["baseline", "verified"],
            minimum_successful_models=1,
            trace_mode="scripted",
            strict_freeze=True,
        )
    assert not (out_dir / "experiment_protocol.json").exists()


def test_model_matrix_strict_freeze_passes_on_clean_tree(
    tmp_path: Path, monkeypatch
):
    import research.runner.experiment_protocol as protocol_module

    monkeypatch.setattr(
        protocol_module,
        "clean_working_tree_status",
        lambda: {"checked": True, "clean": True, "dirty_paths": []},
    )
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
        strict_freeze=True,
    )
    assert manifest["successful_model_count"] == 1
    assert Path(manifest["protocol_path"]).exists()


def test_negative_control_false_block_rate_is_aggregated(tmp_path: Path):
    """The predeclared F3 formula (research/HELDOUT_DESIGN_REVIEW.md):
    raw would-block decisions over finish proposals on observe_only
    negative-control runs. doc_clarification contributes exactly one raw
    block per run BY DESIGN; doc_edit contributes zero."""
    pytest.importorskip("langgraph")
    from research.runner.matrix_analysis import analyze_model_matrix_manifest

    matrix_path = tmp_path / "matrix.json"
    matrix_path.write_text(
        json.dumps(
            {
                "schema_version": "agent-memory-model-matrix/v0.1",
                "runtime": "deterministic",
                "framework": "langgraph_tools",
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
        task_ids=[
            "coding_heldout_negctrl_doc_edit_001",
            "coding_heldout_negctrl_doc_clarification_001",
        ],
        interventions=["memory_baseline", "observe_only"],
        seeds=[0],
        minimum_successful_models=1,
        trace_mode="model_driven",
        action_budget=26,
    )
    report = analyze_model_matrix_manifest(Path(manifest["manifest_path"]))
    false_blocks = report["negative_control_false_blocks"]
    assert false_blocks is not None
    overall = false_blocks["overall"]
    assert overall["runs"] == 2
    assert overall["finish_proposals"] == 2
    assert overall["raw_blocked_proposals"] == 1
    assert overall["false_block_rate"] == 0.5
    assert overall["wilson_95ci"]["total"] == 2
    families = false_blocks["per_family"]
    assert families["irrelevant_requirement_clarification"][
        "raw_blocked_proposals"
    ] == 1
    assert families["documentation_edit_after_fresh_tests"][
        "raw_blocked_proposals"
    ] == 0
    markdown = __import__(
        "research.runner.matrix_analysis", fromlist=["x"]
    ).format_model_matrix_analysis_markdown(report)
    assert "Negative-Control False Blocks" in markdown


def test_interrupted_matrix_reuses_completed_artifacts(tmp_path: Path):
    """Re-invoking a matrix over an output dir with completed run
    artifacts must REUSE them byte-identically, not re-execute or
    rewrite them — re-running would silently resample episodes, and
    rewriting would destroy the original experiment_context."""
    pytest.importorskip("langgraph")
    import hashlib

    matrix_path = tmp_path / "matrix.json"
    matrix_path.write_text(
        json.dumps(
            {
                "schema_version": "agent-memory-model-matrix/v0.1",
                "runtime": "deterministic",
                "framework": "langgraph_tools",
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
    out_dir = tmp_path / "out"
    kwargs = dict(
        matrix_path=matrix_path,
        task_ids=["coding_heldout_temporal_fresh_001"],
        interventions=["memory_baseline", "verification_only"],
        seeds=[0],
        minimum_successful_models=1,
        trace_mode="model_driven",
        action_budget=26,
    )
    first = run_model_matrix(out_dir, **kwargs)
    assert first["reused_run_count"] == 0
    run_files = sorted((out_dir / "runs").rglob("*.json"))
    assert len(run_files) == 2
    hashes_before = {
        p: hashlib.sha256(p.read_bytes()).hexdigest() for p in run_files
    }

    second = run_model_matrix(out_dir, **kwargs)
    assert second["reused_run_count"] == 2
    assert second["models"][0]["completed_run_count"] == 2
    for p, digest in hashes_before.items():
        assert hashlib.sha256(p.read_bytes()).hexdigest() == digest
    assert all(
        info.get("reused") for info in second["models"][0]["runs"]
    )


def test_supervision_decomposition_separates_prompt_from_gate():
    """memory_baseline vs verification_only confounds prompt coaching
    with gating. The three-arm decomposition must isolate each, and must
    refuse (None) when the prompt-matched arm is absent."""
    from research.runner.matrix_analysis import (
        exact_mcnemar_p,
        supervision_decomposition,
    )

    def row(task, seed, treatment, ref_unsup, treat_unsup):
        return {
            "model_name": "m",
            "task_id": task,
            "pressure_profile_id": "resume_medium",
            "seed": seed,
            "reference_condition": "memory_baseline",
            "treatment_condition": treatment,
            "baseline_accepted_oracle_unsupported_finish": ref_unsup,
            "verified_accepted_oracle_unsupported_finish": treat_unsup,
        }

    # 5 cells: baseline fails all 5; observe_only fails 3; gate fails 0.
    rows = []
    for seed in range(5):
        rows.append(row("t", seed, "observe_only", True, seed < 3))
        rows.append(row("t", seed, "verification_only", True, False))
    report = supervision_decomposition(rows)
    assert report is not None
    assert report["matched_cells"] == 5
    assert report["rates"]["memory_baseline"]["unsupported"] == 5
    assert report["rates"]["observe_only"]["unsupported"] == 3
    assert report["rates"]["verification_only"]["unsupported"] == 0
    # prompt effect: baseline 5 -> observe 3 => 2 discordant one-way
    assert report["prompt_effect"]["discordant_reference_only"] == 2
    assert report["prompt_effect"]["discordant_treatment_only"] == 0
    # gate effect: observe 3 -> verification 0 => 3 discordant one-way
    assert report["gate_effect"]["discordant_reference_only"] == 3
    assert report["gate_effect"]["discordant_treatment_only"] == 0
    assert report["combined_confounded"]["discordant_reference_only"] == 5
    assert "confounds prompt" in report["combined_confounded"]["caveat"]

    # Refuses rather than guessing when the prompt-matched arm is missing.
    gate_only = [r for r in rows if r["treatment_condition"] == "verification_only"]
    assert supervision_decomposition(gate_only) is None

    assert exact_mcnemar_p(0, 0) is None
    assert exact_mcnemar_p(3, 0) == 0.25
    assert exact_mcnemar_p(5, 0) == 0.0625
