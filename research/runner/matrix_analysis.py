"""Analysis helpers for paired real-runtime model matrix artifacts."""

from __future__ import annotations

import json
from collections import Counter, defaultdict
from pathlib import Path
from statistics import mean
from typing import Any

from .statistics import build_paired_statistics


def analyze_model_matrix_manifest(manifest_path: Path) -> dict:
    """Build a paired comparison report from a model-matrix manifest."""

    manifest = _read_json(manifest_path)
    manifest_dir = manifest_path.parent
    model_rows = []
    task_rows = []

    for model in manifest.get("models", []):
        rows = _task_rows_for_model(
            model,
            manifest_dir,
            task_ids=manifest.get("task_ids", []),
            memory_conditions=manifest.get(
                "memory_conditions",
                ["full_history"],
            ),
            seeds=manifest.get("seeds", [0]),
        )
        task_rows.extend(rows)
        model_rows.append(_model_summary(model, rows))

    successful_rows = [
        row for row in model_rows if row["status"] == "succeeded"
    ]
    paired_statistics = build_paired_statistics(task_rows)
    return {
        "schema_version": "agent-memory-model-matrix-analysis/v0.2",
        "manifest_path": str(manifest_path.resolve()),
        "protocol_id": manifest.get("protocol_id"),
        "protocol_path": manifest.get("protocol_path"),
        "framework": manifest.get("framework", "react_custom"),
        "runtime": manifest.get("runtime"),
        "runtime_endpoint": manifest.get("runtime_endpoint"),
        "trace_mode": manifest.get("trace_mode"),
        "prompt_template": manifest.get("prompt_template"),
        "constrained_actions": manifest.get("constrained_actions"),
        "thinking": manifest.get("thinking"),
        "memory_conditions": manifest.get(
            "memory_conditions",
            ["full_history"],
        ),
        "task_state_probes": manifest.get("task_state_probes", False),
        "seeds": manifest.get("seeds", [0]),
        "model_count": len(model_rows),
        "successful_model_count": len(successful_rows),
        "task_count": len(set(row["task_id"] for row in task_rows)),
        "planned_pair_count": len(task_rows),
        "eligible_pair_count": paired_statistics["eligible_pair_count"],
        "models": model_rows,
        "tasks": task_rows,
        "aggregate": _aggregate_summary(successful_rows, task_rows),
        "paired_statistics": paired_statistics,
        "limitations": manifest.get("limitations", []),
    }


