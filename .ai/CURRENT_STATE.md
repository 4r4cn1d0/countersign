# Countersign Current State

Last updated: 2026-08-21
Git branch: main
Git commit: a4b0f01 (at the time of writing)
Working tree: clean except this collaboration-setup addition
Project name: Countersign
Former project name(s): Agent Memory Observatory / AI-Agent-Observer

## Canonical sources

- Held-out and freeze roadmap: `research/ROADMAP_HELD_OUT_EVALUATION.md`
- Venue and submission rules: `.claude/skills/neurips-workshop-submission/SKILL.md`
- Compute execution rules: `.claude/skills/runpod-compute-runbook/SKILL.md`
- Paper plan and hard rules: `paper/README.md`
- Paper source: `paper/main.tex`
- Support oracle: `research/runner/support_oracle.py`
- Deployable verifier: `research/runner/verification.py`
- Runtime/controller: `research/runner/benchmark_runner.py`
- Frozen protocol machinery: `research/runner/experiment_protocol.py`
- Current repository overview: `README.md`
- Deviation ledgers: `research/FREEZE_HELDOUT_V1.md`,
  `research/PRESSURE_PHASE_V2.md`, `research/PHASE_E_ERADICATION.md`

## Current venue plan

RESOLVED 2026-08-21 by operator decision (CONFLICT-001 closed; see
DEC-CTR-002).

- venue: **Option 1 (primary) — Managing Agents that Manage Agents
  (Meta-Agents), NeurIPS 2026.** Option 2 (fallback) — AgentWild (Third
  Workshop on Agents in the Wild), same deadline, **no demo track**.
- track: Short Paper.
- deadline: **August 29, 2026 AoE**; notification on or before
  September 29, 2026 AoE.
- page limit: **4 pages** main text (references and appendices
  excluded; main text must be self-contained).
- demo plan: Demo Track submission alongside the short paper — a live
  side-by-side baseline-vs-verified trajectory with hidden evaluation
  revealed only post-termination. Dropped if the fallback venue is used.
- responsible-use requirement: mandatory, desk-reject if omitted.
  Present in `paper/main.tex`.
- source files that establish this:
  `.claude/skills/neurips-workshop-submission/SKILL.md` (authoritative
  venue facts), `paper/README.md`, and
  `research/ROADMAP_HELD_OUT_EVALUATION.md` §"Target venue" — all three
  updated in one commit and now agreeing.
- anonymization: the artifact is held to AgentWild's stricter rule
  (double-blind extending to code and supplementary material)
  regardless of which venue is used.

## Current paper identity

- title: `Countersign: Evidence-Grounded Supervision of Coding-Agent
  Completion Claims` (locked; `paper/main.tex`)
- central object: a supervisory meta-agent with halting authority over a
  worker coding agent's termination
- worker: tool-loop coding agent, self-hosted open-weight model
  (`qwen2.5-coder:14b` in the frozen campaign)
- supervisor: deterministic trace-only audit of cited-evidence
  chronology (freshness, requirement recency, provenance, abstention)
- deployable verifier: `research/runner/verification.py` + the online
  finish gate in `benchmark_runner.py`
- evaluation-only oracle supervisor: `oracle_supervisor` arm
  (`oracle_gate=True`); never deployable, never pooled
- primary research question: see below

## Current research question

Can a lightweight supervisory meta-agent distinguish when a worker coding
agent has sufficient trace evidence to terminate, and intervene without
excessive over-blocking, liveness failure, or new failure modes?

## Operational definitions

### Supported completion

A completion claim is supported when the evidence available at proposal
time justifies it under the frozen support-labeling protocol
(`support_oracle.py`; labels supported / unsupported / uncertain).

### Correct completion

A completion is correct when the post-termination hidden evaluator
judges the final implementation successful (`hidden_validation.py` per
fixture, invoked once after termination).

### Operational memory

The model-visible representation of prior requirements, observations,
tool results, evidence provenance, and task state across an episode.
Degradation profiles transform only this view; canonical state is never
transformed.

### Deployable supervisor

The trace-only online verifier and optional bounded repair mechanism. It
must not access hidden validation before termination.

### Evaluation-only oracle supervisor

Explicitly non-deployable upper-bound condition that may consult hidden
ground truth. Isolated behind `oracle_gate`, labeled evaluation-only,
excluded from primary deployable-supervisor claims.

## Current intervention conditions

Source of truth: `research/runner/interventions.py` (`InterventionSpec`).

