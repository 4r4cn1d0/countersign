# Agent Memory Model Matrix Analysis

- Manifest: `/private/tmp/agent-memory-langgraph-5model-alltasks-m4air/model_matrix_manifest.json`
- Framework: `langgraph`
- Runtime: `ollama`
- Trace mode: `model_driven`
- Prompt template: `memory_pressure_v0`
- Successful models: `5`
- Tasks: `3`

## Model Summary

| Model | Status | Tasks | Parse Statuses | Claims | High-Risk | Blocked | Avg Health | Avg Drift |
|---|---:|---:|---|---:|---:|---:|---:|---:|
| `qwen2.5-coder:7b` | `succeeded` | 3 | json:3 | 4 | 3 | 3 | 0.7660 | 0.7694 |
| `llama3.2:3b` | `succeeded` | 3 | json:1, json_repaired:2 | 10 | 6 | 6 | 0.6166 | 0.6447 |
| `mistral:7b` | `succeeded` | 3 | json:2, unparsed:1 | 4 | 2 | 2 | 0.8184 | 0.5596 |
| `gemma3:4b` | `succeeded` | 3 | json:3 | 6 | 4 | 4 | 0.6035 | 0.7527 |
| `phi4-mini:latest` | `succeeded` | 3 | json:2, unparsed:1 | 5 | 4 | 4 | 0.8010 | 0.5459 |

## Task Rows

| Model | Task | Parse | Claims | High-Risk | Blocked | Health | Drift |
|---|---|---:|---:|---:|---:|---:|---:|
| `qwen2.5-coder:7b` | `coding_stale_tests_001` | `json` | 2 | 0 | 0 | 0.8448 | 0.6207 |
| `qwen2.5-coder:7b` | `repo_audit_done_claims_001` | `json` | 0 | 1 | 1 | 0.7742 | 0.9032 |
| `qwen2.5-coder:7b` | `research_source_tracking_001` | `json` | 2 | 2 | 2 | 0.6789 | 0.7843 |
| `llama3.2:3b` | `coding_stale_tests_001` | `json_repaired` | 1 | 0 | 0 | 0.8636 | 0.5455 |
| `llama3.2:3b` | `repo_audit_done_claims_001` | `json_repaired` | 5 | 3 | 3 | 0.2935 | 0.8261 |
| `llama3.2:3b` | `research_source_tracking_001` | `json` | 4 | 3 | 3 | 0.6927 | 0.5625 |
| `mistral:7b` | `coding_stale_tests_001` | `json` | 1 | 0 | 0 | 0.7954 | 0.8182 |
| `mistral:7b` | `repo_audit_done_claims_001` | `json` | 3 | 2 | 2 | 0.6599 | 0.8605 |
| `mistral:7b` | `research_source_tracking_001` | `unparsed` | 0 | 0 | 0 | 1.0000 | 0.0000 |
| `gemma3:4b` | `coding_stale_tests_001` | `json` | 2 | 1 | 1 | 0.5682 | 0.7273 |
| `gemma3:4b` | `repo_audit_done_claims_001` | `json` | 2 | 1 | 1 | 0.5513 | 0.7949 |
| `gemma3:4b` | `research_source_tracking_001` | `json` | 2 | 2 | 2 | 0.6910 | 0.7358 |
| `phi4-mini:latest` | `coding_stale_tests_001` | `json` | 1 | 0 | 0 | 0.7917 | 0.8333 |
| `phi4-mini:latest` | `repo_audit_done_claims_001` | `unparsed` | 0 | 0 | 0 | 1.0000 | 0.0000 |
| `phi4-mini:latest` | `research_source_tracking_001` | `json` | 4 | 4 | 4 | 0.6114 | 0.8043 |

## Aggregate

- `successful_models`: `5`
- `baseline_task_rows`: `15`
- `parse_status_counts`: `{'json': 11, 'json_repaired': 2, 'unparsed': 2}`
- `total_parsed_claims`: `29`
- `total_high_risk_labels`: `19`
- `total_blocked_actions`: `19`
- `avg_memory_health_score`: `0.7211`
- `avg_semantic_drift_score`: `0.6544`
- `blocked_actions_by_model`: `{'gemma3:4b': 4, 'llama3.2:3b': 6, 'mistral:7b': 2, 'phi4-mini:latest': 4, 'qwen2.5-coder:7b': 3}`

## Limitations

- Runs use the configured agent framework and local model runtime.
- Only succeeded real-runtime rows count as model evidence.
- Skipped rows usually mean the model is not pulled locally.
- LangGraph rows execute a real StateGraph, but the current graph uses bounded benchmark memory/tool nodes rather than arbitrary shell or browser tools.
