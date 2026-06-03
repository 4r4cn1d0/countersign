# Initial Open-Source Agent Stack

The first research MVP uses a dependency-light custom ReAct-style runner as the primary
agent harness. This keeps the benchmark deterministic while the memory-corruption metrics
and verification gates are still being built.

The runner is intentionally adapter-shaped so later experiments can plug in LangGraph,
AutoGen, CrewAI, OpenHands/SWE-agent, or other open-source agent frameworks without
changing the benchmark task schema.

## Initial Choice

- **Primary framework:** custom ReAct-style baseline runner
- **Why:** deterministic, local, auditable, no closed-source dependency, easy to compare
  baseline vs verification-augmented behavior
- **Target production adapters:** LangGraph first, then AutoGen/CrewAI/ReAct/OpenHands-style
  adapters as needed
- **Model families:** Qwen, Llama, Mistral, DeepSeek, Gemma, Phi
- **Runtime assumption:** local or self-hosted open-weight model runtime such as Ollama,
  llama.cpp, or vLLM

Closed-source models are not allowed for benchmark scoring.

## MacBook M4 Air Model Matrix

`model_matrix.json` defines the first real-runtime sweep for a 24 GB MacBook M4 Air.
It uses Ollama, runs models sequentially, and defaults to `model_driven` trace mode so
model-authored claims create the scored trace events:

| Family | Model | Approx size | Role |
|---|---|---:|---|
| Qwen | `qwen2.5-coder:7b` | 4.7 GB | coding/tool-use baseline |
| Llama | `llama3.2:3b` | 2.0 GB | small instruction-following baseline |
| Mistral | `mistral:7b` | 4.4 GB | general instruction/function-calling baseline |
| DeepSeek | `deepseek-r1:8b` | 5.2 GB | reasoning-heavy baseline |
| Gemma | `gemma3:4b` | 3.3 GB | compact multilingual reasoning baseline |
| Phi | `phi4-mini:latest` | 2.5 GB | small reasoning-dense baseline |

Use:

```bash
python3 scripts/agent_memory.py matrix-list
python3 scripts/agent_memory.py matrix --out runs/model-matrix-m4-air --pull-missing --trace-mode model_driven --minimum-successful-models 5 --fail-under-minimum
```

The matrix runner disables deterministic fallback. Missing local models are skipped unless
`--pull-missing` is set, and only `succeeded` rows count as real-runtime evidence. Use
`--trace-mode scripted` only for deterministic trace-shape regression checks.

## Completed Local Checkpoint

On 2026-06-04, the configured matrix ran successfully on the user's MacBook M4 Air:

- Manifest: `/tmp/agent-memory-model-matrix-m4air-5llm/model_matrix_manifest.json`
- Summary: `/tmp/agent-memory-model-matrix-m4air-5llm/model_matrix_summary.md`
- Report: `research/reports/model_matrix_m4air_20260604.md`
- Result: 6 successful models, 12 real Ollama run artifacts, 6 comparison artifacts

The completed run used one bounded seed task, `coding_stale_tests_001`, with `--max-tokens 64`
and the earlier scripted trace path. Future empirical runs should use `model_driven`,
sweep the full task set, and add full framework adapters.

## Completed Pressure Checkpoint

On 2026-06-04, the matrix also ran with model-authored pressure traces:

- Manifest: `/tmp/agent-memory-pressure-matrix-m4air-5llm/model_matrix_manifest.json`
- Summary: `/tmp/agent-memory-pressure-matrix-m4air-5llm/model_matrix_summary.md`
- Report: `research/reports/model_driven_pressure_m4air_20260604.md`
- Result: 6 successful models with `trace_mode=model_driven` and `prompt_template=memory_pressure_v0`
- Concrete finding: `gemma3:4b` treated stale compressed test evidence as sufficient and verification blocked `report_tests_pass`
