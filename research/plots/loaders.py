"""Data loading helpers for scientific figure generation."""

from __future__ import annotations

import json
from pathlib import Path

from ..runner.matrix_analysis import analyze_model_matrix_manifest


def load_manifest(manifest_path: Path) -> dict:
    """Load a model-matrix manifest JSON."""

    with manifest_path.open(encoding="utf-8") as handle:
        return json.load(handle)


def load_analysis_report(manifest_path: Path) -> dict:
    """Build the paired analysis report for a manifest."""

    return analyze_model_matrix_manifest(manifest_path)


def iter_run_payloads(manifest: dict):
    """Yield (run_info, payload) for every run artifact in a manifest."""

    for model in manifest.get("models", []):
        for run_info in model.get("runs", []):
            path = Path(run_info.get("path", ""))
            if not path.is_file():
                continue
            with path.open(encoding="utf-8") as handle:
                yield run_info, json.load(handle)


def select_walkthrough_pair(manifest: dict) -> tuple[dict, dict] | None:
    """Select one baseline/verified run pair for the walkthrough figure.

    Prefers a pair whose baseline accepted a false finish while the verified
    variant blocked one, falling back to the first complete pair.
    """

    pairs: dict[tuple, dict[str, dict]] = {}
    for run_info, payload in iter_run_payloads(manifest):
        key = (
            payload.get("task_id"),
            run_info.get("pressure_profile_id"),
            run_info.get("seed"),
        )
        variant = payload.get("run_metadata", {}).get("agent_variant")
        if variant in {"baseline", "verified"}:
            pairs.setdefault(key, {})[variant] = payload

    complete = [
        entry
        for entry in pairs.values()
        if "baseline" in entry and "verified" in entry
    ]
    if not complete:
        return None

    def interesting(entry: dict[str, dict]) -> bool:
        baseline_metrics = entry["baseline"].get("interaction_metrics", {})
        verified_metrics = entry["verified"].get("interaction_metrics", {})
        return (
            baseline_metrics.get("accepted_false_finishes", 0) > 0
            and verified_metrics.get("blocked_false_finishes", 0) > 0
        )

    for entry in complete:
        if interesting(entry):
            return entry["baseline"], entry["verified"]
    first = complete[0]
    return first["baseline"], first["verified"]
