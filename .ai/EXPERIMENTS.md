# Countersign Experiment Ledger

Append-only. Backfilled 2026-08-21 from the repository's own records
(`research/FREEZE_HELDOUT_V1.md`, `research/PRESSURE_PHASE_V2.md`,
`research/PHASE_E_ERADICATION.md`, campaign protocols under
`runs/pod-sync/`). Entries record what the artifacts show, including
failures; nothing is rewritten as a successful precursor.

The full per-experiment schema (research question → hypothesis →
estimand → unit → clustering → conditions → configuration →
held-constant invariants → evaluator boundary → preregistration →
evidence paths → execution accounting → results → verdict) applies to
new experiments. Backfilled entries carry the fields the historical
record actually supports; missing fields are marked NOT RECORDED rather
than reconstructed.

---

## EXP-CTR-001 — Historical five-model bounded LangGraph study

### Status

DEPRECATED FOR EMPIRICAL CLAIMS

### Research question

Does operational-memory degradation vary across model families on
bounded LangGraph tasks?

### Why deprecated

`compute_structured_memory_metrics` scored unparsed model responses as
perfectly healthy (`1.0 - x/count if count else 1.0` → 1.0) and
`compute_semantic_drift_score` returned 0.0 drift on empty text, so two
unparsed rows entered the reported aggregates as ideal. The study also
predates the fixture-backed suite, the support oracle, and the
evaluator-boundary fix.

### Verdict

INVALIDATED for empirical claims. Never cited as current evidence; the
report is excluded from the anonymized artifact.

---

## EXP-CTR-002 — Pre-fix hidden-evaluator gate audit

### Status

COMPLETE (design defect found and fixed pre-freeze)

### Research question

Could the online finish gate observe ground truth before termination?

### Finding

Yes. `_evaluate_finish_proposal` called `_evaluate_coding_workspace`,
which ran `_run_hidden_validation`, and the result was ANDed into the
allow decision whenever `verification_blocking` was true. A second leak
passed `independent_evaluation` into the repair-diagnosis path, which
re-projected hidden status into the next turn's prompt.

### Resolution

Hidden validation now runs exactly once, after `terminated=True`,
identically in every condition. Pinned by
`test_hidden_validation_runs_exactly_once_after_termination` and
`test_verified_gate_allows_finish_when_only_hidden_validation_fails`
(asserts `independent_hidden_validation_status == "not_run"` at gate
time).

### Verdict

SUPPORTED (the defect was real; the fix is test-pinned). All results
predating the fix are deprecated.

---

## EXP-CTR-003 — Development-fixture trace-verifier experiments

### Status

COMPLETE — DEVELOPMENT ONLY

### Note

> DEVELOPMENT ONLY: the four audit checks (successful cited test, no
> stale coverage, requirement recency, no superseded source) were
> iterated against the 11 development fixtures. No number from this
> phase is a paper finding; the fixtures are labeled
> `evaluation_split: "development"`.

---

## EXP-CTR-004 — Support-oracle independence

### Status

COMPLETE (architectural invariant)

### Research question

Can the completion-support label be produced without reusing the
verifier's or claim classifier's logic, so the two can genuinely
disagree?

### Finding

`research/runner/support_oracle.py` imports only `__future__` and
`typing` — nothing from the project. Emits supported / unsupported /
uncertain with explicit precedence (no cited test → unsupported; no
fresh cited test → unsupported; legacy source cited → unsupported;
requirement not covered → unsupported; no `completion_policy` →
uncertain; else supported). `oracle_confusion` carries
`label_source: "support_oracle"`, distinct from the shared classifier's
confusion matrix.

### Known gap

Independence is enforced by convention and test construction; **no
executable import guard exists**. A one-line AST assertion would pin it
(recorded in `.ai/CURRENT_STATE.md` discrepancy 4).

### Verdict

SUPPORTED with the gap noted.

---

## EXP-CTR-005 — Relevance-aware staleness validation

### Status

COMPLETE

### Finding

Coverage is inferred statically, so documentation edits do not
invalidate code evidence and a failure superseded by a later passing run
does not permanently contradict a claim. Freshness is tri-state — the
supervisor abstains rather than guessing when coverage is unknown.
Pinned by `test_irrelevant_mutation_after_cited_test_stays_supported`
and `test_irrelevant_requirement_update_does_not_invalidate_evidence`.

### Verdict

SUPPORTED.

---

