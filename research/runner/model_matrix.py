"""Real-runtime, paired multi-seed model matrix evaluation helpers."""

from __future__ import annotations

import json
import subprocess
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .benchmark_runner import (
    CONTROLLER_POLICY_VERSION,
    BenchmarkRunConfig,
    BenchmarkRunner,
)
from .comparison import compare_runs
from .interventions import resolve_intervention
from .experiment_protocol import (
    build_artifact_index,
    build_experiment_protocol,
    counterbalanced_variant_order,
    environment_fingerprint,
    indexed_artifact,
    sha256_file,
    unique_ints,
    write_frozen_protocol,
)
from .metrics import build_memory_health_report
from .memory_pressure import (
    DEFAULT_PRESSURE_PROFILES_PATH,
    resolve_pressure_profiles,
    validate_memory_condition,
)


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_MODEL_MATRIX_PATH = ROOT / "research" / "agents" / "model_matrix.json"


def load_model_matrix(path: Path = DEFAULT_MODEL_MATRIX_PATH) -> dict:
    """Load the configured real-runtime model matrix."""

    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


def run_model_matrix(
    output_dir: Path,
    *,
    matrix_path: Path = DEFAULT_MODEL_MATRIX_PATH,
    runtime: str | None = None,
    runtime_endpoint: str | None = None,
    framework: str | None = None,
    task_ids: list[str] | None = None,
    model_names: list[str] | None = None,
    variants: list[str] | None = None,
    seeds: list[int] | None = None,
    pull_missing: bool = False,
    minimum_successful_models: int | None = None,
    temperature: float | None = None,
    max_tokens: int | None = None,
    action_budget: int | None = None,
    trace_mode: str | None = None,
    prompt_template: str | None = None,
    constrained_actions: bool | None = None,
    thinking: bool | None = None,
    memory_conditions: list[str] | None = None,
    pressure_profile_ids: list[str] | None = None,
    pressure_profiles_path: Path = DEFAULT_PRESSURE_PROFILES_PATH,
    memory_pressure_start: int | None = None,
    memory_window: int | None = None,
    task_state_probes: bool | None = None,
    probe_interval: int | None = None,
    probe_max_tokens: int | None = None,
    memory_repair: bool | None = None,
    interventions: list[str] | None = None,
    runner: BenchmarkRunner | None = None,
) -> dict:
    """Run paired baseline/verified trials under a frozen experiment protocol."""

    matrix = load_model_matrix(matrix_path)
    active_runtime = runtime or matrix.get("runtime", "ollama")
    active_framework = framework or matrix.get("framework", "react_custom")
    intervention_mode = interventions is not None
    if intervention_mode:
        if not interventions:
            raise ValueError(
                "At least one intervention condition is required"
            )
        if variants is not None:
            raise ValueError(
                "Use interventions or variants, not both"
            )
        for name in interventions:
            resolve_intervention(name)
        active_variants = list(interventions)
    else:
        active_variants = variants or ["baseline", "verified"]
    if len(set(active_variants)) != len(active_variants):
        raise ValueError("Experiment variants must be unique")
    active_seeds = unique_ints(
        seeds if seeds is not None else matrix.get("seeds", [0])
    )
    active_runner = runner or BenchmarkRunner()
    dataset = active_runner._load_json(active_runner.benchmark_path)
    tasks_by_id = {task["task_id"]: task for task in dataset["tasks"]}
    active_task_ids = task_ids or list(tasks_by_id)
    missing_tasks = [
        task_id for task_id in active_task_ids if task_id not in tasks_by_id
    ]
    if missing_tasks:
        raise ValueError(f"Unknown benchmark tasks: {', '.join(missing_tasks)}")
    selected_tasks = [tasks_by_id[task_id] for task_id in active_task_ids]
    active_temperature = float(
        temperature if temperature is not None else matrix.get("temperature", 0.0)
    )
    active_max_tokens = int(
        max_tokens if max_tokens is not None else matrix.get("max_tokens", 128)
    )
    active_action_budget = int(
        action_budget
        if action_budget is not None
        else matrix.get("action_budget", 32)
    )
    active_trace_mode = trace_mode or matrix.get("trace_mode", "scripted")
    active_prompt_template = prompt_template or matrix.get(
        "prompt_template",
        "default_react_memory_v0",
    )
    active_constrained_actions = (
        bool(constrained_actions)
        if constrained_actions is not None
        else bool(matrix.get("constrained_actions", True))
    )
    active_thinking = (
        bool(thinking)
        if thinking is not None
        else bool(matrix.get("thinking", False))
    )
    active_memory_conditions = list(
        dict.fromkeys(
            memory_conditions
            if memory_conditions is not None
            else matrix.get("memory_conditions", ["full_history"])
        )
    )
    if not active_memory_conditions:
        raise ValueError("At least one memory condition is required")
    for condition in active_memory_conditions:
        validate_memory_condition(condition)
    active_memory_pressure_start = int(
        memory_pressure_start
        if memory_pressure_start is not None
        else matrix.get("memory_pressure_start", 6)
    )
    active_memory_window = int(
        memory_window
        if memory_window is not None
        else matrix.get("memory_window", 8)
    )
    if pressure_profile_ids is not None and memory_conditions is not None:
        raise ValueError(
            "Use pressure profiles or memory conditions, not both"
        )
    active_pressure_profiles = resolve_pressure_profiles(
        profile_ids=pressure_profile_ids,
        registry_path=pressure_profiles_path,
        memory_conditions=active_memory_conditions,
        memory_pressure_start=active_memory_pressure_start,
        memory_window=active_memory_window,
    )
    active_memory_conditions = list(
        dict.fromkeys(
            profile["condition"] for profile in active_pressure_profiles
        )
    )
    active_task_state_probes = (
        bool(task_state_probes)
        if task_state_probes is not None
        else bool(matrix.get("task_state_probes", False))
    )
    active_probe_interval = int(
        probe_interval
        if probe_interval is not None
        else matrix.get("probe_interval", 5)
    )
    active_probe_max_tokens = int(
        probe_max_tokens
        if probe_max_tokens is not None
        else matrix.get("probe_max_tokens", 1536)
    )
    if active_probe_max_tokens < 128:
        raise ValueError("probe_max_tokens must be at least 128")
    active_memory_repair = (
        bool(memory_repair)
        if memory_repair is not None
        else bool(matrix.get("memory_repair", True))
    )
    minimum_successful = int(
        minimum_successful_models
        if minimum_successful_models is not None
        else matrix.get("minimum_successful_models", 5)
    )

    configured_models = list(matrix["models"])
    if model_names:
        requested_models = set(model_names)
        enabled_models = [
            item
            for item in configured_models
            if item["model_name"] in requested_models
        ]
        missing_models = requested_models - {
            item["model_name"] for item in enabled_models
        }
        if missing_models:
            raise ValueError(
                "Unknown configured models: "
                + ", ".join(sorted(missing_models))
            )
    else:
        enabled_models = [
            item
            for item in configured_models
            if item.get("enabled", True)
        ]

    output_dir.mkdir(parents=True, exist_ok=True)
    protocol = build_experiment_protocol(
        matrix_path=matrix_path,
        benchmark_path=active_runner.benchmark_path,
        selected_models=enabled_models,
        selected_tasks=selected_tasks,
        runtime=active_runtime,
        framework=active_framework,
        variants=active_variants,
        seeds=active_seeds,
        temperature=active_temperature,
        max_tokens=active_max_tokens,
        action_budget=active_action_budget,
        trace_mode=active_trace_mode,
        prompt_template=active_prompt_template,
        constrained_actions=active_constrained_actions,
        thinking=active_thinking,
        memory_conditions=active_memory_conditions,
        pressure_profiles=active_pressure_profiles,
        pressure_profiles_path=(
            pressure_profiles_path
            if pressure_profile_ids is not None
            else None
        ),
        memory_pressure_start=active_memory_pressure_start,
        memory_window=active_memory_window,
        task_state_probes=active_task_state_probes,
        probe_interval=active_probe_interval,
        probe_max_tokens=active_probe_max_tokens,
        memory_repair=active_memory_repair,
        controller_policy_version=CONTROLLER_POLICY_VERSION,
        model_names_for_digest=[
            model["model_name"] for model in enabled_models
        ],
    )
    protocol_path = output_dir / "experiment_protocol.json"
    write_frozen_protocol(protocol_path, protocol)

    installed_inventory = _installed_model_inventory(
        active_runtime,
        runtime_endpoint,
    )
    installed_names = set(installed_inventory)
    model_results = []
    for model in enabled_models:
        model_result = _run_one_model(
            model,
            output_dir=output_dir,
            runtime=active_runtime,
            runtime_endpoint=runtime_endpoint,
            framework=active_framework,
            task_ids=active_task_ids,
            variants=active_variants,
            intervention_mode=intervention_mode,
            seeds=active_seeds,
            temperature=active_temperature,
            max_tokens=active_max_tokens,
            action_budget=active_action_budget,
            trace_mode=active_trace_mode,
            prompt_template=active_prompt_template,
            constrained_actions=active_constrained_actions,
            thinking=active_thinking,
            memory_conditions=active_memory_conditions,
            pressure_profiles=active_pressure_profiles,
            memory_pressure_start=active_memory_pressure_start,
            memory_window=active_memory_window,
            task_state_probes=active_task_state_probes,
            probe_interval=active_probe_interval,
            probe_max_tokens=active_probe_max_tokens,
            memory_repair=active_memory_repair,
            protocol_id=protocol["protocol_id"],
            pull_missing=pull_missing,
            installed_names=installed_names,
            installed_inventory=installed_inventory,
            runner=active_runner,
        )
        model_results.append(model_result)
        if model_result["installed"]:
            installed_names.add(model["model_name"])

    successful_models = [
        result["model_name"]
        for result in model_results
        if result["status"] == "succeeded"
    ]
    partial_models = [
        result["model_name"]
        for result in model_results
        if result["status"] == "partial"
    ]
    limitations = [
        "Only fully completed real-runtime model rows count toward the minimum.",
        "Runtime failures and missing paired artifacts remain visible in the manifest.",
        "Action-budget exhaustion, invalid actions, evaluator failure, and lack of a finish proposal remain analysis outcomes and are never silently excluded.",
        "Confidence intervals quantify sampling uncertainty across declared model-task-seed pairs; they do not establish population-level generality.",
    ]
    if active_runtime == "deterministic":
        limitations.append(
            "Deterministic rows validate instrumentation and analysis only; they are not evidence about open-source LLM behavior."
        )
    if active_framework == "langgraph_tools":
        limitations.append(
            "The current autonomous tool environment is coding-task focused and exposes bounded file and test tools."
        )

    manifest_path = output_dir / "model_matrix_manifest.json"
    summary_path = output_dir / "model_matrix_summary.md"
    artifact_index_path = output_dir / "artifact_index.json"
    manifest = {
        "schema_version": "agent-memory-model-matrix-run/v0.2",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "protocol_id": protocol["protocol_id"],
        "protocol_path": str(protocol_path.resolve()),
        "protocol_sha256": sha256_file(protocol_path),
        "matrix_path": str(matrix_path.resolve()),
        "benchmark_path": str(active_runner.benchmark_path.resolve()),
        "output_dir": str(output_dir.resolve()),
        "runtime": active_runtime,
        "framework": active_framework,
        "runtime_endpoint": runtime_endpoint,
        "environment": environment_fingerprint(),
        "hardware_profile": matrix.get("hardware_profile", {}),
        "task_ids": active_task_ids,
        "model_names": [model["model_name"] for model in enabled_models],
        "variants": active_variants,
        "interventions": list(interventions) if intervention_mode else None,
        "seeds": active_seeds,
        "temperature": active_temperature,
        "max_tokens": active_max_tokens,
        "action_budget": active_action_budget,
        "trace_mode": active_trace_mode,
        "prompt_template": active_prompt_template,
        "constrained_actions": active_constrained_actions,
        "thinking": active_thinking,
        "memory_conditions": active_memory_conditions,
        "pressure_profiles": active_pressure_profiles,
        "pressure_profiles_path": (
            str(pressure_profiles_path.resolve())
            if pressure_profile_ids is not None
            else None
        ),
        "memory_pressure_start": active_memory_pressure_start,
        "memory_window": active_memory_window,
        "task_state_probes": active_task_state_probes,
        "probe_interval": active_probe_interval,
        "probe_max_tokens": active_probe_max_tokens,
        "memory_repair": active_memory_repair,
        "pull_missing": pull_missing,
        "minimum_successful_models": minimum_successful,
        "successful_model_count": len(successful_models),
        "successful_models": successful_models,
        "partial_model_count": len(partial_models),
        "partial_models": partial_models,
        "meets_minimum_successful_models": (
            len(successful_models) >= minimum_successful
        ),
        "planned_run_count": (
            len(enabled_models)
            * len(active_task_ids)
            * len(active_pressure_profiles)
            * len(active_seeds)
            * len(active_variants)
        ),
        "completed_run_count": sum(
            model["completed_run_count"] for model in model_results
        ),
        "failed_run_count": sum(
            model["failed_run_count"] for model in model_results
        ),
        "skipped_run_count": sum(
            model["skipped_run_count"] for model in model_results
        ),
        "completed_pair_count": sum(
            model["completed_pair_count"] for model in model_results
        ),
        "models": model_results,
        "limitations": limitations,
        "manifest_path": str(manifest_path.resolve()),
        "summary_markdown": str(summary_path.resolve()),
        "artifact_index_path": str(artifact_index_path.resolve()),
    }
    summary_path.write_text(_model_matrix_summary(manifest), encoding="utf-8")
    artifact_index = build_artifact_index(output_dir)
    _write_json(artifact_index_path, artifact_index)
    manifest["artifact_index_sha256"] = sha256_file(artifact_index_path)
    manifest["artifact_count"] = artifact_index["artifact_count"]
    _write_json(manifest_path, manifest)
    return manifest


