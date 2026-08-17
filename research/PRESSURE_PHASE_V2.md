# Pressure phase (v2 addendum) — predeclared 2026-08-17

## Adaptive-design disclosure (read this first)

This phase was designed AFTER inspecting 101 completed qwen runs of the
full-history held-out matrix (interim peek on 2026-08-17, performed to
decide whether continued spending was justified — recorded here rather
than hidden). What the peek showed: under intact memory
(`full_history`), qwen2.5-coder:14b rarely accepts unsupported finishes
(~1/10 trap runs) — the predeclared ceiling branch (see
FREEZE_HELDOUT_V1.md, "Early-signal note"). The fixtures and the
verifier are unchanged and remain frozen at `heldout-v1-freeze`; this
addendum adds a predeclared CONDITION axis using the pressure machinery
that has existed in the frozen registry since before the freeze.

The full-history runs already collected are this phase's zero-pressure
control arm, not discarded work.

## Design

- **Pressure gradient**: `lossy_compaction` at severities low(1),
  medium(2), high(3) from the frozen registry
  (`research/benchmarks/memory_pressure_profiles.json`), plus the
  already-run `control_full_history`(0). Lossy compaction is the
  production-realistic mechanism: the worker's visible history is
  summarized/truncated the way deployed agents' contexts are.
- **Treatment scope invariant** (from the frozen protocol): only
  model-visible evidence degrades. The evidence ledger, verifier,
  oracle, and hidden evaluator always see canonical state. The
  worker's memory degrades; the supervisor's does not. That asymmetry
  is the mechanism under test.
- **Cells per model**: 6 pair fixtures × 5 seeds × 2 arms
  (`memory_baseline`, `verification_only`) × 3 pressure levels
  = 180 runs. qwen2.5-coder:14b first; devstral-small-2:24b when
  funded (its sequencing after qwen results is a further adaptive
  choice, disclosed here).
- Same frozen tag, `--strict-freeze`, temperature 0.7, seeds 0–4,
  budget 24, `--pressure-profiles lossy_low lossy_medium lossy_high`.

## Predeclared endpoints

1. **Primary: dose–response** — `accepted_unsupported_finish` (and the
   oracle-labeled variant) in the baseline arm as a function of
   severity ordinal 0→3, per model, with the trend summarized by the
   existing dose_response machinery (task-level bootstrap for
   clustering).
2. **Supervision × pressure interaction** — paired
   baseline-vs-verification comparison AT EACH severity level; the
   claim of interest is that the supervision effect grows with
   severity.
3. **Catch integrity under pressure** — the verifier reads the
   canonical ledger, so its decisions are pressure-invariant BY
   CONSTRUCTION; false-block behavior on supported members is
   predicted flat across severities. A rise would indicate a
   contamination bug, not a finding.
4. Budget exhaustion vs severity (capability cost of degraded memory),
   reported, not primary.

## Interpretation commitments (written before data)

- Rising dose–response + growing supervision effect → the paper's
  central mechanistic claim: supervision value scales with worker
  memory degradation because the supervisor's view does not degrade.
- FLAT dose–response even at lossy_high → workers re-verify by habit
  regardless of memory state; reported as a robustness finding, not
  reframed. No further condition-shopping beyond this predeclared
  gradient.

## Other disclosures accumulated to date

- Balance exhaustion stopped the original pod (A100 80GB PCIe,
  EU-RO-1) at 102/300 pair runs; migrated to A100-SXM4-80GB
  (US-KS-2) from the mirrored artifacts. Same sm_80 architecture and
  CUDA stack; sub-class change recorded.
- A few runs (~1–3) completed between the last mirror sync and the
  stop may be re-executed on the new pod; re-execution replaces, never
  merges.
- deepseek-r1:8b third-model probe paused at 2/15 (≈12 min/run pace);
  its ladder decision is deferred and must not be made based on
  held-out results.
