"""Real-runtime model matrix evaluation helpers."""

from __future__ import annotations

import json
import subprocess
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .benchmark_runner import BenchmarkRunConfig, BenchmarkRunner
from .comparison import compare_runs
from .metrics import build_memory_health_report


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_MODEL_MATRIX_PATH = ROOT / "research" / "agents" / "model_matrix.json"


def load_model_matrix(path: Path = DEFAULT_MODEL_MATRIX_PATH) -> dict:
    """Load the configured real-runtime model matrix."""

    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


def run_model_matrix(
    output_dir: Path,
    *,
    matrix_path: Path = DEFAULT_MODEL_MATRIX_PATH,
    runtime: str | None = None,
    runtime_endpoint: str | None = None,
    framework: str | None = None,
    task_ids: list[str] | None = None,
    model_names: list[str] | None = None,
    variants: list[str] | None = None,
    pull_missing: bool = False,
    minimum_successful_models: int | None = None,
    max_tokens: int | None = None,
    trace_mode: str | None = None,
    prompt_template: str | None = None,
    runner: BenchmarkRunner | None = None,
) -> dict:
    """Run benchmark tasks across a configured model matrix.

    Missing local models are skipped unless ``pull_missing`` is true. Real-runtime
    runs disable deterministic fallback so failed Ollama/llama.cpp calls cannot be
    counted as model evidence.
    """

    matrix = load_model_matrix(matrix_path)
    active_runtime = runtime or matrix.get("runtime", "ollama")
    active_framework = framework or matrix.get("framework", "react_custom")
    active_variants = variants or ["baseline", "verified"]
    active_runner = runner or BenchmarkRunner()
    dataset = active_runner._load_json(active_runner.benchmark_path)
    active_task_ids = task_ids or [task["task_id"] for task in dataset["tasks"]]
    active_max_tokens = int(max_tokens if max_tokens is not None else matrix.get("max_tokens", 128))
    active_trace_mode = trace_mode or matrix.get("trace_mode", "scripted")
    active_prompt_template = prompt_template or matrix.get(
        "prompt_template",
        "default_react_memory_v0",
    )
    minimum_successful = (
        minimum_successful_models
        if minimum_successful_models is not None
        else matrix.get("minimum_successful_models", 5)
    )

    output_dir.mkdir(parents=True, exist_ok=True)
    installed_before = _installed_model_names(active_runtime, runtime_endpoint)
    enabled_models = [item for item in matrix["models"] if item.get("enabled", True)]
    if model_names:
        requested_models = set(model_names)
        enabled_models = [
            item for item in enabled_models if item["model_name"] in requested_models
        ]

    model_results = []

    for model in enabled_models:
        model_result = _run_one_model(
            model,
            output_dir=output_dir,
            runtime=active_runtime,
            runtime_endpoint=runtime_endpoint,
            framework=active_framework,
            task_ids=active_task_ids,
            variants=active_variants,
            max_tokens=active_max_tokens,
            trace_mode=active_trace_mode,
            prompt_template=active_prompt_template,
            pull_missing=pull_missing,
            installed_before=installed_before,
            runner=active_runner,
        )
        model_results.append(model_result)
        if model_result["installed"]:
            installed_before.add(model["model_name"])

    successful_models = [
        result["model_name"]
        for result in model_results
        if result["status"] == "succeeded"
    ]
    limitations = [
        "Runs use the configured agent framework and local model runtime.",
        "Only succeeded real-runtime rows count as model evidence.",
        "Skipped rows usually mean the model is not pulled locally.",
    ]
    if active_framework == "langgraph":
        limitations.append(
            "LangGraph rows execute a real StateGraph, but the current graph uses bounded benchmark memory/tool nodes rather than arbitrary shell or browser tools."
        )
    else:
        limitations.append(
            "Model-driven trace mode uses model-authored claims but does not yet execute a full external agent framework."
        )

    manifest = {
        "schema_version": "agent-memory-model-matrix-run/v0.1",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "matrix_path": str(matrix_path.resolve()),
        "output_dir": str(output_dir.resolve()),
        "runtime": active_runtime,
        "framework": active_framework,
        "runtime_endpoint": runtime_endpoint,
        "hardware_profile": matrix.get("hardware_profile", {}),
        "task_ids": active_task_ids,
        "model_names": [model["model_name"] for model in enabled_models],
        "variants": active_variants,
        "max_tokens": active_max_tokens,
        "trace_mode": active_trace_mode,
        "prompt_template": active_prompt_template,
        "pull_missing": pull_missing,
        "minimum_successful_models": minimum_successful,
        "successful_model_count": len(successful_models),
        "successful_models": successful_models,
        "meets_minimum_successful_models": len(successful_models) >= minimum_successful,
        "models": model_results,
        "limitations": limitations,
    }
    manifest_path = output_dir / "model_matrix_manifest.json"
    summary_path = output_dir / "model_matrix_summary.md"
    manifest["manifest_path"] = str(manifest_path.resolve())
    manifest["summary_markdown"] = str(summary_path.resolve())
    _write_json(manifest_path, manifest)
    summary_path.write_text(_model_matrix_summary(manifest), encoding="utf-8")
    return manifest


