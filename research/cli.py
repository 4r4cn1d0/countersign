"""Terminal interface for Agent Memory Observatory research workflows."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from .runner import (
    BenchmarkRunConfig,
    BenchmarkRunner,
    analyze_model_matrix_manifest,
    audit_model_matrix_manifest,
    build_memory_health_report,
    compare_runs,
    format_model_matrix_analysis_markdown,
    generate_artifact_bundle,
    load_model_matrix,
    run_model_matrix,
    validate_manual_measurements,
    verify_run,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="agent-memory")
    subparsers = parser.add_subparsers(dest="command", required=True)

    run_parser = subparsers.add_parser("run", help="Run benchmark task(s)")
    run_parser.add_argument("--task", help="Task ID to run. Omit to run all tasks.")
    run_parser.add_argument("--agent", default="react_custom")
    run_parser.add_argument("--model-family", default="qwen")
    run_parser.add_argument("--model", default="qwen2.5-coder:7b")
    run_parser.add_argument("--variant", default="baseline")
    run_parser.add_argument("--runtime", default="deterministic")
    run_parser.add_argument("--runtime-endpoint")
    run_parser.add_argument("--prompt-template", default="default_react_memory_v0")
    run_parser.add_argument("--temperature", type=float, default=0.0)
    run_parser.add_argument("--max-tokens", type=int, default=256)
    run_parser.add_argument("--action-budget", type=int, default=32)
    run_parser.add_argument(
        "--thinking",
        action=argparse.BooleanOptionalAction,
        default=False,
    )
    run_parser.add_argument(
        "--trace-mode",
        choices=["scripted", "model_driven"],
        default="scripted",
        help="Use scripted benchmark traces or model-authored trace claims.",
    )
    run_parser.add_argument("--seed", type=int, default=0)
    _add_memory_experiment_arguments(run_parser, defaults=True)
    run_parser.add_argument("--out", default="runs")
    run_parser.add_argument("--workspace-root")
    run_parser.add_argument(
        "--allow-runtime-fallback",
        action="store_true",
        help="Explicitly allow deterministic fallback after a local runtime failure.",
    )
    run_parser.add_argument("--format", choices=["table", "json", "markdown"], default="table")
    run_parser.set_defaults(handler=_run_command)

    score_parser = subparsers.add_parser("score", help="Score a saved run JSON")
    score_parser.add_argument("--run", required=True)
    score_parser.add_argument("--out")
    score_parser.add_argument("--format", choices=["table", "json", "markdown"], default="table")
    score_parser.set_defaults(handler=_score_command)

    verify_parser = subparsers.add_parser("verify", help="Apply verification policy")
    verify_parser.add_argument("--run", required=True)
    verify_parser.add_argument("--out")
    verify_parser.add_argument("--format", choices=["table", "json", "markdown"], default="table")
    verify_parser.set_defaults(handler=_verify_command)

    compare_parser = subparsers.add_parser("compare", help="Compare baseline and verified runs")
    compare_parser.add_argument("--baseline", required=True)
    compare_parser.add_argument("--verified", required=True)
    compare_parser.add_argument("--out")
    compare_parser.add_argument("--format", choices=["table", "json", "markdown"], default="table")
    compare_parser.set_defaults(handler=_compare_command)

    bundle_parser = subparsers.add_parser("bundle", help="Generate full benchmark artifact bundle")
    bundle_parser.add_argument("--out", required=True)
    bundle_parser.add_argument("--agent", default="react_custom")
    bundle_parser.add_argument("--model-family", default="qwen")
    bundle_parser.add_argument("--model", default="qwen2.5-coder:7b")
    bundle_parser.add_argument("--runtime", default="deterministic")
    bundle_parser.add_argument("--runtime-endpoint")
    bundle_parser.add_argument("--prompt-template", default="default_react_memory_v0")
    bundle_parser.add_argument("--temperature", type=float, default=0.0)
    bundle_parser.add_argument("--max-tokens", type=int, default=256)
    bundle_parser.add_argument("--action-budget", type=int, default=32)
    bundle_parser.add_argument(
        "--thinking",
        action=argparse.BooleanOptionalAction,
        default=False,
    )
    bundle_parser.add_argument(
        "--trace-mode",
        choices=["scripted", "model_driven"],
        default="scripted",
    )
    bundle_parser.add_argument("--seed", type=int, default=0)
    _add_memory_experiment_arguments(bundle_parser, defaults=True)
    bundle_parser.add_argument("--workspace-root")
    bundle_parser.add_argument(
        "--allow-runtime-fallback",
        action="store_true",
        help="Explicitly allow deterministic fallback after a local runtime failure.",
    )
    bundle_parser.add_argument("--test-status", default="not_run")
    bundle_parser.add_argument("--format", choices=["table", "json", "markdown"], default="table")
    bundle_parser.set_defaults(handler=_bundle_command)

    matrix_parser = subparsers.add_parser("matrix", help="Run real-runtime model matrix")
    matrix_parser.add_argument("--out", required=True)
    matrix_parser.add_argument("--matrix", default="research/agents/model_matrix.json")
    matrix_parser.add_argument("--agent", default=None)
    matrix_parser.add_argument("--runtime", default=None)
    matrix_parser.add_argument("--runtime-endpoint")
    matrix_parser.add_argument("--task", action="append", dest="tasks")
    matrix_parser.add_argument(
        "--model",
        action="append",
        dest="models",
        help="Exact configured model tag to run. Repeat to run a subset.",
    )
    matrix_parser.add_argument(
        "--thinking",
        action=argparse.BooleanOptionalAction,
        default=None,
        help="Enable or disable runtime reasoning mode during action generation.",
    )
    matrix_parser.add_argument("--variant", action="append", dest="variants")
    matrix_parser.add_argument("--pull-missing", action="store_true")
    matrix_parser.add_argument(
        "--seed",
        action="append",
        type=int,
        dest="seeds",
        help="Experiment seed. Repeat for paired multi-seed trials.",
    )
    matrix_parser.add_argument("--temperature", type=float)
    matrix_parser.add_argument("--max-tokens", type=int)
    matrix_parser.add_argument("--action-budget", type=int)
    matrix_parser.add_argument(
        "--constrained-actions",
        action=argparse.BooleanOptionalAction,
        default=None,
        help="Request runtime-enforced JSON schema for model tool actions.",
    )
    matrix_parser.add_argument("--trace-mode", choices=["scripted", "model_driven"])
    matrix_parser.add_argument("--prompt-template")
    _add_memory_experiment_arguments(matrix_parser, defaults=False)
    matrix_parser.add_argument(
        "--pressure-profile",
        action="append",
        dest="pressure_profiles",
        help=(
            "Frozen pressure profile ID. Repeat for a control and one or "
            "more predeclared severities."
        ),
    )
    matrix_parser.add_argument(
        "--pressure-profiles-file",
        default="research/benchmarks/memory_pressure_profiles.json",
    )
    matrix_parser.add_argument("--minimum-successful-models", type=int)
    matrix_parser.add_argument("--fail-under-minimum", action="store_true")
    matrix_parser.add_argument("--format", choices=["table", "json", "markdown"], default="table")
    matrix_parser.set_defaults(handler=_matrix_command)

    matrix_list_parser = subparsers.add_parser("matrix-list", help="Show configured model matrix")
    matrix_list_parser.add_argument("--matrix", default="research/agents/model_matrix.json")
    matrix_list_parser.add_argument("--format", choices=["table", "json", "markdown"], default="table")
    matrix_list_parser.set_defaults(handler=_matrix_list_command)

    matrix_report_parser = subparsers.add_parser(
        "matrix-report",
        help="Analyze a real-runtime model matrix manifest",
    )
    matrix_report_parser.add_argument("--manifest", required=True)
    matrix_report_parser.add_argument("--out")
    matrix_report_parser.add_argument("--format", choices=["table", "json", "markdown"], default="table")
    matrix_report_parser.set_defaults(handler=_matrix_report_command)

    matrix_audit_parser = subparsers.add_parser(
        "matrix-audit",
        help="Verify protocol and artifact hashes for a model matrix",
    )
    matrix_audit_parser.add_argument("--manifest", required=True)
    matrix_audit_parser.add_argument(
        "--format",
        choices=["table", "json", "markdown"],
        default="table",
    )
    matrix_audit_parser.set_defaults(handler=_matrix_audit_command)

    measurement_audit_parser = subparsers.add_parser(
        "measurement-audit",
        help="Validate automatic metrics against frozen manual labels",
    )
    measurement_audit_parser.add_argument(
        "--labels",
        default="research/benchmarks/manual_measurement_labels.json",
    )
    measurement_audit_parser.add_argument(
        "--format",
        choices=["table", "json", "markdown"],
        default="table",
    )
    measurement_audit_parser.set_defaults(
        handler=_measurement_audit_command
    )

    args = parser.parse_args(argv)
    args.handler(args)
    return 0


def _run_command(args: argparse.Namespace) -> None:
    runner = BenchmarkRunner()
    config = BenchmarkRunConfig(
        framework=args.agent,
        model_family=args.model_family,
        model_name=args.model,
        agent_variant=args.variant,
        seed=args.seed,
        runtime=args.runtime,
        runtime_endpoint=args.runtime_endpoint,
        prompt_template=args.prompt_template,
        temperature=args.temperature,
        max_tokens=args.max_tokens,
        action_budget=args.action_budget,
        allow_runtime_fallback=args.allow_runtime_fallback,
        trace_mode=args.trace_mode,
        workspace_root=args.workspace_root or str(Path(args.out) / "workspaces"),
        thinking=args.thinking,
        memory_condition=args.memory_condition,
        memory_pressure_start=args.memory_pressure_start,
        memory_window=args.memory_window,
        task_state_probes=args.task_state_probes,
        probe_interval=args.probe_interval,
        probe_max_tokens=args.probe_max_tokens,
        memory_repair=args.memory_repair,
    )
    runs = [runner.run_task_id(args.task, config)] if args.task else runner.run_all(config)
    written_paths = _write_runs(runs, Path(args.out))
    payload = {
        "runs": runs,
        "written_paths": [str(path.resolve()) for path in written_paths],
    }
    _emit(payload, args.format, title="Benchmark Runs")


def _score_command(args: argparse.Namespace) -> None:
    run = _read_json(Path(args.run))
    report = build_memory_health_report(run)
    if args.out:
        _write_report(report, Path(args.out), args.format)
    _emit(report, args.format, title="Memory Health Report")


def _verify_command(args: argparse.Namespace) -> None:
    run = _read_json(Path(args.run))
    verified = verify_run(run)
    if args.out:
        _write_json(Path(args.out), verified)
    _emit(verified["verification_report"], args.format, title="Verification Report")


def _compare_command(args: argparse.Namespace) -> None:
    baseline = _read_json(Path(args.baseline))
    verified = _read_json(Path(args.verified))
    comparison = compare_runs(baseline, verified)
    if args.out:
        _write_report(comparison, Path(args.out), args.format)
    _emit(comparison, args.format, title="Baseline vs Verified")


def _bundle_command(args: argparse.Namespace) -> None:
    config = BenchmarkRunConfig(
        framework=args.agent,
        model_family=args.model_family,
        model_name=args.model,
        seed=args.seed,
        runtime=args.runtime,
        runtime_endpoint=args.runtime_endpoint,
        prompt_template=args.prompt_template,
        temperature=args.temperature,
        max_tokens=args.max_tokens,
        action_budget=args.action_budget,
        allow_runtime_fallback=args.allow_runtime_fallback,
        trace_mode=args.trace_mode,
        workspace_root=args.workspace_root or str(Path(args.out) / "workspaces"),
        thinking=args.thinking,
        memory_condition=args.memory_condition,
        memory_pressure_start=args.memory_pressure_start,
        memory_window=args.memory_window,
        task_state_probes=args.task_state_probes,
        probe_interval=args.probe_interval,
        probe_max_tokens=args.probe_max_tokens,
        memory_repair=args.memory_repair,
    )
    manifest = generate_artifact_bundle(
        Path(args.out),
        config=config,
        test_status=args.test_status,
    )
    _emit(manifest, args.format, title="Artifact Bundle")


def _matrix_command(args: argparse.Namespace) -> None:
    manifest = run_model_matrix(
        Path(args.out),
        matrix_path=Path(args.matrix),
        runtime=args.runtime,
        runtime_endpoint=args.runtime_endpoint,
        framework=args.agent,
        task_ids=args.tasks,
        model_names=args.models,
        variants=args.variants,
        seeds=args.seeds,
        pull_missing=args.pull_missing,
        minimum_successful_models=args.minimum_successful_models,
        temperature=args.temperature,
        max_tokens=args.max_tokens,
        action_budget=args.action_budget,
        trace_mode=args.trace_mode,
        prompt_template=args.prompt_template,
        constrained_actions=args.constrained_actions,
        thinking=args.thinking,
        memory_conditions=args.memory_conditions,
        pressure_profile_ids=args.pressure_profiles,
        pressure_profiles_path=Path(args.pressure_profiles_file),
        memory_pressure_start=args.memory_pressure_start,
        memory_window=args.memory_window,
        task_state_probes=args.task_state_probes,
        probe_interval=args.probe_interval,
        probe_max_tokens=args.probe_max_tokens,
        memory_repair=args.memory_repair,
    )
    _emit(manifest, args.format, title="Model Matrix")
    if args.fail_under_minimum and not manifest["meets_minimum_successful_models"]:
        raise SystemExit(2)


def _matrix_list_command(args: argparse.Namespace) -> None:
    matrix = load_model_matrix(Path(args.matrix))
    _emit(matrix, args.format, title="Configured Model Matrix")


def _add_memory_experiment_arguments(
    parser: argparse.ArgumentParser,
    *,
    defaults: bool,
) -> None:
    if defaults:
        parser.add_argument(
            "--memory-condition",
            default="full_history",
            choices=[
                "full_history",
                "normal_compaction",
                "lossy_compaction",
                "provenance_loss",
                "temporal_corruption",
                "contradictory_evidence",
                "distractor_pressure",
                "resume_summary",
            ],
        )
    else:
        parser.add_argument(
            "--memory-condition",
            action="append",
            dest="memory_conditions",
            choices=[
                "full_history",
                "normal_compaction",
                "lossy_compaction",
                "provenance_loss",
                "temporal_corruption",
                "contradictory_evidence",
                "distractor_pressure",
                "resume_summary",
            ],
            help="Memory treatment to run. Repeat for a controlled comparison.",
        )
    parser.add_argument(
        "--memory-pressure-start",
        type=int,
        default=6 if defaults else None,
    )
    parser.add_argument(
        "--memory-window",
        type=int,
        default=8 if defaults else None,
    )
    parser.add_argument(
        "--task-state-probes",
        action=argparse.BooleanOptionalAction,
        default=False if defaults else None,
    )
    parser.add_argument(
        "--probe-interval",
        type=int,
        default=5 if defaults else None,
    )
    parser.add_argument(
        "--probe-max-tokens",
        type=int,
        default=1536 if defaults else None,
        help="Separate generation budget for structured task-state probes.",
    )
    parser.add_argument(
        "--memory-repair",
        action=argparse.BooleanOptionalAction,
        default=True if defaults else None,
        help=(
            "After a verified finish is blocked, execute the smallest bounded "
            "evidence refresh before replanning."
        ),
    )


def _matrix_report_command(args: argparse.Namespace) -> None:
    report = analyze_model_matrix_manifest(Path(args.manifest))
    if args.out:
        output = Path(args.out)
        output.parent.mkdir(parents=True, exist_ok=True)
        if args.format == "markdown" or output.suffix == ".md":
            output.write_text(format_model_matrix_analysis_markdown(report), encoding="utf-8")
        else:
            _write_json(output, report)
    _emit(report, args.format, title="Model Matrix Analysis")


def _matrix_audit_command(args: argparse.Namespace) -> None:
    audit = audit_model_matrix_manifest(Path(args.manifest))
    _emit(audit, args.format, title="Model Matrix Artifact Audit")
    if not audit["valid"]:
        raise SystemExit(2)


def _measurement_audit_command(args: argparse.Namespace) -> None:
    report = validate_manual_measurements(Path(args.labels))
    _emit(report, args.format, title="Measurement Validation Audit")
    if report["disagreements"]:
        raise SystemExit(2)


def _write_runs(runs: list[dict], output: Path) -> list[Path]:
    if len(runs) == 1 and output.suffix == ".json":
        _write_json(output, runs[0])
        return [output]

    output.mkdir(parents=True, exist_ok=True)
    paths = []
    for run in runs:
        variant = run["run_metadata"]["agent_variant"]
        path = output / f"{run['task_id']}_{variant}.json"
        _write_json(path, run)
        paths.append(path)
    return paths


def _write_report(report: dict, output: Path, output_format: str) -> None:
    if output_format == "markdown" or output.suffix == ".md":
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(_format_markdown(report, title=_report_title(report)))
    else:
        _write_json(output, report)


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")


def _read_json(path: Path) -> dict:
    return json.loads(path.read_text())


def _emit(payload: dict, output_format: str, title: str) -> None:
    if output_format == "json":
        print(json.dumps(payload, indent=2, sort_keys=True))
    elif output_format == "markdown":
        print(_format_markdown(payload, title=title))
    else:
        print(_format_table(payload, title=title))


def _format_markdown(payload: dict, title: str) -> str:
    if str(payload.get("schema_version", "")).startswith(
        "agent-memory-model-matrix-analysis/"
    ):
        return format_model_matrix_analysis_markdown(payload)

    lines = [f"# {title}", ""]
    if payload.get("schema_version") == (
        "agent-measurement-validation/v0.1"
    ):
        lines.extend(
            _markdown_mapping(
                "Validation Summary",
                {
                    "probe_cases": payload["probe_case_count"],
                    "decision_belief_cases": (
                        payload["decision_belief_case_count"]
                    ),
                    "comparisons": payload["comparison_count"],
                    "exact_matches": payload["exact_match_count"],
                    "exact_match_rate": payload["exact_match_rate"],
                    "mean_absolute_error": payload[
                        "mean_absolute_error"
                    ],
                    "disagreements": len(payload["disagreements"]),
                },
            )
        )
        lines.append(
            f"Label fixture: `{payload['label_fixture']}`"
        )
        lines.append("")
    elif "metrics" in payload:
        lines.extend(_markdown_mapping("Metrics", payload["metrics"]))
    if "decision_counts" in payload:
        lines.extend(_markdown_mapping("Verification Decisions", payload["decision_counts"]))
    if "metric_deltas" in payload:
        lines.extend(_markdown_mapping("Metric Deltas", payload["metric_deltas"]))
    if "behavioral_outcomes" in payload:
        lines.extend(
            _markdown_mapping(
                "Behavioral Outcomes",
                payload["behavioral_outcomes"],
            )
        )
    if "written_paths" in payload:
        lines.append("## Written Files")
        lines.extend(f"- `{path}`" for path in payload["written_paths"])
    if "manifest_path" in payload and "summary_markdown" in payload:
        lines.append("## Bundle Files")
        lines.append(f"- Manifest: `{payload['manifest_path']}`")
        lines.append(f"- Summary: `{payload['summary_markdown']}`")
    if str(payload.get("schema_version", "")).startswith(
        "agent-memory-model-matrix-run/"
    ):
        lines.extend(_markdown_model_matrix(payload))
    if payload.get("schema_version") == "agent-memory-model-matrix/v0.1":
        lines.extend(_markdown_configured_model_matrix(payload))
    if len(lines) == 2:
        lines.append("```json")
        lines.append(json.dumps(payload, indent=2, sort_keys=True))
        lines.append("```")
    return "\n".join(lines) + "\n"


def _report_title(payload: dict) -> str:
    schema_version = payload.get("schema_version", "")
    if str(schema_version).startswith("agent-memory-health/"):
        return "Memory Health Report"
    if schema_version == "agent-memory-verification/v0.1":
        return "Verification Report"
    if schema_version == "agent-memory-comparison/v0.1":
        return "Baseline vs Verified"
    return "Agent Memory Report"


def _markdown_mapping(title: str, values: dict) -> list[str]:
    lines = [f"## {title}", "", "| Field | Value |", "|---|---|"]
    lines.extend(f"| `{key}` | `{value}` |" for key, value in values.items())
    lines.append("")
    return lines


def _format_table(payload: dict, title: str) -> str:
    lines = [title]
    if payload.get("schema_version") == (
        "agent-measurement-validation/v0.1"
    ):
        lines.extend(
            _table_mapping(
                {
                    "probe_cases": payload["probe_case_count"],
                    "decision_belief_cases": (
                        payload["decision_belief_case_count"]
                    ),
                    "comparisons": payload["comparison_count"],
                    "exact_matches": payload["exact_match_count"],
                    "exact_match_rate": payload["exact_match_rate"],
                    "mean_absolute_error": payload[
                        "mean_absolute_error"
                    ],
                    "disagreements": len(payload["disagreements"]),
                    "label_fixture": payload["label_fixture"],
                }
            )
        )
    elif payload.get("schema_version") == "agent-memory-model-matrix-run/v0.1":
        lines.extend(
            [
                f"successful_models  {payload['successful_model_count']}",
                f"minimum_required   {payload['minimum_successful_models']}",
                f"meets_minimum      {payload['meets_minimum_successful_models']}",
                f"framework          {payload.get('framework', 'react_custom')}",
                f"trace_mode         {payload.get('trace_mode', 'scripted')}",
                f"prompt_template    {payload.get('prompt_template', 'default_react_memory_v0')}",
            ]
        )
        lines.extend(
            "{model:<24} {status:<10} runs={runs:<2} comparisons={comparisons}".format(
                model=model["model_name"],
                status=model["status"],
                runs=len(model["runs"]),
                comparisons=len(model["comparisons"]),
            )
            for model in payload["models"]
        )
    elif payload.get("schema_version") == "agent-memory-model-matrix/v0.1":
        lines.extend(
            "{model:<24} {family:<10} {size}GB".format(
                model=model["model_name"],
                family=model["model_family"],
                size=model.get("approx_size_gb", "?"),
            )
            for model in payload["models"]
            if model.get("enabled", True)
        )
    elif str(payload.get("schema_version", "")).startswith(
        "agent-memory-model-matrix-analysis/"
    ):
        lines.extend(
            [
                f"successful_models  {payload['successful_model_count']}",
                f"task_rows          {payload['aggregate']['baseline_task_rows']}",
                f"parse_statuses     {payload['aggregate']['parse_status_counts']}",
                f"blocked_actions    {payload['aggregate']['total_blocked_actions']}",
            ]
        )
        lines.extend(
            "{model:<24} tasks={tasks:<2} parse={parse} blocked={blocked}".format(
                model=model["model_name"],
                tasks=model["baseline_task_count"],
                parse=model["parse_status_counts"],
                blocked=model["blocked_action_count"],
            )
            for model in payload["models"]
        )
    elif "metrics" in payload:
        lines.extend(_table_mapping(payload["metrics"]))
    elif "decision_counts" in payload:
        lines.extend(_table_mapping(payload["decision_counts"]))
    elif "metric_deltas" in payload:
        lines.extend(_table_mapping(payload["metric_deltas"]))
        if "behavioral_outcomes" in payload:
            lines.append("")
            lines.extend(_table_mapping(payload["behavioral_outcomes"]))
    elif "written_paths" in payload:
        lines.extend(f"saved: {path}" for path in payload["written_paths"])
    elif "manifest_path" in payload and "summary_markdown" in payload:
        lines.append(f"manifest: {payload['manifest_path']}")
        lines.append(f"summary:  {payload['summary_markdown']}")
    else:
        lines.append(json.dumps(payload, indent=2, sort_keys=True))
    return "\n".join(lines)


def _markdown_model_matrix(payload: dict) -> list[str]:
    lines = [
        f"- Framework: `{payload.get('framework', 'react_custom')}`",
        f"- Trace mode: `{payload.get('trace_mode', 'scripted')}`",
        f"- Prompt template: `{payload.get('prompt_template', 'default_react_memory_v0')}`",
        "",
        "## Model Results",
        "",
        "| Model | Status | Runs | Comparisons |",
        "|---|---:|---:|---:|",
    ]
    lines.extend(
        "| `{model}` | `{status}` | `{runs}` | `{comparisons}` |".format(
            model=model["model_name"],
            status=model["status"],
            runs=len(model["runs"]),
            comparisons=len(model["comparisons"]),
        )
        for model in payload["models"]
    )
    lines.append("")
    return lines


def _markdown_configured_model_matrix(payload: dict) -> list[str]:
    lines = [
        "## Configured Models",
        "",
        "| Model | Family | Approx Size | Role |",
        "|---|---|---:|---|",
    ]
    lines.extend(
        "| `{model}` | `{family}` | `{size}` | {role} |".format(
            model=model["model_name"],
            family=model["model_family"],
            size=model.get("approx_size_gb", "?"),
            role=model.get("role", ""),
        )
        for model in payload["models"]
        if model.get("enabled", True)
    )
    lines.append("")
    return lines


def _table_mapping(values: dict) -> list[str]:
    width = max([len(str(key)) for key in values] + [5])
    return [f"{key:<{width}}  {value}" for key, value in values.items()]


if __name__ == "__main__":
    raise SystemExit(main())
