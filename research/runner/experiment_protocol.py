"""Frozen experiment protocols and artifact integrity helpers."""

from __future__ import annotations

import hashlib
import json
import platform
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable


def build_experiment_protocol(
    *,
    matrix_path: Path,
    benchmark_path: Path,
    selected_models: list[dict],
    selected_tasks: list[dict],
    runtime: str,
    framework: str,
    variants: list[str],
    seeds: list[int],
    temperature: float,
    max_tokens: int,
    action_budget: int,
    trace_mode: str,
    prompt_template: str,
    constrained_actions: bool,
    thinking: bool,
    memory_conditions: list[str] | None = None,
    pressure_profiles: list[dict] | None = None,
    pressure_profiles_path: Path | None = None,
    memory_pressure_start: int = 6,
    memory_window: int = 8,
    task_state_probes: bool = False,
    probe_interval: int = 5,
    probe_max_tokens: int = 1536,
    memory_repair: bool = True,
    scenario_tree_path: Path | None = Path(
        "research/benchmarks/coding_scenarios"
    ),
    verifier_policy_paths: Iterable[Path] = (
        Path("research/runner/verification.py"),
        Path("research/runner/operational_memory.py"),
        Path("research/runner/benchmark_runner.py"),
    ),
    controller_policy_version: str | None = None,
    model_names_for_digest: Iterable[str] | None = None,
) -> dict:
    """Build a predeclared protocol whose identifier excludes wall-clock time."""

    from .interventions import _SPECS as intervention_specs
    from dataclasses import asdict as _asdict

    active_memory_conditions = memory_conditions or ["full_history"]
    active_pressure_profiles = pressure_profiles or [
        {
            "profile_id": condition,
            "condition": condition,
            "severity": (
                "control" if condition == "full_history" else "ad_hoc"
            ),
            "severity_ordinal": (
                0 if condition == "full_history" else None
            ),
            "activation_action_count": memory_pressure_start,
            "visible_evidence_window": memory_window,
            "induced_corruption": condition != "full_history",
            "frozen_registry_profile": False,
        }
        for condition in active_memory_conditions
    ]
    protocol_body = {
        "schema_version": "agent-memory-experiment-protocol/v0.1",
        "research_question": (
            "How do controlled memory-pressure conditions affect task-state "
            "accuracy and false-completion behavior in open-source coding agents, "
            "and does in-loop evidence verification reduce unsafe completion?"
        ),
        "design": {
            "unit_of_analysis": "model-task-memory-condition-seed pair",
            "pairing": (
                "Baseline and verified variants share model, task, memory "
                "condition, and seed."
            ),
            "runtime": runtime,
            "framework": framework,
            "variants": variants,
            "seeds": seeds,
            "memory_conditions": active_memory_conditions,
            "pressure_profiles": active_pressure_profiles,
            "execution_order": (
                "For each model, task, memory condition, and seed, execute "
                "variants in a seed-derived counterbalanced rotation (see "
                "counterbalanced_variant_order) rather than a fixed order, "
                "so no single condition is consistently first on shared "
                "local hardware (thermal throttling, cache state, prior-"
                "model memory pressure)."
            ),
            "counterbalanced_order_by_seed": {
                str(seed): counterbalanced_variant_order(variants, seed)
                for seed in seeds
            },
        },
        "generation": {
            "temperature": temperature,
            "max_tokens": max_tokens,
            "action_budget": action_budget,
            "trace_mode": trace_mode,
            "prompt_template": prompt_template,
            "constrained_actions": constrained_actions,
            "thinking": thinking,
            "runtime_fallback_allowed": False,
        },
        "memory_pressure": {
            "conditions": active_memory_conditions,
            "profiles": active_pressure_profiles,
            "profile_registry": (
                {
                    "path": _portable_path(pressure_profiles_path),
                    "sha256": sha256_file(pressure_profiles_path),
                }
                if pressure_profiles_path
                else None
            ),
            "activation_action_count": memory_pressure_start,
            "visible_evidence_window": memory_window,
            "canonical_evaluator_state_is_never_transformed": True,
            "treatment_scope": (
                "Only model-visible evidence and observations are transformed."
            ),
        },
        "task_state_probes": {
            "enabled": task_state_probes,
            "interval_actions": probe_interval,
            "max_tokens": probe_max_tokens,
            "method": (
                "A non-intervening model fork reconstructs structured task state "
                "from the same visible memory and is scored against canonical "
                "executable state."
            ),
            "deterministic_probe_policy": (
                "Deterministic oracle probes validate instrumentation and are "
                "excluded from empirical probe outcomes."
            ),
        },
        "memory_repair": {
            "enabled": memory_repair,
            "policy": (
                "After a high-risk finish belief is blocked, derive and execute "
                "the smallest bounded evidence-refresh action, update operational "
                "memory, and require the model to replan."
            ),
            "outcomes": [
                "corruption_detection",
                "false-claim_containment",
                "repair_attempt",
                "repair_success",
                "independently_verified_recovery",
            ],
        },
        "datasets": {
            "benchmark": {
                "path": _portable_path(benchmark_path),
                "sha256": sha256_file(benchmark_path),
                "tasks": selected_tasks,
            },
            "model_matrix": {
                "path": _portable_path(matrix_path),
                "sha256": sha256_file(matrix_path),
                "models": selected_models,
            },
        },
        "predeclared_outcomes": {
            "primary": {
                "name": "accepted_unsupported_finish_trial",
                "definition": (
                    "At least one model-authored finish proposal was accepted "
                    "even though its task-complete claim was stale, "
                    "unsupported, contradicted, or lacked provenance — "
                    "epistemic support only. This is independent of whether "
                    "the hidden evaluator later judged the implementation "
                    "correct: a well-supported claim that turns out incorrect "
                    "is not counted here (see accepted_incorrect_finish_trial "
                    "and supported_but_incorrect_finish_trial)."
                ),
                "comparison": "paired baseline versus verified exact McNemar test",
            },
            "secondary": [
                "accepted_incorrect_finish_trial",
                "supported_but_incorrect_finish_trial",
                "unsupported_but_correct_finish_trial",
                "accepted_false_finish_trial",
                "raw_false_finish_proposal_trial",
                "accepted_finish_evaluator_failure_trial",
                "independent_evaluator_success",
                "accepted_finish",
                "action_budget_exhaustion",
                "recovery_after_block",
                "action_compliance_rate",
                "extra_model_actions",
                "task_state_probe_accuracy",
                "subtask_state_probe_accuracy",
                "latest_test_probe_accuracy",
                "evidence_attribution_probe_accuracy",
                "temporal_ordering_probe_accuracy",
                "objective_fidelity_probe_accuracy",
                "unsuccessful_attempt_probe_accuracy",
                "failed_attempt_probe_accuracy",
                "blocked_attempt_probe_accuracy",
                "repository_state_probe_accuracy",
                "current_evidence_probe_accuracy",
                "stale_evidence_probe_accuracy",
                "uncertain_evidence_probe_accuracy",
                "uncertainty_calibration_probe_accuracy",
                "next_action_probe_accuracy",
                "memory_accuracy_curve_auc",
                "memory_repair_recovery",
            ],
        },
        "analysis_plan": {
            "binary_interval": "Wilson 95% confidence interval",
            "paired_binary_test": "two-sided exact McNemar test",
            "continuous_effect_interval": (
                "deterministic paired bootstrap percentile 95% confidence interval"
            ),
            "bootstrap_resamples": 5000,
            "multiplicity_note": (
                "The primary endpoint is predeclared. Secondary p-values are "
                "descriptive and are not used as independent confirmatory claims."
            ),
        },
        "exclusion_policy": {
            "exclude_from_complete_case_paired_inference": [
                "a baseline or verified artifact is missing",
                "a local runtime request fails before a run artifact is produced",
                "a run artifact records a runtime error",
            ],
            "retain_as_observed_outcomes": [
                "action-budget exhaustion",
                "invalid model action output",
                "independent evaluator failure",
                "failure to issue an accepted finish",
            ],
            "reporting": (
                "Every planned run remains in intention-to-run execution "
                "accounting. Every pair omitted from complete-case inference "
                "appears in the exclusion ledger with model, task, pressure "
                "profile, seed, and reason."
            ),
        },
        "integrity": {
            "scenario_tree_sha256": (
                hash_directory_tree(scenario_tree_path)
                if scenario_tree_path
                else None
            ),
            "scenario_tree_path": (
                _portable_path(scenario_tree_path)
                if scenario_tree_path
                else None
            ),
            "verifier_policy_hashes": source_file_hashes(
                verifier_policy_paths
            ),
            "intervention_spec_hash": sha256_json(
                {
                    name: _asdict(spec)
                    for name, spec in sorted(intervention_specs.items())
                }
            ),
            "dependency_lock_hashes": dependency_lock_hash(),
            "clean_working_tree": clean_working_tree_status(),
            "controller_policy_version": controller_policy_version,
            "model_digests": (
                {
                    name: ollama_model_digest(name)
                    for name in model_names_for_digest
                }
                if model_names_for_digest
                else {}
            ),
            "hidden_validation_scope": (
                "Hidden/ground-truth validation runs exactly once, after "
                "episode termination, identically for every intervention "
                "condition. The online finish gate and unsafe-mutation gate "
                "never consult it — see CONTROLLER_POLICY_VERSION and "
                "_evaluate_finish_proposal in benchmark_runner.py."
            ),
        },
        "source_revision": git_revision(),
    }
    protocol_id = sha256_json(protocol_body)
    return {
        **protocol_body,
        "protocol_id": protocol_id,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }


def write_frozen_protocol(path: Path, protocol: dict) -> None:
    """Write a protocol once and reject incompatible reuse of an output directory."""

    if path.exists():
        existing = json.loads(path.read_text(encoding="utf-8"))
        existing_id = existing.get("protocol_id")
        if (
            existing_id != protocol.get("protocol_id")
            or existing_id != protocol_content_id(existing)
        ):
            raise RuntimeError(
                "Output directory already contains a different frozen experiment "
                f"protocol: {path}"
            )
        return
    write_json(path, protocol)


def build_artifact_index(
    output_dir: Path,
    *,
    excluded_names: set[str] | None = None,
) -> dict:
    """Hash stable experiment artifacts so later edits are detectable."""

    excluded = excluded_names or {
        "artifact_index.json",
        "model_matrix_manifest.json",
    }
    entries = []
    for path in sorted(output_dir.rglob("*")):
        if not path.is_file() or path.name in excluded:
            continue
        if "__pycache__" in path.parts or path.suffix == ".pyc":
            continue
        relative_path = path.relative_to(output_dir).as_posix()
        entries.append(
            {
                "path": relative_path,
                "sha256": sha256_file(path),
                "size_bytes": path.stat().st_size,
            }
        )
    return {
        "schema_version": "agent-memory-artifact-index/v0.1",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "artifact_count": len(entries),
        "artifacts": entries,
    }


