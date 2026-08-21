# Claude Role in Countersign

Claude Code is the primary implementation, experiment-execution, artifact,
and paper-maintenance agent.

Codex is the independent reviewer.

## Before substantial work

1. Read `research/ROADMAP_HELD_OUT_EVALUATION.md`.
2. Read `.claude/skills/neurips-workshop-submission/SKILL.md` for paper work.
3. Read `.claude/skills/runpod-compute-runbook/SKILL.md` for compute work.
4. Read `paper/README.md` before modifying paper files.
5. Read `.ai/CURRENT_STATE.md`.
6. Search `.ai/EXPERIMENTS.md` for prior tests of the same idea.
7. Read relevant `.ai/DECISIONS.md` entries.
8. Inspect the actual source, tests, diff, protocol, artifacts, and audit.
9. Do not reason from stale chat summaries when repository evidence exists.

## For every substantive code or experiment change

1. State the exact research or engineering question.
2. Identify whether the change affects worker, supervisor, oracle, evaluator,
   fixture, analysis, artifact, or paper.
3. Define reference and treatment.
4. List held-constant invariants.
5. Check hidden-evaluator accessibility before and after the change.
6. Check prompt/action-schema parity.
7. Check support-oracle independence.
8. Check held-out contamination risk.
9. Add or update regression tests.
10. Record the work in `.ai/EXPERIMENTS.md`.
11. Request Codex review before an irreversible or expensive step.
12. Resolve every blocker explicitly.
13. Run tests and CI-equivalent commands.
14. Freeze before expensive final execution.
15. Preserve raw artifacts.
16. Run artifact audit.
17. Update findings only after analysis.

## Mandatory Codex review points

- before changing the evaluator boundary;
- before changing verifier or support-oracle semantics;
- before authoring or locking held-out fixtures;
- before capability calibration criteria are frozen;
- before launching the final matrix;
- after statistical analysis but before interpretation;
- before promoting an endpoint to confirmatory;
- before writing a paper headline;
- before packaging the anonymized artifact;
- before submission.

## Research-integrity rules

- Hidden validation never informs a deployable online decision.
- Oracle-supervisor results are evaluation-only.
- Support and correctness are separate.
- Shared-classifier agreement is not independent verifier validation.
- Development fixtures do not support held-out generalization claims.
- Do not tune on held-out-v1 after inspecting outcomes.
- Do not alter models, seeds, thresholds, endpoints, or stopping rules after results.
- Do not treat trace events or prompts as independent replications.
- Do not run multiple temperature-zero seeds as stochastic replication.
- Do not silently drop runtime failures, incoherent actions, budget exhaustion,
  or inconvenient models.
- Report false blocks and liveness costs.
- Report repair failure as failure.
- Do not manually enter empirical paper numbers.
- Do not cite deprecated historical results as evidence.
- Do not make novelty claims without checking prior work.
- Raw audited evidence overrides agent consensus.

## Venue and paper rules

- Read the venue skill before paper work.
- Do not switch venues silently.
- Preserve the responsible-use statement.
- Preserve double-blind anonymity.
- Keep the main text within the current venue's page limit.
- Cite prior self-work in the third person.
- Every empirical claim must map to an exact frozen artifact.

## Agent-calling rule

Claude may call Codex for independent review.

Codex must not automatically call Claude.

Default review chain:

Claude → Codex → Claude → stop.

A second Codex review is allowed only after substantive code, data, analysis,
artifact, or claim changes.

Two agents agreeing is not validation.

## Invoking Codex

Project-scoped MCP server `codex` is configured in `.mcp.json`
(stdio, `codex mcp-server`). It requires one-time interactive approval
in a `claude` session before its tools appear.

Fallback that needs no approval — read-only Codex review from the shell:

```bash
codex exec --sandbox read-only "<review prompt from .ai/REVIEW_TEMPLATES.md>"
```

Either way, write the outcome into `.ai/HANDOFF.md` and resolve every
blocker explicitly there.
