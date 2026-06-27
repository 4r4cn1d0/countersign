# Agent Memory Observatory

Terminal-first research and tooling for studying memory corruption in long-horizon AI
agents.

The core question is practical AI safety: when an open-source agent works across a long
task, does its memory of goals, evidence, tool results, sources, and completion state
degrade in ways that cause false claims or bad actions? The project measures those
failures and tests verification mechanisms that stop unsupported memory claims before the
agent acts on them.

This is not a claim that AI agents literally have dementia. Dementia, confabulation, and
reality-monitoring neuroscience are used as modeling lenses for source-monitoring failure,
semantic drift, temporal disordering, episodic loss, and plausible-but-false reconstruction
of task state.

## Current Status

The project is a working MVP/demo, not just a write-up.

- Backend/API: FastAPI trace ingestion, sessions, events, metrics, search, WebSocket stream.
- Frontend: React/TypeScript dashboard for sessions, execution graphs, reasoning traces,
  tool calls, and research report inspection.
- SDK: Python instrumentation hooks for agent traces.
- Research CLI: benchmark runs, scoring, verification, comparisons, artifact bundles,
  model matrices, and matrix reports.
- Real-agent path: bounded LangGraph benchmark graph using local Ollama models, plus a
  coding-focused LangGraph tool loop with real file and test tools.
- Benchmark suite: 10 long-horizon tasks, including 8 coding tasks and 8
  fixture-backed repositories with independent hidden validators.
- Controlled experiments: 8 model-visible memory conditions, canonical evaluator state,
  repeatable condition/seed pairing, and non-intervening task-state probes.
- Current Mistral path: `devstral-small-2:24b-ctx8k` is installed and has completed
  a real durable `langgraph_tools` recovery run. The verifier blocked four false
  finish claims and accepted zero false completions; the run exhausted its action
  budget before hidden evaluator success, so it is failure evidence rather than a
  solved recovery demo.

Latest verified test state:

- Research suite: 185 passed, 1 skipped.
- Full backend suite: database-backed integration tests require PostgreSQL/TimescaleDB
  outside the managed sandbox; the sandbox blocks localhost DB sockets.
- Frontend: 26 passed; production build succeeds.

## Historical Five-Model Result

The June 4, 2026 real-agent comparison used:

- `qwen2.5-coder:7b`
- `llama3.2:3b`
- `mistral:7b`
- `gemma3:4b`
- `phi4-mini:latest`

Artifact manifest:

```text
/tmp/agent-memory-langgraph-5model-alltasks-m4air/model_matrix_manifest.json
```

Report:

- [LangGraph five-model all-task comparison](research/reports/langgraph_5model_alltasks_comparison_20260604.md)

Aggregate result:

- 5 successful LangGraph/Ollama model rows.
- 3 seed tasks per model.
- 30 run artifacts.
- 15 verification artifacts.
- 15 score artifacts.
- 15 baseline-vs-verified comparisons.
- Parse statuses across baseline rows: `json:11`, `json_repaired:2`, `unparsed:2`.
- 29 parsed memory/task claims.
- 19 high-risk labels.
- 19 verification-blocked actions.

Gemma 4 12B MLX is installed and runnable, but it is not counted in the clean five-model
comparison yet because its current LangGraph run returned empty final content after using
the generation budget in `thinking`.

That comparison remains valid historical evidence, but it predates the current
fixture-backed coding suite, controlled memory conditions, and task-state probes.

## How We Make It a Full Tool-Using Agent

The present five-model LangGraph path is real framework execution, but it is still a
bounded benchmark graph: goal intake, memory loading, model call, trace emission, scoring,
and verification. The first coding-focused tool-loop upgrade is now implemented as
`--agent langgraph_tools`:

- A workspace sandbox per run.
- File read/write tools.
- Test execution tools.
- An evidence ledger that records every tool output and source timestamp.
- Verification gates before high-risk actions such as "tests pass", "task complete",
  or "file changed".

Broader source-fetch, browser, data-analysis, shell, and git tools remain future work.

Detailed implementation plan:

- [Tool-Using Agents](docs/TOOL_USING_AGENTS.md)

## Long-Horizon Tasks Are Not Only Coding

Coding is a useful first domain because stale tests and false completion are easy to
verify. It should not be the only domain. The benchmark should also include:

- Research synthesis with source tracking.
- Data analysis with stale intermediate results.
- Web or repository investigation with delayed verification.
- Literature review or policy review where citations matter.
- Operational planning where task-state drift matters.

Detailed task taxonomy:

- [Long-Horizon Tasks](docs/LONG_HORIZON_TASKS.md)
- [Benchmark Seed Tasks](research/benchmarks/README.md)

## Subsystem Docs

The main pieces are documented here:

- [Complete Implementation Reference](docs/IMPLEMENTATION_REFERENCE.md) - exhaustive,
  evidence-grounded description of the backend, SDK, frontend, benchmark, agent loop,
  memory model, verification, repair, experiments, tests, limitations, and remaining work.
- [Architecture](docs/ARCHITECTURE.md) - backend, frontend, SDK, research runner, agents,
  artifacts, and data flow.
