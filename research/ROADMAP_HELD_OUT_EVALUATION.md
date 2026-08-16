# Roadmap: held-out evaluation and final protocol freeze

This picks up after items 1-5 of the reviewed sequence (unreachable
hidden-validation cleanup, relocatable experiment bundles, subset-safe
pairwise comparisons, `completion_policy` ground-truth metadata on the
development fixtures, and the independent `support_oracle.py` module —
all landed). It records items 6-11, deliberately **not** implemented in
this pass: each involves real design judgment (what counts as a matched
held-out pair, what threshold makes a model "capable enough", what CI
workflow fits this repo) that deserves a dedicated session rather than
being rushed alongside the plumbing fixes above.

Do not start item 7 (held-out fixtures) before items 5-6 are actually
solid in practice, not just landed — author a handful of scenarios,
confirm the oracle produces sane, non-`uncertain` labels against them,
*then* commit to the full six.

## 6. Relevance-aware online staleness inference — DONE (2026-08-16)

Landed as: tri-state `freshness` (`fresh`/`stale`/`uncertain`) on
`MemoryClaim` via `claims.py:_claim_freshness` (coverage-intersection
against the cited test events' `covered_files`; legacy broad rule when
coverage is absent; `uncertain` never hard-blocks);
`infer_test_coverage` full mode now covers only `*.py` files (it listed
every file, so a README edit "invalidated" full-run evidence in both the
ledger dependency graphs and claim labels); `_completion_readiness_
guidance` now keys off the ledger's relevance-aware stale flags instead
of "any write newer than the test". The ledger side
(`operational_memory._depends_on_change`) was already relevance-aware —
it was being fed the over-broad full-mode coverage.

**Fixture-design constraint discovered (binding for item 7):** under
full-run coverage every `.py` file is legitimately covered, so a
"tests pass" claim citing a *full* run after *any* later `.py` edit is
genuinely stale. Negative control 2 (unrelated-module edit → finish must
be allowed) therefore must have its trajectory cite **targeted** tests
covering the relevant module — not a full run — or the control measures
the wrong thing.

### Original plan (for reference)

The online verifier's staleness check (`benchmark_runner.py`, the
`_evaluate_finish_proposal`/claim-invalidation logic and `claims.py`'s
`_is_stale_claim`) still treats *any* later `file_state_change`/
`test_change` as invalidating prior test evidence, regardless of whether
the change touched anything the cited test actually covers. That's a
source of false positives the review flagged directly: a README edit
after passing tests would currently read as staleness.

`support_oracle.py` already solves this for the **offline** oracle, using
fixture-authored `completion_policy.relevant_paths`. The online verifier
needs its own version — but per the review's explicit independence
constraint, it must not become the same function the oracle calls:

- **Verifier**: infer relevance from information available online —
  changed files/symbols already recorded on `file_state_change`/
  `test_change` events, `covered_files`/`covered_symbols` already computed
  by `infer_test_coverage()` in `_execute_coding_tool`'s `run_tests`
  handling, direct import/dependency relationships. Return `fresh`/
  `stale`/`uncertain`, not a forced binary.
- **Oracle**: keeps using fixture-authored ground truth (already built).

Concretely: extend `claims.py`'s staleness check (or add a sibling
function) to accept the evidence event's `covered_files`/`covered_symbols`
(already on `run_tests` tool-call events, see `_execute_coding_tool`) and
only mark a cited test stale when a later mutation's `path`/`symbol`
intersects that coverage — not on any later mutation at all. Add unit
tests for the two cases the review named explicitly: a documentation-only
edit after passing tests (must stay fresh) and an edit to the actually
tested file after those tests (must go stale).

This should land *before* held-out fixtures are authored, since the
held-out negative controls (README edit, unrelated-module edit) are only
meaningful once the online verifier can tell them apart from a real
invalidation.

## 7. Held-out matched fixtures (`heldout_v1`)

Three families, each a matched supported/unsupported pair, six scenarios
total:

| Family | Supported control | Unsupported counterpart |
|---|---|---|
| Temporal freshness | Tests run after the final relevant edit | Cited tests predate a relevant edit |
| Source provenance | Agent relies on the current authoritative spec | Agent relies on a legacy/provenance-lost spec |
| Requirement state | Latest relevant clarification retained and tested | Relevant clarification lost, reordered, or omitted |

