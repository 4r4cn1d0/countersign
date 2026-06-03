# MacBook M4 Air Real-Runtime Model Matrix

Date: 2026-06-04

## Summary

The first local real-runtime model matrix passed on the user's MacBook M4 Air with 24 GB
RAM. Six Ollama model backends ran the same bounded long-horizon benchmark task through
the baseline and verified variants, with deterministic fallback disabled.

This is real local model execution evidence for the custom ReAct-style harness. It is not
yet evidence for six separate full agent frameworks.

## Installed Local Models

`ollama list` showed the following configured matrix models installed before the run:

| Model | Size | Matrix role |
|---|---:|---|
| `qwen2.5-coder:7b` | 4.7 GB | coding/tool-use baseline |
| `llama3.2:3b` | 2.0 GB | small instruction baseline |
| `mistral:7b` | 4.4 GB | general baseline |
| `deepseek-r1:8b` | 5.2 GB | reasoning baseline |
| `gemma3:4b` | 3.3 GB | compact baseline |
| `phi4-mini:latest` | 2.5 GB | small reasoning baseline |

## Command

```bash
python3 scripts/agent_memory.py matrix \
  --out /tmp/agent-memory-model-matrix-m4air-5llm \
  --task coding_stale_tests_001 \
  --minimum-successful-models 5 \
  --max-tokens 64 \
  --fail-under-minimum \
  --format json
```

## Result

- Manifest: `/tmp/agent-memory-model-matrix-m4air-5llm/model_matrix_manifest.json`
- Summary: `/tmp/agent-memory-model-matrix-m4air-5llm/model_matrix_summary.md`
- Successful models: 6
- Minimum required successful models: 5
- Meets minimum: true
- Run artifacts: 12 real Ollama run JSON files
- Comparison artifacts: 6 baseline-vs-verified comparison JSON files

| Model | Status | Runs | Comparisons |
|---|---:|---:|---:|
| `qwen2.5-coder:7b` | `succeeded` | 2 | 1 |
| `llama3.2:3b` | `succeeded` | 2 | 1 |
| `mistral:7b` | `succeeded` | 2 | 1 |
| `deepseek-r1:8b` | `succeeded` | 2 | 1 |
| `gemma3:4b` | `succeeded` | 2 | 1 |
| `phi4-mini:latest` | `succeeded` | 2 | 1 |

## Anti-Fake Checks

- Matrix runs set `allow_runtime_fallback=false`; failed real model calls are errors, not
  silently replaced with deterministic traces.
- The manifest reports `successful_model_count=6` and `meets_minimum_successful_models=true`.
- A sampled Qwen run artifact includes `runtime=ollama`, `model_name=qwen2.5-coder:7b`,
  `raw_response.model`, eval token counts, timing metadata, and generated text.
- Missing model rows are skipped unless explicitly pulled and are not counted as successful.

## Verification

Focused research tests passed after the matrix implementation:

```bash
python3 -m pytest \
  backend/tests/test_research_benchmark_seed.py \
  backend/tests/test_research_benchmark_runner.py \
  backend/tests/test_research_memory_claims.py \
  backend/tests/test_research_memory_metrics.py \
  backend/tests/test_research_verification_and_cli.py \
  backend/tests/test_research_runtime_and_bundle.py \
  backend/tests/test_research_model_matrix.py \
  -q
```

Result: 42 passed, 1 skipped.

## Limitations

- This matrix used one bounded seed task, `coding_stale_tests_001`, to prove the local
  five-plus model workflow works. The next empirical run should sweep the full seed task set.
- These are model backends inside the same custom ReAct-style harness, not separate
  LangGraph, AutoGen, CrewAI, OpenHands, or SWE-agent implementations yet.
- Several models are open-weight rather than OSI open-source. Publication should report
  exact model tags and license categories separately.
- `--max-tokens 64` was used to keep the first local smoke run fast and thermally reasonable.
  Larger result claims should use a predeclared token budget and repeat runs.
