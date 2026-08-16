"""Analysis helpers for paired real-runtime model matrix artifacts."""

from __future__ import annotations

import json
from collections import Counter, defaultdict
from pathlib import Path
from statistics import mean
from typing import Any

from .comparison_plan import (
    comparison_key,
    extra_pairwise_comparisons,
    reference_and_treatment_variants,
)
from .experiment_protocol import resolve_bundle_path
from .failure_attribution import classify_run_failure
from .statistics import build_paired_statistics


def _confirmatory_comparisons_from_manifest(
    manifest: dict,
    manifest_dir: Path,
) -> dict:
    """Load the frozen protocol's predeclared comparisons, if available.

    Returns {} (not an error) when the protocol file is missing or
    unreadable — callers must fall back to a sensible default rather than
    fail, since not every manifest (e.g. ad hoc test fixtures) writes a
    frozen protocol. Resolves protocol_relative_path first so a
    copied/relocated bundle (e.g. an anonymized workshop artifact) still
    finds its protocol — falling back to the absolute protocol_path only
    reintroduces the exact silent-fallback failure mode this was added to
    fix (confirmatory_comparisons becomes {}, and the report falls back to
    whichever treatment condition sorts first).
    """

    protocol_location = resolve_bundle_path(
        manifest_dir,
        relative_path=manifest.get("protocol_relative_path"),
        absolute_path=manifest.get("protocol_path"),
    )
    if protocol_location is None or not protocol_location.exists():
        return {}
    try:
        protocol = _read_json(protocol_location)
    except (OSError, ValueError):
        return {}
    return protocol.get("confirmatory_comparisons", {}) or {}


def _negative_control_tasks_from_manifest(
    manifest: dict,
    manifest_dir: Path,
) -> dict[str, str]:
    """Map negative-control task_id -> control family, from the frozen
    protocol's embedded task list.

    The protocol (not seed_tasks.json) is the source so a relocated
    bundle stays self-contained and the mapping is the FROZEN one.
    Returns {} when no protocol is readable — the aggregate is then
    simply absent, never guessed.
    """

    protocol_location = resolve_bundle_path(
        manifest_dir,
        relative_path=manifest.get("protocol_relative_path"),
        absolute_path=manifest.get("protocol_path"),
    )
    if protocol_location is None or not protocol_location.exists():
        return {}
    try:
        protocol = _read_json(protocol_location)
    except (OSError, ValueError):
        return {}
    tasks = (
        protocol.get("datasets", {}).get("benchmark", {}).get("tasks", [])
    )
    return {
        task["task_id"]: str(
            task.get("negative_control_family") or "unspecified"
        )
        for task in tasks
        if task.get("matched_pair_role") == "negative_control"
    }


def negative_control_false_blocks(
    task_rows: list[dict],
    negative_control_families: dict[str, str],
) -> dict | None:
    """Supervisor false-block rate on the all-supported negative controls.

    Predeclared formula (research/HELDOUT_DESIGN_REVIEW.md, F3): raw
    verifier "block" decisions over finish proposals, computed on
    observe_only runs — every negative-control finish is supported by
    construction, so every raw block here is a false positive. The
    doc_clarification control contributes ~1 raw block per run BY DESIGN
    (the temporal requirement rule's measured cost) and is therefore
    also broken out per family.
    """

    from .statistics import wilson_interval

    if not negative_control_families:
        return None
    rows = [
        row
        for row in task_rows
        if row.get("task_id") in negative_control_families
        and row.get("treatment_condition") == "observe_only"
    ]
    if not rows:
        return None

    def _bucket(bucket_rows: list[dict]) -> dict:
        proposals = sum(
            row["verified_finish_proposals"] for row in bucket_rows
        )
        raw_blocks = sum(
            row["verified_raw_blocked_finish_proposals"]
            for row in bucket_rows
        )
        return {
            "runs": len(bucket_rows),
            "finish_proposals": proposals,
            "raw_blocked_proposals": raw_blocks,
            "false_block_rate": (
                round(raw_blocks / proposals, 4) if proposals else None
            ),
            "wilson_95ci": (
                wilson_interval(raw_blocks, proposals)
                if proposals
                else None
            ),
        }

    by_model: dict[str, list[dict]] = {}
    by_family: dict[str, list[dict]] = {}
    for row in rows:
        by_model.setdefault(str(row.get("model_name")), []).append(row)
        by_family.setdefault(
            negative_control_families[row["task_id"]], []
        ).append(row)
    return {
        "formula": (
            "raw verifier block decisions / finish proposals on "
            "observe_only negative-control runs (all supported by "
            "construction)"
        ),
        "overall": _bucket(rows),
        "per_model": {
            name: _bucket(model_rows)
            for name, model_rows in sorted(by_model.items())
        },
        "per_family": {
            family: _bucket(family_rows)
            for family, family_rows in sorted(by_family.items())
        },
    }


