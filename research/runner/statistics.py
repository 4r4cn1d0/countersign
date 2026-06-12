"""Predeclared paired statistics for the model-matrix experiment."""

from __future__ import annotations

import math
import random
from statistics import mean
from typing import Callable, Iterable


def wilson_interval(successes: int, total: int, z: float = 1.959963984540054) -> dict:
    """Return a Wilson score interval for a binary proportion."""

    if total <= 0:
        return {
            "successes": successes,
            "total": total,
            "rate": None,
            "ci95": [None, None],
        }
    proportion = successes / total
    denominator = 1 + (z * z / total)
    center = (proportion + z * z / (2 * total)) / denominator
    margin = (
        z
        * math.sqrt(
            proportion * (1 - proportion) / total
            + z * z / (4 * total * total)
        )
        / denominator
    )
    return {
        "successes": successes,
        "total": total,
        "rate": round(proportion, 6),
        "ci95": [
            round(max(0.0, center - margin), 6),
            round(min(1.0, center + margin), 6),
        ],
    }


def exact_mcnemar(baseline: list[bool], verified: list[bool]) -> dict:
    """Return the two-sided exact McNemar result for paired binary outcomes."""

    if len(baseline) != len(verified):
        raise ValueError("Paired binary outcomes must have equal lengths")
    baseline_only = sum(
        1 for base, intervention in zip(baseline, verified) if base and not intervention
    )
    verified_only = sum(
        1 for base, intervention in zip(baseline, verified) if not base and intervention
    )
    discordant = baseline_only + verified_only
    if discordant == 0:
        p_value = 1.0
    else:
        smaller = min(baseline_only, verified_only)
        tail = sum(
            math.comb(discordant, value)
            for value in range(smaller + 1)
        ) / (2**discordant)
        p_value = min(1.0, 2 * tail)
    return {
        "paired_trials": len(baseline),
        "baseline_only": baseline_only,
        "verified_only": verified_only,
        "discordant_pairs": discordant,
        "p_value_two_sided_exact": round(p_value, 8),
    }


def paired_bootstrap_mean_difference(
    baseline: Iterable[float],
    verified: Iterable[float],
    *,
    resamples: int = 5000,
    seed: int = 0,
) -> dict:
    """Estimate verified-minus-baseline mean difference with paired resampling."""

    baseline_values = list(baseline)
    verified_values = list(verified)
    if len(baseline_values) != len(verified_values):
        raise ValueError("Paired continuous outcomes must have equal lengths")
    differences = [
        intervention - base
        for base, intervention in zip(baseline_values, verified_values)
    ]
    if not differences:
        return {
            "paired_trials": 0,
            "mean_difference": None,
            "ci95": [None, None],
            "bootstrap_resamples": resamples,
        }
    rng = random.Random(seed)
    sample_means = []
    for _ in range(resamples):
        sample_means.append(
            mean(rng.choice(differences) for _ in range(len(differences)))
        )
    sample_means.sort()
    lower = _percentile(sample_means, 0.025)
    upper = _percentile(sample_means, 0.975)
    return {
        "paired_trials": len(differences),
        "mean_difference": round(mean(differences), 6),
        "ci95": [round(lower, 6), round(upper, 6)],
        "bootstrap_resamples": resamples,
    }


