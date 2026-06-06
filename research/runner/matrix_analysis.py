"""Analysis helpers for real-runtime model matrix artifacts."""

from __future__ import annotations

import json
from collections import Counter, defaultdict
from pathlib import Path
from statistics import mean
from typing import Any


def analyze_model_matrix_manifest(manifest_path: Path) -> dict:
    """Build a compact comparison report from a model-matrix manifest."""

    manifest = _read_json(manifest_path)
    manifest_dir = manifest_path.parent
    model_rows = []
    task_rows = []

    for model in manifest.get("models", []):
        rows = _task_rows_for_model(model, manifest_dir)
        task_rows.extend(rows)
        model_rows.append(_model_summary(model, rows))

    successful_rows = [row for row in model_rows if row["status"] == "succeeded"]
    report = {
        "schema_version": "agent-memory-model-matrix-analysis/v0.1",
        "manifest_path": str(manifest_path.resolve()),
        "framework": manifest.get("framework", "react_custom"),
        "runtime": manifest.get("runtime"),
        "runtime_endpoint": manifest.get("runtime_endpoint"),
        "trace_mode": manifest.get("trace_mode"),
        "prompt_template": manifest.get("prompt_template"),
        "model_count": len(model_rows),
        "successful_model_count": len(successful_rows),
        "task_count": len(set(row["task_id"] for row in task_rows)),
        "models": model_rows,
        "tasks": task_rows,
        "aggregate": _aggregate_summary(successful_rows, task_rows),
        "limitations": manifest.get("limitations", []),
    }
    return report


