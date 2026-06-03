# Agent Memory Observatory — Backend

FastAPI service for ingesting long-horizon agent traces, persisting them in TimescaleDB,
and exposing REST/WebSocket APIs for analysis.

The backend is the infrastructure layer for the current research direction: measuring
memory corruption, semantic drift, source confusion, stale evidence, and false completion
in open-source AI agents. Existing trace events already capture the raw material needed
for that work: reasoning steps, tool calls, planning phases, memory access, annotations,
and errors.

## Setup

1. Start dependencies:

```bash
docker compose up -d
```

2. Install and configure:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
python generate_keys.py
```

3. Migrate:

```bash
python migrations/run_migrations.py
```

4. Run:

```bash
python main.py
```

## Structure

```
backend/
├── main.py              # App entry (create_app factory)
├── config.py            # Settings (pydantic-settings)
├── api/
│   ├── routes/          # health, sessions, events, trace, metrics
│   └── middleware/      # auth, logging, rate_limit, errors
├── models/              # Pydantic domain models
├── services/            # database, redis, message_queue, auth, trace_processor
├── adapters/            # Framework SDK adapters (future)
├── migrations/
└── tests/
```

## Docs

- `AUTH_README.md` — JWT and API keys
- `DATABASE_SETUP.md` / `DATABASE_SCHEMA.md` — schema reference
- `../RESEARCH_PLAN.md` — long-horizon memory corruption research framing

## Tests

```bash
pytest tests/ -q
```
