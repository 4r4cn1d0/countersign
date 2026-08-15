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
`research/reports/model_driven_pressure_m4air_20260604.md`. The Gemma 4 12B local
attempt is recorded in `research/reports/gemma4_12b_local_attempt_20260604.md`.
The first real external-agent-framework checkpoint is recorded in
`research/reports/langgraph_qwen_real_agent_20260604.md`. The first five-model,
all-seed-task LangGraph comparison is recorded in
`research/reports/langgraph_5model_alltasks_comparison_20260604.md`.

At this checkpoint, the MVP is ready as a MATS-style application/demo artifact: it has a
safety motivation, deterministic open-source-style benchmark harness, terminal CLI,
generated artifact bundle, verification intervention, dashboard inspection layer, and
passing backend/frontend/research tests.

It is not yet a finished empirical result about real open-source LLM agents. Since the
June 4 checkpoint, the coding path has become a model-driven LangGraph loop with real
file reads/writes, test execution, independent hidden evaluation, controlled model-visible
memory treatments, and non-intervening task-state probes. Browser, source-fetch, and
data-analysis task environments remain future work.

The June 11 implementation checkpoint contained 10 tasks, including 8 coding tasks and 4
fixture-backed repositories. Eight memory conditions are available as a first-class matrix
axis. A real `devstral-small-2:24b` run completed 8 valid actions with evaluator success,
and a live 768-token shadow probe produced parseable state JSON with `0.9333` accuracy.

The suite has since grown to 13 tasks — 11 coding tasks, all backed by checked-in fixture
repositories with hidden validators and fixture-authored `completion_policy` ground-truth
metadata, labeled `evaluation_split: development`. Five intervention conditions
(`memory_baseline`, `observe_only`, `verification_only`, `repair_only`,
`verification_and_repair`) run with identical prompts, raw-versus-enforced verifier
decisions, and predeclared pairwise comparisons. Held-out evaluation tasks remain future
work — see `research/ROADMAP_HELD_OUT_EVALUATION.md`.

## Real-Runtime Model Matrix

The next empirical upgrade is a local Ollama model matrix for a MacBook M4 Air with 24 GB
RAM. The configured matrix lives in `research/agents/model_matrix.json` and currently
targets seven sequentially-run model backends:

- `qwen2.5-coder:7b`
- `llama3.2:3b`
- `devstral-small-2:24b`
- `deepseek-r1:8b`
- `gemma3:4b`
- `gemma4:12b-mlx`
- `phi4-mini:latest`

This satisfies the requirement for at least five different model families while leaving
extra rows if a model is unavailable or too slow locally. Gemma 4 12B MLX is included as a
larger, newer Gemma-family stress test for local agentic reasoning and long-context
pressure; it should be run sequentially and reported separately if thermal or memory
pressure makes it slow. The Ollama registry currently exposes `gemma4:12b-mlx` as the
12B Apple Silicon tag; `gemma4:latest` is the E4B default row and should not be treated
as 12B evidence. These runs use the same custom
ReAct-style harness across model backends. The configured default is now `model_driven`
trace mode, where model-authored JSON claims create trace events that are scored against
provenance and verification rules. The older `scripted` mode remains available for
deterministic regression tests and should be labeled as such. The first LangGraph adapter
and coding-focused tool loop are implemented. Later phases should add source/browser/data
environments and a second framework adapter.

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

Run a single heavyweight configured model:

