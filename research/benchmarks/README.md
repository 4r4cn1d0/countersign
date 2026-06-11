# Long-Horizon Memory Corruption Benchmark

This directory defines the first benchmark slice for the Agent Memory Observatory.

The benchmark is designed to pressure open-source AI agents over long-horizon tasks where
memory can degrade: stale tool outputs, compressed summaries, task-list drift, source
confusion, and false completion. The goal is to compare baseline agents against agents
with memory verification enabled.

## Task Families

- **coding:** multi-file implementation, debugging, test verification, and task completion.
- **repo_audit:** repository or task-list inspection where claims must be tied to code evidence.
- **research_synthesis:** long-form research with source tracking and attribution.
- **data_analysis:** iterative analysis where intermediate results can become stale.
- **web_investigation:** multi-step browser/repository investigation with delayed verification.

## Ground Truth Shape

Every benchmark task includes:

- Original goal and expected task horizon.
- Required subtasks.
- Drift inducers such as stale tests, summary compression, or ambiguous completion language.
- Ground-truth checkpoints with expected evidence.
- High-risk claims that require verification before the agent can use them.
- Targeted failure modes such as semantic drift, temporal disordering, source confusion, and
  false completion.

The current seed file contains 10 manually auditable tasks: 8 coding tasks, one
repository-audit task, and one research-synthesis task. All eight coding tasks are
checked-in fixture repositories with 20 planned model actions, multiple source and test
files, a staged false lead and rollback, a mid-run requirement update, stale test
evidence, delayed final validation, hidden validation, and a stable repository hash.

The coding suite covers parser repair, multi-file normalization, post-test invoice edits,
checklist-versus-code auditing, namespace cache invalidation, active-versus-legacy source
confusion, lossless schema migration, and coordinated retry policy changes. The same
fixtures can be run under `lossy_compaction` and `resume_summary` memory conditions to
measure degraded or resumed model-visible memory without changing evaluator state.

## Files

- `ground_truth_schema.json` documents the expected fields and enums.
- `seed_tasks.json` contains the 10 benchmark tasks.
- `coding_scenarios/` contains all eight repository fixtures, staged false-lead patches,
  solution patches, versioned scenario manifests, and hidden validators.

Each coding scenario manifest records:

- A SHA-256 hash of the initial repository, validated when the fixture loads.
- Exactly 20 planned model actions, inside the benchmark's 20-50 action range.
- Explicit false-lead, rollback, stale-evidence, and delayed-validation step IDs.
- Independent subtasks and the memory-pressure conditions used for compaction studies.
- A requirement update injected into the live tool loop after action 12.

The hidden validator is stored outside the model workspace and executes independently
after visible `unittest` discovery. A fixture is rejected at load time if its schema,
repository hash, action count, final-test step, or hidden validator is invalid.

## Evaluation Intent

For each task, a run should produce:

- A full trace of prompts, responses, tool calls, memory events, plans, summaries, and final
  completion claims.
- Extracted memory claims with provenance and timestamps.
- Scores for goal fidelity, task-state accuracy, source attribution, temporal accuracy,
  semantic drift, and false completion.
- A comparison between baseline and verification-augmented runs.
