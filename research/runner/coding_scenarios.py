"""Fixture-backed coding benchmark scenario loading."""

from __future__ import annotations

import json
from hashlib import sha256
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_SCENARIO_ROOT = ROOT / "research" / "benchmarks" / "coding_scenarios"
SCENARIO_SCHEMA_VERSION = "agent-memory-coding-scenario/v1"
MIN_MODEL_ACTIONS = 20
MAX_MODEL_ACTIONS = 50


def workspace_sha256(workspace_root: Path) -> str:
    """Hash a fixture repository using stable relative paths and file bytes."""

    digest = sha256()
    for path in sorted(workspace_root.rglob("*")):
        if not path.is_file():
            continue
        relative_path = path.relative_to(workspace_root).as_posix()
        digest.update(relative_path.encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def load_fixture_scenario(
    task_id: str,
    *,
    scenario_root: Path = DEFAULT_SCENARIO_ROOT,
) -> dict | None:
    """Load a coding scenario and resolve its workspace and solution files."""

    task_root = scenario_root / task_id
    manifest_path = task_root / "scenario.json"
    if not manifest_path.exists():
        return None

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("task_id") != task_id:
        raise ValueError(
            f"Coding scenario task_id mismatch in {manifest_path}: "
            f"{manifest.get('task_id')!r}"
        )
    if manifest.get("schema_version") != SCENARIO_SCHEMA_VERSION:
        raise ValueError(
            f"Unsupported coding scenario schema in {manifest_path}: "
            f"{manifest.get('schema_version')!r}"
        )

    workspace_root = task_root / "workspace"
    initial_files = {
        path.relative_to(workspace_root).as_posix(): path.read_text(
            encoding="utf-8"
        )
        for path in sorted(workspace_root.rglob("*"))
        if path.is_file()
    }
    if not initial_files:
        raise ValueError(f"Coding scenario has no workspace files: {task_id}")
    repository_hash = workspace_sha256(workspace_root)
    if manifest.get("workspace_sha256") != repository_hash:
        raise ValueError(
            f"Coding scenario workspace hash mismatch for {task_id}: "
            f"expected {manifest.get('workspace_sha256')!r}, got {repository_hash!r}"
        )

    steps = []
    for declared_step in manifest.get("steps", []):
        step = dict(declared_step)
        content_from = step.pop("content_from", None)
        if content_from:
            content_path = task_root / str(content_from)
            if not content_path.is_file():
                raise ValueError(
                    f"Missing coding scenario replacement file: {content_path}"
                )
            step["content"] = content_path.read_text(encoding="utf-8")
        steps.append(step)

    hidden_validation = task_root / "hidden_validation.py"
    if not hidden_validation.is_file():
        raise ValueError(
            f"Coding scenario is missing hidden_validation.py: {task_id}"
        )

    final_test_step_id = manifest.get("final_test_step_id")
    step_ids = [step.get("step_id") for step in steps]
    if len(step_ids) != len(set(step_ids)):
        raise ValueError(f"Coding scenario has duplicate step IDs: {task_id}")
    if final_test_step_id not in step_ids:
        raise ValueError(
            f"Coding scenario final test step is missing: {task_id}"
        )
    if "finish" not in step_ids:
        raise ValueError(f"Coding scenario finish step is missing: {task_id}")
    planned_model_actions = len(
        [
            step
            for step in steps
            if step.get("step_id") != final_test_step_id
        ]
    )
    if not MIN_MODEL_ACTIONS <= planned_model_actions <= MAX_MODEL_ACTIONS:
        raise ValueError(
            f"Coding scenario must plan {MIN_MODEL_ACTIONS}-{MAX_MODEL_ACTIONS} "
            f"model actions, got {planned_model_actions}: {task_id}"
        )

    return {
        **manifest,
        "initial_files": initial_files,
        "steps": steps,
        "hidden_validation_path": str(hidden_validation.resolve()),
        "repository_hash": repository_hash,
        "planned_model_actions": planned_model_actions,
    }


def fixture_scenario_ids(
    *,
    scenario_root: Path = DEFAULT_SCENARIO_ROOT,
) -> list[str]:
    """Return fixture task IDs with complete scenario manifests."""

    if not scenario_root.exists():
        return []
    return sorted(
        path.parent.name
        for path in scenario_root.glob("*/scenario.json")
        if path.is_file()
    )