def build_paired_statistics(rows: list[dict]) -> dict:
    """Apply the frozen analysis plan and preserve an explicit exclusion ledger."""

    eligible = [row for row in rows if row.get("pair_eligible")]
    exclusions = [
        {
            "model_name": row.get("model_name"),
            "task_id": row.get("task_id"),
            "memory_condition": row.get(
                "memory_condition",
                "full_history",
            ),
            "seed": row.get("seed"),
            "reason": row.get("exclusion_reason") or "unspecified",
        }
        for row in rows
        if not row.get("pair_eligible")
    ]
    binary_metrics: dict[str, tuple[Callable[[dict], bool], Callable[[dict], bool]]] = {
        "accepted_false_finish_trial": (
            lambda row: row["baseline_accepted_false_finishes"] > 0,
            lambda row: row["verified_accepted_false_finishes"] > 0,
        ),
        "raw_false_finish_proposal_trial": (
            lambda row: row["baseline_false_finish_proposals"] > 0,
            lambda row: row["verified_false_finish_proposals"] > 0,
        ),
        "accepted_finish_evaluator_failure_trial": (
            lambda row: row["baseline_accepted_finish_evaluator_failures"] > 0,
            lambda row: row["verified_accepted_finish_evaluator_failures"] > 0,
        ),
        "independent_evaluator_success": (
            lambda row: bool(row["baseline_evaluator_success"]),
            lambda row: bool(row["verified_evaluator_success"]),
        ),
        "accepted_finish": (
            lambda row: row["baseline_protocol_completion_status"]
            == "accepted_finish",
            lambda row: row["verified_protocol_completion_status"]
            == "accepted_finish",
        ),
        "action_budget_exhaustion": (
            lambda row: row["baseline_protocol_completion_status"]
            == "action_budget_exhausted",
            lambda row: row["verified_protocol_completion_status"]
            == "action_budget_exhausted",
        ),
        "independently_verified_memory_recovery": (
            lambda row: bool(
                row.get("baseline_memory_repair_recovery", False)
            ),
            lambda row: bool(
                row.get("verified_memory_repair_recovery", False)
            ),
        ),
    }
    binary_results = {}
    for name, (baseline_getter, verified_getter) in binary_metrics.items():
        baseline_values = [baseline_getter(row) for row in eligible]
        verified_values = [verified_getter(row) for row in eligible]
        binary_results[name] = {
            "baseline": wilson_interval(sum(baseline_values), len(baseline_values)),
            "verified": wilson_interval(sum(verified_values), len(verified_values)),
            "risk_difference_verified_minus_baseline": (
                round(
                    (
                        sum(verified_values) - sum(baseline_values)
                    )
                    / len(eligible),
                    6,
                )
                if eligible
                else None
            ),
            "mcnemar": exact_mcnemar(baseline_values, verified_values),
        }

    continuous_results = {
        "action_compliance_rate": paired_bootstrap_mean_difference(
            [row["baseline_action_compliance_rate"] for row in eligible],
            [row["verified_action_compliance_rate"] for row in eligible],
        ),
        "model_action_count": paired_bootstrap_mean_difference(
            [row["baseline_model_action_count"] for row in eligible],
            [row["verified_model_action_count"] for row in eligible],
        ),
    }
    probe_metrics = {
        "task_state_probe_accuracy": (
            "baseline_probe_overall_accuracy",
            "verified_probe_overall_accuracy",
        ),
        "subtask_state_probe_accuracy": (
            "baseline_probe_subtask_accuracy",
            "verified_probe_subtask_accuracy",
        ),
        "latest_test_probe_accuracy": (
            "baseline_probe_latest_test_accuracy",
            "verified_probe_latest_test_accuracy",
        ),
        "evidence_attribution_probe_accuracy": (
            "baseline_probe_evidence_attribution_accuracy",
            "verified_probe_evidence_attribution_accuracy",
        ),
        "objective_fidelity_probe_accuracy": (
            "baseline_probe_objective_fidelity",
            "verified_probe_objective_fidelity",
        ),
        "unsuccessful_attempt_probe_accuracy": (
            "baseline_probe_unsuccessful_attempt_accuracy",
            "verified_probe_unsuccessful_attempt_accuracy",
        ),
        "failed_attempt_probe_accuracy": (
            "baseline_probe_failed_attempt_accuracy",
            "verified_probe_failed_attempt_accuracy",
        ),
        "blocked_attempt_probe_accuracy": (
            "baseline_probe_blocked_attempt_accuracy",
            "verified_probe_blocked_attempt_accuracy",
        ),
        "repository_state_probe_accuracy": (
            "baseline_probe_repository_state_accuracy",
            "verified_probe_repository_state_accuracy",
        ),
        "current_evidence_probe_accuracy": (
            "baseline_probe_current_evidence_accuracy",
            "verified_probe_current_evidence_accuracy",
        ),
        "stale_evidence_probe_accuracy": (
            "baseline_probe_stale_evidence_accuracy",
            "verified_probe_stale_evidence_accuracy",
        ),
        "uncertain_evidence_probe_accuracy": (
            "baseline_probe_uncertain_evidence_accuracy",
            "verified_probe_uncertain_evidence_accuracy",
        ),
        "memory_accuracy_curve_auc": (
            "baseline_probe_curve_auc",
            "verified_probe_curve_auc",
        ),
        "uncertainty_calibration_probe_accuracy": (
            "baseline_probe_uncertainty_calibration_accuracy",
            "verified_probe_uncertainty_calibration_accuracy",
        ),
        "next_action_probe_accuracy": (
            "baseline_probe_next_action_accuracy",
            "verified_probe_next_action_accuracy",
        ),
    }
    for name, (baseline_key, verified_key) in probe_metrics.items():
        probe_rows = [
            row
            for row in eligible
            if row.get(baseline_key) is not None
            and row.get(verified_key) is not None
        ]
        continuous_results[name] = paired_bootstrap_mean_difference(
            [float(row[baseline_key]) for row in probe_rows],
            [float(row[verified_key]) for row in probe_rows],
        )
    structured_metrics = {
        "structured_memory_score": (
            "baseline_structured_memory_score",
            "verified_structured_memory_score",
        ),
        "requirement_recall": (
            "baseline_requirement_recall",
            "verified_requirement_recall",
        ),
        "temporal_ordering_accuracy": (
            "baseline_temporal_ordering_accuracy",
            "verified_temporal_ordering_accuracy",
        ),
        "stale_decision_use_rate": (
            "baseline_stale_decision_use_rate",
            "verified_stale_decision_use_rate",
        ),
    }
    for name, (baseline_key, verified_key) in structured_metrics.items():
        metric_rows = [
            row
            for row in eligible
            if row.get(baseline_key) is not None
            and row.get(verified_key) is not None
        ]
        continuous_results[name] = paired_bootstrap_mean_difference(
            [float(row[baseline_key]) for row in metric_rows],
            [float(row[verified_key]) for row in metric_rows],
        )
    return {
        "schema_version": "agent-memory-paired-statistics/v0.1",
        "analysis_unit": "model-task-memory-condition-seed pair",
        "planned_pair_count": len(rows),
        "eligible_pair_count": len(eligible),
        "excluded_pair_count": len(exclusions),
        "exclusion_ledger": exclusions,
        "primary_endpoint": "accepted_false_finish_trial",
        "binary_outcomes": binary_results,
        "continuous_outcomes": continuous_results,
        "interpretation_guardrails": [
            "Action-budget exhaustion is retained as an outcome, not excluded.",
            "Raw false proposals and accepted false finishes are reported separately.",
            "Only the primary endpoint is predeclared as confirmatory.",
            "Small-sample confidence intervals may be wide even when observed rates are zero.",
        ],
    }


def _percentile(sorted_values: list[float], probability: float) -> float:
    if len(sorted_values) == 1:
        return sorted_values[0]
    index = probability * (len(sorted_values) - 1)
    lower = math.floor(index)
    upper = math.ceil(index)
    if lower == upper:
        return sorted_values[lower]
    fraction = index - lower
    return (
        sorted_values[lower] * (1 - fraction)
        + sorted_values[upper] * fraction
    )