| intervention | agent_variant | verifier | raw decision logged | blocking | repair | oracle gate | paper role |
|---|---|---|---|---|---|---|---|
| `memory_baseline` | baseline | no | n/a | no | no | no | reference arm |
| `observe_only` | verified | yes | yes | no | no | no | passive measurement |
| `verification_only` | verified | yes | yes | yes | no | no | primary treatment |
| `verification_and_repair` | verified | yes | yes | yes | yes | no | full system |
| `repair_only` (secondary) | verified | yes | yes | no | yes | no | secondary ablation |
| `oracle_supervisor` | verified | yes | yes | yes | no | **yes** | evaluation-only bound |

**IMPORTANT — see BLOCKER-001 in `.ai/HANDOFF.md`.** All primary arms
share one *identical* instrumented prompt, pinned by
`test_tool_action_prompt_is_identical_across_conditions`
(`backend/tests/test_research_benchmark_runner.py:2290`). The baseline is
an "instrumented baseline", not a naive agent. Verified empirically:
first prompts byte-identical in 10/10 matched provenance cells, first
responses identical in 9/10. `paper/main.tex` currently describes a
prompt treatment that does not exist; that text is a known blocker
awaiting operator ratification of the correction.

## Current primary endpoint

- endpoint: `accepted_unsupported_finish_trial` — an accepted completion
  claim lacking adequate contemporaneous support, independent of hidden
  correctness
- support-label source: independent support oracle
  (`support_oracle.score_finish_proposals`), not the shared claim
  classifier
- primary comparison: `memory_baseline__vs__verification_only`
- statistical test: paired exact McNemar
- clustering/sensitivity analysis: per-model reporting plus task-level
  cluster bootstrap; no pooled multi-arm inference; the E6 replication's
  pooled cluster-aware analysis requires one runtime environment
- frozen protocol path: `runs/pod-sync/final-matrix/experiment_protocol.json`
- protocol ID: `1b70f72ef5ba7a0816b6b8f16b815c5a36faf98cd2d5608b1f3c59dd40ddeb7e`
  (source revision `d80b1c23237271734a35ee2e317c4e1e18d55417`)

Six later campaign protocols exist under `runs/pod-sync/*` on source
revision `5acd35e3…` (`heldout-v1-freeze.2`); the verifier-policy hashes
are byte-identical across all three freeze tags.

## Data split

### Development fixtures

- count: 11
- fixture root: `research/benchmarks/coding_scenarios/`
- split label: `evaluation_split: "development"`
- used to develop verifier: yes
- publication role: none — no development number appears in the paper

### Held-out matched pairs

- count: 6 members in 3 families — `temporal_fresh`/`temporal_stale`,
  `provenance_auth`/`provenance_legacy`,
  `requirement_covered`/`requirement_lost`
- split label: `evaluation_split: "heldout_v1"` from creation
- freeze status: frozen at tag `heldout-v1-freeze`
  (+ `.1`, `.2` infrastructure-only)
- first inspected date: 2026-08-17 (disclosed interim peek recorded in
  `research/PRESSURE_PHASE_V2.md`)
- held-out version: v1

### Negative controls

- count: 4 — `negctrl_doc_edit`, `negctrl_unrelated_edit`,
  `negctrl_no_change`, `negctrl_doc_clarification`
- purpose: price false blocks; no designed trap
- arms: `memory_baseline` + `observe_only` (predeclared)
- false-positive metric: raw would-block decisions on oracle-**supported**
  proposals (a control can still emit an evidence-free claim, and
  blocking that is correct)

## Model and sampling plan

- candidate worker models: `research/agents/model_matrix.json`
- calibration threshold: ≥50% hidden-evaluator success on development
  controls, ≥90% valid structured actions, no systematic budget
  exhaustion
- fallback ladder: probe `qwen2.5-coder:32b`, else single model with
  stated limitation; no post-hoc model shopping
- final selected models: `qwen2.5-coder:14b` (campaign worker) and
  `devstral-small-2:24b` (calibrated, E6 pending)
- temperature: 0.7 (temperature 0.0 multi-seed is refused by the runner)
- seeds: 0–4
- action budget: 24 (fallback 40 probed; unchanged result)
- max tokens: 1024 in the frozen protocol
  (note: `model_matrix.json` records 256 — the CLI value governs; see
  discrepancy list)
- GPU/runtime: RunPod CUDA (A100 80GB PCIe, then H100 80GB HBM3);
  ollama + langgraph_tools; Mac/Metal runs are never mixed in
- model digests: `qwen2.5-coder:14b 9ec8897f747e`,
  `devstral-small-2:24b 24277f07f62d`

## Current evidence level

### Publication-eligible results

