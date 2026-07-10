# Easy-Tier Capability Calibration Protocol (Tasks 33.6 and 38.7)

Pre-registered: 2026-07-07, before any calibration run was executed.

## Motivation

Six real-model attempts at Task 38.7 (devstral-small-2:24b ×2, llama3.2:3b,
qwen2.5-coder:7b ×3) failed to reach independently verified recovery. The most
recent attempt failed under `full_history` with no induced memory pressure on a
raw coding-capability gap. Task 33.6 requires demonstrating that baseline local
models can fail *for memory reasons* rather than only coding incapability. This
protocol separates the two by first establishing which models can complete the
easy-tier fixtures with no memory pressure, then measuring memory-attributed
failure and recovery on exactly those models.

## Fixtures

Easy tier (`tier: "easy"` in `research/benchmarks/seed_tasks.json`):

- `coding_easy_flag_default_001` — single-function flag parsing with a
  mid-task default clarification.
- `coding_easy_greeting_format_001` — single-function greeting formatting with
  stale-source confusion (obsolete NOTES.md).
- `coding_easy_list_dedupe_001` — single-function ordered dedupe with a
  mid-task regression revert.

All three preserve the benchmark memory structure (false lead, stale passing
evidence, requirement update, delayed final validation, hidden validator) while
dropping the coding floor to one trivial function per task.

## Stages

### Stage 1 — Capability floor (full_history, baseline)

- Models: qwen2.5-coder:7b, qwen2.5-coder:14b, llama3.2:3b, deepseek-r1:8b,
  devstral-small-2:24b
- Conditions: `memory_condition=full_history`, `agent_variant=baseline`,
  `action_budget=32` (raised from the matrix default 24 and recorded here),
  seeds 0-2, temperature 0.0
- Runs: 5 models × 3 easy tasks × 3 seeds = 45
- **Pass criterion (per model):** evaluator success on ≥ 2 of 3 seeds on ≥ 2 of
  3 easy tasks.

### Stage 2 — Memory-attributed failure (33.6 evidence)

- Models: Stage-1 passers only
- Conditions: identical (model, task, seed) tuples under
  `lossy_compaction`, `temporal_corruption` (medium), and `resume_summary`,
  `agent_variant=baseline`
- **33.6 evidence:** pressure-condition failures classified
  `memory_contributed_failure` by `classify_run_failure` on tuples whose
  full-history counterpart succeeded.

### Stage 3 — Recovery (38.7 evidence)

- Models: Stage-1 passers only
- Conditions: same pressure tuples, `agent_variant=verified`,
  `memory_repair` enabled
- **Primary endpoint:** strict `memory_repair_recovery == true` on ≥ 1 run.
- **Secondary endpoint (predeclared):** `contained_recovery == true`
  (recovery_level ≥ 3: detection, repair, valid replan, zero accepted false
  finishes) reported alongside the strict metric. If strict recovery is not
  observed, Task 38.7 is reported at the contained tier with the strict result
  stated plainly as 0/N.

## Predeclared fallback ladder (Stage 1 failure)

Applied in order only if no model passes Stage 1:

1. Raise `action_budget` to 40.
2. Run qwen2.5-coder:32b (q4) solo as a capability-ceiling probe.
3. Simplify easy-fixture edge cases further (permitted only before the Task-42
   protocol freeze).

## Accounting rules

- Failed, invalid, and budget-exhausted runs stay in all denominators.
- Runtime/infrastructure failures (Ollama crash, timeout) are recorded with
  reasons and excluded only from eligibility, never silently dropped.
- No deterministic-fallback run counts as real-runtime evidence.
- deepseek-r1:8b think-tag parse failures, if they break constrained actions,
  trigger the predeclared alternate phi4-mini for the Task-42 roster.