```bash
python3 scripts/agent_memory.py matrix \
  --out runs/gemma4-pressure \
  --model gemma4:12b-mlx \
  --pull-missing \
  --trace-mode model_driven \
  --prompt-template memory_pressure_v0 \
  --minimum-successful-models 1 \
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

Gemma 4 12B checkpoint:
The initial `/tmp/agent-memory-gemma4-12b-attempt-m4air/model_matrix_manifest.json`
reported 0 successful rows because Ollama `0.24.0` could not pull the tag. After
installing Homebrew Ollama `0.30.4`, `gemma4:12b-mlx` pulled successfully and ran through
LangGraph. `/tmp/agent-memory-langgraph-gemma4-12b-real-agent-m4air/model_matrix_manifest.json`
reports 1 successful Gemma 4 12B row. However, the benchmark response was `unparsed`
because Gemma spent the generation budget in `thinking` and returned empty final content,
even with a 1024-token baseline probe. This is real runtime evidence but not yet a useful
memory-corruption trace.

Real LangGraph checkpoint:
`/tmp/agent-memory-langgraph-5model-real-agents-m4air/model_matrix_manifest.json` reports
5 successful rows for `framework=langgraph`, `trace_mode=model_driven`, and
`prompt_template=memory_pressure_v0`. The generated traces contain LangGraph nodes for
goal intake, memory loading, model call, and trace emission. The five-model run covered
Qwen, Llama, Mistral, Gemma, and Phi. Mistral and Phi produced clean JSON, Llama required
JSON repair, and Qwen/Gemma were unparsed at the shorter token cap. None made a high-risk
completion claim on the first stale-test pressure task.

First-five all-task LangGraph comparison:
`/tmp/agent-memory-langgraph-5model-alltasks-m4air/model_matrix_manifest.json` reports
5 successful local model rows across all three seed tasks: `coding_stale_tests_001`,
`repo_audit_done_claims_001`, and `research_source_tracking_001`. The counted models are
`qwen2.5-coder:7b`, `llama3.2:3b`, `mistral:7b`, `gemma3:4b`, and `phi4-mini:latest`.
The run generated 30 run artifacts, 15 verification artifacts, 15 score artifacts, and
15 baseline-vs-verified comparison artifacts with zero model-row errors. The analysis
report shows 15 baseline task rows, parse status counts `json:11`, `json_repaired:2`,
`unparsed:2`, 29 parsed claims, 19 high-risk labels, and 19 blocked verification actions.
This remains the strongest completed multi-model comparison artifact, while the newer
10-task tool-loop and Devstral checkpoints are currently single-model or deterministic
implementation evidence rather than a completed five-model result.

Coding tool-loop checkpoint:
`framework=langgraph_tools` now runs a coding-focused LangGraph StateGraph loop over an
isolated parser workspace. The loop performs real file listing, file reading, file writing,
and `python -m unittest discover -s .` execution, records an evidence ledger, emits stale
pre-edit test-pass/task-complete claims, and reruns tests after the final edit. Smoke
artifact: `/tmp/agent-memory-langgraph-tools-coding-smoke/coding_stale_tests_001_baseline.json`.
This is the first real file/test tool path, but it is not yet a five-model tool-agent
matrix and it does not yet include source/browser/data-analysis tools.

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

## Execution Plan to Submission (locked 2026-08-16)

Target: Managing Agents that Manage Agents (NeurIPS 2026) — 4-page Short
Paper + Demo Track. Deadline August 29, 2026 AoE. Venue facts, framing,
and checklists live in `.claude/skills/neurips-workshop-submission/SKILL.md`;
predeclared experiment settings live in
`research/ROADMAP_HELD_OUT_EVALUATION.md` §11.

### Phase 1 — Finish the build (assistant; Aug 16–19)

1. **Relevance-aware online staleness — the critical path, ~1–2 days.**
   The supervisor currently treats *any* later write as invalidating
   cited test evidence. Extend the staleness check to use the
   `covered_files`/`covered_symbols` already recorded on test events: a
   cited test goes stale only when a later mutation intersects its
   coverage; returns `fresh`/`stale`/`uncertain`; stays independent of
   the oracle's fixture-authored ground truth. Unit tests for the two
   canonical cases (README edit stays fresh; tested-file edit goes
   stale). Everything downstream is meaningless without this — the
   negative controls would all be trivially blocked.
2. **Oracle-supervisor arm — ~half day.** The flagged evaluation-only
   condition where the gate consults the hidden validator: new
   `InterventionSpec`, explicit `oracle_gate` flag, firewall tests
   proving it cannot leak into any other arm,
   `CONTROLLER_POLICY_VERSION` bump.
3. **Held-out-v1 fixtures — ~1–2 days, with one user checkpoint.**
   Three matched pairs (temporal freshness, source provenance,
   requirement state) under the context-parity rule, plus the four
   negative controls; `completion_policy` and
   `evaluation_split: heldout_v1` from birth. Author one pair first,
   confirm the oracle emits sane non-`uncertain` labels and a
   deterministic smoke run behaves, **then** commit to all six. User
   checkpoint: a 15-minute review of the pair designs before finalizing
   — the last point where change is cheap.
4. **Strict freeze — ~half day, target Aug 19.** Frozen protocol with
   both fixture-tree hashes, strict-mode checks (clean tree, resolved
   policy hashes, model digests), the 380-run schedule, and a tagged
   commit. After this, verifier/oracle logic is immutable; any change
   means held-out-v2.

### Phase 2 — Compute (user's RunPod + assistant babysitting; Aug 19–21)

5. **Pod bring-up (~1 hour).** Clone at the frozen tag, install via the
   CI recipe (it is the Linux install script), `ollama pull` the
   models, record digests. User decision: GPU choice — an A100 80GB
   (~$1.2–2/hr) keeps the 32B fallback viable; total spend $10–40.
6. **Calibration at final settings** (temperature 0.7, seeds 0–4,
   development fixtures only): `qwen2.5-coder:14b`,
   `devstral-small-2:24b`, predeclared fallback ladder to 32B. A few
   hours. Models that clear the floor proceed; no post-hoc shopping.
7. **The 380-run matrix.** One environment, checkpoint/resume armed,
   roughly overnight on one pod (half that on two). Then
   `matrix-audit`, pull the bundle off the pod, verify `valid: true`
   from the copy.

### Phase 3 — Analysis + human validation (Aug 21–24)

8. **Reports and figures** (assistant): `matrix-report`, pairwise
   stats, per-comparison aggregates, supervisor-failure analyses
   (over-blocking, liveness failure after repeated blocks, worker
   adaptation), figures via academic-plotting, honesty pass via
   statistical-analysis.
9. **Blinded human validation — the one item only humans can do.**
   `validation-sample` from the final manifest → user (+ ideally a
   second rater) labels the blinded CSVs, ~half a day of human time →
   `validation-agreement` → decide whether oracle agreement justifies
   promoting `accepted_oracle_unsupported_finish_trial` to primary.
   User decision: second rater, or predeclare single-rater as a stated
   limitation now, not after.

### Phase 4 — Paper + demo (Aug 24–28; pages 1–2 can start during Phase 2)

10. **The 4-page Short Paper**: NeurIPS 2026 workshop template,
    supervisory framing throughout, drafted via ml-paper-writing,
    related work via paper-lookup. Title and abstract opening are
    locked in the project skill.
11. **The responsible-use statement** — the desk-rejection item.
    Drafted early, alongside the intro, not at the deadline.
12. **Demo-track material**: the paired live trajectory (same
    worker/task/seed, supervisor on vs off, hidden evaluation revealed
    only at termination).
13. **Internal review, Aug 28**: academic-paper-reviewer 5-seat panel +
    peer-review claims-vs-evidence pass; fix what they catch.

### Phase 5 — Package + submit (Aug 28–29 AoE)

14. **Anonymized artifact** from the relocatable bundle: scrub
    `spiderishi`/`4r4cn1d0`/paths/repo links, third-person
    self-citations, `matrix-audit` green from inside the copy,
    deprecated reports excluded.
15. **OpenReview upload** with margin before the AoE cutoff. User item:
    an OpenReview account that is not identity-linked in the submission
    itself.

### User decision list (in order of when they bite)

| When | Decision |
|---|---|
| ~Aug 18 | 15-min review of held-out pair designs (last cheap change) |
| Aug 19 | RunPod go + GPU choice |
| Aug 22 | Second rater: who, or predeclare single-rater |
| Aug 24 | Oracle-endpoint promotion (informed by kappa) |
| Aug 28 | Final read + submit authority |

Slack in the plan: about 2 days, all of it consumed if calibration
forces the 32B fallback *and* fixture authoring hits surprises. The two
failure modes with pre-agreed answers: models fail calibration →
fallback ladder, honest single-model limitation if needed; repair does
not recover tasks → reported as the negative result, which this venue
explicitly welcomes.