def _run_one_model(
    model: dict,
    *,
    output_dir: Path,
    runtime: str,
    runtime_endpoint: str | None,
    framework: str,
    task_ids: list[str],
    variants: list[str],
    intervention_mode: bool,
    seeds: list[int],
    temperature: float,
    max_tokens: int,
    action_budget: int,
    trace_mode: str,
    prompt_template: str,
    constrained_actions: bool,
    thinking: bool,
    memory_conditions: list[str],
    pressure_profiles: list[dict],
    memory_pressure_start: int,
    memory_window: int,
    task_state_probes: bool,
    probe_interval: int,
    probe_max_tokens: int,
    memory_repair: bool,
    protocol_id: str,
    pull_missing: bool,
    installed_names: set[str],
    installed_inventory: dict[str, dict],
    runner: BenchmarkRunner,
) -> dict:
    model_name = model["model_name"]
    model_slug = _model_slug(model_name)
    installed = runtime == "deterministic" or _model_is_installed(
        model_name,
        installed_names,
    )
    planned_run_count = (
        len(task_ids)
        * len(pressure_profiles)
        * len(seeds)
        * len(variants)
    )
    result: dict[str, Any] = {
        "model_family": model["model_family"],
        "model_name": model_name,
        "display_name": model.get("display_name", model_name),
        "runtime": runtime,
        "runtime_model_metadata": _model_inventory_record(
            model_name,
            installed_inventory,
        ),
        "approx_size_gb": model.get("approx_size_gb"),
        "license_note": model.get("license_note"),
        "role": model.get("role"),
        "installed": installed,
        "status": "pending",
        "planned_run_count": planned_run_count,
        "completed_run_count": 0,
        "failed_run_count": 0,
        "skipped_run_count": 0,
        "completed_pair_count": 0,
        "runs": [],
        "comparisons": [],
        "errors": [],
    }

    if not installed and pull_missing and runtime == "ollama":
        pull_result = _pull_ollama_model(model_name)
        result["pull"] = pull_result
        installed = pull_result["returncode"] == 0
        result["installed"] = installed

    if not installed:
        result["status"] = "skipped"
        result["skipped_run_count"] = planned_run_count
        result["skip_reason"] = f"model not installed locally: {model_name}"
        return result

    run_paths: dict[tuple[str, str, int, str], Path] = {}
    for task_id in task_ids:
        for pressure_profile in pressure_profiles:
            profile_id = pressure_profile["profile_id"]
            memory_condition = pressure_profile["condition"]
            profile_pressure_start = int(
                pressure_profile["activation_action_count"]
            )
            profile_memory_window = int(
                pressure_profile["visible_evidence_window"]
            )
            for seed in seeds:
                trial_id = (
                    f"{model_slug}:{task_id}:{profile_id}:seed-{seed}"
                )
                # Seed-derived counterbalanced rotation, not a fixed order —
                # avoids correlating any one condition with thermal
                # throttling, cache state, or prior-model memory pressure
                # on shared local hardware. See experiment_protocol.py.
                for variant in counterbalanced_variant_order(variants, seed):
                    if intervention_mode:
                        spec = resolve_intervention(variant)
                        row_agent_variant = spec.agent_variant
                        row_verifier_enabled = spec.verifier_enabled
                        row_intervention = variant
                    else:
                        row_agent_variant = variant
                        row_verifier_enabled = variant == "verified"
                        row_intervention = "legacy"
                    run_config = BenchmarkRunConfig(
                        framework=framework,
                        model_family=model["model_family"],
                        model_name=model_name,
                        agent_variant=row_agent_variant,
                        verifier_enabled=row_verifier_enabled,
                        intervention=row_intervention,
                        seed=seed,
                        runtime=runtime,
                        runtime_endpoint=runtime_endpoint,
                        prompt_template=prompt_template,
                        temperature=temperature,
                        max_tokens=max_tokens,
                        action_budget=action_budget,
                        allow_runtime_fallback=False,
                        trace_mode=trace_mode,
                        workspace_root=str(output_dir / "workspaces"),
                        constrained_actions=constrained_actions,
                        thinking=thinking,
                        memory_condition=memory_condition,
                        pressure_profile_id=profile_id,
                        pressure_severity=str(
                            pressure_profile.get(
                                "severity",
                                "unspecified",
                            )
                        ),
                        pressure_severity_ordinal=int(
                            pressure_profile.get(
                                "severity_ordinal",
                                0,
                            )
                            or 0
                        ),
                        memory_pressure_start=profile_pressure_start,
                        memory_window=profile_memory_window,
                        task_state_probes=task_state_probes,
                        probe_interval=probe_interval,
                        probe_max_tokens=probe_max_tokens,
                        memory_repair=memory_repair,
                    )
                    seed_dir = f"seed-{seed}"
                    run_path = (
                        output_dir
                        / "runs"
                        / model_slug
                        / profile_id
                        / seed_dir
                        / variant
                        / f"{task_id}.json"
                    )
                    try:
                        run = runner.run_task_id(task_id, run_config)
                    except RuntimeError as exc:
                        result["failed_run_count"] += 1
                        result["errors"].append(
                            {
                                "task_id": task_id,
                                "memory_condition": memory_condition,
                                "pressure_profile_id": profile_id,
                                "pressure_severity": (
                                    pressure_profile.get("severity")
                                ),
                                "seed": seed,
                                "variant": variant,
                                "trial_id": trial_id,
                                "error_type": "runtime_error",
                                "error": str(exc),
                            }
                        )
                        continue

                    run["experiment_context"] = {
                        "protocol_id": protocol_id,
                        "trial_id": trial_id,
                        "memory_condition": memory_condition,
                        "pressure_profile_id": profile_id,
                        "pressure_severity": pressure_profile.get(
                            "severity"
                        ),
                        "pressure_severity_ordinal": (
                            pressure_profile.get("severity_ordinal")
                        ),
                        "memory_pressure_start": profile_pressure_start,
                        "memory_window": profile_memory_window,
                        "seed": seed,
                        "variant": variant,
                    }
                    _write_json(run_path, run)
                    run_paths[
                        (task_id, profile_id, seed, variant)
                    ] = run_path
                    run_info = indexed_artifact(
                        run_path,
                        output_dir=output_dir,
                        extra={
                            "task_id": task_id,
                            "memory_condition": memory_condition,
                            "pressure_profile_id": profile_id,
                            "pressure_severity": pressure_profile.get(
                                "severity"
                            ),
                            "pressure_severity_ordinal": (
                                pressure_profile.get(
                                    "severity_ordinal"
                                )
                            ),
                            "seed": seed,
                            "variant": variant,
                            "trial_id": trial_id,
                            "runtime_error": run["run_metadata"].get(
                                "runtime_error"
                            ),
                            "termination_reason": run["run_metadata"].get(
                                "termination_reason"
                            ),
                            "evaluator_success": run["run_metadata"].get(
                                "evaluator_success"
                            ),
                        },
                    )
                    result["runs"].append(run_info)
                    result["completed_run_count"] += 1

                    row_file_name = (
                        f"{task_id}__{variant}.json"
                        if intervention_mode
                        else f"{task_id}.json"
                    )
                    if row_agent_variant == "baseline":
                        score_path = (
                            output_dir
                            / "scores"
                            / model_slug
                            / profile_id
                            / seed_dir
                            / row_file_name
                        )
                        _write_json(
                            score_path,
                            build_memory_health_report(run),
                        )
                        run_info["score_json"] = str(score_path.resolve())
                        run_info["score_sha256"] = sha256_file(score_path)
                    if row_agent_variant == "verified":
                        verification_path = (
                            output_dir
                            / "verifications"
                            / model_slug
                            / profile_id
                            / seed_dir
                            / row_file_name
                        )
                        _write_json(
                            verification_path,
                            run.get("verification_report", {}),
                        )
                        run_info["verification_json"] = str(
                            verification_path.resolve()
                        )
                        run_info["verification_sha256"] = sha256_file(
                            verification_path
                        )

                if intervention_mode:
                    comparison_pairs = [
                        ("memory_baseline", label)
                        for label in variants
                        if label != "memory_baseline"
                    ]
                else:
                    comparison_pairs = [("baseline", "verified")]
                for baseline_label, compared_label in comparison_pairs:
                    baseline_path = run_paths.get(
                        (task_id, profile_id, seed, baseline_label)
                    )
                    verified_path = run_paths.get(
                        (task_id, profile_id, seed, compared_label)
                    )
                    if not (baseline_path and verified_path):
                        continue
                    comparison_file_name = (
                        f"{task_id}__{compared_label}.json"
                        if intervention_mode
                        else f"{task_id}.json"
                    )
                    comparison_path = (
                        output_dir
                        / "comparisons"
                        / model_slug
                        / profile_id
                        / f"seed-{seed}"
                        / comparison_file_name
                    )
                    baseline = _read_json(baseline_path)
                    verified = _read_json(verified_path)
                    comparison = compare_runs(baseline, verified)
                    comparison["experiment_context"] = {
                        "protocol_id": protocol_id,
                        "trial_id": trial_id,
                        "memory_condition": memory_condition,
                        "pressure_profile_id": profile_id,
                        "pressure_severity": pressure_profile.get(
                            "severity"
                        ),
                        "pressure_severity_ordinal": (
                            pressure_profile.get("severity_ordinal")
                        ),
                        "seed": seed,
                        "baseline_condition": baseline_label,
                        "compared_condition": compared_label,
                    }
                    _write_json(comparison_path, comparison)
                    result["comparisons"].append(
                        indexed_artifact(
                            comparison_path,
                            output_dir=output_dir,
                            extra={
                                "task_id": task_id,
                                "memory_condition": memory_condition,
                                "pressure_profile_id": profile_id,
                                "pressure_severity": (
                                    pressure_profile.get("severity")
                                ),
                                "pressure_severity_ordinal": (
                                    pressure_profile.get(
                                        "severity_ordinal"
                                    )
                                ),
                                "seed": seed,
                                "trial_id": trial_id,
                                "blocked_actions": comparison[
                                    "verification_overhead"
                                ]["blocked_actions"],
                                "metric_deltas": comparison[
                                    "metric_deltas"
                                ],
                                "behavioral_outcomes": comparison[
                                    "behavioral_outcomes"
                                ],
                            },
                        )
                    )
                    result["completed_pair_count"] += 1

    if result["completed_run_count"] == planned_run_count and not result["errors"]:
        result["status"] = "succeeded"
    elif result["completed_run_count"] == 0:
        result["status"] = "failed"
    else:
        result["status"] = "partial"
    return result


