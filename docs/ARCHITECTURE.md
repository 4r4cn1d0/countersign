# Architecture

Agent Memory Observatory has two connected layers:

- An observability platform for collecting and inspecting agent traces.
- A research workflow for turning those traces into memory-corruption evidence.

## System Map

```text
Agent or benchmark run
  -> trace events
  -> backend API / saved JSON artifacts
  -> memory-claim extraction
  -> memory health metrics
  -> verification gates
  -> comparison reports
  -> dashboard and terminal reports
```

## Backend

The backend is a FastAPI service for operational trace observability:

- Session creation and lookup.
- Trace event ingestion.
- Batch ingestion.
- Session search.
- Execution graph endpoints.
- Metrics endpoints.
- WebSocket streaming.

It is useful for demos and dashboard inspection, while the research CLI can also operate
directly on saved JSON artifacts without requiring the full service to be running.

Related files:

- `backend/main.py`
- `backend/api/routes/`
- `backend/models/`
- `backend/services/`
- `backend/tests/`

## Frontend

The frontend is a React/TypeScript dashboard. It provides:

- Session list and trace inspection.
- Execution graph visualization.
- Reasoning and tool-call views.
- Research report inspection for memory health and verification outputs.

Related files:

- `frontend/src/`
- [Dashboard](DASHBOARD.md)

## SDK

The Python SDK is for instrumenting external agents and sending events to the backend.
It is separate from the benchmark runner. The benchmark runner creates reproducible
research artifacts; the SDK supports live/real application traces.

Related files:

- `sdk/agent_observability/`

## Research Runner

The research runner is the empirical core:

- Loads seed tasks from `research/benchmarks/seed_tasks.json`.
- Runs baseline and verified variants.
- Supports deterministic traces, model-driven traces, and bounded LangGraph runs.
- Extracts memory claims.
- Labels high-risk claims.
- Computes memory health metrics.
- Applies verification policy.
- Writes run, score, verification, comparison, bundle, and matrix artifacts.

Related files:

- `research/runner/benchmark_runner.py`
- `research/runner/claims.py`
- `research/runner/labeling.py`
- `research/runner/metrics.py`
- `research/runner/verification.py`
- `research/runner/comparison.py`
- `research/runner/artifacts.py`
- `research/runner/model_matrix.py`
- `research/runner/matrix_analysis.py`

## Agent Runtime Layer

The current real-agent runtime path uses:

- LangGraph as the external open-source agent framework.
- Ollama as the local model runtime.
- Local open-weight model rows from `research/agents/model_matrix.json`.

The current five-model LangGraph graph is bounded. It has graph nodes for goal intake,
memory loading, model call, and trace emission. The new `langgraph_tools` path adds a
coding-focused StateGraph loop with workspace setup, planning, tool choice, file reads,
file writes, test execution, evidence-ledger updates, verification events, and final trace
emission. Broader shell/git/browser/source-fetch tools remain future work.

Related docs:

- [Tool-Using Agents](TOOL_USING_AGENTS.md)
- [Open Model Matrix](OPEN_MODEL_MATRIX.md)

## Artifact Flow

Artifacts are designed to make "no faking" checks possible:

- `runs/` stores full baseline and verified run JSON.
- `scores/` stores memory health reports.
- `verifications/` stores verification decisions and blocked actions.
- `comparisons/` stores baseline-vs-verified deltas.
- `model_matrix_manifest.json` stores model rows, task IDs, run paths, and success counts.
- `model_matrix_summary.md` and matrix reports summarize results.

The CLI can regenerate reports from manifests, which makes the evidence inspectable after
the run is complete.

Related doc:

- [CLI and Artifacts](CLI_AND_ARTIFACTS.md)
