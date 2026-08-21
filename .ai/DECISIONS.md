# Countersign Decisions

Durable decision record. Each entry states what was decided, on what
evidence, and what would justify revisiting it. `.ai/` does not
override the venue skill, the paper README, or frozen protocols; a
superseding decision must update every canonical file in one commit.

---

## DEC-CTR-001 — Project name is Countersign

Date: 2026-08-18
Operator: repository owner
Commit: repository rename to `countersign`

### Decision

The project is named Countersign. "Agent Memory Observatory" and
"AI-Agent-Observer" are historical aliases only and must not appear in
reviewer-facing artifacts.

### Reason

Single current identity; old names also carry deanonymization risk in a
double-blind submission.

### Evidence

`README.md`, `paper/main.tex` title, venue skill header.

### Alternatives rejected

Keeping the observatory framing — it described a passive logger, which
misrepresents a supervisor with halting authority.

### Consequences

Anonymization greps include the old names.

### Revisit condition

None foreseeable.

### Status

ACTIVE

---

## DEC-CTR-002 — Venue and track are Meta-Agents NeurIPS 2026, 4-page Short Paper + Demo

Date: 2026-08-16 (locked), reconfirmed 2026-08-21
Operator: repository owner
Commit: venue skill creation

### Decision

Target: "Managing Agents that Manage Agents" (Meta-Agents), NeurIPS
2026. Track: Short Paper, max 4 pages main text, plus the Demo Track.
Deadline 2026-08-29 AoE, OpenReview, double-blind, non-archival.

### Reason

The supervision loop matches the CFP's meta-agent, oversight, and
evaluation topics; the dashboard's side-by-side trajectory view fits
the demo track.

### Evidence

`.claude/skills/neurips-workshop-submission/SKILL.md` and
`paper/README.md` agree (verified byte-identical skill copy at
`~/.claude/skills/...`, 2026-08-21). No conflict.

### Alternatives rejected

"Who Verifies the Agents?" and AgentWild — documented as alternates in
the venue skill; the same paper must not go to more than one.

### Consequences

4-page limit governs; responsible-use statement is mandatory
(desk-reject item); prior self-work cited in the third person.

### Revisit condition

Only an operator decision, applied to the venue skill, paper README,
`paper/main.tex`, `.ai/CURRENT_STATE.md`, and this file in one commit.

### Status

ACTIVE

---

## DEC-CTR-003 — Support and hidden-evaluator correctness are distinct outcomes

Date: 2026-08 (design), enforced throughout
Operator: repository owner
Commit: support-oracle introduction

### Decision

"Justified" (claim supported by evidence available at proposal time)
and "correct" (post-termination hidden evaluator passes) are separate
outcomes, never collapsed in code, analysis, or prose.

### Reason

Conflating them makes "the verifier improved outcomes" unfalsifiable —
the paper's organizing principle.

### Evidence

`research/runner/support_oracle.py` vs the hidden validator; the 2×2 in
`paper/main.tex` Table 1 crosses them explicitly.

### Alternatives rejected

A single "success" endpoint.

### Consequences

Every claim names which outcome it concerns; the empty
unsupported∧incorrect cell is reported as the central caveat.

### Revisit condition

None — this is the paper's core construct.

### Status

ACTIVE

---

## DEC-CTR-004 — The deployable verifier cannot access hidden validation before termination

Date: 2026-08 (gate restructuring)
Operator: repository owner
Commit: evaluator-boundary fix (pre-freeze)

### Decision

No deployable condition may call, read, or receive hidden-validation
output before the episode terminates; the hidden evaluator runs exactly
once, post-termination, identically in every condition.

### Reason

The original online finish gate consulted the hidden evaluator, which
made "verification reduces false completions" an artifact of running
the answer key mid-episode.

### Evidence

`research/runner/benchmark_runner.py` post-termination call site;
regression tests pin the call count and timing.

### Alternatives rejected

Keeping the oracle-informed gate with a caveat.

### Consequences