def audit_model_matrix_manifest(manifest_path: Path) -> dict:
    """Verify protocol, index, and indexed artifact hashes from a saved manifest."""

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    protocol_path = Path(manifest["protocol_path"])
    index_path = Path(manifest["artifact_index_path"])
    protocol = (
        json.loads(protocol_path.read_text(encoding="utf-8"))
        if protocol_path.exists()
        else {}
    )
    checks = {
        "manifest_exists": manifest_path.exists(),
        "protocol_exists": protocol_path.exists(),
        "artifact_index_exists": index_path.exists(),
        "protocol_hash_matches": (
            protocol_path.exists()
            and sha256_file(protocol_path) == manifest.get("protocol_sha256")
        ),
        "protocol_id_matches_manifest": (
            protocol.get("protocol_id") == manifest.get("protocol_id")
        ),
        "protocol_id_matches_content": (
            protocol.get("protocol_id") == protocol_content_id(protocol)
        ),
        "artifact_index_hash_matches": (
            index_path.exists()
            and sha256_file(index_path)
            == manifest.get("artifact_index_sha256")
        ),
    }
    missing_artifacts = []
    hash_mismatches = []
    if index_path.exists():
        index = json.loads(index_path.read_text(encoding="utf-8"))
        output_dir = Path(manifest["output_dir"])
        for artifact in index.get("artifacts", []):
            artifact_path = output_dir / artifact["path"]
            if not artifact_path.exists():
                missing_artifacts.append(artifact["path"])
                continue
            actual_hash = sha256_file(artifact_path)
            if actual_hash != artifact["sha256"]:
                hash_mismatches.append(
                    {
                        "path": artifact["path"],
                        "expected_sha256": artifact["sha256"],
                        "actual_sha256": actual_hash,
                    }
                )
    valid = (
        all(checks.values())
        and not missing_artifacts
        and not hash_mismatches
    )
    return {
        "schema_version": "agent-memory-artifact-audit/v0.1",
        "manifest_path": str(manifest_path.resolve()),
        "valid": valid,
        "checks": checks,
        "missing_artifacts": missing_artifacts,
        "hash_mismatches": hash_mismatches,
    }


def environment_fingerprint() -> dict:
    """Capture the execution environment without claiming bitwise reproducibility."""

    return {
        "python_version": sys.version.split()[0],
        "platform": platform.platform(),
        "machine": platform.machine(),
        "processor": platform.processor(),
        "source_revision": git_revision(),
    }


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def sha256_json(payload: Any) -> str:
    encoded = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def protocol_content_id(protocol: dict) -> str:
    body = {
        key: value
        for key, value in protocol.items()
        if key not in {"protocol_id", "created_at"}
    }
    return sha256_json(body)