def _installed_model_inventory(
    runtime: str,
    endpoint: str | None = None,
) -> dict[str, dict]:
    if runtime != "ollama":
        return {}
    url = f"{(endpoint or 'http://127.0.0.1:11434').rstrip('/')}/api/tags"
    try:
        with urllib.request.urlopen(url, timeout=5) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except (
        urllib.error.URLError,
        TimeoutError,
        json.JSONDecodeError,
    ):
        return {}

    inventory = {}
    for model in payload.get("models", []):
        record = {
            key: model.get(key)
            for key in ["name", "model", "digest", "size", "modified_at", "details"]
            if model.get(key) is not None
        }
        for key in [model.get("name"), model.get("model")]:
            if key:
                inventory[key] = record
    return inventory


def _installed_model_names(runtime: str, endpoint: str | None = None) -> set[str]:
    """Backward-compatible installed-name helper used by tests and callers."""

    return set(_installed_model_inventory(runtime, endpoint))


def _model_inventory_record(
    model_name: str,
    inventory: dict[str, dict],
) -> dict | None:
    if model_name in inventory:
        return inventory[model_name]
    if ":" not in model_name and f"{model_name}:latest" in inventory:
        return inventory[f"{model_name}:latest"]
    if model_name.endswith(":latest"):
        return inventory.get(model_name.removesuffix(":latest"))
    return None


