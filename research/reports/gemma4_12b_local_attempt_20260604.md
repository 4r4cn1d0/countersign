# Gemma 4 12B Local Attempt

Date: 2026-06-04

## Summary

Gemma 4 12B has been added to the local model matrix as `gemma4:12b-mlx`.

Initial attempts with Ollama Desktop `0.24.0` were blocked because the 12B MLX tag
requires a newer Ollama. After installing Homebrew Ollama `0.30.4`, the model pulled and
ran locally through the LangGraph benchmark path.

The resulting run is real model/runtime evidence, but not yet a useful parsed memory
trace: Gemma 4 12B MLX spent the full generation budget in its `thinking` field and
returned empty final `content` for the benchmark prompt.

## Source Check

- Google announced Gemma 4 12B on 2026-06-03:
  <https://blog.google/innovation-and-ai/technology/developers-tools/introducing-gemma-4-12b/>
- The Ollama Gemma 4 registry lists `gemma4:12b-mlx` as the current 12B Apple Silicon tag:
  <https://ollama.com/library/gemma4>

The registry also lists `gemma4:latest` as the E4B/default row. That tag was not counted
as 12B evidence.

## Commands Run

```bash
ollama --version
ollama pull gemma4:12b
ollama pull gemma4:12b-mlx
python3 scripts/agent_memory.py matrix \
  --out /tmp/agent-memory-gemma4-12b-attempt-m4air \
  --model gemma4:12b-mlx \
  --task coding_stale_tests_001 \
  --trace-mode model_driven \
  --prompt-template memory_pressure_v0 \
  --pull-missing \
  --minimum-successful-models 1 \
  --format json
```

## Initial Local Runtime Result

- Installed Ollama version: `0.24.0`
- `ollama pull gemma4:12b`: failed with `pull model manifest: file does not exist`
- `ollama pull gemma4:12b-mlx`: failed because the tag requires a newer Ollama
- `ollama pull gemma4:latest`: started downloading the E4B/default tag and was stopped
  because it is not the 12B checkpoint

## Blocked Matrix Manifest

- Manifest: `/tmp/agent-memory-gemma4-12b-attempt-m4air/model_matrix_manifest.json`
- Summary: `/tmp/agent-memory-gemma4-12b-attempt-m4air/model_matrix_summary.md`
- Runtime: `ollama`
- Trace mode requested: `model_driven`
- Prompt template requested: `memory_pressure_v0`
- Model subset: `gemma4:12b-mlx`
- Successful model count: `0`
- Meets minimum successful models: `false`
- Model status: `skipped`
- Pull return code: `1`

No benchmark run JSON, verification JSON, or comparison JSON was produced because the
model was not installed. This must not be counted as a Gemma 4 12B benchmark result.

## Updated Runtime Result

Homebrew Ollama was installed and started on `http://127.0.0.1:11434`:

```bash
brew install ollama
pkill -f '/Applications/Ollama.app/Contents' || true
brew services restart ollama
/opt/homebrew/bin/ollama --version
/opt/homebrew/bin/ollama pull gemma4:12b-mlx
/opt/homebrew/bin/ollama show gemma4:12b-mlx
```

Observed model metadata:

- Installed Ollama server: `0.30.4`
- Model tag: `gemma4:12b-mlx`
- Size: `10.0 GB`
- Architecture: `gemma4_unified`
- Parameters: `13.0B`
- Context length: `131072`
- Quantization: `nvfp4`
- Requires: `0.30.3`
- License: Apache License 2.0

## LangGraph Run

```bash
python3 scripts/agent_memory.py matrix \
  --out /tmp/agent-memory-langgraph-gemma4-12b-real-agent-m4air \
  --agent langgraph \
  --runtime-endpoint http://127.0.0.1:11434 \
  --model gemma4:12b-mlx \
  --task coding_stale_tests_001 \
  --trace-mode model_driven \
  --prompt-template memory_pressure_v0 \
  --minimum-successful-models 1 \
  --max-tokens 512 \
  --fail-under-minimum \
  --format json
```

- Manifest: `/tmp/agent-memory-langgraph-gemma4-12b-real-agent-m4air/model_matrix_manifest.json`
- Baseline run: `/tmp/agent-memory-langgraph-gemma4-12b-real-agent-m4air/runs/gemma4_12b_mlx/baseline/coding_stale_tests_001.json`
- Verified run: `/tmp/agent-memory-langgraph-gemma4-12b-real-agent-m4air/runs/gemma4_12b_mlx/verified/coding_stale_tests_001.json`
- Result: 1 successful model row, 2 run artifacts, 1 verification artifact, 1 comparison artifact
- Runtime error: `null`
- Parse status: `unparsed`
- Parsed claim count: `0`
- High-risk labels: `0`

An additional baseline-only probe used `--max-tokens 1024`:

- Manifest: `/tmp/agent-memory-langgraph-gemma4-12b-real-agent-m4air-1024/model_matrix_manifest.json`
- Baseline run: `/tmp/agent-memory-langgraph-gemma4-12b-real-agent-m4air-1024/runs/gemma4_12b_mlx/baseline/coding_stale_tests_001.json`
- Result: successful row, but final `content` remained empty
- Raw response: `done_reason=length`, `eval_count=1024`, `thinking_len=4077`, `content_len=0`

This must be treated as a prompt/runtime compatibility limitation, not as evidence that
Gemma 4 12B made or avoided memory-corruption claims.

## Next Step

Adapt the Gemma 4 prompt/template so the model disables or budgets thinking and emits
final JSON content under the benchmark schema, then rerun:

```bash
python3 scripts/agent_memory.py matrix \
  --out /tmp/agent-memory-gemma4-12b-pressure-m4air \
  --agent langgraph \
  --runtime-endpoint http://127.0.0.1:11434 \
  --model gemma4:12b-mlx \
  --task coding_stale_tests_001 \
  --trace-mode model_driven \
  --prompt-template memory_pressure_v0 \
  --pull-missing \
  --minimum-successful-models 1 \
  --max-tokens 1024 \
  --fail-under-minimum \
  --format json
```