- [Tool-Using Agents](docs/TOOL_USING_AGENTS.md) - how to move from bounded LangGraph to
  real shell/file/test/browser agents.
- [Long-Horizon Tasks](docs/LONG_HORIZON_TASKS.md) - coding and non-coding task families.
- [Memory Verification](docs/MEMORY_VERIFICATION.md) - claim extraction, provenance,
  scoring, and high-risk gates.
- [CLI and Artifacts](docs/CLI_AND_ARTIFACTS.md) - terminal commands, saved JSON, bundles,
  reports, and reproducibility.
- [Open Model Matrix](docs/OPEN_MODEL_MATRIX.md) - local model set, LangGraph/Ollama
  comparison, and Gemma 4 status.
- [Dashboard](docs/DASHBOARD.md) - frontend inspection layer and where it fits.
- [Research Plan](RESEARCH_PLAN.md) - thesis, current evidence, metrics, and next research
  steps.
- [Implementation Tasks](.kiro/specs/agent-observability-platform/tasks.md) - task log and
  completion evidence.

## Quick Start

Install optional real-agent dependencies:

```bash
python3 -m pip install --user -r research/agents/requirements-real-agents.txt
```

List configured local models:

```bash
python3 scripts/agent_memory.py matrix-list
```

Use the Ollama endpoint that is actually serving the target models. On a normal Ollama
setup this is usually `http://127.0.0.1:11434`; the successful local LangGraph sweep used
a temporary Desktop Ollama server on `http://127.0.0.1:11435`.

Run the first-five LangGraph comparison:

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

Generate a matrix report:

```bash
python3 scripts/agent_memory.py matrix-report \
  --manifest runs/langgraph-first-five/model_matrix_manifest.json \
  --out runs/langgraph-first-five/report.md \
  --format markdown
```

Run one benchmark task:

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

Run the coding-focused LangGraph tool loop:

```bash
python3 scripts/agent_memory.py run \
  --task coding_stale_tests_001 \
  --agent langgraph_tools \
  --runtime ollama \
  --runtime-endpoint http://127.0.0.1:11435 \
  --model-family mistral \
  --model devstral-small-2:24b \
  --trace-mode model_driven \
  --memory-condition temporal_corruption \
  --memory-pressure-start 2 \
  --task-state-probes \
  --probe-max-tokens 768 \
  --out runs/langgraph-tools-coding \
  --format json
```

Every `langgraph_tools` run writes a sibling `*.run-checkpoint.json` after
each graph node. If the process is interrupted, continue from the last durable
state without replaying completed model actions:

```bash
python3 scripts/agent_memory.py resume \
  --checkpoint runs/langgraph-tools-coding/workspaces/<run>.run-checkpoint.json \
  --out runs/langgraph-tools-coding/resumed.json \
  --format json
```

Resume verifies the checkpoint checksum, original run configuration, and exact
workspace content hash before continuing.

Run tests:

```bash
python3 -m pytest backend/tests/test_research_benchmark_seed.py \
  backend/tests/test_research_benchmark_runner.py \
  backend/tests/test_research_memory_claims.py \
  backend/tests/test_research_memory_metrics.py \
  backend/tests/test_research_verification_and_cli.py \
  backend/tests/test_research_runtime_and_bundle.py \
  backend/tests/test_research_model_matrix.py \
  backend/tests/test_research_memory_experiments.py -q

cd backend
python3 -m pytest -q
```

## Backend and Dashboard

Start infrastructure:

```bash
cd backend
docker compose up -d
```

Run backend:

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
python generate_keys.py
python migrations/run_migrations.py
python main.py
```

API docs in debug mode:

```text
http://localhost:8000/api/docs
```

Run frontend:

```bash
cd frontend
npm install
npm run dev
```

## Python SDK

```bash
pip install -e sdk/
```

```python
from agent_observability import AgentTracer

tracer = AgentTracer(api_key="<JWT>", endpoint="http://localhost:8000")
tracer.start_session(agent_type="demo", goal="example run")
tracer.record_event({"event_type": "annotation", "text": "hello", "sequence_number": 1})
tracer.flush()
```

## Repository Layout

```text
backend/                 FastAPI backend, data models, services, migrations, tests
frontend/                React dashboard and research report UI
sdk/                     Python tracing SDK
research/                Benchmark runner, verification, metrics, agents, reports
research/benchmarks/     Seed long-horizon memory-pressure tasks
research/agents/         Open model matrix and real-agent dependency notes
research/reports/        Generated research checkpoint reports
scripts/agent_memory.py  Terminal entrypoint for research workflows
docs/                    Subsystem documentation
.kiro/specs/...          Implementation plan, work log, requirements, design
```

## Limits To Be Honest About

- The strongest five-model evidence still uses bounded LangGraph memory/tool nodes.
- The new `langgraph_tools` mode uses real coding file/test tools, but only for coding
  tasks so far.
- The next phase needs model-matrix runs through `langgraph_tools` and additional real
  source/data/browser tools for non-coding long-horizon tasks.
- Local models are open-weight; licenses should be reported per model for publication.
- Gemma 4 12B MLX needs prompt/runtime tuning before it can be counted as parsed
  comparison evidence.

## License

See [LICENSE](LICENSE).
