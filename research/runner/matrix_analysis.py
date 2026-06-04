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
            "## Coding-Agent Reality Matrix",
            "",
            "| Model | Final Tests Passed | Stale Evidence Rows | False Completion Claims | Verification Helped | Action Parses | Action Statuses | Avg Extra Tools | Extra Trace Events |",
            "|---|---:|---:|---:|---:|---|---|---:|---:|",
        ]
    )
    for model in report["models"]:
        lines.append(
            "| `{model}` | {final} | {stale} | {false} | {helped} | {parse} | {status} | {tools:.2f} | {events} |".format(
                model=model["model_name"],
                final=model["final_test_success_count"],
                stale=model["stale_evidence_row_count"],
                false=model["false_completion_claim_count"],
                helped=model["verification_helped_count"],
                parse=_format_counter(model["tool_action_parse_status_counts"]),
                status=_format_counter(model["tool_action_status_counts"]),
                tools=model["avg_extra_tool_calls"],
                events=model["extra_trace_event_count"],
            )
        )

    lines.extend(
        [
            "",
            "## Task Rows",
            "",
            "| Model | Task | Parse | Final Tests | Stale | False | Verified False | Helped | Extra Tools | Blocked | Health | Drift |",
            "|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
        ]
    )
    for row in report["tasks"]:
        lines.append(
            "| `{model}` | `{task}` | `{parse}` | {final} | {stale} | {false} | {verified_false} | {helped} | {extra_tools} | {blocked} | {health:.4f} | {drift:.4f} |".format(
                model=row["model_name"],
                task=row["task_id"],
                parse=row["parse_status"],
                final=row["final_test_success"],
                stale=row["stale_claim_count"],
                false=row["false_completion_claim_count"],
                verified_false=row["verified_false_completion_claim_count"],
                helped=row["verification_helped"],
                extra_tools=row["extra_tool_calls"],
                blocked=row["blocked_action_count"],
                health=row["memory_health_score"],
                drift=row["semantic_drift_score"],
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
        verified_health = (
            verified.get("effective_memory_health_report")
            or verified.get("memory_health_report")
            or {}
        )
        baseline_counts = health.get("claim_counts", {})
        verified_counts = verified_health.get("claim_counts", {})
        verified_metadata = verified.get("run_metadata", {})
        baseline_tool_iterations = int(metadata.get("tool_loop_iterations") or 0)
        verified_tool_iterations = int(
            verified_metadata.get("tool_loop_iterations") or baseline_tool_iterations
        )
        final_test_status = _final_test_status(run)
        verified_final_test_status = _final_test_status(verified) if verified else {}
        false_completion_claims = int(baseline_counts.get("false_completion", 0))
        verified_false_completion_claims = int(
            verified_counts.get("false_completion", false_completion_claims)
        )
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
                "verified_false_completion_claim_count": verified_false_completion_claims,
                "verification_helped": (
                    verified_false_completion_claims < false_completion_claims
                    or int(verified_counts.get("stale", stale_claims)) < stale_claims
                ),
                "tool_loop_iterations": baseline_tool_iterations,
                "verified_tool_loop_iterations": verified_tool_iterations,
                "final_test_success": final_test_status.get("status") == "success",
                "final_test_returncode": final_test_status.get("returncode"),
                "verified_final_test_success": (
                    verified_final_test_status.get("status") == "success"
                    if verified
                    else None
                ),
                "verified_final_test_returncode": verified_final_test_status.get(
                    "returncode"
                ),
                "extra_tool_calls": verified_tool_iterations - baseline_tool_iterations,
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
        "verification_helped_count": sum(1 for row in rows if row["verification_helped"]),
        "final_test_success_count": sum(1 for row in rows if row["final_test_success"]),
        "tool_action_parse_status_counts": dict(sorted(tool_action_parse_counts.items())),
        "tool_action_status_counts": dict(sorted(tool_action_status_counts.items())),
        "avg_extra_tool_calls": _mean(row["extra_tool_calls"] for row in rows),
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
        "verification_helped_rows": sum(
            1 for row in task_rows if row["verification_helped"]
        ),
        "final_test_success_rows": sum(
            1 for row in task_rows if row["final_test_success"]
        ),
        "total_extra_tool_calls": sum(row["extra_tool_calls"] for row in task_rows),
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
        and event.get("graph_node") == "choose_tool"
    )
    return dict(sorted(counts.items()))


def _tool_action_status_counts(run: dict) -> dict[str, int]:
    counts = Counter(
        event.get("action_status", "unknown")
        for event in run.get("trace_events", [])
        if event.get("event_type") == "decision_point"
        and event.get("graph_node") == "choose_tool"
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
        if (
            event.get("event_type") == "tool_call"
            and event.get("tool_name") == "run_tests"
        ):
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