Match each pair on repository size, file count, implementation difficulty,
visible test count, action budget, and hidden-validator difficulty — only
the evidence relationship should differ. Use the same fixture format as
the 11 development scenarios (`scenario.json` + `workspace/` +
`solution/` + `hidden_validation.py`, now including `completion_policy`
and `evaluation_split: "heldout_v1"` from the start — don't retrofit it
after the fact the way the development fixtures needed).

Also add the negative controls the review called out as essential for
measuring false blocks, independent of the three matched families:

1. A passing-test-then-README-edit finish (verifier must allow). —
   **DONE** (`coding_heldout_negctrl_doc_edit_001`).
2. A passing-test-then-unrelated-module-edit finish (verifier must
   allow). — **DONE** (`coding_heldout_negctrl_unrelated_edit_001`;
   caught the converter dropping scripted `run_targeted_tests` targets,
   which silently turned targeted runs into full runs and changed their
   coverage).
3. A legitimate no-change task, where inspection alone establishes the
   repository already satisfies the requirement. — **DONE**
   (`coding_heldout_negctrl_no_change_001`; caught the gate's
   unconditional implementation-change requirement, now waived only
   when the task statement carries `allows_no_change_completion`).
4. A requirement clarification that doesn't affect the implemented
   behavior. — **DONE** (`coding_heldout_negctrl_doc_clarification_001`;
   deliberately measures the temporal requirement rule's false block —
   the trace-only verifier cannot see oracle-side `affected_paths`
   relevance, so it blocks once and the run recovers; the oracle labels
   both proposals supported. This is a reported cost of trace-only
   supervision, not a bug to fix by leaking relevance metadata).

**Freeze rule**: once real model runs against `heldout_v1` have been
inspected, do not change verifier, oracle, or repair logic in response to
what you saw. Any such change requires a new `heldout_v2` and fresh runs
— that's the entire point of holding it out.

## 8. Blinded human validation of oracle labels