def write_model_matrix_analysis(
    manifest_path: Path,
    output_path: Path,
    output_format: str,
) -> dict:
    """Write a matrix analysis report and return the report payload."""

    report = analyze_model_matrix_manifest(manifest_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    if output_format == "markdown" or output_path.suffix == ".md":
        output_path.write_text(format_model_matrix_analysis_markdown(report), encoding="utf-8")
    else:
        output_path.write_text(
            json.dumps(report, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    return report


def format_model_matrix_analysis_markdown(report: dict) -> str:
    """Format a model-matrix analysis report as Markdown."""

    lines = [
        "# Agent Memory Model Matrix Analysis",
        "",
        f"- Manifest: `{report['manifest_path']}`",
        f"- Framework: `{report.get('framework')}`",
        f"- Runtime: `{report.get('runtime')}`",
        f"- Trace mode: `{report.get('trace_mode')}`",
        f"- Prompt template: `{report.get('prompt_template')}`",
        f"- Successful models: `{report['successful_model_count']}`",
        f"- Tasks: `{report['task_count']}`",
        "",
        "## Model Summary",
        "",
        "| Model | Status | Tasks | Parse Statuses | Claims | High-Risk | Blocked | Avg Health | Avg Drift |",
        "|---|---:|---:|---|---:|---:|---:|---:|---:|",
    ]
    for model in report["models"]:
        lines.append(
            "| `{model}` | `{status}` | {tasks} | {parse} | {claims} | {risk} | {blocked} | {health:.4f} | {drift:.4f} |".format(
                model=model["model_name"],
                status=model["status"],
                tasks=model["baseline_task_count"],
                parse=_format_counter(model["parse_status_counts"]),
                claims=model["parsed_claim_count"],
                risk=model["high_risk_label_count"],
                blocked=model["blocked_action_count"],
                health=model["avg_memory_health_score"],
                drift=model["avg_semantic_drift_score"],
            )
        )

    lines.extend(
        [
            "",
            "## Coding-Agent Intervention Matrix",
            "",
            "| Model | Baseline Eval Pass | Verified Eval Pass | Baseline Accepted False | Verified Proposed False | Blocked False | Verified Accepted False | Recoveries | Avg Extra Actions |",
            "|---|---:|---:|---:|---:|---:|---:|---:|---:|",
        ]
    )
    for model in report["models"]:
        lines.append(
            "| `{model}` | {baseline_eval} | {verified_eval} | {baseline_false} | {verified_proposed} | {blocked_false} | {verified_false} | {recoveries} | {actions:.2f} |".format(
                model=model["model_name"],
                baseline_eval=model["baseline_evaluator_success_count"],
                verified_eval=model["verified_evaluator_success_count"],
                baseline_false=model["baseline_accepted_false_finish_count"],
                verified_proposed=model["verified_false_finish_proposal_count"],
                blocked_false=model["verified_blocked_false_finish_count"],
                verified_false=model["verified_accepted_false_finish_count"],
                recoveries=model["verified_recovery_count"],
                actions=model["avg_extra_model_actions"],
            )
        )

    lines.extend(
        [
            "",
            "## Task Rows",
            "",
            "| Model | Task | Baseline Eval | Verified Eval | Baseline Proposed False | Baseline Accepted False | Verified Proposed False | Blocked False | Verified Accepted False | Recovered | Extra Actions |",
            "|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
        ]
    )
    for row in report["tasks"]:
        lines.append(
            "| `{model}` | `{task}` | {baseline_eval} | {verified_eval} | {baseline_proposed} | {baseline_accepted} | {verified_proposed} | {blocked_false} | {verified_accepted} | {recovered} | {extra_actions} |".format(
                model=row["model_name"],
                task=row["task_id"],
                baseline_eval=row["baseline_evaluator_success"],
                verified_eval=row["verified_evaluator_success"],
                baseline_proposed=row["baseline_false_finish_proposals"],
                baseline_accepted=row["baseline_accepted_false_finishes"],
                verified_proposed=row["verified_false_finish_proposals"],
                blocked_false=row["verified_blocked_false_finishes"],
                verified_accepted=row["verified_accepted_false_finishes"],
                recovered=row["verified_recovery_after_block"],
                extra_actions=row["extra_model_actions"],
            )
        )

    lines.extend(["", "## Aggregate", ""])
    for key, value in report["aggregate"].items():
        lines.append(f"- `{key}`: `{value}`")

    if report.get("limitations"):
        lines.extend(["", "## Limitations", ""])
        lines.extend(f"- {item}" for item in report["limitations"])

    lines.append("")
    return "\n".join(lines)


def _task_rows_for_model(model: dict, manifest_dir: Path) -> list[dict]:
    verified_by_task = {}
    for run_info in model.get("runs", []):
        if run_info.get("variant") != "verified":
            continue
        verified = _read_json(_resolve_artifact_path(run_info["path"], manifest_dir))
        verified_by_task[run_info["task_id"]] = verified

    rows = []
    for run_info in model.get("runs", []):
        if run_info.get("variant") != "baseline":
            continue
        run = _read_json(_resolve_artifact_path(run_info["path"], manifest_dir))
        metadata = run.get("run_metadata", {})
        health = run.get("memory_health_report", {})
        metrics = health.get("metrics", {})
        verified = verified_by_task.get(run_info["task_id"], {})
        verification_report = verified.get("verification_report", {})
        baseline_counts = health.get("claim_counts", {})
        verified_metadata = verified.get("run_metadata", {})
        baseline_interaction = run.get("interaction_metrics", {})
        verified_interaction = verified.get("interaction_metrics", {})
        baseline_tool_iterations = int(metadata.get("tool_loop_iterations") or 0)
        verified_tool_iterations = int(
            verified_metadata.get("tool_loop_iterations") or baseline_tool_iterations
        )
        final_test_status = _final_test_status(run)
        verified_final_test_status = _final_test_status(verified) if verified else {}
        false_completion_claims = int(baseline_counts.get("false_completion", 0))
        stale_claims = int(baseline_counts.get("stale", 0))
        rows.append(
            {
                "model_name": model["model_name"],
                "model_family": model.get("model_family"),
                "task_id": run_info["task_id"],
                "parse_status": metadata.get("model_trace_parse_status") or "unknown",
                "parsed_claim_count": int(metadata.get("model_trace_claim_count") or 0),
                "high_risk_label_count": len(run.get("high_risk_labels", [])),
                "blocked_action_count": len(verification_report.get("blocked_actions", [])),
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
                "tool_loop_iterations": baseline_tool_iterations,
                "verified_tool_loop_iterations": verified_tool_iterations,
                "baseline_evaluator_success": (
                    final_test_status.get("status") == "success"
                ),
                "baseline_evaluator_returncode": final_test_status.get("returncode"),
                "verified_evaluator_success": (
                    verified_final_test_status.get("status") == "success"
                    if verified
                    else None
                ),
                "verified_evaluator_returncode": verified_final_test_status.get(
                    "returncode"
                ),
                "extra_model_actions": (
                    verified_tool_iterations - baseline_tool_iterations
                ),
                "extra_trace_events": max(
                    0,
                    len(verified.get("trace_events", [])) - len(run.get("trace_events", [])),
                ),
                "verification_event_count": _verification_event_count(verified),
                "tool_action_parse_status_counts": _tool_action_parse_status_counts(run),
                "tool_action_status_counts": _tool_action_status_counts(run),
                "memory_health_score": float(metrics.get("memory_health_score", 0.0)),
                "semantic_drift_score": float(metrics.get("semantic_drift_score", 0.0)),
                "false_completion_rate": float(metrics.get("false_completion_rate", 0.0)),
                "runtime_error": metadata.get("runtime_error"),
                "run_path": str(_resolve_artifact_path(run_info["path"], manifest_dir)),
            }
        )
    return rows


def _model_summary(model: dict, rows: list[dict]) -> dict:
    parse_counts = Counter(row["parse_status"] for row in rows)
    tool_action_parse_counts: Counter[str] = Counter()
    tool_action_status_counts: Counter[str] = Counter()
    for row in rows:
        tool_action_parse_counts.update(row["tool_action_parse_status_counts"])
        tool_action_status_counts.update(row["tool_action_status_counts"])
    return {
        "model_name": model["model_name"],
        "model_family": model.get("model_family"),
        "status": model.get("status"),
        "baseline_task_count": len(rows),
        "parse_status_counts": dict(sorted(parse_counts.items())),
        "parsed_claim_count": sum(row["parsed_claim_count"] for row in rows),
        "high_risk_label_count": sum(row["high_risk_label_count"] for row in rows),
        "blocked_action_count": sum(row["blocked_action_count"] for row in rows),
        "stale_evidence_row_count": sum(1 for row in rows if row["used_stale_evidence"]),
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
            row["baseline_accepted_finish_evaluator_failures"] for row in rows
        ),
        "verified_accepted_finish_evaluator_failure_count": sum(
            row["verified_accepted_finish_evaluator_failures"] for row in rows
        ),
        "verified_recovery_count": sum(
            1 for row in rows if row["verified_recovery_after_block"]
        ),
        "baseline_evaluator_success_count": sum(
            1 for row in rows if row["baseline_evaluator_success"]
        ),
        "verified_evaluator_success_count": sum(
            1 for row in rows if row["verified_evaluator_success"]
        ),
        "tool_action_parse_status_counts": dict(sorted(tool_action_parse_counts.items())),
        "tool_action_status_counts": dict(sorted(tool_action_status_counts.items())),
        "avg_extra_model_actions": _mean(
            row["extra_model_actions"] for row in rows
        ),
        "extra_trace_event_count": sum(row["extra_trace_events"] for row in rows),
        "verification_event_count": sum(row["verification_event_count"] for row in rows),
        "avg_memory_health_score": _mean(row["memory_health_score"] for row in rows),
        "avg_semantic_drift_score": _mean(row["semantic_drift_score"] for row in rows),
        "avg_false_completion_rate": _mean(row["false_completion_rate"] for row in rows),
        "errors": model.get("errors", []),
    }


def _aggregate_summary(successful_rows: list[dict], task_rows: list[dict]) -> dict[str, Any]:
    parse_counts: Counter[str] = Counter(row["parse_status"] for row in task_rows)
    blocked_by_model: dict[str, int] = defaultdict(int)
    for row in task_rows:
        blocked_by_model[row["model_name"]] += row["blocked_action_count"]
    return {
        "successful_models": len(successful_rows),
        "baseline_task_rows": len(task_rows),
        "parse_status_counts": dict(sorted(parse_counts.items())),
        "total_parsed_claims": sum(row["parsed_claim_count"] for row in task_rows),
        "total_high_risk_labels": sum(row["high_risk_label_count"] for row in task_rows),
        "total_blocked_actions": sum(row["blocked_action_count"] for row in task_rows),
        "total_stale_claims": sum(row["stale_claim_count"] for row in task_rows),
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
            1 for row in task_rows if row["verified_recovery_after_block"]
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
        "total_extra_trace_events": sum(row["extra_trace_events"] for row in task_rows),
        "avg_memory_health_score": _mean(
            row["memory_health_score"] for row in task_rows
        ),
        "avg_semantic_drift_score": _mean(
            row["semantic_drift_score"] for row in task_rows
        ),
        "blocked_actions_by_model": dict(sorted(blocked_by_model.items())),
    }


def _resolve_artifact_path(path: str, manifest_dir: Path) -> Path:
    artifact_path = Path(path)
    return artifact_path if artifact_path.is_absolute() else manifest_dir / artifact_path


def _format_counter(counter: dict) -> str:
    if not counter:
        return "-"
    return ", ".join(f"{key}:{value}" for key, value in sorted(counter.items()))


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


def _mean(values) -> float:
    items = list(values)
    return round(mean(items), 4) if items else 0.0


def _read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))
