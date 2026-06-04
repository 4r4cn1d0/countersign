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
            "## Task Rows",
            "",
            "| Model | Task | Parse | Claims | High-Risk | Blocked | Health | Drift |",
            "|---|---|---:|---:|---:|---:|---:|---:|",
        ]
    )
    for row in report["tasks"]:
        lines.append(
            "| `{model}` | `{task}` | `{parse}` | {claims} | {risk} | {blocked} | {health:.4f} | {drift:.4f} |".format(
                model=row["model_name"],
                task=row["task_id"],
                parse=row["parse_status"],
                claims=row["parsed_claim_count"],
                risk=row["high_risk_label_count"],
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
        rows.append(
            {
                "model_name": model["model_name"],
                "model_family": model.get("model_family"),
                "task_id": run_info["task_id"],
                "parse_status": metadata.get("model_trace_parse_status") or "unknown",
                "parsed_claim_count": int(metadata.get("model_trace_claim_count") or 0),
                "high_risk_label_count": len(run.get("high_risk_labels", [])),
                "blocked_action_count": len(verification_report.get("blocked_actions", [])),
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
    return {
        "model_name": model["model_name"],
        "model_family": model.get("model_family"),
        "status": model.get("status"),
        "baseline_task_count": len(rows),
        "parse_status_counts": dict(sorted(parse_counts.items())),
        "parsed_claim_count": sum(row["parsed_claim_count"] for row in rows),
        "high_risk_label_count": sum(row["high_risk_label_count"] for row in rows),
        "blocked_action_count": sum(row["blocked_action_count"] for row in rows),
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


def _mean(values) -> float:
    items = list(values)
    return round(mean(items), 4) if items else 0.0


def _read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))
