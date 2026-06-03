# Agent Memory Observatory

Research and tooling for studying memory corruption in long-horizon AI agents.

The project started as an agent observability platform for tracing tool calls, reasoning
steps, planning phases, memory access, and decision points. The current direction is to
use that observability foundation to study whether open-source AI agents develop
confabulation-like memory failures during long-horizon tasks, and whether verification
mechanisms can reduce semantic drift, false completion, and source confusion.

This is not a claim that AI agents literally have dementia. Dementia, confabulation, and
reality-monitoring neuroscience are used as modeling lenses for failure modes such as
episodic loss, source-attribution failure, temporal disordering, semantic drift, and
plausible-but-false reconstruction of task state.

## Research Goal

Measure and reduce memory corruption in open-source agents and open-source LLMs during
long-horizon tasks.

The target MVP/demo should show:

- Long-horizon agent traces with task state, tool outputs, summaries, and memory events.
- Detected memory failures such as stale test claims, false task completion, unsupported
  recalled facts, and semantic drift from the original goal.
- A verification layer that checks memory claims against provenance, recent tool evidence,
  source history, and current environment state before the agent acts or marks work done.
- Evaluation results comparing baseline agents against verification-augmented agents.

## Current MVP Foundation

The implemented foundation already supports the core observability needed for this
research:

- Backend trace ingestion and retrieval for agent sessions.
- TimescaleDB/PostgreSQL storage for session and trace history.
- Redis-backed event streaming.
- Python SDK instrumentation hooks.
- Frontend dashboard for sessions, execution graphs, reasoning traces, and tool calls.
- WebSocket support for live trace updates.

The next phase is to add research-specific memory corruption metrics, benchmarks,
verification policies, and demo tasks.

## Stack

- **Backend:** FastAPI, PostgreSQL + TimescaleDB, Redis Streams
- **Frontend:** React, TypeScript, Material UI, D3
- **SDK:** Python tracing SDK for agent instrumentation
- **Target agents/models:** open-source agent frameworks and open-source LLMs only

## Quick start

### 1. Infrastructure (Docker)

```bash
cd backend
docker compose up -d
```

Starts TimescaleDB, Redis, and MinIO.

### 2. Backend

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

API (debug mode): `http://localhost:8000/api/docs`

### 3. Tests

```bash
cd backend
pytest tests/ -q
```

Integration tests for the database schema require a running Postgres instance (`TEST_DATABASE_URL`).

## Python SDK

```bash
pip install -e sdk/
```

```python
from agent_observability import AgentTracer, trace_agent, trace_tool

tracer = AgentTracer(api_key="<JWT>", endpoint="http://localhost:8000")
tracer.start_session(agent_type="demo", goal="example run")
tracer.record_event({"event_type": "annotation", "text": "hello", "sequence_number": 1})
tracer.flush()
```

## WebSocket (real-time)

Connect to `ws://localhost:8000/api/v1/ws?token=<JWT>`, then send:

```json
{"type": "subscribe", "session_id": "<uuid>"}
```

Server responds with a snapshot and streams `{"type":"event",...}` as events are processed.

## API overview

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/v1/health` | Health check |
| POST | `/api/v1/sessions` | Create session |
| GET | `/api/v1/sessions/{id}` | Get session |
| GET | `/api/v1/sessions` | List sessions |
| POST | `/api/v1/sessions/search` | Search sessions |
| POST | `/api/v1/sessions/{id}/events` | Ingest events |
| POST | `/api/v1/sessions/{id}/events/batch` | Bulk ingest |
| GET | `/api/v1/sessions/{id}/trace` | Full trace |
| GET | `/api/v1/sessions/{id}/graph` | Execution graph |
| GET | `/api/v1/sessions/{id}/metrics` | Session metrics |
| GET | `/api/v1/metrics/aggregate` | Aggregate analytics |
| GET | `/api/v1/metrics/timeseries` | Time-series metrics |

All session/event/trace/metrics routes require `Authorization: Bearer <JWT>`. See `backend/AUTH_README.md`.

## Repository layout

```
├── backend/           # FastAPI service
│   ├── main.py
│   ├── api/routes/
│   ├── models/
│   ├── services/
│   ├── migrations/
│   └── tests/
├── scripts/           # Tooling (e.g. index_kiro.py)
├── index.json         # Indexed .kiro specs snapshot
└── pyproject.toml     # Lint/format config
```

## Specs

Authoritative product specs live under `.kiro/specs/agent-observability-platform/`:

- `tasks.md` — implementation plan and work log
- `requirements.md` / `design.md` — restore from backup or `index.json` if missing

Additional research framing:

- `RESEARCH_PLAN.md` — current long-horizon memory corruption research plan

Re-index the repo with:

```bash
python3 scripts/index_kiro.py --root . --out index.json
```

## License

See [LICENSE](LICENSE).
