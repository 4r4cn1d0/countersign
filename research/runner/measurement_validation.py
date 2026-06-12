"""Validation of automatic measurement code against frozen manual labels."""

from __future__ import annotations

import json
from pathlib import Path
from statistics import mean

from .decision_beliefs import (
    extract_decision_beliefs,
    summarize_decision_beliefs,
)
from .task_state_probes import score_task_state_probe


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_MANUAL_LABELS_PATH = (
    ROOT / "research" / "benchmarks" / "manual_measurement_labels.json"
)


def load_manual_measurement_labels(
    path: Path = DEFAULT_MANUAL_LABELS_PATH,
) -> dict:
    """Load the frozen, manually specified measurement-validation fixture."""

    with path.open(encoding="utf-8") as handle:
        payload = json.load(handle)
    if payload.get("schema_version") != (
        "agent-manual-measurement-labels/v0.1"
    ):
        raise ValueError("Unsupported manual measurement label schema")
    if not payload.get("probe_cases") or not payload.get(
        "decision_belief_cases"
    ):
        raise ValueError(
            "Manual labels require probe and decision-belief cases"
        )
    return payload


def validate_manual_measurements(
    path: Path = DEFAULT_MANUAL_LABELS_PATH,
) -> dict:
    """Compare automatic scores with frozen manual checkpoint labels."""

    labels = load_manual_measurement_labels(path)
    probe_results = [
        _validate_probe_case(case) for case in labels["probe_cases"]
    ]
    decision_results = [
        _validate_decision_case(case)
        for case in labels["decision_belief_cases"]
    ]
    comparisons = [
        comparison
        for result in [*probe_results, *decision_results]
        for comparison in result["comparisons"]
    ]
    disagreements = [
        comparison
        for comparison in comparisons
        if not comparison["matches_manual_label"]
    ]
    return {
        "schema_version": "agent-measurement-validation/v0.1",
        "label_fixture": str(path),
        "annotation_method": labels.get("annotation_method"),
        "probe_case_count": len(probe_results),
        "decision_belief_case_count": len(decision_results),
        "comparison_count": len(comparisons),
        "exact_match_count": len(comparisons) - len(disagreements),
        "exact_match_rate": _rate(
            len(comparisons) - len(disagreements),
            len(comparisons),
        ),
        "mean_absolute_error": round(
            mean(
                abs(
                    float(comparison["automatic"])
                    - float(comparison["manual"])
                )
                for comparison in comparisons
            ),
            4,
        )
        if comparisons
        else None,
        "probe_results": probe_results,
        "decision_belief_results": decision_results,
        "disagreements": disagreements,
    }


def _validate_probe_case(case: dict) -> dict:
    automatic = score_task_state_probe(
        case.get("prediction"),
        case["expected_state"],
    )
    comparisons = _comparisons(
        case["case_id"],
        automatic,
        case["manual_scores"],
    )
    return {
        "case_id": case["case_id"],
        "description": case["description"],
        "comparisons": comparisons,
    }


def _validate_decision_case(case: dict) -> dict:
    run = case["run"]
    beliefs = extract_decision_beliefs(run)
    automatic = summarize_decision_beliefs(
        beliefs,
        trace_events=run.get("trace_events", []),
    )
    comparisons = _comparisons(
        case["case_id"],
        automatic,
        case["manual_summary"],
    )
    return {
        "case_id": case["case_id"],
        "description": case["description"],
        "extracted_beliefs": beliefs,
        "comparisons": comparisons,
    }


def _comparisons(
    case_id: str,
    automatic: dict,
    manual: dict,
) -> list[dict]:
    comparisons = []
    for metric, manual_value in manual.items():
        automatic_value = automatic.get(metric)
        matches = (
            abs(float(automatic_value) - float(manual_value)) <= 0.0001
            if isinstance(manual_value, (int, float))
            and isinstance(automatic_value, (int, float))
            else automatic_value == manual_value
        )
        comparisons.append(
            {
                "case_id": case_id,
                "metric": metric,
                "manual": manual_value,
                "automatic": automatic_value,
                "matches_manual_label": matches,
            }
        )
    return comparisons


def _rate(count: int, total: int) -> float:
    return round(count / total, 4) if total else 0.0