def git_revision() -> str | None:
    try:
        completed = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            capture_output=True,
            check=False,
            text=True,
            timeout=5,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return None
    revision = completed.stdout.strip()
    return revision if completed.returncode == 0 and revision else None


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def indexed_artifact(
    path: Path,
    *,
    output_dir: Path,
    extra: dict | None = None,
) -> dict:
    payload = {
        "path": str(path.resolve()),
        "relative_path": path.relative_to(output_dir).as_posix(),
        "sha256": sha256_file(path),
        "size_bytes": path.stat().st_size,
    }
    if extra:
        payload.update(extra)
    return payload


def unique_ints(values: Iterable[int]) -> list[int]:
    """Preserve declared seed order while rejecting an empty seed set."""

    result = list(dict.fromkeys(int(value) for value in values))
    if not result:
        raise ValueError("At least one experiment seed is required")
    return result


def _portable_path(path: Path) -> str:
    try:
        return path.resolve().relative_to(Path.cwd().resolve()).as_posix()
    except ValueError:
        return path.name


def hash_directory_tree(root: Path) -> str | None:
    """Hash every file under root by relative path and content.

    Used to freeze the full fixture tree (scenarios, workspaces, solutions,
    hidden validators) as a single value — catching any post-freeze edit
    to a fixture, not just to seed_tasks.json.
    """
    if not root.exists():
        return None
    entries = []
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        if "__pycache__" in path.parts or path.suffix == ".pyc":
            continue
        entries.append(
            f"{path.relative_to(root).as_posix()}:{sha256_file(path)}"
        )
    return hashlib.sha256(
        "\n".join(entries).encode("utf-8")
    ).hexdigest()


def source_file_hashes(paths: Iterable[Path]) -> dict[str, str | None]:
    """Hash specific source files (verifier policy, interventions, etc.)."""

    return {
        _portable_path(path): (sha256_file(path) if path.exists() else None)
        for path in paths
    }


def clean_working_tree_status() -> dict:
    """Best-effort check for uncommitted changes at protocol-freeze time.

    Does not raise: a research environment may legitimately lack git or a
    working tree. ``checked`` is False when the check itself couldn't run;
    callers should treat that as "unknown", not "clean".
    """

    try:
        completed = subprocess.run(
            ["git", "status", "--porcelain"],
            capture_output=True,
            check=False,
            text=True,
            timeout=5,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return {"checked": False, "clean": None, "dirty_paths": []}
    if completed.returncode != 0:
        return {"checked": False, "clean": None, "dirty_paths": []}
    dirty_paths = [
        line[3:] for line in completed.stdout.splitlines() if line.strip()
    ]
    return {
        "checked": True,
        "clean": not dirty_paths,
        "dirty_paths": dirty_paths,
    }


def ollama_model_digest(model_name: str) -> str | None:
    """Best-effort exact model digest (not the mutable tag) via `ollama list`.

    Returns None (never raises) when Ollama isn't installed, isn't running,
    or the model isn't pulled locally — callers should treat a None digest
    as "unverified", not as an error.
    """

    try:
        completed = subprocess.run(
            ["ollama", "list"],
            capture_output=True,
            check=False,
            text=True,
            timeout=10,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return None
    if completed.returncode != 0:
        return None
    for line in completed.stdout.splitlines()[1:]:
        columns = line.split()
        if columns and columns[0] == model_name:
            return columns[1] if len(columns) > 1 else None
    return None


def counterbalanced_variant_order(
    variants: list[str],
    seed: int,
) -> list[str]:
    """Deterministic per-seed cyclic rotation of the variant execution order.

    Executing conditions in a fixed order on shared local hardware can
    correlate a condition with thermal throttling, cache state, or memory
    pressure from the prior model. A seed-derived rotation counterbalances
    that without sacrificing reproducibility: the same (variants, seed)
    pair always produces the same order.
    """

    if not variants:
        return []
    shift = seed % len(variants)
    return [*variants[shift:], *variants[:shift]]


def dependency_lock_hash(
    candidates: Iterable[Path] = (
        Path("backend/requirements.txt"),
        Path("research/requirements-analysis.txt"),
    ),
) -> dict[str, str | None]:
    """Hash whichever dependency-lock files exist, for environment freezing."""

    return {
        _portable_path(path): (sha256_file(path) if path.exists() else None)
        for path in candidates
        if path.exists()
    }
