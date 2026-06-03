# Research Plan: Long-Horizon Agent Memory Corruption

## Thesis

Open-source AI agents working on long-horizon tasks can develop memory corruption patterns
that resemble confabulation, source-monitoring failure, and semantic drift. These failures
can cause agents to make false claims, repeat work, act on stale evidence, or mark tasks as
complete without proof.

The goal is to measure those failures and reduce them using memory-verification mechanisms.

This project is terminal-first. The primary artifact should be a reproducible CLI and saved
run/report files; the frontend is an inspection and demo layer after the empirical workflow
works from the command line.

## Current MVP Checkpoint

The current implementation-backed checkpoint is recorded in
`research/reports/mvp_checkpoint_20260604.md`. The first local real-runtime model matrix
checkpoint is recorded in `research/reports/model_matrix_m4air_20260604.md`. The first
model-driven pressure checkpoint is recorded in
`research/reports/model_driven_pressure_m4air_20260604.md`.

At this checkpoint, the MVP is ready as a MATS-style application/demo artifact: it has a
safety motivation, deterministic open-source-style benchmark harness, terminal CLI,
generated artifact bundle, verification intervention, dashboard inspection layer, and
passing backend/frontend/research tests.

It is not yet a finished empirical result about real open-source LLM agents. The checkpoint
bundle is deterministic harness output; real Ollama or llama.cpp runs must be generated and
labeled separately before making model-performance claims.

## Real-Runtime Model Matrix

The next empirical upgrade is a local Ollama model matrix for a MacBook M4 Air with 24 GB
RAM. The configured matrix lives in `research/agents/model_matrix.json` and currently
targets six sequentially-run model backends:

- `qwen2.5-coder:7b`
- `llama3.2:3b`
- `mistral:7b`
- `deepseek-r1:8b`
- `gemma3:4b`
- `phi4-mini:latest`

This satisfies the requirement for at least five different model families while leaving
one spare if a model is unavailable or too slow locally. These runs use the same custom
ReAct-style harness across model backends. The configured default is now `model_driven`
trace mode, where model-authored JSON claims create trace events that are scored against
provenance and verification rules. The older `scripted` mode remains available for
deterministic regression tests and should be labeled as such. A later phase should add
full LangGraph, AutoGen, CrewAI, OpenHands/SWE-agent, or non-deterministic ReAct adapters.

Run the configured matrix:

```bash
python3 scripts/agent_memory.py matrix-list
python3 scripts/agent_memory.py matrix \
  --out runs/model-matrix-m4-air \
  --pull-missing \
  --trace-mode model_driven \
  --minimum-successful-models 5 \
  --fail-under-minimum \
  --format json
```

Only `succeeded` model rows count as real-runtime evidence. Skipped rows mean the model
was not available locally; failed rows mean the runtime or model call failed. Deterministic
fallback is disabled for matrix runs.

Completed local checkpoint: `/tmp/agent-memory-model-matrix-m4air-5llm/model_matrix_manifest.json`
reports 6 successful Ollama model rows, 12 run artifacts, 6 comparison artifacts, and
`meets_minimum_successful_models=true` for `coding_stale_tests_001`; that checkpoint used
the earlier scripted trace path. The next checkpoint should use `trace_mode=model_driven`
and report parse success/failure counts for model-authored claims.

Completed model-driven pressure checkpoint:
`/tmp/agent-memory-pressure-matrix-m4air-5llm/model_matrix_manifest.json` reports 6
successful Ollama model rows using `prompt_template=memory_pressure_v0`. Gemma 3 4B
produced an unsupported stale test-pass claim from compressed memory, and verification
blocked `report_tests_pass`.

License note: several candidate models are open-weight rather than OSI open-source. For
publication, report exact model tags and licenses separately.

## Scope

This project will use only open-source agent frameworks and open-source LLMs.

Candidate agent frameworks:

- LangGraph agents
- AutoGen agents
- CrewAI agents
- OpenHands or SWE-agent style coding agents
- Custom ReAct-style agents where framework control is useful

Candidate model families:

- Llama
- Qwen
- Mistral / Mixtral
- DeepSeek open models
- Gemma
- Phi

The exact model set should be chosen based on local or hosted open-weight availability and
repeatability.

## Failure Taxonomy

The benchmark should track agent memory failures across these categories:

- **Semantic drift:** the agent's working goal changes meaning over time.
- **Episodic loss:** the agent forgets earlier events, decisions, failures, or user instructions.
- **Source confusion:** the agent remembers a claim but loses whether it came from a user,
  tool output, retrieved document, code inspection, or its own inference.