def analyze_model_matrix_manifest(manifest_path: Path) -> dict:
    """Build a paired comparison report from a model-matrix manifest."""

    manifest = _read_json(manifest_path)
    manifest_dir = manifest_path.parent
    pressure_profiles = _manifest_pressure_profiles(manifest)
    confirmatory_comparisons = _confirmatory_comparisons_from_manifest(
        manifest, manifest_dir
    )
    reference_variant, treatment_variants = reference_and_treatment_variants(
        manifest.get("variants") or ["baseline", "verified"]
    )
    task_ids = manifest.get("task_ids", [])
    seeds = manifest.get("seeds", [0])
    models = manifest.get("models", [])

    model_rows = []
    task_rows = []
    # comparison key -> {"task_rows": [...], "model_rows": [...]} — the
    # disjoint per-comparison partitions everything downstream (pairwise
    # statistics AND per-comparison descriptive aggregates) is built from.
    comparison_partitions: dict[str, dict[str, list[dict]]] = {}

    for model in models:
        for treatment_variant in treatment_variants:
            rows = _task_rows_for_model(
                model,
                manifest_dir,
                task_ids=task_ids,
                pressure_profiles=pressure_profiles,
                seeds=seeds,
                reference_variant=reference_variant,
                treatment_variant=treatment_variant,
            )
            task_rows.extend(rows)
            summary = _model_summary(
                model,
                rows,
                reference_variant=reference_variant,
                treatment_variant=treatment_variant,
            )
            model_rows.append(summary)
            partition = comparison_partitions.setdefault(
                comparison_key(reference_variant, treatment_variant),
                {"task_rows": [], "model_rows": []},
            )
            partition["task_rows"].extend(rows)
            partition["model_rows"].append(summary)

    for extra_reference, extra_treatment in extra_pairwise_comparisons(
        manifest.get("variants") or [reference_variant, *treatment_variants]
    ):
        extra_key = comparison_key(extra_reference, extra_treatment)
        if extra_key in comparison_partitions:
            # Already built as a reference-based comparison (e.g. a reduced
            # experiment where verification_only is itself the reference) —
            # extending would double-count every row.
            continue
        partition = comparison_partitions.setdefault(
            extra_key,
            {"task_rows": [], "model_rows": []},
        )
        for model in models:
            extra_rows = _task_rows_for_model(
                model,
                manifest_dir,
                task_ids=task_ids,
                pressure_profiles=pressure_profiles,
                seeds=seeds,
                reference_variant=extra_reference,
                treatment_variant=extra_treatment,
            )
            partition["task_rows"].extend(extra_rows)
            partition["model_rows"].append(
                _model_summary(
                    model,
                    extra_rows,
                    reference_variant=extra_reference,
                    treatment_variant=extra_treatment,
                )
            )

    successful_rows = [
        row for row in model_rows if row["status"] == "succeeded"
    ]

    # Every entry is its own independent paired sample — computed from a
    # disjoint set of rows, never pooled together. Pooling the same
    # reference/baseline observation across multiple treatment comparisons
    # (as if each were an independent pair) would violate McNemar's
    # independence assumption and artificially inflate the effective
    # sample size.
    pairwise_statistics = {
        key: build_paired_statistics(partition["task_rows"])
        for key, partition in comparison_partitions.items()
    }

    # Descriptive summaries suffer the same duplication as pooled
    # inference did: the blended task_rows list repeats every reference
    # run once per treatment comparison, so blended counts overstate
    # distinct trials by the number of treatment arms. The per-comparison
    # variants below are the ones paper tables must use; the blended
    # versions are retained only as quick cross-condition exploration
    # aids and carry an explicit flag saying so.
    aggregate_by_comparison = {
        key: _aggregate_summary(
            [
                row
                for row in partition["model_rows"]
                if row["status"] == "succeeded"
            ],
            partition["task_rows"],
        )
        for key, partition in comparison_partitions.items()
    }
    pressure_analysis_by_comparison = {
        key: _pressure_analysis(partition["task_rows"])
        for key, partition in comparison_partitions.items()
    }
    dose_response_by_comparison = {
        key: dose_response_curves(partition["task_rows"])
        for key, partition in comparison_partitions.items()
    }
    blended_aggregate = _aggregate_summary(successful_rows, task_rows)
    blended_aggregate["blended_across_comparisons"] = len(
        treatment_variants
    ) > 1
    blended_pressure = _pressure_analysis(task_rows)
    blended_pressure["blended_across_comparisons"] = len(
        treatment_variants
    ) > 1
    blended_dose_response = dose_response_curves(task_rows)
    blended_dose_response["blended_across_comparisons"] = len(
        treatment_variants
    ) > 1

    # A single confirmatory primary_endpoint statistic only exists when
    # there is exactly one treatment condition to compare against the
    # reference — the legacy two-arm case. A multi-arm intervention
    # manifest has no single valid pooled statistic; use
    # pairwise_statistics for a specific, independent comparison instead
    # (e.g. f"{reference_condition}__vs__verification_only").
    paired_statistics = (
        pairwise_statistics[
            comparison_key(reference_variant, treatment_variants[0])
        ]
        if len(treatment_variants) == 1
        else None
    )

    distinct_model_names = {model["model_name"] for model in models}
    successful_model_names = {row["model_name"] for row in successful_rows}
    return {
        "schema_version": "agent-memory-model-matrix-analysis/v0.4",
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
        "pressure_profiles": pressure_profiles,
        "task_state_probes": manifest.get("task_state_probes", False),
        "seeds": seeds,
        "reference_condition": reference_variant,
        "treatment_conditions": treatment_variants,
        "confirmatory_comparisons": confirmatory_comparisons,
        # Distinct models evaluated — NOT len(models); a multi-arm
        # manifest produces one model-summary row per (model, treatment).
        "model_count": len(distinct_model_names),
        "successful_model_count": len(successful_model_names),
        "model_treatment_summary_count": len(model_rows),
        "task_count": len(set(row["task_id"] for row in task_rows)),
        "planned_pair_count": len(task_rows),
        "eligible_pair_count": sum(
            1 for row in task_rows if row["pair_eligible"]
        ),
        "models": model_rows,
        "tasks": task_rows,
        # Blended descriptive summaries repeat each reference run once per
        # treatment comparison (flagged via blended_across_comparisons).
        # Paper tables must use the *_by_comparison variants instead.
        "aggregate": blended_aggregate,
        "aggregate_by_comparison": aggregate_by_comparison,
        # None for multi-arm manifests — see pairwise_statistics. Only
        # populated for a legacy two-arm (single-treatment) manifest,
        # where it is identical to the one entry in pairwise_statistics.
        "paired_statistics": paired_statistics,
        "pairwise_statistics": pairwise_statistics,
        # Supervisor false-block rate on the all-supported negative
        # controls (predeclared formula; None when the manifest ran no
        # observe_only negative-control runs).
        "negative_control_false_blocks": negative_control_false_blocks(
            task_rows,
            _negative_control_tasks_from_manifest(manifest, manifest_dir),
        ),
        "execution_accounting": _execution_accounting(
            manifest,
            task_rows,
        ),
        "pressure_analysis": blended_pressure,
        "pressure_analysis_by_comparison": pressure_analysis_by_comparison,
        "dose_response": blended_dose_response,
        "dose_response_by_comparison": dose_response_by_comparison,
        "limitations": manifest.get("limitations", []),
    }


def dose_response_curves(task_rows: list[dict]) -> dict:
    """Aggregate accuracy and failure dose-response data by severity.

    Groups paired task rows by pressure severity ordinal and reports
    per-action-index mean probe accuracy, accepted-false-finish rates,
    and the distribution of first-corrupted-belief sequence numbers.
    """

    groups: dict[int, list[dict]] = defaultdict(list)
    for row in task_rows:
        ordinal = int(row.get("pressure_severity_ordinal") or 0)
        groups[ordinal].append(row)

    severities = []
    for ordinal in sorted(groups):
        rows = groups[ordinal]
        row_count = len(rows)
        accuracy_by_action: dict[int, list[float]] = defaultdict(list)
        for row in rows:
            for point in row.get("baseline_probe_trajectory") or []:
                action = int(point.get("action_count") or 0)
                accuracy_by_action[action].append(
                    float(point.get("overall_accuracy") or 0.0)
                )
        first_corrupted = sorted(
            row["baseline_first_stale_claim_sequence"]
            for row in rows
            if row.get("baseline_first_stale_claim_sequence") is not None
        )
        severities.append(
            {
                "pressure_severity_ordinal": ordinal,
                "pressure_severity": rows[0].get(
                    "pressure_severity",
                    "unspecified",
                ),
                "row_count": row_count,
                "baseline_accepted_false_finish_rate": round(
                    sum(
                        1
                        for row in rows
                        if int(
                            row.get("baseline_accepted_false_finishes")
                            or 0
                        )
                        > 0
                    )
                    / row_count,
                    4,
                ),
                "verified_accepted_false_finish_rate": round(
                    sum(
                        1
                        for row in rows
                        if int(
                            row.get("verified_accepted_false_finishes")
                            or 0
                        )
                        > 0
                    )
                    / row_count,
                    4,
                ),
                "verified_contained_recovery_rate": round(
                    sum(
                        1
                        for row in rows
                        if row.get("verified_contained_recovery")
                    )
                    / row_count,
                    4,
                ),
                "mean_probe_accuracy_by_action": [
                    {
                        "action_count": action,
                        "mean_overall_accuracy": round(
                            mean(values),
                            4,
                        ),
                        "sample_count": len(values),
                    }
                    for action, values in sorted(
                        accuracy_by_action.items()
                    )
                ],
                "first_corrupted_belief_sequences": first_corrupted,
            }
        )
    return {
        "schema_version": "agent-memory-dose-response/v0.1",
        "severities": severities,
    }