def write_model_matrix_analysis(
    manifest_path: Path,
    output_path: Path,
    output_format: str,
) -> dict:
    """Write a matrix analysis report and return the report payload."""

    report = analyze_model_matrix_manifest(manifest_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    if output_format == "markdown" or output_path.suffix == ".md":
        output_path.write_text(
            format_model_matrix_analysis_markdown(report),
            encoding="utf-8",
        )
    else:
        output_path.write_text(
            json.dumps(report, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    return report


def format_model_matrix_analysis_markdown(report: dict) -> str:
    """Format a model-matrix analysis report as Markdown."""

    statistics = report["paired_statistics"]
    primary = statistics["binary_outcomes"]["accepted_false_finish_trial"]
    lines = [
        "# Agent Memory Model Matrix Analysis",
        "",
        f"- Manifest: `{report['manifest_path']}`",
        f"- Protocol ID: `{report.get('protocol_id')}`",
        f"- Framework: `{report.get('framework')}`",
        f"- Runtime: `{report.get('runtime')}`",
        f"- Seeds: `{report.get('seeds')}`",
        f"- Memory conditions: `{report.get('memory_conditions')}`",
        f"- Task-state probes: `{report.get('task_state_probes')}`",
        f"- Constrained actions: `{report.get('constrained_actions')}`",
        f"- Thinking mode: `{report.get('thinking')}`",
        f"- Fully successful models: `{report['successful_model_count']}`",
        f"- Planned pairs: `{report['planned_pair_count']}`",
        f"- Statistically eligible pairs: `{report['eligible_pair_count']}`",
        "",
        "## Primary Endpoint",
        "",
        (
            "- Baseline accepted-false-finish rate: "
            f"`{_rate_text(primary['baseline'])}`"
        ),
        (
            "- Verified accepted-false-finish rate: "
            f"`{_rate_text(primary['verified'])}`"
        ),
        (
            "- Verified minus baseline risk difference: "
            f"`{primary['risk_difference_verified_minus_baseline']}`"
        ),
        (
            "- Exact paired McNemar p-value: "
            f"`{primary['mcnemar']['p_value_two_sided_exact']}`"
        ),
        "",
        "A zero observed verified rate is not treated as proof of zero risk; the Wilson interval above reports the uncertainty implied by the sample size.",
        "",
        "## Model Summary",
        "",
        "| Model | Status | Pairs | Eligible | Baseline Accepted False | Blocked False | Repair Successes | Recovered Tasks | Verified Accepted False | Avg Extra Actions |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for model in report["models"]:
        lines.append(
            "| `{model}` | `{status}` | {pairs} | {eligible} | {baseline_false} | {blocked_false} | {repair_successes} | {recoveries} | {verified_false} | {actions:.2f} |".format(
                model=model["model_name"],
                status=model["status"],
                pairs=model["pair_count"],
                eligible=model["eligible_pair_count"],
                baseline_false=model[
                    "baseline_accepted_false_finish_count"
                ],
                blocked_false=model[
                    "verified_blocked_false_finish_count"
                ],
                repair_successes=model[
                    "verified_memory_repair_success_count"
                ],
                recoveries=model[
                    "verified_memory_repair_recovery_count"
                ],
                verified_false=model[
                    "verified_accepted_false_finish_count"
                ],
                actions=model["avg_extra_model_actions"],
            )
        )

    lines.extend(
        [
            "",
            "## Coding-Agent Intervention Matrix",
            "",
            "| Model | Task | Memory | Seed | Eligible | Baseline Outcome | Verified Outcome | Baseline Accepted False | Blocked False | Repair Attempts | Repair Recovery | Verified Accepted False | Baseline Structured Memory | Verified Structured Memory | Extra Actions |",
            "|---|---|---|---:|---:|---|---|---:|---:|---:|---:|---:|---:|---:|---:|",
        ]
    )
    for row in report["tasks"]:
        lines.append(
            "| `{model}` | `{task}` | `{memory}` | {seed} | {eligible} | `{baseline_outcome}` | `{verified_outcome}` | {baseline_false} | {blocked_false} | {repair_attempts} | {repair_recovery} | {verified_false} | {baseline_structured} | {verified_structured} | {actions} |".format(
                model=row["model_name"],
                task=row["task_id"],
                memory=row["memory_condition"],
                seed=row["seed"],
                eligible=row["pair_eligible"],
                baseline_outcome=row["baseline_task_outcome"],
                verified_outcome=row["verified_task_outcome"],
                baseline_false=row["baseline_accepted_false_finishes"],
                blocked_false=row["verified_blocked_false_finishes"],
                repair_attempts=row["verified_memory_repair_attempts"],
                repair_recovery=row["verified_memory_repair_recovery"],
                verified_false=row["verified_accepted_false_finishes"],
                baseline_structured=row[
                    "baseline_structured_memory_score"
                ],
                verified_structured=row[
                    "verified_structured_memory_score"
                ],
                actions=row["extra_model_actions"],
            )
        )

    lines.extend(["", "## Paired Statistical Outcomes", ""])
    for name, result in statistics["binary_outcomes"].items():
        lines.append(
            f"- `{name}`: baseline "
            f"`{_rate_text(result['baseline'])}`; verified "
            f"`{_rate_text(result['verified'])}`; risk difference "
            f"`{result['risk_difference_verified_minus_baseline']}`; "
            f"exact McNemar p=`{result['mcnemar']['p_value_two_sided_exact']}`"
        )
    for name, result in statistics["continuous_outcomes"].items():
        lines.append(
            f"- `{name}` verified-minus-baseline mean: "
            f"`{result['mean_difference']}`; bootstrap 95% CI "
            f"`{result['ci95']}`"
        )

    lines.extend(["", "## Exclusion Ledger", ""])
    if statistics["exclusion_ledger"]:
        lines.extend(
            "- `{model}` / `{task}` / `{memory}` / seed `{seed}`: {reason}".format(
                model=item["model_name"],
                task=item["task_id"],
                memory=item.get("memory_condition", "full_history"),
                seed=item["seed"],
                reason=item["reason"],
            )
            for item in statistics["exclusion_ledger"]
        )
    else:
        lines.append("- No pairs excluded.")

    lines.extend(["", "## Aggregate", ""])
    for key, value in report["aggregate"].items():
        lines.append(f"- `{key}`: `{value}`")

    if report.get("limitations"):
        lines.extend(["", "## Limitations", ""])
        lines.extend(f"- {item}" for item in report["limitations"])
    lines.append("")
    return "\n".join(lines)


def _task_rows_for_model(
    model: dict,
    manifest_dir: Path,
    *,
    task_ids: list[str],
    memory_conditions: list[str],
    seeds: list[int],
) -> list[dict]:
    runs_by_pair: dict[
        tuple[str, str, int],
        dict[str, dict],
    ] = defaultdict(dict)
    for task_id in task_ids:
        for memory_condition in memory_conditions:
            for seed in seeds:
                runs_by_pair[
                    (task_id, memory_condition, int(seed))
                ]
    for run_info in model.get("runs", []):
        seed = int(run_info.get("seed", 0))
        memory_condition = run_info.get(
            "memory_condition",
            "full_history",
        )
        runs_by_pair[(run_info["task_id"], memory_condition, seed)][
            run_info["variant"]
        ] = run_info
    for error in model.get("errors", []):
        key = (
            error["task_id"],
            error.get("memory_condition", "full_history"),
            int(error.get("seed", 0)),
        )
        runs_by_pair[key].setdefault(
            f"{error.get('variant')}_error",
            error,
        )

    rows = []
    for (task_id, memory_condition, seed), pair in sorted(
        runs_by_pair.items()
    ):
        baseline_info = pair.get("baseline")
        verified_info = pair.get("verified")
        baseline = _read_run_info(baseline_info, manifest_dir)
        verified = _read_run_info(verified_info, manifest_dir)
        baseline_metadata = baseline.get("run_metadata", {})
        verified_metadata = verified.get("run_metadata", {})
        baseline_interaction = baseline.get("interaction_metrics", {})
        verified_interaction = verified.get("interaction_metrics", {})
        baseline_health = baseline.get("memory_health_report", {})
        verified_health = verified.get("memory_health_report", {})
        baseline_probe = baseline.get("task_state_probe_summary", {})
        verified_probe = verified.get("task_state_probe_summary", {})
        metrics = baseline_health.get("metrics", {})
        baseline_headline = baseline_health.get("headline_metrics", {})
        verified_headline = verified_health.get("headline_metrics", {})
        exploratory = baseline_health.get("exploratory_metrics", {})
        verification_report = verified.get("verification_report", {})
        baseline_counts = baseline_health.get("claim_counts", {})
        baseline_final = _final_test_status(baseline)
        verified_final = _final_test_status(verified)
        baseline_iterations = int(
            baseline_metadata.get("tool_loop_iterations") or 0
        )
        verified_iterations = int(
            verified_metadata.get("tool_loop_iterations") or 0
        )
        pair_complete = bool(baseline_info and verified_info)
        exclusion_reason = _pair_exclusion_reason(
            pair_complete=pair_complete,
            baseline_info=baseline_info,
            verified_info=verified_info,
            baseline_metadata=baseline_metadata,
            verified_metadata=verified_metadata,
            pair=pair,
        )
        false_completion_claims = int(
            baseline_counts.get("false_completion", 0)
        )
        stale_claims = int(baseline_counts.get("stale", 0))
        rows.append(
            {
                "model_name": model["model_name"],
                "model_family": model.get("model_family"),
                "task_id": task_id,
                "memory_condition": memory_condition,
                "seed": seed,
                "trial_id": (
                    baseline_info or verified_info or {}
                ).get("trial_id"),
                "pair_complete": pair_complete,
                "pair_eligible": exclusion_reason is None,
                "exclusion_reason": exclusion_reason,
                "parse_status": baseline_metadata.get(
                    "model_trace_parse_status"
                )
                or "unknown",
                "parsed_claim_count": int(
                    baseline_metadata.get("model_trace_claim_count") or 0
                ),
                "high_risk_label_count": len(
                    baseline.get("high_risk_labels", [])
                ),
                "blocked_action_count": len(
                    verification_report.get("blocked_actions", [])
                ),
                "stale_claim_count": stale_claims,
                "used_stale_evidence": stale_claims > 0,
                "false_completion_claim_count": false_completion_claims,
                "baseline_false_finish_proposals": int(
                    baseline_interaction.get("false_finish_proposals", 0)
                ),
                "baseline_accepted_false_finishes": int(
                    baseline_interaction.get("accepted_false_finishes", 0)
                ),
                "baseline_accepted_finish_evaluator_failures": int(
                    baseline_interaction.get(
                        "accepted_finish_evaluator_failures",
                        0,
                    )
                ),
                "verified_false_finish_proposals": int(
                    verified_interaction.get("false_finish_proposals", 0)
                ),
                "verified_blocked_false_finishes": int(
                    verified_interaction.get("blocked_false_finishes", 0)
                ),
                "verified_accepted_false_finishes": int(
                    verified_interaction.get("accepted_false_finishes", 0)
                ),
                "verified_accepted_finish_evaluator_failures": int(
                    verified_interaction.get(
                        "accepted_finish_evaluator_failures",
                        0,
                    )
                ),
                "verified_recovery_after_block": bool(
                    verified_interaction.get("recovery_after_block", False)
                ),
                "baseline_memory_repair_recovery": bool(
                    baseline_interaction.get(
                        "memory_repair_recovery",
                        False,
                    )
                ),
                "verified_memory_corruption_detections": int(
                    verified_interaction.get(
                        "memory_corruption_detections",
                        0,
                    )
                ),
                "verified_memory_corruption_containments": int(
                    verified_interaction.get(
                        "memory_corruption_containments",
                        0,
                    )
                ),
                "verified_memory_repair_attempts": int(
                    verified_interaction.get(
                        "memory_repair_attempts",
                        0,
                    )
                ),
                "verified_memory_repair_successes": int(
                    verified_interaction.get(
                        "memory_repair_successes",
                        0,
                    )
                ),
                "verified_memory_repair_recovery": bool(
                    verified_interaction.get(
                        "memory_repair_recovery",
                        False,
                    )
                ),
                "baseline_evaluator_success": (
                    baseline_final.get("status") == "success"
                    if baseline
                    else None
                ),
                "verified_evaluator_success": (
                    verified_final.get("status") == "success"
                    if verified
                    else None
                ),
                "baseline_evaluator_returncode": baseline_final.get(
                    "returncode"
                ),
                "verified_evaluator_returncode": verified_final.get(
                    "returncode"
                ),
                "baseline_protocol_completion_status": (
                    baseline_interaction.get("protocol_completion_status")
                    or baseline_interaction.get("termination_reason")
                    or baseline_metadata.get("termination_reason")
                ),
                "verified_protocol_completion_status": (
                    verified_interaction.get("protocol_completion_status")
                    or verified_interaction.get("termination_reason")
                    or verified_metadata.get("termination_reason")
                ),
                "baseline_task_outcome": baseline_interaction.get(
                    "task_outcome",
                    "missing_run" if not baseline else "unknown",
                ),
                "verified_task_outcome": verified_interaction.get(
                    "task_outcome",
                    "missing_run" if not verified else "unknown",
                ),
                "baseline_model_action_count": int(
                    baseline_interaction.get(
                        "model_action_count",
                        baseline_iterations,
                    )
                ),
                "verified_model_action_count": int(
                    verified_interaction.get(
                        "model_action_count",
                        verified_iterations,
                    )
                ),
                "baseline_action_compliance_rate": float(
                    baseline_interaction.get("action_compliance_rate", 0.0)
                ),
                "verified_action_compliance_rate": float(
                    verified_interaction.get("action_compliance_rate", 0.0)
                ),
                "baseline_probe_eligible_count": int(
                    baseline_probe.get("eligible_probe_count", 0)
                ),
                "verified_probe_eligible_count": int(
                    verified_probe.get("eligible_probe_count", 0)
                ),
                "baseline_probe_overall_accuracy": baseline_probe.get(
                    "mean_overall_accuracy"
                ),
                "verified_probe_overall_accuracy": verified_probe.get(
                    "mean_overall_accuracy"
                ),
                "baseline_probe_subtask_accuracy": baseline_probe.get(
                    "mean_subtask_state_accuracy"
                ),
                "verified_probe_subtask_accuracy": verified_probe.get(
                    "mean_subtask_state_accuracy"
                ),
                "baseline_probe_latest_test_accuracy": baseline_probe.get(
                    "mean_latest_test_accuracy"
                ),
                "verified_probe_latest_test_accuracy": verified_probe.get(
                    "mean_latest_test_accuracy"
                ),
                "baseline_probe_evidence_attribution_accuracy": (
                    baseline_probe.get(
                        "mean_evidence_attribution_accuracy"
                    )
                ),
                "baseline_structured_memory_score": baseline_headline.get(
                    "structured_memory_score"
                ),
                "verified_structured_memory_score": verified_headline.get(
                    "structured_memory_score"
                ),
                "baseline_requirement_recall": baseline_headline.get(
                    "requirement_recall"
                ),
                "verified_requirement_recall": verified_headline.get(
                    "requirement_recall"
                ),
                "baseline_temporal_ordering_accuracy": (
                    baseline_headline.get(
                        "temporal_ordering_accuracy"
                    )
                ),
                "verified_temporal_ordering_accuracy": (
                    verified_headline.get(
                        "temporal_ordering_accuracy"
                    )
                ),
                "baseline_stale_decision_use_rate": float(
                    baseline_headline.get(
                        "stale_decision_use_rate",
                        0.0,
                    )
                ),
                "verified_stale_decision_use_rate": float(
                    verified_headline.get(
                        "stale_decision_use_rate",
                        0.0,
                    )
                ),
                "verified_probe_evidence_attribution_accuracy": (
                    verified_probe.get(
                        "mean_evidence_attribution_accuracy"
                    )
                ),
                "baseline_probe_objective_fidelity": baseline_probe.get(
                    "mean_objective_fidelity"
                ),
                "verified_probe_objective_fidelity": verified_probe.get(
                    "mean_objective_fidelity"
                ),
                "baseline_probe_unsuccessful_attempt_accuracy": (
                    baseline_probe.get("mean_unsuccessful_attempt_f1")
                ),
                "verified_probe_unsuccessful_attempt_accuracy": (
                    verified_probe.get("mean_unsuccessful_attempt_f1")
                ),
                "baseline_probe_repository_state_accuracy": (
                    baseline_probe.get("mean_repository_state_f1")
                ),
                "verified_probe_repository_state_accuracy": (
                    verified_probe.get("mean_repository_state_f1")
                ),
                "baseline_probe_current_evidence_accuracy": (
                    baseline_probe.get("mean_current_evidence_f1")
                ),
                "verified_probe_current_evidence_accuracy": (
                    verified_probe.get("mean_current_evidence_f1")
                ),
                "baseline_probe_stale_evidence_accuracy": (
                    baseline_probe.get("mean_stale_evidence_f1")
                ),
                "verified_probe_stale_evidence_accuracy": (
                    verified_probe.get("mean_stale_evidence_f1")
                ),
                "baseline_probe_uncertainty_calibration_accuracy": (
                    baseline_probe.get(
                        "mean_uncertainty_calibration_accuracy"
                    )
                ),
                "verified_probe_uncertainty_calibration_accuracy": (
                    verified_probe.get(
                        "mean_uncertainty_calibration_accuracy"
                    )
                ),
                "baseline_probe_next_action_accuracy": (
                    baseline_probe.get("mean_next_action_accuracy")
                ),
                "verified_probe_next_action_accuracy": (
                    verified_probe.get("mean_next_action_accuracy")
                ),
                "extra_model_actions": (
                    verified_iterations - baseline_iterations
                ),
                "extra_trace_events": max(
                    0,
                    len(verified.get("trace_events", []))
                    - len(baseline.get("trace_events", [])),
                ),
                "verification_event_count": _verification_event_count(
                    verified
                ),
                "tool_action_parse_status_counts": (
                    _tool_action_parse_status_counts(baseline)
                ),
                "tool_action_status_counts": _tool_action_status_counts(
                    baseline
                ),
                "memory_health_score": float(
                    metrics.get("memory_health_score", 0.0)
                ),
                "semantic_drift_score": float(
                    exploratory.get("semantic_drift_score", 0.0)
                ),
                "false_completion_rate": float(
                    metrics.get("false_completion_rate", 0.0)
                ),
                "baseline_runtime_error": baseline_metadata.get(
                    "runtime_error"
                ),
                "verified_runtime_error": verified_metadata.get(
                    "runtime_error"
                ),
                "run_path": (
                    str(_resolve_artifact_path(baseline_info["path"], manifest_dir))
                    if baseline_info
                    else None
                ),
                "verified_run_path": (
                    str(_resolve_artifact_path(verified_info["path"], manifest_dir))
                    if verified_info
                    else None
                ),
            }
        )
    return rows


def _model_summary(model: dict, rows: list[dict]) -> dict:
    parse_counts = Counter(row["parse_status"] for row in rows)
    tool_action_parse_counts: Counter[str] = Counter()
    tool_action_status_counts: Counter[str] = Counter()
    for row in rows:
        tool_action_parse_counts.update(
            row["tool_action_parse_status_counts"]
        )
        tool_action_status_counts.update(
            row["tool_action_status_counts"]
        )
    eligible = [row for row in rows if row["pair_eligible"]]
    return {
        "model_name": model["model_name"],
        "model_family": model.get("model_family"),
        "status": model.get("status"),
        "pair_count": len(rows),
        "eligible_pair_count": len(eligible),
        "excluded_pair_count": len(rows) - len(eligible),
        "baseline_task_count": len(rows),
        "parse_status_counts": dict(sorted(parse_counts.items())),
        "parsed_claim_count": sum(
            row["parsed_claim_count"] for row in rows
        ),
        "high_risk_label_count": sum(
            row["high_risk_label_count"] for row in rows
        ),
        "blocked_action_count": sum(
            row["blocked_action_count"] for row in rows
        ),
        "stale_evidence_row_count": sum(
            1 for row in rows if row["used_stale_evidence"]
        ),
        "stale_claim_count": sum(row["stale_claim_count"] for row in rows),
        "false_completion_claim_count": sum(
            row["false_completion_claim_count"] for row in rows
        ),
        "baseline_accepted_false_finish_count": sum(
            row["baseline_accepted_false_finishes"] for row in rows
        ),
        "verified_false_finish_proposal_count": sum(
            row["verified_false_finish_proposals"] for row in rows
        ),
        "verified_blocked_false_finish_count": sum(
            row["verified_blocked_false_finishes"] for row in rows
        ),
        "verified_accepted_false_finish_count": sum(
            row["verified_accepted_false_finishes"] for row in rows
        ),
        "baseline_accepted_finish_evaluator_failure_count": sum(
            row["baseline_accepted_finish_evaluator_failures"]
            for row in rows
        ),
        "verified_accepted_finish_evaluator_failure_count": sum(
            row["verified_accepted_finish_evaluator_failures"]
            for row in rows
        ),
        "verified_recovery_count": sum(
            1 for row in rows if row["verified_recovery_after_block"]
        ),
        "verified_memory_repair_recovery_count": sum(
            1 for row in rows if row["verified_memory_repair_recovery"]
        ),
        "verified_memory_repair_attempt_count": sum(
            row["verified_memory_repair_attempts"] for row in rows
        ),
        "verified_memory_repair_success_count": sum(
            row["verified_memory_repair_successes"] for row in rows
        ),
        "baseline_evaluator_success_count": sum(
            1 for row in rows if row["baseline_evaluator_success"]
        ),
        "verified_evaluator_success_count": sum(
            1 for row in rows if row["verified_evaluator_success"]
        ),
        "tool_action_parse_status_counts": dict(
            sorted(tool_action_parse_counts.items())
        ),
        "tool_action_status_counts": dict(
            sorted(tool_action_status_counts.items())
        ),
        "avg_extra_model_actions": _mean(
            row["extra_model_actions"] for row in eligible
        ),
        "extra_trace_event_count": sum(
            row["extra_trace_events"] for row in rows
        ),
        "verification_event_count": sum(
            row["verification_event_count"] for row in rows
        ),
        "avg_memory_health_score": _mean(
            row["memory_health_score"] for row in rows
        ),
        "avg_baseline_structured_memory_score": _mean(
            row["baseline_structured_memory_score"]
            for row in rows
            if row["baseline_structured_memory_score"] is not None
        ),
        "avg_verified_structured_memory_score": _mean(
            row["verified_structured_memory_score"]
            for row in rows
            if row["verified_structured_memory_score"] is not None
        ),
        "avg_semantic_drift_score": _mean(
            row["semantic_drift_score"] for row in rows
        ),
        "avg_false_completion_rate": _mean(
            row["false_completion_rate"] for row in rows
        ),
        "errors": model.get("errors", []),
    }


def _aggregate_summary(
    successful_rows: list[dict],
    task_rows: list[dict],
) -> dict[str, Any]:
    parse_counts: Counter[str] = Counter(
        row["parse_status"] for row in task_rows
    )
    blocked_by_model: dict[str, int] = defaultdict(int)
    for row in task_rows:
        blocked_by_model[row["model_name"]] += row["blocked_action_count"]
    return {
        "successful_models": len(successful_rows),
        "planned_pair_rows": len(task_rows),
        "eligible_pair_rows": sum(
            1 for row in task_rows if row["pair_eligible"]
        ),
        "excluded_pair_rows": sum(
            1 for row in task_rows if not row["pair_eligible"]
        ),
        "baseline_task_rows": len(task_rows),
        "parse_status_counts": dict(sorted(parse_counts.items())),
        "total_parsed_claims": sum(
            row["parsed_claim_count"] for row in task_rows
        ),
        "total_high_risk_labels": sum(
            row["high_risk_label_count"] for row in task_rows
        ),
        "total_blocked_actions": sum(
            row["blocked_action_count"] for row in task_rows
        ),
        "total_stale_claims": sum(
            row["stale_claim_count"] for row in task_rows
        ),
        "total_false_completion_claims": sum(
            row["false_completion_claim_count"] for row in task_rows
        ),
        "baseline_accepted_false_finishes": sum(
            row["baseline_accepted_false_finishes"] for row in task_rows
        ),
        "verified_false_finish_proposals": sum(
            row["verified_false_finish_proposals"] for row in task_rows
        ),
        "verified_blocked_false_finishes": sum(
            row["verified_blocked_false_finishes"] for row in task_rows
        ),
        "verified_accepted_false_finishes": sum(
            row["verified_accepted_false_finishes"] for row in task_rows
        ),
        "baseline_accepted_finish_evaluator_failures": sum(
            row["baseline_accepted_finish_evaluator_failures"]
            for row in task_rows
        ),
        "verified_accepted_finish_evaluator_failures": sum(
            row["verified_accepted_finish_evaluator_failures"]
            for row in task_rows
        ),
        "verified_recovery_rows": sum(
            1
            for row in task_rows
            if row["verified_recovery_after_block"]
        ),
        "verified_memory_repair_recovery_rows": sum(
            1
            for row in task_rows
            if row["verified_memory_repair_recovery"]
        ),
        "verified_memory_repair_attempts": sum(
            row["verified_memory_repair_attempts"]
            for row in task_rows
        ),
        "verified_memory_repair_successes": sum(
            row["verified_memory_repair_successes"]
            for row in task_rows
        ),
        "baseline_evaluator_success_rows": sum(
            1 for row in task_rows if row["baseline_evaluator_success"]
        ),
        "verified_evaluator_success_rows": sum(
            1 for row in task_rows if row["verified_evaluator_success"]
        ),
        "total_extra_model_actions": sum(
            row["extra_model_actions"] for row in task_rows
        ),
        "total_extra_trace_events": sum(
            row["extra_trace_events"] for row in task_rows
        ),
        "avg_memory_health_score": _mean(
            row["memory_health_score"] for row in task_rows
        ),
        "avg_baseline_structured_memory_score": _mean(
            row["baseline_structured_memory_score"]
            for row in task_rows
            if row["baseline_structured_memory_score"] is not None
        ),
        "avg_verified_structured_memory_score": _mean(
            row["verified_structured_memory_score"]
            for row in task_rows
            if row["verified_structured_memory_score"] is not None
        ),
        "avg_semantic_drift_score": _mean(
            row["semantic_drift_score"] for row in task_rows
        ),
        "blocked_actions_by_model": dict(sorted(blocked_by_model.items())),
    }


def _pair_exclusion_reason(
    *,
    pair_complete: bool,
    baseline_info: dict | None,
    verified_info: dict | None,
    baseline_metadata: dict,
    verified_metadata: dict,
    pair: dict,
) -> str | None:
    if not pair_complete:
        missing = []
        if not baseline_info:
            missing.append("baseline")
        if not verified_info:
            missing.append("verified")
        errors = [
            value.get("error", "")
            for key, value in pair.items()
            if key.endswith("_error")
        ]
        detail = f"; runtime errors: {' | '.join(errors)}" if errors else ""
        return f"missing paired artifact(s): {', '.join(missing)}{detail}"
    runtime_errors = [
        error
        for error in [
            baseline_metadata.get("runtime_error"),
            verified_metadata.get("runtime_error"),
        ]
        if error
    ]
    if runtime_errors:
        return "run artifact recorded runtime error: " + " | ".join(
            str(error) for error in runtime_errors
        )
    return None


def _read_run_info(run_info: dict | None, manifest_dir: Path) -> dict:
    if not run_info:
        return {}
    path = _resolve_artifact_path(run_info["path"], manifest_dir)
    if not path.exists():
        return {}
    return _read_json(path)


def _resolve_artifact_path(path: str, manifest_dir: Path) -> Path:
    artifact_path = Path(path)
    return (
        artifact_path
        if artifact_path.is_absolute()
        else manifest_dir / artifact_path
    )


def _tool_action_parse_status_counts(run: dict) -> dict[str, int]:
    counts = Counter(
        event.get("parse_status", "unknown")
        for event in run.get("trace_events", [])
        if event.get("event_type") == "model_response"
        and event.get("graph_node") == "choose_action"
    )
    return dict(sorted(counts.items()))


def _tool_action_status_counts(run: dict) -> dict[str, int]:
    counts = Counter(
        event.get("action_status", "unknown")
        for event in run.get("trace_events", [])
        if event.get("event_type") == "decision_point"
        and event.get("graph_node") == "choose_action"
    )
    return dict(sorted(counts.items()))


def _verification_event_count(run: dict) -> int:
    return sum(
        1
        for event in run.get("trace_events", [])
        if event.get("event_type") == "verification_decision"
    )


def _final_test_status(run: dict) -> dict:
    for event in reversed(run.get("trace_events", [])):
        if event.get("event_type") == "evaluation_result":
            return {
                "status": event.get("status"),
                "returncode": event.get("returncode"),
            }
    return {}


def _rate_text(interval: dict) -> str:
    if interval["rate"] is None:
        return "n/a"
    lower, upper = interval["ci95"]
    return (
        f"{interval['successes']}/{interval['total']} = "
        f"{interval['rate']:.4f} (95% CI {lower:.4f}-{upper:.4f})"
    )


def _mean(values) -> float:
    items = list(values)
    return round(mean(items), 4) if items else 0.0


def _read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))