Present. `.ai/FINDINGS.md` F1–F4 and N1–N4 derive from the audited frozen
campaign (490 runs, seven protocols, verifier hashes identical across
freeze tags), independently traced 2026-08-20 with 33 of 36 checks
reproducing exactly. Two conditions still gate submission: BLOCKER-001
(paper text vs implementation) and OPEN-001 (final-matrix manifest
missing locally).

### Validated methodology invariants

Listed with code path and test in `.ai/FINDINGS.md`. Highlights:

- hidden validation runs once, post-termination, in every condition
  (`test_hidden_validation_runs_exactly_once_after_termination`);
- the online gate never consults ground truth
  (`test_verified_gate_allows_finish_when_only_hidden_validation_fails`);
- prompts are identical across primary conditions
  (`test_tool_action_prompt_is_identical_across_conditions`);
- raw and enforced decisions are distinct
  (`test_observe_only_never_blocks_and_records_raw_would_block_decision`);
- the support oracle imports nothing from claims/verification (by
  construction — **no executable import guard exists; see discrepancy 4**);
- a confounded contrast cannot be silently reported as a gate effect
  (`test_supervision_decomposition_separates_prompt_from_gate`);
- temperature-0.0 multi-seed matrices are refused (pseudoreplication).

### Development-only observations

> DEVELOPMENT ONLY: verifier rules were iterated against the 11
> development fixtures; calibration ran there (qwen 15/15, devstral
> 15/15 evaluator success). None of it supports a generalization claim.

### Deprecated evidence

- historical five-model LangGraph report (unparsed rows scored as
  perfectly healthy; predates the fixture-backed suite);
- pre-fix runs where the online finish gate consulted the hidden
  evaluator;
- metrics generated before NA handling;
- shared-classifier confusion presented as external precision/recall;
- any artifact failing `matrix-audit`.

## Known documentation discrepancies (recorded, not silently fixed)

1. Venue conflict — CONFLICT-001 above.
2. `max_tokens`: `model_matrix.json` says 256; the frozen protocol and
   `FREEZE_HELDOUT_V1.md` say 1024. The protocol governs the campaign.
3. `model_matrix.json.hardware_profile` is `macbook_m4_air_24gb` while
   the frozen environment is RunPod CUDA.
4. The support-oracle import rule is stated in two docstrings but has no
   executable guard; a one-line AST test would pin it.
5. ~~`research/benchmarks/README.md` fixture counts~~ — FIXED
   2026-08-21: it said 13 tasks / eight fixtures / "every fixture is
   development"; the truth is 23 tasks, 21 fixtures (11 development +
   10 held-out).
6. CORRECTED STATEMENT (the earlier wording here was itself wrong):
   `tier` **does** exist — it is a required field of every task in
   `seed_tasks.json` (`ground_truth_schema.json`, asserted by
   `test_research_benchmark_seed.py`). What is true is the inverse
   pair: `tier` is absent from the 21 `coding_scenarios/*/scenario.json`
   manifests, and `evaluation_split` is absent from the development
   entries in `seed_tasks.json` (present only on the held-out ten).
   Pinned by `test_frozen_config_divergence.py`.

## Current blockers

1. **BLOCKER-001** — the paper describes a prompt treatment that is not
   implemented; abstract, §3, §4, and Appendix D need correction and the
   operator should ratify the reframing.
2. **CONFLICT-001** — canonical venue files disagree; operator decision
   required before venue-dependent paper work.
3. **OPEN-001** — `final-matrix` manifest and artifact index are absent
   locally, so that campaign cannot be audited from a copied location;
   blocks the anonymized-artifact build.

## Immediate execution queue

1. Operator resolves CONFLICT-001 (venue) and ratifies the BLOCKER-001
   reframing.
2. Apply the BLOCKER-001 corrections to `paper/main.tex`, the Bayes
   appendix labels, and `supervision_decomposition`'s naming; re-run the
   suite; re-check the 4-page fit.
3. Recover or regenerate the `final-matrix` manifest/index (OPEN-001).
4. Operator's blinded labeling round.
5. E6 replication on a CUDA pod (predeclared; local variant aborted at
   commit a4b0f01 with no outcome peeking).
6. Anonymized artifact build + Codex Phase-H audit.
7. Submission before Aug 29, 2026 AoE.

## Frozen constraints

- Hidden validation never enters a deployable online decision.
- Support and correctness remain separate.
- Existing development fixtures are not relabeled as held out.
- Held-out fixtures are not tuned after outcome inspection.
- No seed-count, model, threshold, endpoint, or stopping-rule changes
  after results are inspected.
- Main result numbers come only from generated analysis over audited
  artifacts.
- No manual editing of paper result values.
- No pooled multi-arm inference.
- No unvalidated shared-classifier precision/recall in the headline.
- No public repository links or author identifiers in the double-blind
  artifact.