Repair feedback carries visible-evidence diagnosis only.

### Revisit condition

None; any change requires a new held-out version.

### Status

ACTIVE

---

## DEC-CTR-005 — The oracle supervisor is evaluation-only

Date: 2026-08 (arm design)
Operator: repository owner

### Decision

`oracle_supervisor` may use hidden ground truth, is always labeled
non-deployable, and is excluded from primary deployable-supervisor
claims and from pooled inference.

### Reason

It is an upper bound on what supervision could achieve, not a system
anyone could ship.

### Evidence

`research/runner/interventions.py` spec; the paper reports it only as a
bound (Appendix accounting).

### Consequences

Its 5 refusals never enter the precision/false-block numbers.

### Revisit condition

None.

### Status

ACTIVE

---

## DEC-CTR-006 — Development fixtures are not held-out evidence

Date: 2026-08 (split lock)
Operator: repository owner

### Decision

The development suite (on which verifier rules were iterated) supports
no generalization claim; only frozen held-out fixtures do.

### Evidence

`research/FREEZE_HELDOUT_V1.md`; fixture split labels.

### Consequences

Development observations are prefixed "DEVELOPMENT ONLY:" in `.ai/`
files and never appear as paper findings.

### Revisit condition

None.

### Status

ACTIVE

---

## DEC-CTR-007 — heldout-v1 is not tuned after outcome inspection

Date: 2026-08-17 (freeze)
Operator: repository owner
Commit: tag `heldout-v1-freeze` (+ `.1`, `.2` infra-only)

### Decision

After the freeze, no verifier, oracle, or fixture logic changes in
response to held-out outcomes. Corrections create heldout_v2; the three
freeze tags carry byte-identical verifier-policy hashes.

### Evidence

`git diff` across the three tags touches no hashed policy file
(verified 2026-08-20); campaign protocols record matching hashes.

### Consequences

Two infrastructure fixes (interruption recovery; a tool-level crash
guard) were applied and ledgered without touching rule semantics.

### Revisit condition

Any semantic change forces heldout_v2 and a new campaign.

### Status

ACTIVE

---

## DEC-CTR-008 — Primary endpoint and comparison are frozen

Date: 2026-08-17 (predeclaration)
Operator: repository owner

### Decision

Primary endpoint: accepted-unsupported finish. Primary comparison:
`memory_baseline` vs `verification_only`. The three-arm decomposition
(adding `observe_only`) is the predeclared confound-resolution branch;
all other contrasts are exploratory.

### Reason

Preregistration without a named primary invites forking-paths
criticism.

### Evidence

`research/ROADMAP_HELD_OUT_EVALUATION.md` §11;
`research/PHASE_E_ERADICATION.md`; stated in `paper/main.tex` §3.

### Consequences

Because baseline and verification_only differ in both prompt and gate,
that contrast is never reported as a gate effect on its own.

### Revisit condition

None post-freeze.

### Status

ACTIVE

---

## DEC-CTR-009 — Multi-arm inference is pairwise, never pooled

Date: 2026-08 (analysis plan)
Operator: repository owner

### Decision

No pooling of a duplicated reference arm across treatments; cross-model
pooling, if reported at all, uses the predeclared cluster-aware
sensitivity analysis with model and task as random effects.

### Evidence

`research/runner/matrix_analysis.py::supervision_decomposition` returns
None when the prompt-matched arm is absent, so a confounded contrast
cannot be silently reported as a gate effect.

### Consequences

The E6 replication reports per-model results; the local-execution
variant that would have mixed Metal and CUDA was aborted partly for
this reason (commit a4b0f01).

### Revisit condition

None.

### Status

ACTIVE

---

## DEC-CTR-010 — Shared-classifier agreement is not external validation

Date: 2026-08 (metrics correction)
Operator: repository owner

### Decision

Confusion between the online verifier and the shared claim classifier
is internal consistency only. External precision/recall requires the
independent support oracle, and near-vacuous agreements (claims citing
no evidence at all) are disclosed as such.