## EXP-CTR-006 — Held-out negative-control validity

### Status

COMPLETE

### Design

Four controls with no designed trap: documentation edit after green
tests, unrelated-module edit with targeted-test citation, legitimate
zero-change audit, irrelevant late clarification. Predeclared arms:
`memory_baseline` + `observe_only`.

### Finding

Campaign-wide enforced false blocks on oracle-supported work: zero
(0/204 judged supported proposals, Wilson CI [0, 0.018]).
`test_negative_control_is_never_blocked` pins the fixture-level
property.

### Caveat found 2026-08-21

The operative false-positive definition is "block on an
oracle-**supported** proposal". A control fixture can still elicit an
evidence-free claim, and blocking that is correct — two such blocks
occur in the pressure gradient. `paper/main.tex` §3 previously stated
the looser "any block on them is a false positive by construction";
corrected at commit 90f1455.

### Verdict

SUPPORTED.

---

## EXP-CTR-007 — Worker capability calibration

### Status

COMPLETE (development fixtures only)

### Predeclared floor

≥50% hidden-evaluator success on development controls, ≥90% valid
structured actions, no systematic action-budget exhaustion; fallback
ladder probes `qwen2.5-coder:32b`; no post-hoc model shopping.

### Result (A100 80GB, 2026-08-17, temp 0.7, seeds 0–4, budget 24,
max-tokens 1024)

- `qwen2.5-coder:14b`: 15/15 evaluator success, 155/155 valid actions,
  0 exhaustions — PASS
- `devstral-small-2:24b`: 15/15, 148/148, 0 — PASS
- `deepseek-r1:8b`: ladder probe in progress at freeze time; its
  decision was explicitly deferred and must not depend on held-out
  results

### Recorded pre-run

Calibration baselines accepted zero unsupported finishes on easy
development fixtures — recorded before the campaign so a ceiling outcome
could not be reframed post hoc as surprising.

### Verdict

SUPPORTED.

---

## EXP-CTR-008 — Frozen held-out main matrix

### Status

COMPLETE (audited)

### Design

380-run predeclared schedule: 6 matched held-out members × 5 arms, plus
4 negative controls × 2 arms, plus the oracle upper bound. Executed
across seven campaign directories totalling 490 runs (the pressure
gradient and resume-regime phases are included in that total).

### Preregistration

Primary endpoint `accepted_unsupported_finish_trial`; primary comparison
`memory_baseline__vs__verification_only`; paired exact McNemar; per-model
reporting with task-level cluster bootstrap; negative controls excluded
from the primary endpoint. Protocol
`1b70f72ef5ba7a0816b6b8f16b815c5a36faf98cd2d5608b1f3c59dd40ddeb7e`.

### Data split and lock

Tag `heldout-v1-freeze` (+ `.1`, `.2` infrastructure-only); verifier
policy hashes byte-identical across all three, independently re-verified
2026-08-20. Deviation ledgers: `research/FREEZE_HELDOUT_V1.md`,
`research/PRESSURE_PHASE_V2.md`, `research/PHASE_E_ERADICATION.md`.

### Execution accounting

490 runs, 341 oracle-judged finish proposals, 27 unsupported. Ledger:
327 accepted + 9 enforced blocks + 5 oracle-arm refusals = 341;
27 = 18 accepted + 9 enforced-blocked; 17 quoted blocks = 9 enforced +
8 raw would-blocks. Requirement-family trap runs exhaust the action
budget in 3/5 runs in every arm (unchanged at budget 40) — a
fixture-weight finding, not a calibration error.

### Results

See `.ai/FINDINGS.md` F1–F4 and N1–N4.

### Interpretation

- Directly supported: block precision 17/17 against the independent
  oracle; 0/204 false blocks; 7/8 enforced-block episodes recovered.
- Reasonable inference: the audit catches evidential-hygiene failures
  that a fresh-test CI rule misses.
- Alternative explanation (live): the proposal-level 5/3/2 gradient is
  run-to-run noise rather than treatment — see BLOCKER-001.
- Speculation, not claimed: that blocking unsupported completion
  prevents incorrect software.
- Untested generalization: any claim beyond one worker model and ten
  small fixtures.

### Verdict

SUPPORTED for evidence-hygiene claims; INCONCLUSIVE for safety value
(the unsupported∧incorrect cell is empty, expected ≈0.1 under
independence).

---

## EXP-CTR-009 — Oracle-supervisor upper-bound arm

