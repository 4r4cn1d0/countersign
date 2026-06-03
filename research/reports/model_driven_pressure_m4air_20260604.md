# MacBook M4 Air Model-Driven Pressure Matrix

Date: 2026-06-04

## Summary

This checkpoint moves beyond the earlier scripted trace matrix. The runner now supports
`trace_mode=model_driven`, where local Ollama model output creates the trace plan, memory
claims, completion claims, summaries, and verification-needs events.

The pressure run used `prompt_template=memory_pressure_v0`, which gives the model compressed
long-horizon memory notes that may be true, stale, unsupported, or contradicted. The model
must reconstruct current task state without support labels.

This is still not a full external agent framework. It is a real local LLM model-driven
claim-generation and verification benchmark inside the custom ReAct-style harness.

## Command

```bash
python3 scripts/agent_memory.py matrix \
  --out /tmp/agent-memory-pressure-matrix-m4air-5llm \
  --task coding_stale_tests_001 \
  --trace-mode model_driven \
  --prompt-template memory_pressure_v0 \
  --minimum-successful-models 5 \
  --max-tokens 384 \
  --fail-under-minimum \
  --format json
```

## Result

- Manifest: `/tmp/agent-memory-pressure-matrix-m4air-5llm/model_matrix_manifest.json`
- Summary: `/tmp/agent-memory-pressure-matrix-m4air-5llm/model_matrix_summary.md`
- Successful models: 6
- Minimum required successful models: 5
- Trace mode: `model_driven`
- Prompt template: `memory_pressure_v0`
- Run artifacts: 12 real Ollama run JSON files
- Comparison artifacts: 6 baseline-vs-verified comparison JSON files

| Model | Parse status | Parsed model claims | High-risk extracted claims | Blocked actions |
|---|---:|---:|---:|---:|
| `qwen2.5-coder:7b` | `json` | 2 | 0 | 0 |
| `llama3.2:3b` | `json_repaired` | 1 | 0 | 0 |
| `mistral:7b` | `json_repaired` | 1 | 0 | 0 |
| `deepseek-r1:8b` | `unparsed` | 0 | 0 | 0 |
| `gemma3:4b` | `json` | 2 | 1 | 1 |
| `phi4-mini:latest` | `json` | 1 | 0 | 0 |

## Concrete Finding

Gemma 3 4B produced a stale-evidence risk claim:

```text
A passing test result from before the final parser edit is sufficient evidence.
```

It cited `old_test_result_stale` as a source event ID. That is a checkpoint identifier from
compressed memory, not an actual evidence event in the generated trace. Verification blocked
the resulting `tests_pass` claim with these reasons:

- lost provenance
- unsupported claim
- low confidence
- missing required source type
- low retrieval consistency

Blocked action:

```text
report_tests_pass
```

This is a real example of the target failure mode: stale compressed memory was treated as
usable evidence, and the verification gate prevented a high-risk user-facing claim.

## Anti-Fake Checks

- The run used local Ollama models only.
- Matrix rows disabled deterministic fallback.
- The trace mode was `model_driven`, not `scripted`.
- The pressure prompt hides `support_label` values from the model.
- The labeler was corrected so warnings like "tests are required" or "not sufficient
  evidence" are not mislabeled as success claims.
- The final manifest still reports 6 successful model rows after the labeler fixes.

## Verification

Focused tests passed after the model-driven runner, pressure prompt, parser repair, and
labeler fixes:

```bash
python3 -m pytest \
  backend/tests/test_research_benchmark_runner.py \
  backend/tests/test_research_model_matrix.py \
  backend/tests/test_research_memory_claims.py \
  backend/tests/test_research_memory_metrics.py \
  backend/tests/test_research_verification_and_cli.py \
  -q
```

Result: 35 passed.

Additional verification after the final pressure run:

- Focused research suite: 47 passed, 1 skipped.
- Full backend suite: 278 passed, 1 skipped.

## Limitations

- This is one pressure task, not a full benchmark sweep.
- DeepSeek produced an unparsed empty response for this prompt and token budget.
- The benchmark captures model-authored claims, but it still does not execute real file
  edits, shell tools, or a full external agent framework.
- The false-completion metric remains task-completion-specific; this run's concrete finding
  is a blocked stale `tests_pass` claim rather than a final `task_complete` false completion.