def _model_is_installed(model_name: str, installed: set[str]) -> bool:
    if model_name in installed:
        return True
    if ":" not in model_name and f"{model_name}:latest" in installed:
        return True
    if model_name.endswith(":latest") and model_name.removesuffix(":latest") in installed:
        return True
    return False


def _pull_ollama_model(model_name: str) -> dict:
    try:
        completed = subprocess.run(
            ["ollama", "pull", model_name],
            capture_output=True,
            check=False,
            text=True,
        )
        return {
            "command": f"ollama pull {model_name}",
            "returncode": completed.returncode,
            "stdout": completed.stdout[-2000:],
            "stderr": completed.stderr[-2000:],
        }
    except FileNotFoundError as exc:
        return {
            "command": f"ollama pull {model_name}",
            "returncode": 127,
            "stdout": "",
            "stderr": str(exc),
        }


def _model_matrix_summary(manifest: dict) -> str:
    lines = [
        "# Agent Memory Model Matrix Summary",
        "",
        f"- Protocol ID: `{manifest['protocol_id']}`",
        f"- Runtime: `{manifest['runtime']}`",
        f"- Framework: `{manifest.get('framework', 'react_custom')}`",
        f"- Seeds: `{manifest['seeds']}`",
        f"- Constrained actions: `{manifest['constrained_actions']}`",
        f"- Thinking mode: `{manifest['thinking']}`",
        f"- Memory conditions: `{manifest['memory_conditions']}`",
        "- Pressure profiles: "
        f"`{[profile['profile_id'] for profile in manifest['pressure_profiles']]}`",
        f"- Task-state probes: `{manifest['task_state_probes']}`",
        f"- Planned runs: `{manifest['planned_run_count']}`",
        f"- Completed runs: `{manifest['completed_run_count']}`",
        f"- Failed runs: `{manifest['failed_run_count']}`",
        f"- Skipped runs: `{manifest['skipped_run_count']}`",
        f"- Completed pairs: `{manifest['completed_pair_count']}`",
        f"- Minimum successful models: `{manifest['minimum_successful_models']}`",
        f"- Fully successful models: `{manifest['successful_model_count']}`",
        f"- Meets minimum: `{manifest['meets_minimum_successful_models']}`",
        "",
        "| Model | Family | Status | Planned | Completed | Failed | Skipped | Pairs |",
        "|---|---|---:|---:|---:|---:|---:|---:|",
    ]
    for model in manifest["models"]:
        lines.append(
            "| `{model}` | `{family}` | `{status}` | {planned} | {completed} | {failed} | {skipped} | {pairs} |".format(
                model=model["model_name"],
                family=model["model_family"],
                status=model["status"],
                planned=model["planned_run_count"],
                completed=model["completed_run_count"],
                failed=model["failed_run_count"],
                skipped=model["skipped_run_count"],
                pairs=model["completed_pair_count"],
            )
        )
    lines.extend(["", "## Limitations", ""])
    lines.extend(f"- {item}" for item in manifest["limitations"])
    lines.append("")
    return "\n".join(lines)


def _model_slug(model_name: str) -> str:
    return (
        model_name.replace("/", "_")
        .replace(":", "_")
        .replace(".", "_")
        .replace("-", "_")
    )


def _read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