def _first_corrupted_claim_sequence(run: dict | None) -> int | None:
    """Sequence number of the earliest stale/contradicted/unsupported claim."""

    if not run:
        return None
    events_by_id = {
        event.get("event_id"): event
        for event in run.get("trace_events", [])
    }
    sequences = [
        events_by_id.get(claim.get("event_id"), {}).get("sequence_number")
        for claim in run.get("memory_claims", [])
        if claim.get("stale")
        or claim.get("support_status") in {"contradicted", "unsupported"}
    ]
    numeric = [
        sequence for sequence in sequences if isinstance(sequence, int)
    ]
    return min(numeric) if numeric else None


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

    reference_condition = report.get("reference_condition", "baseline")
    treatment_conditions = report.get("treatment_conditions", ["verified"])
    pairwise_statistics = report.get("pairwise_statistics", {})
    default_comparison = comparison_key(
        reference_condition, treatment_conditions[0]
    )
    if report.get("paired_statistics") is not None:
        # Legacy two-arm manifest: exactly one treatment, so this is a
        # single valid comparison, not a pooled/blended one.
        primary_comparison = default_comparison
        statistics = report["paired_statistics"]
    else:
        # Multi-arm manifest: there is no single valid pooled statistic
        # (see analyze_model_matrix_manifest). Use the frozen protocol's
        # predeclared primary comparison — never default to whichever
        # treatment condition happens to sort first, which previously
        # silently picked memory_baseline vs observe_only instead of the
        # intended memory_baseline vs verification_only.
        declared_primary = report.get("confirmatory_comparisons", {}).get(
            "primary"
        )
        primary_comparison = (
            declared_primary
            if declared_primary and declared_primary in pairwise_statistics
            else default_comparison
        )
        statistics = pairwise_statistics.get(primary_comparison, {})
    primary = statistics.get("binary_outcomes", {}).get(
        "accepted_unsupported_finish_trial"
    )
    if primary is None:
        lines = [
            "# Agent Memory Model Matrix Analysis",
            "",
            f"- Manifest: `{report['manifest_path']}`",
            "",
            "No paired statistics are available for this manifest.",
            "",
        ]
        return "\n".join(lines)
    lines = [
        "# Agent Memory Model Matrix Analysis",
        "",
        f"- Manifest: `{report['manifest_path']}`",
        f"- Protocol ID: `{report.get('protocol_id')}`",
        f"- Framework: `{report.get('framework')}`",
        f"- Runtime: `{report.get('runtime')}`",
        f"- Seeds: `{report.get('seeds')}`",
        f"- Memory conditions: `{report.get('memory_conditions')}`",
        "- Pressure profiles: "
        f"`{[profile['profile_id'] for profile in report.get('pressure_profiles', [])]}`",
        f"- Task-state probes: `{report.get('task_state_probes')}`",
        f"- Constrained actions: `{report.get('constrained_actions')}`",
        f"- Thinking mode: `{report.get('thinking')}`",
        f"- Fully successful models: `{report['successful_model_count']}`",
        f"- Planned pairs: `{report['planned_pair_count']}`",
        f"- Statistically eligible pairs: `{report['eligible_pair_count']}`",
        "",
        f"## Primary Endpoint (`{primary_comparison}`)",
        "",
        (
            f"- Reference condition (`{reference_condition}`) "
            f"accepted-unsupported-finish rate: `{_rate_text(primary['baseline'])}`"
        ),
        (
            f"- Treatment condition (`{primary_comparison.split('__vs__')[-1]}`) "
            f"accepted-unsupported-finish rate: `{_rate_text(primary['verified'])}`"
        ),
        (
            "- Treatment minus reference risk difference: "
            f"`{primary['risk_difference_verified_minus_baseline']}`"
        ),
        (
            "- Exact paired McNemar p-value: "
            f"`{primary['mcnemar']['p_value_two_sided_exact']}`"
        ),
        "",
        (
            "A zero observed treatment rate is not treated as proof of zero "
            "risk; the Wilson interval above reports the uncertainty "
            "implied by the sample size. This is one independent pairwise "
            "comparison, never pooled with any other treatment condition — "
            "see `pairwise_statistics` in the JSON report for the "
            f"remaining comparisons: `{sorted(pairwise_statistics)}`."
        ),
        "",
        "## Model Summary",
        "",
        "One row per model × treatment comparison; the Comparison column is "
        "what distinguishes otherwise-identical rows in a multi-arm run.",
        "",
        "| Model | Comparison | Status | Pairs | Eligible | Reference Accepted Unsupported | Blocked Unsupported | Repair Successes | Contained Recoveries | Recovered Tasks | Treatment Accepted Unsupported | Avg Extra Actions |",
        "|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for model in report["models"]:
        lines.append(
            "| `{model}` | `{comparison}` | `{status}` | {pairs} | {eligible} | {baseline_false} | {blocked_false} | {repair_successes} | {contained} | {recoveries} | {verified_false} | {actions:.2f} |".format(
                model=model["model_name"],
                comparison=_row_comparison(model),
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
                contained=model.get(
                    "verified_contained_recovery_count",
                    0,
                ),
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
            "| Model | Comparison | Task | Pressure Profile | Severity | Seed | Eligible | Reference Outcome | Treatment Outcome | Reference Memory Failure | Reference Accepted Unsupported | Blocked Unsupported | Repair Attempts | Contained Recovery | Recovery Level | Repair Recovery | Treatment Accepted Unsupported | Reference Structured Memory | Treatment Structured Memory | Extra Actions |",
            "|---|---|---|---|---|---:|---:|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
        ]
    )
    for row in report["tasks"]:
        lines.append(
            "| `{model}` | `{comparison}` | `{task}` | `{profile}` | `{severity}` | {seed} | {eligible} | `{baseline_outcome}` | `{verified_outcome}` | {memory_failure} | {baseline_false} | {blocked_false} | {repair_attempts} | {contained_recovery} | {recovery_level} | {repair_recovery} | {verified_false} | {baseline_structured} | {verified_structured} | {actions} |".format(
                model=row["model_name"],
                comparison=_row_comparison(row),
                task=row["task_id"],
                profile=row["pressure_profile_id"],
                severity=row["pressure_severity"],
                seed=row["seed"],
                eligible=row["pair_eligible"],
                baseline_outcome=row["baseline_task_outcome"],
                verified_outcome=row["verified_task_outcome"],
                memory_failure=row[
                    "baseline_memory_contributed_failure"
                ],
                baseline_false=row["baseline_accepted_false_finishes"],
                blocked_false=row["verified_blocked_false_finishes"],
                repair_attempts=row["verified_memory_repair_attempts"],
                contained_recovery=row.get(
                    "verified_contained_recovery",
                    False,
                ),
                recovery_level=row.get("verified_recovery_level", 0),
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

    lines.extend(
        ["", f"## Paired Statistical Outcomes (`{primary_comparison}`)", ""]
    )
    for name, result in statistics["binary_outcomes"].items():
        lines.append(
            f"- `{name}`: reference "
            f"`{_rate_text(result['baseline'])}`; treatment "
            f"`{_rate_text(result['verified'])}`; risk difference "
            f"`{result['risk_difference_verified_minus_baseline']}`; "
            f"exact McNemar p=`{result['mcnemar']['p_value_two_sided_exact']}`"
        )
    for name, result in statistics["continuous_outcomes"].items():
        lines.append(
            f"- `{name}` treatment-minus-reference mean: "
            f"`{result['mean_difference']}`; bootstrap 95% CI "
            f"`{result['ci95']}`"
        )

    other_comparisons = {
        key: value
        for key, value in sorted(pairwise_statistics.items())
        if key != primary_comparison
    }
    if other_comparisons:
        lines.extend(["", "## Other Pairwise Comparisons", ""])
        for key, stats in other_comparisons.items():
            outcome = stats.get("binary_outcomes", {}).get(
                "accepted_unsupported_finish_trial"
            )
            if outcome is None:
                lines.append(f"- `{key}`: no paired outcome available")
                continue
            lines.append(
                f"- `{key}`: reference "
                f"`{_rate_text(outcome['baseline'])}`; treatment "
                f"`{_rate_text(outcome['verified'])}`; risk difference "
                f"`{outcome['risk_difference_verified_minus_baseline']}`; "
                f"exact McNemar p="
                f"`{outcome['mcnemar']['p_value_two_sided_exact']}`"
            )

    false_blocks = report.get("negative_control_false_blocks")
    if false_blocks:
        lines.extend(
            ["", "## Negative-Control False Blocks (observe_only)", ""]
        )
        lines.append(f"Formula: {false_blocks['formula']}.")
        lines.append("")
        lines.append(
            "| Scope | Runs | Finish proposals | Raw blocks | "
            "False-block rate |"
        )
        lines.append("| --- | --- | --- | --- | --- |")

        def _false_block_row(label: str, bucket: dict) -> str:
            rate = bucket.get("false_block_rate")
            ci = (bucket.get("wilson_95ci") or {}).get("ci95") or [None, None]
            rate_text = (
                f"{rate} [{ci[0]}, {ci[1]}]" if rate is not None else "n/a"
            )
            return (
                f"| {label} | {bucket['runs']} | "
                f"{bucket['finish_proposals']} | "
                f"{bucket['raw_blocked_proposals']} | {rate_text} |"
            )

        lines.append(_false_block_row("overall", false_blocks["overall"]))
        for name, bucket in false_blocks["per_model"].items():
            lines.append(_false_block_row(f"model `{name}`", bucket))
        for family, bucket in false_blocks["per_family"].items():
            lines.append(_false_block_row(f"family `{family}`", bucket))
        lines.append("")
        lines.append(
            "The `irrelevant_requirement_clarification` family contributes "
            "~1 raw block per run BY DESIGN (the temporal requirement "
            "rule's measured cost); other families are expected near zero."
        )

    lines.extend(["", "## Exclusion Ledger", ""])
    if statistics["exclusion_ledger"]:
        lines.extend(
            "- `{model}` / `{task}` / `{profile}` (`{severity}`) / seed `{seed}`: {reason}".format(
                model=item["model_name"],
                task=item["task_id"],
                profile=item.get(
                    "pressure_profile_id",
                    item.get("memory_condition", "full_history"),
                ),
                severity=item.get("pressure_severity"),
                seed=item["seed"],
                reason=item["reason"],
            )
            for item in statistics["exclusion_ledger"]
        )
    else:
        lines.append("- No pairs excluded.")

    accounting = report["execution_accounting"]
    lines.extend(["", "## Intention-To-Run Accounting", ""])
    for key, value in accounting.items():
        if key not in {"schema_version", "note"}:
            lines.append(f"- `{key}`: `{value}`")
    lines.append(f"- Note: {accounting['note']}")

    pressure_analysis = report.get(
        "pressure_analysis_by_comparison", {}
    ).get(primary_comparison, report["pressure_analysis"])
    dose_response = report.get("dose_response_by_comparison", {}).get(
        primary_comparison, report.get("dose_response", {})
    )
    lines.extend(
        ["", f"## Pressure Dose Response (`{primary_comparison}`)", ""]
    )
    for item in pressure_analysis["dose_response"]:
        lines.append(
            "- Severity `{severity}`: planned `{planned}`, "
            "memory-contributed failures `{failures}` "
            "(rate `{rate}`), evaluator success rate `{success}`, "
            "mean probe accuracy `{probe}`.".format(
                severity=item["severity_ordinal"],
                planned=item["planned_baseline_run_count"],
                failures=item["memory_contributed_failure_count"],
                rate=item[
                    "memory_contributed_failure_rate_all_planned"
                ],
                success=item["evaluator_success_rate_all_planned"],
                probe=item["mean_probe_accuracy"],
            )
        )
    lines.append(
        "- Natural versus induced-associated counts: "
        f"`{pressure_analysis['natural_vs_induced_corruption_counts']}`"
    )
    for entry in dose_response.get("severities", []):
        lines.append(
            "- Severity `{ordinal}` (`{severity}`): "
            "baseline accepted-false rate `{baseline_rate}`, "
            "contained-recovery rate `{contained_rate}`, "
            "per-action accuracy points `{points}`, "
            "first corrupted-belief sequences `{sequences}`.".format(
                ordinal=entry["pressure_severity_ordinal"],
                severity=entry["pressure_severity"],
                baseline_rate=entry[
                    "baseline_accepted_false_finish_rate"
                ],
                contained_rate=entry[
                    "verified_contained_recovery_rate"
                ],
                points=len(entry["mean_probe_accuracy_by_action"]),
                sequences=entry["first_corrupted_belief_sequences"],
            )
        )

    aggregate_by_comparison = report.get("aggregate_by_comparison", {})
    if aggregate_by_comparison:
        # One subsection per independent comparison. The blended aggregate
        # (report["aggregate"]) repeats every reference run once per
        # treatment arm, so its counts overstate distinct trials in a
        # multi-arm run — it stays JSON-only, flagged
        # blended_across_comparisons, and is never rendered here.
        lines.extend(["", "## Aggregate (per comparison)", ""])
        for comparison in sorted(aggregate_by_comparison):
            lines.extend([f"### `{comparison}`", ""])
            for key, value in aggregate_by_comparison[comparison].items():
                lines.append(f"- `{key}`: `{value}`")
            lines.append("")
    else:
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
    pressure_profiles: list[dict],
    seeds: list[int],
    reference_variant: str = "baseline",
    treatment_variant: str = "verified",
) -> list[dict]:
    runs_by_pair: dict[
        tuple[str, str, int],
        dict[str, dict],
    ] = defaultdict(dict)
    for task_id in task_ids:
        for pressure_profile in pressure_profiles:
            for seed in seeds:
                runs_by_pair[
                    (
                        task_id,
                        pressure_profile["profile_id"],
                        int(seed),
                    )
                ]
    for run_info in model.get("runs", []):
        seed = int(run_info.get("seed", 0))
        pressure_profile_id = run_info.get(
            "pressure_profile_id",
            run_info.get("memory_condition", "full_history"),
        )
        runs_by_pair[(run_info["task_id"], pressure_profile_id, seed)][
            run_info["variant"]
        ] = run_info
    for error in model.get("errors", []):
        key = (
            error["task_id"],
            error.get(
                "pressure_profile_id",
                error.get("memory_condition", "full_history"),
            ),
            int(error.get("seed", 0)),
        )
        runs_by_pair[key].setdefault(
            f"{error.get('variant')}_error",
            error,
        )

    rows = []
    profiles_by_id = {
        profile["profile_id"]: profile for profile in pressure_profiles
    }
    for (task_id, pressure_profile_id, seed), pair in sorted(
        runs_by_pair.items()
    ):
        pressure_profile = profiles_by_id.get(
            pressure_profile_id,
            {
                "profile_id": pressure_profile_id,
                "condition": pressure_profile_id,
                "severity": "unspecified",
                "severity_ordinal": None,
                "activation_action_count": None,
                "visible_evidence_window": None,
                "induced_corruption": False,
            },
        )
        memory_condition = pressure_profile["condition"]
        baseline_info = pair.get(reference_variant)
        verified_info = pair.get(treatment_variant)
        baseline = _read_run_info(baseline_info, manifest_dir)
        verified = _read_run_info(verified_info, manifest_dir)
        baseline_attribution = (
            baseline.get("failure_attribution")
            or classify_run_failure(baseline)
            if baseline
            else {}
        )
        verified_attribution = (
            verified.get("failure_attribution")
            or classify_run_failure(verified)
            if verified
            else {}
        )
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
            reference_variant=reference_variant,
            treatment_variant=treatment_variant,
        )
        false_completion_claims = int(
            baseline_counts.get("false_completion", 0)
        )
        stale_claims = int(baseline_counts.get("stale", 0))
        rows.append(
            {
                "reference_condition": reference_variant,
                "treatment_condition": treatment_variant,
                "model_name": model["model_name"],
                "model_family": model.get("model_family"),
                "task_id": task_id,
                "memory_condition": memory_condition,
                "pressure_profile_id": pressure_profile_id,
                "pressure_severity": pressure_profile.get("severity"),
                "pressure_severity_ordinal": pressure_profile.get(
                    "severity_ordinal"
                ),
                "pressure_activation_action_count": pressure_profile.get(
                    "activation_action_count"
                ),
                "pressure_visible_evidence_window": pressure_profile.get(
                    "visible_evidence_window"
                ),
                "induced_corruption_condition": bool(
                    pressure_profile.get("induced_corruption")
                ),
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
                "baseline_accepted_unsupported_finish": bool(
                    baseline_interaction.get(
                        "accepted_unsupported_finish", False
                    )
                ),
                "baseline_accepted_incorrect_finish": bool(
                    baseline_interaction.get(
                        "accepted_incorrect_finish", False
                    )
                ),
                "baseline_supported_but_incorrect_finish": bool(
                    baseline_interaction.get(
                        "supported_but_incorrect_finish", False
                    )
                ),
                "baseline_unsupported_but_correct_finish": bool(
                    baseline_interaction.get(
                        "unsupported_but_correct_finish", False
                    )
                ),
                # Secondary, not-yet-confirmatory endpoint: independent of
                # the shared claim classifier, but not yet human-validated
                # (see support_oracle.py / oracle_confusion_matrix).
                "baseline_accepted_oracle_unsupported_finish": bool(
                    baseline_interaction.get(
                        "accepted_oracle_unsupported_finish", False
                    )
                ),
                "baseline_accepted_oracle_uncertain_finish": bool(
                    baseline_interaction.get(
                        "accepted_oracle_uncertain_finish", False
                    )
                ),
                "verified_false_finish_proposals": int(
                    verified_interaction.get("false_finish_proposals", 0)
                ),
                "verified_finish_proposals": int(
                    verified_interaction.get("finish_proposals", 0)
                ),
                "verified_raw_blocked_finish_proposals": int(
                    verified_interaction.get(
                        "raw_blocked_finish_proposals", 0
                    )
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
                "verified_accepted_unsupported_finish": bool(
                    verified_interaction.get(
                        "accepted_unsupported_finish", False
                    )
                ),
                "verified_accepted_incorrect_finish": bool(
                    verified_interaction.get(
                        "accepted_incorrect_finish", False
                    )
                ),
                "verified_supported_but_incorrect_finish": bool(
                    verified_interaction.get(
                        "supported_but_incorrect_finish", False
                    )
                ),
                "verified_unsupported_but_correct_finish": bool(
                    verified_interaction.get(
                        "unsupported_but_correct_finish", False
                    )
                ),
                "verified_accepted_oracle_unsupported_finish": bool(
                    verified_interaction.get(
                        "accepted_oracle_unsupported_finish", False
                    )
                ),
                "verified_accepted_oracle_uncertain_finish": bool(
                    verified_interaction.get(
                        "accepted_oracle_uncertain_finish", False
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
                "baseline_contained_recovery": bool(
                    baseline_interaction.get("contained_recovery", False)
                ),
                "verified_contained_recovery": bool(
                    verified_interaction.get("contained_recovery", False)
                ),
                "verified_recovery_level": int(
                    verified_interaction.get("recovery_level", 0)
                ),
                "baseline_probe_trajectory": baseline_probe.get(
                    "trajectory",
                    [],
                ),
                "baseline_first_stale_claim_sequence": (
                    _first_corrupted_claim_sequence(baseline)
                ),
                "verified_first_stale_claim_sequence": (
                    _first_corrupted_claim_sequence(verified)
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
                "baseline_failure_attribution": baseline_attribution,
                "verified_failure_attribution": verified_attribution,
                "baseline_memory_contributed_failure": bool(
                    baseline_attribution.get("memory_contributed")
                ),
                "verified_memory_contributed_failure": bool(
                    verified_attribution.get("memory_contributed")
                ),
                "baseline_corruption_origin": baseline_attribution.get(
                    "corruption_origin",
                    "not_observed",
                ),
                "verified_corruption_origin": verified_attribution.get(
                    "corruption_origin",
                    "not_observed",
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
                # None (not a forced float default) when the underlying rate
                # had an empty denominator — see metrics.py:_rate.
                "baseline_stale_decision_use_rate": baseline_headline.get(
                    "stale_decision_use_rate"
                ),
                "verified_stale_decision_use_rate": verified_headline.get(
                    "stale_decision_use_rate"
                ),
                "baseline_decision_belief_coverage": float(
                    baseline_headline.get(
                        "decision_belief_coverage",
                        0.0,
                    )
                ),
                "verified_decision_belief_coverage": float(
                    verified_headline.get(
                        "decision_belief_coverage",
                        0.0,
                    )
                ),
                "baseline_unsupported_tool_decision_use_rate": (
                    baseline_headline.get(
                        "unsupported_tool_decision_use_rate"
                    )
                ),
                "verified_unsupported_tool_decision_use_rate": (
                    verified_headline.get(
                        "unsupported_tool_decision_use_rate"
                    )
                ),
                "baseline_stale_tool_decision_use_rate": (
                    baseline_headline.get("stale_tool_decision_use_rate")
                ),
                "verified_stale_tool_decision_use_rate": (
                    verified_headline.get("stale_tool_decision_use_rate")
                ),
                "baseline_contradicted_tool_decision_use_rate": (
                    baseline_headline.get(
                        "contradicted_tool_decision_use_rate"
                    )
                ),
                "verified_contradicted_tool_decision_use_rate": (
                    verified_headline.get(
                        "contradicted_tool_decision_use_rate"
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
                "baseline_probe_failed_attempt_accuracy": (
                    baseline_probe.get("mean_failed_attempt_f1")
                ),
                "verified_probe_failed_attempt_accuracy": (
                    verified_probe.get("mean_failed_attempt_f1")
                ),
                "baseline_probe_blocked_attempt_accuracy": (
                    baseline_probe.get("mean_blocked_attempt_f1")
                ),
                "verified_probe_blocked_attempt_accuracy": (
                    verified_probe.get("mean_blocked_attempt_f1")
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
                "baseline_probe_uncertain_evidence_accuracy": (
                    baseline_probe.get("mean_uncertain_evidence_f1")
                ),
                "verified_probe_uncertain_evidence_accuracy": (
                    verified_probe.get("mean_uncertain_evidence_f1")
                ),
                "baseline_probe_curve_auc": (
                    baseline_probe.get("curve_statistics", {}).get(
                        "area_under_curve"
                    )
                ),
                "verified_probe_curve_auc": (
                    verified_probe.get("curve_statistics", {}).get(
                        "area_under_curve"
                    )
                ),
                "baseline_probe_first_degradation_action": (
                    baseline_probe.get("curve_statistics", {}).get(
                        "first_degradation_action"
                    )
                ),
                "verified_probe_first_degradation_action": (
                    verified_probe.get("curve_statistics", {}).get(
                        "first_degradation_action"
                    )
                ),
                "baseline_first_memory_signal_sequence": (
                    baseline_attribution.get(
                        "first_memory_signal_sequence"
                    )
                ),
                "verified_first_memory_signal_sequence": (
                    verified_attribution.get(
                        "first_memory_signal_sequence"
                    )
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
                    baseline_probe.get(
                        "mean_next_action_appropriateness",
                        baseline_probe.get("mean_next_action_accuracy"),
                    )
                ),
                "verified_probe_next_action_accuracy": (
                    verified_probe.get(
                        "mean_next_action_appropriateness",
                        verified_probe.get("mean_next_action_accuracy"),
                    )
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
                # None (not a forced float default) when the underlying run had
                # no parseable claims/text to score — an unparsed model response
                # must not be counted as a perfectly healthy/zero-drift one.
                "memory_health_score": metrics.get("memory_health_score"),
                "semantic_drift_score": exploratory.get("semantic_drift_score"),
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
                    str(_resolve_artifact_path(baseline_info, manifest_dir))
                    if baseline_info
                    else None
                ),
                "verified_run_path": (
                    str(_resolve_artifact_path(verified_info, manifest_dir))
                    if verified_info
                    else None
                ),
            }
        )
    return rows


def _model_summary(
    model: dict,
    rows: list[dict],
    *,
    reference_variant: str = "baseline",
    treatment_variant: str = "verified",
) -> dict:
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
        "reference_condition": reference_variant,
        "treatment_condition": treatment_variant,
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
        "verified_contained_recovery_count": sum(
            1 for row in rows if row.get("verified_contained_recovery")
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
            row["memory_health_score"]
            for row in rows
            if row["memory_health_score"] is not None
        ),
        "memory_health_score_excluded_count": sum(
            1 for row in rows if row["memory_health_score"] is None
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
        "avg_baseline_decision_belief_coverage": _mean(
            row["baseline_decision_belief_coverage"] for row in rows
        ),
        "avg_verified_decision_belief_coverage": _mean(
            row["verified_decision_belief_coverage"] for row in rows
        ),
        "avg_baseline_unsupported_tool_decision_use_rate": _mean(
            row["baseline_unsupported_tool_decision_use_rate"]
            for row in rows
            if row["baseline_unsupported_tool_decision_use_rate"] is not None
        ),
        "avg_verified_unsupported_tool_decision_use_rate": _mean(
            row["verified_unsupported_tool_decision_use_rate"]
            for row in rows
            if row["verified_unsupported_tool_decision_use_rate"] is not None
        ),
        "avg_baseline_stale_tool_decision_use_rate": _mean(
            row["baseline_stale_tool_decision_use_rate"]
            for row in rows
            if row["baseline_stale_tool_decision_use_rate"] is not None
        ),
        "avg_verified_stale_tool_decision_use_rate": _mean(
            row["verified_stale_tool_decision_use_rate"]
            for row in rows
            if row["verified_stale_tool_decision_use_rate"] is not None
        ),
        "avg_baseline_contradicted_tool_decision_use_rate": _mean(
            row["baseline_contradicted_tool_decision_use_rate"]
            for row in rows
            if row["baseline_contradicted_tool_decision_use_rate"] is not None
        ),
        "avg_verified_contradicted_tool_decision_use_rate": _mean(
            row["verified_contradicted_tool_decision_use_rate"]
            for row in rows
            if row["verified_contradicted_tool_decision_use_rate"] is not None
        ),
        "avg_semantic_drift_score": _mean(
            row["semantic_drift_score"]
            for row in rows
            if row["semantic_drift_score"] is not None
        ),
        "semantic_drift_score_excluded_count": sum(
            1 for row in rows if row["semantic_drift_score"] is None
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
        "verified_contained_recovery_rows": sum(
            1
            for row in task_rows
            if row.get("verified_contained_recovery")
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
            row["memory_health_score"]
            for row in task_rows
            if row["memory_health_score"] is not None
        ),
        "memory_health_score_excluded_count": sum(
            1 for row in task_rows if row["memory_health_score"] is None
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
        "avg_baseline_decision_belief_coverage": _mean(
            row["baseline_decision_belief_coverage"]
            for row in task_rows
        ),
        "avg_verified_decision_belief_coverage": _mean(
            row["verified_decision_belief_coverage"]
            for row in task_rows
        ),
        "avg_baseline_unsupported_tool_decision_use_rate": _mean(
            row["baseline_unsupported_tool_decision_use_rate"]
            for row in task_rows
            if row["baseline_unsupported_tool_decision_use_rate"] is not None
        ),
        "avg_verified_unsupported_tool_decision_use_rate": _mean(
            row["verified_unsupported_tool_decision_use_rate"]
            for row in task_rows
            if row["verified_unsupported_tool_decision_use_rate"] is not None
        ),
        "avg_baseline_stale_tool_decision_use_rate": _mean(
            row["baseline_stale_tool_decision_use_rate"]
            for row in task_rows
            if row["baseline_stale_tool_decision_use_rate"] is not None
        ),
        "avg_verified_stale_tool_decision_use_rate": _mean(
            row["verified_stale_tool_decision_use_rate"]
            for row in task_rows
            if row["verified_stale_tool_decision_use_rate"] is not None
        ),
        "avg_baseline_contradicted_tool_decision_use_rate": _mean(
            row["baseline_contradicted_tool_decision_use_rate"]
            for row in task_rows
            if row["baseline_contradicted_tool_decision_use_rate"] is not None
        ),
        "avg_verified_contradicted_tool_decision_use_rate": _mean(
            row["verified_contradicted_tool_decision_use_rate"]
            for row in task_rows
            if row["verified_contradicted_tool_decision_use_rate"] is not None
        ),
        "avg_semantic_drift_score": _mean(
            row["semantic_drift_score"]
            for row in task_rows
            if row["semantic_drift_score"] is not None
        ),
        "semantic_drift_score_excluded_count": sum(
            1 for row in task_rows if row["semantic_drift_score"] is None
        ),
        "blocked_actions_by_model": dict(sorted(blocked_by_model.items())),
    }


def _manifest_pressure_profiles(manifest: dict) -> list[dict]:
    profiles = manifest.get("pressure_profiles")
    if profiles:
        return profiles
    return [
        {
            "profile_id": condition,
            "condition": condition,
            "severity": (
                "control" if condition == "full_history" else "ad_hoc"
            ),
            "severity_ordinal": (
                0 if condition == "full_history" else None
            ),
            "activation_action_count": manifest.get(
                "memory_pressure_start"
            ),
            "visible_evidence_window": manifest.get("memory_window"),
            "induced_corruption": condition != "full_history",
        }
        for condition in manifest.get(
            "memory_conditions",
            ["full_history"],
        )
    ]


def _execution_accounting(manifest: dict, rows: list[dict]) -> dict:
    planned = int(manifest.get("planned_run_count", 0))
    completed = int(manifest.get("completed_run_count", 0))
    failed = int(manifest.get("failed_run_count", 0))
    skipped = int(manifest.get("skipped_run_count", 0))
    unaccounted = max(0, planned - completed - failed - skipped)
    outcome_counts: Counter[str] = Counter()
    for row in rows:
        for prefix in ("baseline", "verified"):
            attribution = row.get(f"{prefix}_failure_attribution", {})
            if attribution:
                outcome_counts[
                    attribution.get("outcome_class", "unknown")
                ] += 1
    return {
        "schema_version": "agent-execution-accounting/v0.1",
        "intention_to_run_denominator": planned,
        "completed_artifact_count": completed,
        "runtime_failure_count": failed,
        "skipped_run_count": skipped,
        "unaccounted_run_count": unaccounted,
        "completed_artifact_rate": _planned_rate(completed, planned),
        "runtime_failure_rate": _planned_rate(failed, planned),
        "skipped_run_rate": _planned_rate(skipped, planned),
        "all_planned_runs_accounted_for": unaccounted == 0,
        "observed_outcome_class_counts": dict(
            sorted(outcome_counts.items())
        ),
        "complete_case_inferential_pair_count": sum(
            1 for row in rows if row.get("pair_eligible")
        ),
        "planned_pair_slot_count": len(rows),
        "note": (
            "Runtime failures, skipped runs, and missing artifacts remain in "
            "the intention-to-run denominator. Paired inferential statistics "
            "use complete artifacts and report their separate exclusion ledger."
        ),
    }


def _pressure_analysis(rows: list[dict]) -> dict:
    by_profile: dict[str, list[dict]] = defaultdict(list)
    for row in rows:
        by_profile[row["pressure_profile_id"]].append(row)

    profile_summaries = []
    for profile_id, profile_rows in sorted(
        by_profile.items(),
        key=lambda item: (
            item[1][0].get("pressure_severity_ordinal")
            if item[1][0].get("pressure_severity_ordinal") is not None
            else 999,
            item[0],
        ),
    ):
        observed = [row for row in profile_rows if row.get("run_path")]
        memory_failures = sum(
            row["baseline_memory_contributed_failure"]
            for row in observed
        )
        evaluator_successes = sum(
            row["baseline_evaluator_success"] is True
            for row in observed
        )
        origin_counts = Counter(
            row["baseline_corruption_origin"] for row in observed
        )
        profile_summaries.append(
            {
                "pressure_profile_id": profile_id,
                "memory_condition": profile_rows[0][
                    "memory_condition"
                ],
                "severity": profile_rows[0]["pressure_severity"],
                "severity_ordinal": profile_rows[0][
                    "pressure_severity_ordinal"
                ],
                "activation_action_count": profile_rows[0][
                    "pressure_activation_action_count"
                ],
                "visible_evidence_window": profile_rows[0][
                    "pressure_visible_evidence_window"
                ],
                "induced_corruption_condition": profile_rows[0][
                    "induced_corruption_condition"
                ],
                "planned_baseline_run_count": len(profile_rows),
                "observed_baseline_run_count": len(observed),
                "missing_baseline_run_count": (
                    len(profile_rows) - len(observed)
                ),
                "memory_contributed_failure_count": memory_failures,
                "memory_contributed_failure_rate_all_planned": (
                    _planned_rate(memory_failures, len(profile_rows))
                ),
                "memory_contributed_failure_rate_observed": (
                    _planned_rate(memory_failures, len(observed))
                ),
                "evaluator_success_count": evaluator_successes,
                "evaluator_success_rate_all_planned": _planned_rate(
                    evaluator_successes,
                    len(profile_rows),
                ),
                "corruption_origin_counts": dict(
                    sorted(origin_counts.items())
                ),
                "mean_probe_accuracy": _mean(
                    row["baseline_probe_overall_accuracy"]
                    for row in observed
                    if row["baseline_probe_overall_accuracy"] is not None
                ),
                "mean_first_degradation_action": _mean(
                    row["baseline_probe_first_degradation_action"]
                    for row in observed
                    if row[
                        "baseline_probe_first_degradation_action"
                    ]
                    is not None
                ),
                "mean_first_memory_signal_sequence": _mean(
                    row["baseline_first_memory_signal_sequence"]
                    for row in observed
                    if row["baseline_first_memory_signal_sequence"]
                    is not None
                ),
                "mean_trajectory_actions": _mean(
                    row["baseline_model_action_count"]
                    for row in observed
                ),
            }
        )

    matched_effects = _matched_pressure_effects(rows)
    severity_groups: dict[int, list[dict]] = defaultdict(list)
    for summary in profile_summaries:
        ordinal = summary.get("severity_ordinal")
        if ordinal is not None:
            severity_groups[int(ordinal)].append(summary)
    dose_response = []
    for ordinal, summaries in sorted(severity_groups.items()):
        planned = sum(
            summary["planned_baseline_run_count"]
            for summary in summaries
        )
        memory_failures = sum(
            summary["memory_contributed_failure_count"]
            for summary in summaries
        )
        evaluator_successes = sum(
            summary["evaluator_success_count"]
            for summary in summaries
        )
        dose_response.append(
            {
                "severity_ordinal": ordinal,
                "severity_labels": sorted(
                    {
                        str(summary["severity"])
                        for summary in summaries
                    }
                ),
                "planned_baseline_run_count": planned,
                "memory_contributed_failure_count": memory_failures,
                "memory_contributed_failure_rate_all_planned": (
                    _planned_rate(memory_failures, planned)
                ),
                "evaluator_success_rate_all_planned": _planned_rate(
                    evaluator_successes,
                    planned,
                ),
                "mean_probe_accuracy": _mean(
                    summary["mean_probe_accuracy"]
                    for summary in summaries
                ),
                "mean_first_degradation_action": _mean(
                    summary["mean_first_degradation_action"]
                    for summary in summaries
                    if summary["mean_first_degradation_action"] != 0.0
                ),
                "mean_trajectory_actions": _mean(
                    summary["mean_trajectory_actions"]
                    for summary in summaries
                ),
            }
        )

    origin_counts = Counter(
        row["baseline_corruption_origin"]
        for row in rows
        if row.get("run_path")
    )
    return {
        "schema_version": "agent-memory-pressure-analysis/v0.1",
        "profile_summaries": profile_summaries,
        "matched_control_effects": matched_effects,
        "dose_response": dose_response,
        "natural_vs_induced_corruption_counts": dict(
            sorted(origin_counts.items())
        ),
        "causal_guardrail": (
            "Induced-associated means the first strict memory signal occurred "
            "after an active pressure transformation. Causal attribution "
            "requires a matched control regression and is still limited to "
            "the declared model-task-seed tuple."
        ),
    }


def _matched_pressure_effects(rows: list[dict]) -> list[dict]:
    controls = {
        (row["model_name"], row["task_id"], row["seed"]): row
        for row in rows
        if row.get("pressure_severity_ordinal") == 0
        and row.get("run_path")
    }
    effects = []
    for row in rows:
        if (
            row.get("pressure_severity_ordinal") in {None, 0}
            or not row.get("run_path")
        ):
            continue
        key = (row["model_name"], row["task_id"], row["seed"])
        control = controls.get(key)
        if not control:
            continue
        control_probe = control.get("baseline_probe_overall_accuracy")
        pressure_probe = row.get("baseline_probe_overall_accuracy")
        effects.append(
            {
                "model_name": row["model_name"],
                "task_id": row["task_id"],
                "seed": row["seed"],
                "control_profile_id": control["pressure_profile_id"],
                "pressure_profile_id": row["pressure_profile_id"],
                "severity": row["pressure_severity"],
                "severity_ordinal": row[
                    "pressure_severity_ordinal"
                ],
                "control_evaluator_success": control[
                    "baseline_evaluator_success"
                ],
                "pressure_evaluator_success": row[
                    "baseline_evaluator_success"
                ],
                "evaluator_regression": bool(
                    control["baseline_evaluator_success"] is True
                    and row["baseline_evaluator_success"] is False
                ),
                "new_memory_contributed_failure": bool(
                    not control[
                        "baseline_memory_contributed_failure"
                    ]
                    and row["baseline_memory_contributed_failure"]
                ),
                "control_memory_contributed_failure": control[
                    "baseline_memory_contributed_failure"
                ],
                "pressure_memory_contributed_failure": row[
                    "baseline_memory_contributed_failure"
                ],
                "probe_accuracy_delta_pressure_minus_control": (
                    round(float(pressure_probe) - float(control_probe), 4)
                    if pressure_probe is not None
                    and control_probe is not None
                    else None
                ),
            }
        )
    return effects


def _planned_rate(count: int, total: int) -> float | None:
    return round(count / total, 4) if total else None


def _pair_exclusion_reason(
    *,
    pair_complete: bool,
    baseline_info: dict | None,
    verified_info: dict | None,
    baseline_metadata: dict,
    verified_metadata: dict,
    pair: dict,
    reference_variant: str = "baseline",
    treatment_variant: str = "verified",
) -> str | None:
    if not pair_complete:
        missing = []
        if not baseline_info:
            missing.append(reference_variant)
        if not verified_info:
            missing.append(treatment_variant)
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
    path = _resolve_artifact_path(run_info, manifest_dir)
    if not path.exists():
        return {}
    return _read_json(path)


def _resolve_artifact_path(run_info: dict, manifest_dir: Path) -> Path:
    # relative_path (from indexed_artifact) is authoritative inside a
    # relocated/copied bundle; the absolute "path" only works on the
    # machine that generated it.
    resolved = resolve_bundle_path(
        manifest_dir,
        relative_path=run_info.get("relative_path"),
        absolute_path=run_info.get("path"),
    )
    return resolved if resolved is not None else Path(run_info.get("path", ""))


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


def _row_comparison(row: dict) -> str:
    """Comparison label for a model-summary or task row.

    This column is what keeps otherwise-identical rows distinguishable in
    a multi-arm run — without it, three treatment conditions for the same
    model/task/seed render as three visually identical table rows.
    """

    return comparison_key(
        row.get("reference_condition", "baseline"),
        row.get("treatment_condition", "verified"),
    )


def _mean(values) -> float:
    items = list(values)
    return round(mean(items), 4) if items else 0.0


def _read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))