def _run_one_model(
    model: dict,
    *,
    output_dir: Path,
    runtime: str,
    runtime_endpoint: str | None,
    framework: str,
    task_ids: list[str],
    variants: list[str],
    max_tokens: int,
    trace_mode: str,
    prompt_template: str,
    pull_missing: bool,
    installed_before: set[str],
    runner: BenchmarkRunner,
) -> dict:
    model_name = model["model_name"]
    model_slug = _model_slug(model_name)
    installed = runtime == "deterministic" or _model_is_installed(
        model_name,
        installed_before,
    )
    result: dict[str, Any] = {
        "model_family": model["model_family"],
        "model_name": model_name,
        "display_name": model.get("display_name", model_name),
        "runtime": runtime,
        "approx_size_gb": model.get("approx_size_gb"),
        "license_note": model.get("license_note"),
        "role": model.get("role"),
        "installed": installed,
        "status": "pending",
        "runs": [],
        "comparisons": [],
        "errors": [],
    }

    if not installed and pull_missing:
        pull_result = _pull_ollama_model(model_name)
        result["pull"] = pull_result
        installed = pull_result["returncode"] == 0
        result["installed"] = installed

    if not installed:
        result["status"] = "skipped"
        result["skip_reason"] = f"model not installed locally: {model_name}"
        return result

    run_paths: dict[tuple[str, str], Path] = {}
    for task_id in task_ids:
        for variant in variants:
            run_config = BenchmarkRunConfig(
                framework=framework,
                model_family=model["model_family"],
                model_name=model_name,
                agent_variant=variant,
                runtime=runtime,
                runtime_endpoint=runtime_endpoint,
                max_tokens=max_tokens,
                trace_mode=trace_mode,
                prompt_template=prompt_template,
                allow_runtime_fallback=False,
            )
            run_path = output_dir / "runs" / model_slug / variant / f"{task_id}.json"
            try:
                run = runner.run_task_id(task_id, run_config)
            except RuntimeError as exc:
                result["status"] = "failed"
                result["errors"].append(
                    {
                        "task_id": task_id,
                        "variant": variant,
                        "error": str(exc),
                    }
                )
                return result

            _write_json(run_path, run)
            run_paths[(task_id, variant)] = run_path
            result["runs"].append(
                {
                    "task_id": task_id,
                    "variant": variant,
                    "path": str(run_path.resolve()),
                    "runtime_error": run["run_metadata"].get("runtime_error"),
                }
            )

            if variant == "baseline":
                score_path = output_dir / "scores" / model_slug / f"{task_id}.json"
                _write_json(score_path, build_memory_health_report(run))
                result["runs"][-1]["score_json"] = str(score_path.resolve())
            if variant == "verified":
                verification_path = output_dir / "verifications" / model_slug / f"{task_id}.json"
                _write_json(verification_path, run["verification_report"])
                result["runs"][-1]["verification_json"] = str(verification_path.resolve())

        baseline_path = run_paths.get((task_id, "baseline"))
        verified_path = run_paths.get((task_id, "verified"))
        if baseline_path and verified_path:
            comparison_path = output_dir / "comparisons" / model_slug / f"{task_id}.json"
            baseline = json.loads(baseline_path.read_text(encoding="utf-8"))
            verified = json.loads(verified_path.read_text(encoding="utf-8"))
            comparison = compare_runs(baseline, verified)
            _write_json(comparison_path, comparison)
            result["comparisons"].append(
                {
                    "task_id": task_id,
                    "path": str(comparison_path.resolve()),
                    "blocked_actions": comparison["verification_overhead"][
                        "blocked_actions"
                    ],
                    "metric_deltas": comparison["metric_deltas"],
                }
            )

    result["status"] = "succeeded"
    return result


