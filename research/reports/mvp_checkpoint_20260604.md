# Research MVP Checkpoint: 2026-06-04

## Status

The Agent Memory Observatory research MVP is implementation-backed for a deterministic
open-source-style benchmark harness, terminal workflow, report artifacts, and dashboard
inspection. It is MATS application-level in direction and framing: it has a safety
motivation, reproducible benchmark tasks, an intervention, metrics, generated artifacts,
tests, a terminal path, and a dashboard path.

It is not yet strong empirical evidence about real open-source LLM agents. Real-runtime
results must be generated separately with Ollama or llama.cpp and labeled separately from
deterministic harness results.

## Passing Commands

All commands below passed on this checkpoint run.

```bash
cd /Users/spiderishi/Coding/Agent\ Observer/AI\ Agent\ Observer/backend
python3 -m pytest -q
```

Result: `269 passed, 1 skipped`.

```bash
cd /Users/spiderishi/Coding/Agent\ Observer/AI\ Agent\ Observer
python3 -m pytest backend/tests/test_research_benchmark_seed.py backend/tests/test_research_benchmark_runner.py backend/tests/test_research_memory_claims.py backend/tests/test_research_memory_metrics.py backend/tests/test_research_verification_and_cli.py backend/tests/test_research_runtime_and_bundle.py -q
```

Result: `38 passed, 1 skipped`.

```bash
cd /Users/spiderishi/Coding/Agent\ Observer/AI\ Agent\ Observer/frontend
npm run test:run
npm run build
npm audit --audit-level=moderate
```

Results: frontend tests `26 passed`; production build passed with Vite chunk-size warning
only; audit found `0 vulnerabilities`.

```bash
cd /Users/spiderishi/Coding/Agent\ Observer/AI\ Agent\ Observer
python3 scripts/agent_memory.py bundle --out /tmp/agent-memory-mvp-checkpoint-20260604 --test-status 'backend=269p1s frontend=26p build=pass audit=0vuln research=38p1s' --format json
```

Result: complete artifact bundle generated.

## Artifact Paths

- Manifest: `/tmp/agent-memory-mvp-checkpoint-20260604/manifest.json`
- Generated summary: `/tmp/agent-memory-mvp-checkpoint-20260604/summary.md`
- Baseline runs: `/tmp/agent-memory-mvp-checkpoint-20260604/runs/baseline/`
- Verified runs: `/tmp/agent-memory-mvp-checkpoint-20260604/runs/verified/`
- Scores: `/tmp/agent-memory-mvp-checkpoint-20260604/scores/`
- Verifications: `/tmp/agent-memory-mvp-checkpoint-20260604/verifications/`
- Comparisons: `/tmp/agent-memory-mvp-checkpoint-20260604/comparisons/`

The summary command block was verified against the manifest and rerun: 9 commands
completed, 3 tasks loaded, and baseline/verified/comparison artifact schemas matched.

## MVP Evidence

- Benchmark tasks cover stale tests, false done claims, and research source tracking.
- Runs capture trace events, high-risk labels, memory claims, provenance, metrics, and
  verification reports.
- Verification gates block high-risk claims with stale evidence, missing source types,
  lost provenance, unsupported claims, and contradicted claims.
- The CLI supports `run`, `score`, `verify`, `compare`, and `bundle`.
- The dashboard consumes the same report shapes and renders memory health, trace risk,
  claim inspection, and baseline-vs-verified comparison views.

## Readiness Judgment

MATS-ready as an application/demo artifact: yes, with honest limitations.

MATS-ready as a finished empirical result: not yet. The next evidence upgrade is to run
the same tasks through a real open-source runtime and agent framework, then compare those
results against the deterministic harness.

## Remaining Limitations

- The checkpoint bundle is deterministic harness output, not real Ollama or llama.cpp
  model output.
- Optional real-runtime test is skipped unless `AGENT_MEMORY_REAL_RUNTIME` is set to
  `ollama` or `llama_cpp`.
- Current benchmark has only three seed tasks; stronger results need broader long-horizon
  tasks and multiple open-source agent frameworks.
- Vite reports a frontend chunk-size warning; it is not a failing build, but code splitting
  should be considered before a polished public demo.
- Historical optional task `4.5` remains unchecked; the research MVP tasks 16-25 are the
  current scope of this checkpoint.
