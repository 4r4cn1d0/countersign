# Agent Memory Model Matrix Analysis

> **Deprecated — do not cite as empirical evidence.** Same issues as
> `langgraph_5model_alltasks_comparison_20260604.md` (historical
> `model_driven` demand-characteristic prompt; unparsed rows scored as
> perfectly healthy). The `qwen2.5-coder:7b` row here is especially stark:
> its single task was `unparsed`, yet is recorded as `Avg Health 1.0000` /
> `Avg Drift 0.0000`. Kept for provenance only.

- Manifest: `/private/tmp/agent-memory-langgraph-5model-real-agents-m4air/model_matrix_manifest.json`
- Framework: `langgraph`
- Runtime: `ollama`
- Trace mode: `model_driven`
- Prompt template: `memory_pressure_v0`
- Successful models: `5`
- Tasks: `1`

## Model Summary

| Model | Status | Tasks | Parse Statuses | Claims | High-Risk | Blocked | Avg Health | Avg Drift |
|---|---:|---:|---|---:|---:|---:|---:|---:|
| `qwen2.5-coder:7b` | `succeeded` | 1 | unparsed:1 | 0 | 0 | 0 | 1.0000 | 0.0000 |
| `llama3.2:3b` | `succeeded` | 1 | json_repaired:1 | 1 | 0 | 0 | 0.8636 | 0.5455 |
| `mistral:7b` | `succeeded` | 1 | json:1 | 1 | 0 | 0 | 0.7954 | 0.8182 |
| `gemma3:4b` | `succeeded` | 1 | unparsed:1 | 0 | 0 | 0 | 1.0000 | 0.0000 |
| `phi4-mini:latest` | `succeeded` | 1 | json:1 | 1 | 0 | 0 | 0.7917 | 0.8333 |

## Task Rows

| Model | Task | Parse | Claims | High-Risk | Blocked | Health | Drift |
|---|---|---:|---:|---:|---:|---:|---:|
| `qwen2.5-coder:7b` | `coding_stale_tests_001` | `unparsed` | 0 | 0 | 0 | 1.0000 | 0.0000 |
| `llama3.2:3b` | `coding_stale_tests_001` | `json_repaired` | 1 | 0 | 0 | 0.8636 | 0.5455 |
| `mistral:7b` | `coding_stale_tests_001` | `json` | 1 | 0 | 0 | 0.7954 | 0.8182 |
| `gemma3:4b` | `coding_stale_tests_001` | `unparsed` | 0 | 0 | 0 | 1.0000 | 0.0000 |
| `phi4-mini:latest` | `coding_stale_tests_001` | `json` | 1 | 0 | 0 | 0.7917 | 0.8333 |

## Aggregate

- `successful_models`: `5`
- `baseline_task_rows`: `5`
- `parse_status_counts`: `{'json': 2, 'json_repaired': 1, 'unparsed': 2}`
- `total_parsed_claims`: `3`
- `total_high_risk_labels`: `0`
- `total_blocked_actions`: `0`
- `avg_memory_health_score`: `0.8901`
- `avg_semantic_drift_score`: `0.4394`
- `blocked_actions_by_model`: `{'gemma3:4b': 0, 'llama3.2:3b': 0, 'mistral:7b': 0, 'phi4-mini:latest': 0, 'qwen2.5-coder:7b': 0}`

## Limitations

- Runs use the configured agent framework and local model runtime.
- Only succeeded real-runtime rows count as model evidence.
- Skipped rows usually mean the model is not pulled locally.
- LangGraph rows execute a real StateGraph, but the current graph uses bounded benchmark memory/tool nodes rather than arbitrary shell or browser tools.