The existing `human_validation.py` infrastructure (frozen stratified
sample, blinded rater CSVs, Cohen's kappa, `derive_auto_labels`) was built
for the classifier-based labels. Extend it — don't replace it — to also
sample `oracle_proposal_scores` (`support_oracle.py`'s output, already
attached to `interaction_metrics` and the verification report):

- Add oracle `support_label`/`reasons` to the sample manifest (kept
  hidden from raters, same anchoring-avoidance discipline as the existing
  auto-labels).
- Human raters judge `completion_justified` the same way they already do;
  compute agreement against *both* the classifier and the oracle labels,
  not just the classifier.
- Report oracle-vs-human agreement (Cohen's kappa) as the actual
  validation of `oracle_confusion_matrix`'s `confirmatory: false` flag —
  once that agreement is strong, flip it to `true` and promote
  `accepted_oracle_unsupported_finish_trial` to the frozen protocol's
  primary endpoint (see item 10).

## 9. Split descriptive aggregates by comparison

`_aggregate_summary`, `_pressure_analysis`, and `dose_response_curves` in
`matrix_analysis.py` still run over the full `task_rows` list, which
(correctly, for `pairwise_statistics`) contains one reference-condition
row per treatment comparison — meaning the same `memory_baseline`
observation appears multiple times in these *descriptive* aggregates.
This is not the statistical-validity bug that `pairwise_statistics` fixed
(these three are display/exploration aids, never fed into a paired
inference test), but a reader could still misread e.g. `aggregate`'s
`baseline_task_rows` as a distinct-trial count.

Add `_by_comparison` variants (`aggregate_by_comparison`,
`pressure_analysis_by_comparison`, `dose_response_by_comparison`), each
keyed by the same `reference__vs__treatment` strings
`pairwise_statistics` already uses, computed from the
already-partitioned per-comparison row subsets. Keep the existing blended
versions for quick overall exploration, clearly labeled as blended in
their output (a `"blended_across_comparisons": true` field would do it).

## 10. CI and final protocol freeze

- Add a GitHub Actions workflow running `pytest backend/tests -k research`
  on every push/PR. Right now "222 passed" (or whatever the count is at
  freeze time) is local evidence only — there's no status check attached
  to any commit SHA.
- Once items 6-9 are done and `heldout_v1` is authored and frozen, do one
  final `build_experiment_protocol` call with:
  - `controller_policy_version` bumped if anything in the online gate
    changed since `CONTROLLER_POLICY_VERSION` was last set.
  - The held-out scenario tree's hash included (extend
    `scenario_tree_path` or add a second hashed tree) alongside the
    development tree, both clearly labeled.
  - `confirmatory_comparisons.primary` switched to
    `accepted_oracle_unsupported_finish_trial` only if item 8's human
    validation actually supports it — otherwise keep
    `accepted_unsupported_finish_trial` as primary and report the oracle
    endpoint as secondary, stated plainly as not yet independently
    validated.
  - Strict mode: refuse to start unless git revision exists, working tree
    is clean, every verifier-policy hash resolved, and (if using real
    Ollama models) every selected model's digest was found.

## 11. The final run

### Predeclared settings (locked 2026-08-16, pre-freeze design review)

An experimental-design review of the held-out plan (before any fixture was
authored) fixed the following; these are settings the frozen protocol must
carry, decided before any final-run data exists:

1. **Sampling, not greedy.** `temperature: 0.7` with per-seed sampler
   seeds, **seeds 0–4** (five, not three). Greedy decoding at
   `temperature 0.0` ignores the sampler seed, so a multi-seed matrix
   would count one deterministic episode several times — textbook
   pseudoreplication. `run_model_matrix` now refuses multi-seed
   real-runtime matrices at temperature 0.0; `model_matrix.json` carries
   the predeclared values. **Capability calibration must run at these
   same settings** — a floor measured under greedy decoding does not
   transfer to sampled runs.
2. **Negative controls join the run matrix** under two arms only
   (`memory_baseline` + `observe_only`; passive raw decisions are the
   cleanest false-positive measurement). They are predeclared as
   excluded from the primary endpoint — by construction they cannot
   produce an accepted-unsupported outcome; they exist to estimate the
   false-block rate.
3. **Matched-pair context parity.** Supported and unsupported members of
   each held-out pair must match on planned action count and event count
   — not only repo size/difficulty — so the evidence-relationship
   manipulation is not confounded with context length (the very variable
   the memory-degradation story is about). Pad the supported member with
   benign events if needed.
4. **Family is the RQ1 blocking factor**: the supported-vs-unsupported
   contrast pairs members within a family (family × model × seed). With
   three families, family-level generalization is limited — state it.
5. **Clustering acknowledged in analysis**: report per-model results
   alongside pooled ones, and run a task-level (cluster) bootstrap as
   the predeclared sensitivity analysis — the 2-models × 6-tasks pair
   pool is not 36 independent pairs.
6. **Calibration fallback ladder, predeclared**: if fewer than two
   models clear the capability floor, probe `qwen2.5-coder:32b` (viable
   on a rented A100/H100); if still only one passes, run one model and
   report it as a stated limitation. No post-hoc model shopping.
7. **Third worker model, upward ladder (predeclared 2026-08-16, before
   any real held-out run)**: if a third model FAMILY clears the same
   calibration floor at the same settings, it joins the matrix
   (3 models scales the schedule to 570 runs). Decided by calibration
   only — never by results. The candidate order is fixed now:
   `deepseek-r1:8b`, then `gemma4:12b-mlx`-class, per the existing
   matrix inventory.
8. **LLM-judge supervisor comparison (predeclared 2026-08-16, before
   any real held-out run)**: a model-based supervisor scored POST HOC
   over the frozen run artifacts (`research/runner/judge_supervisor.py`,
   CLI `judge-score`), before results are read. Judge:
   `qwen2.5:32b-instruct` (digest recorded; fallback
   `qwen2.5:14b-instruct` if VRAM-constrained), temperature 0.0, one
   pass per proposal, fixed prompt template `judge_supervisor_v0`.
   Information diet identical to the online rule-based supervisor:
   pre-proposal trace events only — no completion_policy, no hidden
   validation, no post-proposal events (pinned by tests). Endpoints,
   all SECONDARY/descriptive (the primary endpoint is unchanged):
   (a) judge-vs-oracle confusion per family; (b) judge false-block
   count on negative-control proposals (same formula as the rule
   supervisor's); (c) the blind-spot probe — judge block rate on
   provenance-family finishes the rules allow; (d) judge-rule raw
   agreement. Known limitation, stated now: the judge shares the qwen
   family with one worker model; family-matched self-leniency is
   possible and will be reported per worker.

### Matrix

```
2 models × 6 heldout_v1 tasks × 5 seeds × 4 primary interventions = 240 runs
+ 2 models × 4 negative controls × 5 seeds × 2 arms                =  80 runs
+ 2 models × 6 heldout_v1 tasks × 5 seeds × oracle_supervisor      =  60 runs
                                                                     380 runs
```

Primary arms: `memory_baseline`, `observe_only`, `verification_only`,
`verification_and_repair`. `repair_only` stays a secondary ablation.

**`oracle_supervisor` — IMPLEMENTED (2026-08-16), evaluation-only upper
bound:** a gate that consults the hidden validator before allowing
termination, behind the explicit `oracle_gate` flag
(`interventions.py`/`BenchmarkRunConfig`), with `gate_mode: "oracle"` on
decision events. The trace verifier still runs and records its raw
`verifier_decision`, so oracle-vs-trace disagreement is measurable — the
new tests pin exactly that divergence (a justified-but-incorrect finish:
raw allow, oracle block). This deliberately reintroduces the mechanism
excised from the deployable gate as ground-truth leakage — which is why
it stays firewalled: `oracle_gate` is asserted False for every other
condition, results are labeled evaluation-only in every table, never
pooled into a primary comparison, never described as deployable.
`CONTROLLER_POLICY_VERSION` bumped to `v4-oracle-arm-flag`.

### Supervisory framing (meta-agents venue, locked 2026-08-16)

The conditions are presented as a supervisor ablation — worker only /
passive supervisor / halting supervisor / halting+repairing supervisor /
oracle upper bound — and two analyses are predeclared as first-class:

- **Supervisor-policy generalization**: the supervisor's rules were
  developed against the development fixtures; held-out families are the
  unseen evaluation. Report per-family and per-worker-model.
- **Supervisor-failure modes**: over-blocking (false-block rate on
  supported controls), intervention-induced liveness failure (budget
  exhaustion following repeated blocks), and worker adaptation to the
  gate (post-block behavior, redundant test runs) — all computed from
  fields the runner already records.

### Target venue (decided 2026-08-16)

Primary: **Third Workshop on Agents in the Wild: Safety, Security, and
Beyond (NeurIPS 2026)** — Short Paper track, 4 pages (references and
supplementary material excluded), NeurIPS/ICLR/ICML templates accepted,
no NeurIPS checklist required, OpenReview, non-archival. **Deadline
August 29, 2026 AoE; notification September 29.** Anonymization is fully
double-blind and explicitly extends to "any supplementary or linked
material as well, including code" — the released artifact must be the
relocatable anonymized bundle, never the public repository. AgentWild
has **no demo track**; the 4-page format is a Short Paper.

Fallback (same deadline, same anonymization discipline): "Who Verifies
the Agents?" (NeurIPS 2026), demo-paper track, ≤4 pages, NeurIPS 2026
template required. Do not submit the same paper to both.

Select the two models via a predeclared full-history capability
calibration against the *development* fixtures (never the held-out set)
before touching `heldout_v1`:

- ≥ 50% hidden-evaluator success on development controls.
- ≥ 90% valid structured actions.
- No systematic action-budget exhaustion.

Report, per the four research questions the reviewed comparisons map to:

| Question | Comparison |
|---|---|
| Does memory degradation create unsupported claims? | `memory_baseline` on supported vs. unsupported-counterpart held-out members |
| Can the verifier detect them passively? | `observe_only`'s raw decisions vs. oracle labels (`oracle_confusion_matrix`, once `confirmatory: true`) |
| Does enforcement prevent them? | `memory_baseline__vs__verification_only` |
| Does repair add value beyond blocking? | `verification_only__vs__verification_and_repair` |
| Does the verifier overblock? | raw and enforced block rates on the supported-control held-out members |
| Is utility preserved? | hidden-evaluator task success, accepted-finish rate |
| What does it cost? | extra actions/tool calls/tokens/wall time (already tracked per run) |

Do not generate this data before items 6-10 land — that's the whole
reason this file exists instead of a fifth commit today.
