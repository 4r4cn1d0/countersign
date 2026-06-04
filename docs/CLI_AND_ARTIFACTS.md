# CLI and Artifacts

The project is terminal-first. The dashboard is useful for demos, but the empirical
workflow should be reproducible from saved commands and JSON/Markdown artifacts.

## Entrypoint

```bash
python3 scripts/agent_memory.py --help
```

Available research commands:

- `run` - run one task or all benchmark tasks.
- `score` - score a saved run JSON.
- `verify` - apply verification gates to a saved run.
- `compare` - compare baseline and verified runs.
- `bundle` - generate a complete artifact bundle.
- `matrix-list` - list configured model rows.
- `matrix` - run tasks across configured models.
- `matrix-report` - analyze a model matrix manifest.

Use the Ollama endpoint that is actually serving the target local models. Most setups use
`http://127.0.0.1:11434`; the successful local five-model run used a temporary Desktop
Ollama server on `http://127.0.0.1:11435`.

## Single Task Run

```bash
python3 scripts/agent_memory.py run \
  --task coding_stale_tests_001 \
  --agent langgraph \
  --runtime ollama \
  --runtime-endpoint http://127.0.0.1:11434 \
  --model qwen2.5-coder:7b \
  --trace-mode model_driven \
  --prompt-template memory_pressure_v0 \
  --out runs/single-task \
  --format json
```

## Score and Verify

```bash
python3 scripts/agent_memory.py score \
  --run runs/single-task/coding_stale_tests_001.json \
  --out runs/single-task/score.json \
  --format json

python3 scripts/agent_memory.py verify \
  --run runs/single-task/coding_stale_tests_001.json \
  --out runs/single-task/verified.json \
  --format json
```

## Model Matrix

```bash
python3 scripts/agent_memory.py matrix \
  --out runs/langgraph-first-five \
  --agent langgraph \
  --runtime-endpoint http://127.0.0.1:11434 \
  --model qwen2.5-coder:7b \
  --model llama3.2:3b \
  --model mistral:7b \
  --model gemma3:4b \
  --model phi4-mini:latest \
  --trace-mode model_driven \
  --prompt-template memory_pressure_v0 \
  --minimum-successful-models 5 \
  --fail-under-minimum
```

Generate a report:

```bash
python3 scripts/agent_memory.py matrix-report \
  --manifest runs/langgraph-first-five/model_matrix_manifest.json \
  --out runs/langgraph-first-five/report.md \
  --format markdown
```

## Artifact Layout

A matrix run writes:

```text
model_matrix_manifest.json
model_matrix_summary.md
runs/<model>/<variant>/<task>.json
scores/<model>/<task>.json
verifications/<model>/<task>.json
comparisons/<model>/<task>.json
```

The manifest is the key audit file. It records:

- Runtime and framework.
- Prompt template and trace mode.
- Model names.
- Task IDs.
- Success counts.
- Minimum-success threshold.
- Paths to run and comparison artifacts.
- Limitations.

## No-Faking Rules

For matrix runs:

- Deterministic fallback is disabled.
- Missing local models are skipped unless `--pull-missing` is used.
- Failed runtime calls do not count as successful model evidence.
- `--fail-under-minimum` exits nonzero if the run does not meet the model-count bar.
- Reports are generated from saved manifests rather than hand-written summaries.

## Current Strongest Artifact

```text
/tmp/agent-memory-langgraph-5model-alltasks-m4air/model_matrix_manifest.json
```

Report:

```text
research/reports/langgraph_5model_alltasks_comparison_20260604.md
```