- **Temporal disordering:** the agent treats old evidence as newer than later changes.
- **Tool-result confabulation:** the agent invents or mutates tool results.
- **False completion:** the agent marks a task done without implementation and verification evidence.
- **Confabulated continuity:** after context pressure or summarization, the agent fills gaps with
  plausible but unsupported task history.

## Long-Horizon Task Design

Evaluation tasks should be long enough to pressure memory and planning:

- Multi-file coding tasks with tests and changing requirements.
- Debugging tasks where earlier test results become stale after edits.
- Research tasks requiring source tracking and synthesis over many documents.
- Data-analysis tasks with iterative hypotheses and intermediate results.
- Multi-step web or repo investigation tasks with delayed verification.

Each task should have ground-truth checkpoints:

- Original user goal.
- Required subtasks.
- Tool outputs and timestamps.
- File or environment state changes.
- Which claims are supported, unsupported, stale, or contradicted.
- Whether task completion is actually justified.

## Metrics

Primary metrics:

- **Goal fidelity:** similarity between current agent goal representation and original objective.
- **Task-state accuracy:** correctness of done, pending, blocked, and failed subtask claims.
- **Evidence attribution accuracy:** whether remembered claims cite the right source type.
- **Temporal accuracy:** whether the agent correctly distinguishes stale vs recent evidence.
- **Semantic drift score:** how far agent summaries/plans drift from ground-truth task state.
- **False completion rate:** how often the agent claims or marks completion without proof.
- **Recovery rate:** how often verification detects and repairs corrupted memory before action.

Outcome metrics:

- Long-horizon task success rate.
- Number of repeated or wasted actions.
- Number of unsafe or unsupported user-facing claims.
- Verification overhead in extra tool calls, time, and tokens.

## Verification Mechanisms

The intervention layer should verify memory claims before they influence high-risk actions.

Mechanisms to implement:

- **Provenance tracking:** every memory claim records its source, timestamp, and confidence.
- **Uncertainty gating:** unsupported or low-confidence claims trigger verification before use.
- **Retrieval-consistency scoring:** compare recalled claims with trace history, retrieved records,
  tool outputs, and current repository state.
- **Reality-monitoring classification:** classify each claim as user-provided, tool-observed,
  retrieved, inferred, summarized, or unsupported.
- **Staleness checks:** invalidate claims when files, tests, tasks, or environment state changed
  after the supporting evidence.
- **Action-risk policy:** require stronger evidence for actions like marking tasks done, reporting
  test success, deleting files, submitting PRs, or making claims to the user.

## Terminal Workflow

The research MVP should be usable without the web frontend:

```bash
agent-memory run --task coding_stale_tests_001 --agent react_custom --model qwen2.5-coder:7b
agent-memory score --run runs/coding_stale_tests_001.json
agent-memory verify --run runs/coding_stale_tests_001.json
agent-memory compare --baseline runs/baseline.json --verified runs/verified.json
```

CLI outputs should support JSON for scripts, Markdown for writeups, and concise terminal
tables for fast inspection.

## Demo MVP

The demo should show a baseline agent and a verification-augmented agent on the same
long-horizon task.

Minimum demo flow:

1. Run an open-source agent on a multi-step task.
2. Capture the full trace in the observability backend.
3. Display memory claims, sources, tool results, and task-state assertions.
4. Highlight detected drift or unsupported completion claims.
5. Run the same task with verification enabled.
6. Compare false completion, semantic drift, and task success.

The demo should include a terminal-first path before the dashboard path: run, score, verify,
compare, then inspect the same artifacts in the dashboard.

## Relationship To The Existing Platform

The observability backend, SDK, WebSocket stream, and dashboard are the infrastructure layer.
The research contribution sits above them:

- benchmark task generation,
- trace labeling,
- memory health metrics,
- verification policies,
- and before/after evaluation.

## MATS-Style Readiness Target

The project should read as empirical technical AI safety research, not merely agent tooling.
The minimum application-ready artifact should include:

- a safety motivation and threat model for long-horizon agent memory corruption,
- a reproducible open-source benchmark and terminal runner,
- baseline vs verification-augmented results,
- metrics for false completion, source confusion, stale evidence, semantic drift, and task-state accuracy,
- a clear intervention with ablations planned,
- limitations that distinguish deterministic harness results from real open-source LLM agent results,
- and next experiments for LangGraph, AutoGen, CrewAI, OpenHands/SWE-agent, or ReAct-style agents.