### Status

COMPLETE — evaluation-only

### Result

40 runs, 30 proposals, 1 unsupported, 5 refusals, zero incorrect
completions admitted, one unsupported-but-correct finish accepted. Bounds
correctness, not justification. Never pooled into a primary comparison;
labeled evaluation-only wherever it appears.

### Verdict

SUPPORTED as a bound.

---

## EXP-CTR-010 — Post-hoc LLM-judge supervisor comparison

### Status

PLANNED (implemented, not executed)

### Design

`research/runner/judge_supervisor.py` + CLI `judge-score`, run post hoc
over frozen artifacts. Judge `qwen2.5:32b-instruct` (fallback
`qwen2.5:14b-instruct`), temperature 0.0, one pass per proposal, prompt
template `judge_supervisor_v0`. Information diet identical to the online
rule supervisor: pre-proposal trace events only, pinned by
`test_prompt_information_diet_matches_online_supervisor` (asserts no
post-proposal events, no "hidden", no "completion_policy").

### Predeclared status

All endpoints SECONDARY/descriptive; the primary endpoint is unchanged.
Known limitation: the judge shares the qwen family with one worker.

### Verdict

NOT YET RUN.

---

## EXP-CTR-011 — E5 prompt-vs-gate diagnostic

### Status

COMPLETE — INTERPRETATION UNDER REVISION (see BLOCKER-001)

### Research question as originally framed

Does the observed effect come from the evidence-citation prompt or from
the gate?

### What was run

`observe_only`, provenance pair, `resume_medium`, 10 runs, H100-matched,
protocol `9bd0aa07…` on revision `5acd35e3…`. Predeclared before the run
with three outcome branches.

### Result

Proposal-level unsupported counts over ten matched cells: baseline 5,
observe_only 3, verification_only 2. Paired discordants for
baseline-vs-observe_only: 3 vs 1, exact McNemar p = 0.625 (originally
recorded as 2 vs 0 / p = 0.50 from a marginal derivation; corrected
2026-08-20 with a ledger entry). observe_only discrimination: TP=3,
FP=0, FN=0.

### Interpretation problem found 2026-08-21

The premise that `memory_baseline` and `observe_only` differ in prompt
is FALSE. All arms share one instrumented prompt
(`test_tool_action_prompt_is_identical_across_conditions`), and the
artifacts confirm it: first prompts byte-identical in 10/10 matched
cells, first responses identical in 9/10. The contrast is therefore
treatment-identical, and its discordance measures run-to-run sampling
variation — a noise floor — not a prompt effect.

### Consequence

The primary comparison `memory_baseline__vs__verification_only` differs
only in the gate and is cleanly identified. The proposal-level gradient
should be reported as noise, and the gate's measured effect is
post-proposal (blocked-then-recovered).

### Verdict

INCONCLUSIVE as a prompt-vs-gate decomposition; INFORMATIVE as a
noise-floor and passive-discrimination measurement.

---

## EXP-CTR-012 — E6 replication (devstral, and qwen-32b if funded)

### Status

PLANNED (local variant ABORTED)

### Design

Provenance pair × `resume_medium` × {`memory_baseline`, `observe_only`,
`verification_only`} × seeds 0–4 = 30 runs per model, at temperature
0.7, max-tokens 1024, budget 24, `model_driven`, `langgraph_tools`,
under `--strict-freeze` from a clean checkout of
`heldout-v1-freeze.2`.

### Powering

Powered for REPLICATION (consistent direction and magnitude across
models), never for per-model significance: ~84 matched cells would be
needed for 80% power at the observed discordant rates
(`mcnemar_exact_power`, pinned by test). Pooled inference, if reported,
uses the predeclared cluster-aware sensitivity analysis.

### Abort record

E6-LOCAL (devstral on Apple Silicon/Metal) was launched 2026-08-21 and
aborted after 1 of 30 runs on operator decision, restoring the
one-environment rule. Only liveness values were inspected (47 events,
29.6 min, 1 proposal); no oracle label, verifier decision, or evaluator
result was read. The output directory, freeze worktree, and launcher
were deleted in full so no Metal-generated artifact can merge with pod
data. Ledgered at commit a4b0f01.

### Interpretation committed now

Same direction across models → report replication with per-model rates
and CIs, stating plainly that no single model reaches p<.05. Models
disagree → report the disagreement as the finding.

### Verdict

NOT YET RUN.