def _installed_model_names(runtime: str, endpoint: str | None = None) -> set[str]:
    if runtime == "deterministic":
        return set()
    if runtime != "ollama":
        return set()

    url = f"{(endpoint or 'http://127.0.0.1:11434').rstrip('/')}/api/tags"
    try:
        with urllib.request.urlopen(url, timeout=5) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError):
        return set()

    names = set()
    for model in payload.get("models", []):
        if model.get("name"):
            names.add(model["name"])
        if model.get("model"):
            names.add(model["model"])
    return names


def _model_is_installed(model_name: str, installed: set[str]) -> bool:
    if model_name in installed:
        return True
    if ":" not in model_name and f"{model_name}:latest" in installed:
        return True
    if model_name.endswith(":latest") and model_name.removesuffix(":latest") in installed:
        return True
    return False


def _pull_ollama_model(model_name: str) -> dict:
    try:
        completed = subprocess.run(
            ["ollama", "pull", model_name],
            capture_output=True,
            check=False,
            text=True,
        )
        return {
            "command": f"ollama pull {model_name}",
            "returncode": completed.returncode,
            "stdout": completed.stdout[-2000:],
            "stderr": completed.stderr[-2000:],
        }
    except FileNotFoundError as exc:
        return {
            "command": f"ollama pull {model_name}",
            "returncode": 127,
            "stdout": "",
            "stderr": str(exc),
        }


def _model_matrix_summary(manifest: dict) -> str:
    lines = [
        "# Agent Memory Model Matrix Summary",
        "",
        f"- Runtime: `{manifest['runtime']}`",
        f"- Framework: `{manifest.get('framework', 'react_custom')}`",
        f"- Trace mode: `{manifest.get('trace_mode', 'scripted')}`",
        f"- Prompt template: `{manifest.get('prompt_template', 'default_react_memory_v0')}`",
        f"- Minimum successful models: `{manifest['minimum_successful_models']}`",
        f"- Successful models: `{manifest['successful_model_count']}`",
        f"- Meets minimum: `{manifest['meets_minimum_successful_models']}`",
        "",
        "| Model | Family | Status | Runs | Comparisons |",
        "|---|---|---:|---:|---:|",
    ]
    for model in manifest["models"]:
        lines.append(
            "| `{model}` | `{family}` | `{status}` | `{runs}` | `{comparisons}` |".format(
                model=model["model_name"],
                family=model["model_family"],
                status=model["status"],
                runs=len(model["runs"]),
                comparisons=len(model["comparisons"]),
            )
        )

    lines.extend(["", "## Limitations", ""])
    lines.extend(f"- {item}" for item in manifest["limitations"])
    lines.append("")
    return "\n".join(lines)


def _model_slug(model_name: str) -> str:
    return (
        model_name.replace("/", "_")
        .replace(":", "_")
        .replace(".", "_")
        .replace("-", "_")
    )


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
