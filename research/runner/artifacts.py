"""Benchmark artifact bundle generation."""

from __future__ import annotations

import json
import subprocess
from dataclasses import asdict, is_dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .benchmark_runner import BenchmarkRunConfig, BenchmarkRunner
from .comparison import compare_runs
from .metrics import build_memory_health_report
from .verification import verify_run


def generate_artifact_bundle(
    output_dir: Path,
    config: BenchmarkRunConfig | None = None,
    runner: BenchmarkRunner | None = None,
    test_status: str = "not_run",
) -> dict:
    """Generate a complete benchmark artifact bundle."""

    active_runner = runner or BenchmarkRunner()
    run_config = config or BenchmarkRunConfig()
    output_dir.mkdir(parents=True, exist_ok=True)

    baseline_dir = output_dir / "runs" / "baseline"
    verified_dir = output_dir / "runs" / "verified"
    score_dir = output_dir / "scores"
    verification_dir = output_dir / "verifications"
    comparison_dir = output_dir / "comparisons"
    for directory in [
        baseline_dir,
        verified_dir,
        score_dir,
        verification_dir,
        comparison_dir,
    ]:
        directory.mkdir(parents=True, exist_ok=True)

    dataset = active_runner._load_json(active_runner.benchmark_path)
    bundle_tasks = []
    commands = []

    for task in dataset["tasks"]:
        baseline_config = _replace_dataclass(run_config, agent_variant="baseline")
        verified_config = _replace_dataclass(run_config, agent_variant="verified")
        baseline_run = active_runner.run_task(task, baseline_config)
        verified_run = active_runner.run_task(task, verified_config)

        baseline_run_path = baseline_dir / f"{task['task_id']}.json"
        verified_run_path = verified_dir / f"{task['task_id']}.json"
        score_json_path = score_dir / f"{task['task_id']}.json"
        score_md_path = score_dir / f"{task['task_id']}.md"
        verification_json_path = verification_dir / f"{task['task_id']}.json"
        verification_md_path = verification_dir / f"{task['task_id']}.md"
        comparison_json_path = comparison_dir / f"{task['task_id']}.json"
        comparison_md_path = comparison_dir / f"{task['task_id']}.md"

        score = build_memory_health_report(baseline_run, task)
        verification = verified_run["verification_report"]
        comparison = compare_runs(baseline_run, verified_run)

        _write_json(baseline_run_path, baseline_run)
        _write_json(verified_run_path, verified_run)
        _write_json(score_json_path, score)
        _write_markdown(score_md_path, _markdown_report("Memory Health Report", score))
        _write_json(verification_json_path, verification)
        _write_markdown(
            verification_md_path,
            _markdown_report("Verification Report", verification),
        )
        _write_json(comparison_json_path, comparison)
        _write_markdown(
            comparison_md_path,
            _markdown_report("Baseline vs Verified", comparison),
        )

        bundle_tasks.append(
            {
                "task_id": task["task_id"],
                "baseline_run": str(baseline_run_path.resolve()),
                "verified_run": str(verified_run_path.resolve()),
                "score_json": str(score_json_path.resolve()),
                "score_markdown": str(score_md_path.resolve()),
                "verification_json": str(verification_json_path.resolve()),
                "verification_markdown": str(verification_md_path.resolve()),
                "comparison_json": str(comparison_json_path.resolve()),
                "comparison_markdown": str(comparison_md_path.resolve()),
            }
        )
        commands.extend(
            [
                f"python3 scripts/agent_memory.py run --task {task['task_id']} --variant baseline --out {baseline_run_path}",
                f"python3 scripts/agent_memory.py run --task {task['task_id']} --variant verified --out {verified_run_path}",
                f"python3 scripts/agent_memory.py compare --baseline {baseline_run_path} --verified {verified_run_path} --out {comparison_json_path}",
            ]
        )

    manifest = {
        "schema_version": "agent-memory-artifact-bundle/v0.1",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "git_ref": _git_ref(),
        "config": _config_dict(run_config),
        "test_status": test_status,
        "commands": commands,
        "tasks": bundle_tasks,
    }
    manifest_path = output_dir / "manifest.json"
    summary_path = output_dir / "summary.md"
    _write_json(manifest_path, manifest)
    summary = generate_artifact_summary(manifest)
    _write_markdown(summary_path, summary)

    manifest["manifest_path"] = str(manifest_path.resolve())
    manifest["summary_markdown"] = str(summary_path.resolve())
    _write_json(manifest_path, manifest)
    return manifest


def generate_artifact_summary(manifest: dict) -> str:
    """Generate a Markdown summary from bundle artifacts."""

    lines = [
        "# Agent Memory Artifact Summary",
        "",
        "This summary is generated from machine-readable benchmark artifacts.",
        "",
        "## Bundle",
        "",
        f"- Schema: `{manifest['schema_version']}`",
        f"- Created: `{manifest['created_at']}`",
        f"- Git ref: `{manifest.get('git_ref') or 'unknown'}`",
        f"- Runtime: `{manifest['config']['runtime']}`",
        f"- Model: `{manifest['config']['model_name']}`",
        f"- Variant baseline/verified: `baseline` / `verified`",
        f"- Test status: `{manifest['test_status']}`",
        "",
        "## Tasks",
        "",
        "| Task | False Completion Delta | Memory Health Delta | Blocked Actions |",
        "|---|---:|---:|---:|",
    ]

    for task in manifest["tasks"]:
        comparison = json.loads(Path(task["comparison_json"]).read_text())
        deltas = comparison["metric_deltas"]
        overhead = comparison["verification_overhead"]
        lines.append(
            "| `{task}` | `{false_completion}` | `{memory_health}` | `{blocked}` |".format(
                task=task["task_id"],
                false_completion=deltas.get("false_completion_rate", 0.0),
                memory_health=deltas.get("memory_health_score", 0.0),
                blocked=overhead.get("blocked_actions", 0),
            )
        )

    lines.extend(
        [
            "",
            "## Commands",
            "",
            "```bash",
            *manifest["commands"],
            "```",
            "",
            "## Limitations",
            "",
            "- Deterministic harness results are not real open-source LLM agent results.",
            "- Real-runtime runs must be labeled separately in the manifest.",
            "- This summary only reports values present in generated artifacts.",
            "",
        ]
    )
    return "\n".join(lines)


def _replace_dataclass(config: BenchmarkRunConfig, **updates: Any) -> BenchmarkRunConfig:
    values = _config_dict(config)
    values.update(updates)
    return BenchmarkRunConfig(**values)


def _config_dict(config: BenchmarkRunConfig) -> dict:
    if is_dataclass(config):
        return asdict(config)
    return dict(config)


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")


def _write_markdown(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)


def _markdown_report(title: str, payload: dict) -> str:
    lines = [f"# {title}", "", "```json", json.dumps(payload, indent=2, sort_keys=True), "```", ""]
    return "\n".join(lines)


def _git_ref() -> str | None:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=Path(__file__).resolve().parents[2],
            capture_output=True,
            check=True,
            text=True,
        )
        return result.stdout.strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        return None
