# Long-Horizon Tasks

Long-horizon tasks do not have to be coding tasks. Coding is a strong first testbed because
files, diffs, tests, and task-completion claims are easy to verify. But memory corruption
in agents also matters for research, analysis, investigation, operations, and reporting.

## What Makes a Task Long-Horizon

A task should include several of these pressures:

- Multiple subtasks with dependencies.
- Delayed verification.
- Evidence that becomes stale after later actions.
- Summaries or memory compression.
- Source ambiguity.
- Intermediate results that can be misremembered.
- A final answer that requires integrating earlier facts.
- A temptation to claim completion without fresh evidence.

## Task Families

### Coding

Examples:

- Multi-file implementation with tests.
- Debugging where old passing tests become stale after edits.
- Repo audit where the agent must prove which tasks are really done.
- Refactor where behavior must remain unchanged.

Failure modes:

- False completion.
- Stale test evidence.
- Tool-result confabulation.
- File-change misremembering.

### Research Synthesis

Examples:

- Compare papers or reports across many sources.
- Track which source supports which claim.
- Maintain uncertainty labels while summarizing.
- Update conclusions after a contradictory source appears.

Failure modes:

- Source confusion.
- Unsupported citation.
- Overconfident synthesis.
- Semantic drift from the original research question.

### Data Analysis

Examples:

- Iterative hypothesis testing over a dataset.
- Data cleaning with intermediate assumptions.
- Re-running calculations after filtering changes.
- Explaining results with provenance.

Failure modes:

- Treating old outputs as current.
- Misremembering which filter or script produced a result.
- Claiming statistical support without the right analysis.

### Web or Repository Investigation

Examples:

- Multi-step issue triage.
- Documentation audit across several pages.
- Comparing changelogs and source code.
- Tracking what was checked and what remains unknown.

Failure modes:

- Temporal disordering.
- Confusing source pages.
- Claiming a repo state without current inspection.

### Operational Planning

Examples:

- Long checklist execution.
- Incident/postmortem reconstruction.
- Multi-step deployment plan review.
- Risk assessment with changing constraints.

Failure modes:

- Task-state drift.
- Forgotten blockers.
- Unsupported "ready" claims.
- Confabulated continuity after summary compression.

## Ground Truth Requirements

Every benchmark task should define:

- Original user goal.
- Required subtasks.
- Evidence sources.
- Expected fresh evidence for completion.
- Known stale evidence.
- Contradictory evidence if applicable.
- High-risk claims to verify.
- Expected failure modes.
- Success criteria.

## Scoring Across Domains

The same core metrics can apply across domains:

- Goal fidelity.
- Task-state accuracy.
- Evidence attribution accuracy.
- Temporal accuracy.
- Semantic drift.
- False completion rate.
- Verification recovery rate.

Domain-specific evidence changes, but the memory-corruption structure is the same.

## Recommended Next Seeds

Add one task from each category:

- Coding: make a small code change, run tests, then modify a file so old tests become
  stale.
- Research: synthesize three sources where one source contradicts an earlier summary.
- Data analysis: compute a metric, change filtering rules, and test whether the agent
  still cites the old result.
- Repo investigation: inspect a task list and code files, then require evidence for each
  "done" claim.
- Operations: maintain a deployment checklist where one prerequisite becomes blocked.
