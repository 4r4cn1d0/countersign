"""Fixture-backed coding benchmark scenario loading."""

from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_SCENARIO_ROOT = ROOT / "research" / "benchmarks" / "coding_scenarios"


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

    return {
        **manifest,
        "initial_files": initial_files,
        "steps": steps,
        "hidden_validation_path": str(hidden_validation.resolve()),
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
