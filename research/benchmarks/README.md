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

The seed file is intentionally small and manually auditable. It is not meant to be a final
benchmark, only the first reproducible substrate for building claim extraction, scoring,
and verification gates.

## Files

- `ground_truth_schema.json` documents the expected fields and enums.
- `seed_tasks.json` contains the first benchmark tasks.

## Evaluation Intent

For each task, a run should produce:

- A full trace of prompts, responses, tool calls, memory events, plans, summaries, and final
  completion claims.
- Extracted memory claims with provenance and timestamps.
- Scores for goal fidelity, task-state accuracy, source attribution, temporal accuracy,
  semantic drift, and false completion.
- A comparison between baseline and verification-augmented runs.
