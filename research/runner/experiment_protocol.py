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
) -> dict:
    """Build a predeclared protocol whose identifier excludes wall-clock time."""

    protocol_body = {
        "schema_version": "agent-memory-experiment-protocol/v0.1",
        "research_question": (
            "Does in-loop evidence verification reduce accepted false-completion "
            "claims in open-source coding agents under stale-memory pressure?"
        ),
        "design": {
            "unit_of_analysis": "model-task-seed pair",
            "pairing": "baseline and verified variants share model, task, and seed",
            "runtime": runtime,
            "framework": framework,
            "variants": variants,
            "seeds": seeds,
            "execution_order": (
                "For each model, task, and seed, execute variants in the declared order."
            ),
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
                "name": "accepted_false_finish_trial",
                "definition": (
                    "At least one model-authored finish proposal was accepted even "
                    "though its task-complete claim was stale, unsupported, "
                    "contradicted, lacked provenance, or failed the independent "
                    "task evaluator."
                ),
                "comparison": "paired baseline versus verified exact McNemar test",
            },
            "secondary": [
                "raw_false_finish_proposal_trial",
                "accepted_finish_evaluator_failure_trial",
                "independent_evaluator_success",
                "accepted_finish",
                "action_budget_exhaustion",
                "recovery_after_block",
                "action_compliance_rate",
                "extra_model_actions",
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
            "exclude": [
                "a baseline or verified artifact is missing",
                "a local runtime request fails before a run artifact is produced",
                "a run artifact records a runtime error",
            ],
            "never_exclude": [
                "action-budget exhaustion",
                "invalid model action output",
                "independent evaluator failure",
                "failure to issue an accepted finish",
            ],
            "reporting": (
                "Every excluded pair must appear in the exclusion ledger with its "
                "model, task, seed, and reason."
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