### Evidence

`paper/main.tex` limitation (4): most agreements concern claims citing
no evidence; only 4 of 17 blocks required substantive reasoning.

### Status

ACTIVE

---

## DEC-CTR-011 — Paper result values are generated, never hand-entered

Date: 2026-08 (paper rules)
Operator: repository owner

### Decision

Every empirical value derives from analysis over audited artifacts.
`paper/figures/gen_figures.py` recomputes all plotted values from the
run manifests at plot time.

### Evidence

`paper/README.md` hard rule 1; the figure script's docstring.

### Consequences

Two numeric defects (a marginal-vs-paired McNemar slip and a
criterion-label drift) were found by artifact tracing and corrected at
commits d9e8eaf and 90f1455 rather than argued from memory.

### Status

ACTIVE

---

## DEC-CTR-012 — The responsible-use statement cannot be removed

Date: 2026-08-16
Operator: repository owner

### Decision

The statement stays in every draft and the submission; omitting it
warrants desk rejection at this venue.

### Evidence

Venue skill hard requirement; `paper/README.md` hard rule 3.

### Consequences

Under the current layout it follows page 4 (see OPEN-002 in
`.ai/HANDOFF.md`), on the standard reading that impact statements are
excluded from the page limit.

### Status

ACTIVE

---

## DEC-CTR-013 — The submission artifact is relocatable and double-blind

Date: 2026-08 (artifact design)
Operator: repository owner

### Decision

The artifact ships as a relocatable bundle whose integrity audit must
pass from the copied location, with no git history, author identifiers,
machine paths, or repository links.

### Evidence

`resolve_bundle_path` machinery; artifact-index audits pass for six of
seven campaigns (see OPEN-001 for the exception).

### Revisit condition

OPEN-001 must be resolved before packaging.

### Status

ACTIVE

---

## DEC-CTR-014 — One compatible runtime/GPU environment per compared dataset

Date: 2026-08-21 (reaffirmed)
Operator: repository owner

### Decision

Calibration and compared runs share a pod image and GPU class. Mac
(Metal) runs are never mixed with pod (CUDA) runs in one dataset.

### Reason

Different kernels produce different samples at the same seed.

### Evidence

`.claude/skills/runpod-compute-runbook/SKILL.md` §0.

### Consequences

E6-LOCAL (devstral on Apple Silicon) was aborted after 1 of 30 runs and
its artifacts deleted unmerged; E6 executes on a CUDA pod. Ledgered at
commit a4b0f01 with the no-peeking disclosure.

### Status

ACTIVE

---

## DEC-CTR-015 — Sampling settings are fixed before outcome inspection

Date: 2026-08-17
Operator: repository owner

### Decision

Temperature 0.7, sampler seeds 0–4, action budget 24, max tokens 1024,
model ladder, and stopping rule are fixed before results are inspected
and not changed afterward. Multi-seed real-runtime matrices at
temperature 0.0 are refused by the runner (pseudoreplication guard).

### Evidence

Frozen protocol `generation` block; the guard's regression test.

### Status

ACTIVE

---

## DEC-CTR-016 — Claude implements and executes; Codex reviews independently

Date: 2026-08-21
Operator: repository owner
Commit: this setup

### Decision

Claude Code is the primary implementation, experiment-execution,
artifact, and paper-maintenance agent. Codex is the independent
research-design, verifier-architecture, statistics, artifact-integrity,
and paper-review agent. Review chain: Claude → Codex → Claude → STOP.
Codex does not call Claude recursively.

### Reason

Independent adversarial review before expensive or public steps; agent
agreement is not evidence.

### Evidence

`CLAUDE.md`, `AGENTS.md`, `.mcp.json`, `.ai/REVIEW_TEMPLATES.md`.

### Consequences

Mandatory Codex review points are listed in `CLAUDE.md`; unresolved
objections stay visible in `.ai/HANDOFF.md`.

### Revisit condition

Operator may change the division of labor.

### Status

ACTIVE
