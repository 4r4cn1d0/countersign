# Countersign Findings

Empirical claims live here only with an exact evidence path. `.ai/` is
a coordination layer, not an alternative source of results: the frozen
manifests and audited artifacts are authoritative.

## Publication-eligible findings

All numbers below are recomputed from audited run artifacts under
`runs/pod-sync/` (seven campaigns, 490 runs, verified 2026-08-20 by a
six-lane artifact audit in which 33 of 36 traceability checks
reproduced exactly; the three defects found were corrected at commits
d9e8eaf and 90f1455). Protocol lineage: `heldout-v1-freeze` /`.1`/`.2`
with byte-identical verifier-policy hashes.

### F1 — Block precision and false-block rate

- Claim: across every arm with a live verifier, all 17 blocks landed on
  proposals the independent support oracle also labelled unsupported,
  and none on the 204 supported proposals a verifier judged.
- Worker: `qwen2.5-coder:14b`; runtime ollama/langgraph_tools; CUDA
  pods (A100 then H100 — cross-phase GPU change disclosed).
- Split: heldout_v1, ten fixtures (six matched-pair members, four
  negative controls); seeds 0–4; temperature 0.7.
- Endpoint: raw verifier block decisions vs oracle support labels.
- Effect: precision 1.00, Wilson 95% CI [0.82, 1.00]; false-block rate
  0/204, CI [0, 0.018]; recall 17/18 = 0.94, CI [0.74, 0.99].
- Clustering caveat: intervals treat cells as independent though
  proposals nest in episodes and ten fixtures — nominal coverage is
  approximate.
- Limitation (load-bearing): 13 of the 17 blocks are the trivial case
  (a claim citing no evidence at all); only 4 required substantive
  reasoning about staleness or provenance. Read as "the gate does not
  misfire," not "it discriminates hard cases."
- Evidence: `runs/pod-sync/*/runs/**.json`; ledger in
  `paper/main.tex` Appendix (proposal accounting).

### F2 — Counterfactual CI-gate ablation

- Claim: replaying every stored proposal of the four ablation campaigns
  against "require a successful test run after the last edit" catches 2
  of 15 unsupported proposals; Countersign judged 11 of those 15 and
  caught all 11.
- Neither gate blocked any of the 161 supported proposals both judged.
- Caveat: 7 of the 11 catches are no-citation claims — a condition the
  CI rule does not evaluate at all — so part of the gap measures
  "requires citations," not superior temporal reasoning.
- Evidence: replay logic in `paper/figures/gen_figures.py`
  (`simple_gate_blocks`), recomputed at plot time.

### F3 — Justified vs correct (the central caveat)

- Claim: over 327 accepted completions, the 2×2 of oracle claim-verdict
  against hidden-evaluator work-verdict is 307 supported∧correct,
  2 supported∧incorrect, 18 unsupported∧correct, 0 unsupported∧incorrect.
- Interpretation: every accepted unsupported completion concerned work
  that passed hidden evaluation, so Countersign is measured to catch
  poor evidential hygiene; its safety value remains a hypothesis this
  campaign cannot confirm.
- Caveat: expected count in the empty cell under verdict independence
  is ≈0.1 — emptiness is weak evidence either way.
- Evidence: `paper/main.tex` Table 1, recomputed from run artifacts.

### F4 — Post-block liveness

- Claim: the 9 enforced blocks hit 8 episodes; 7 recovered to supported
  termination, 1 ended on the missed proposal, and none exhausted its
  action budget after a block.
- Evidence: per-run `interaction_metrics` + `verification_decision`
  trace events across the seven campaigns (2026-08-21 query).

## Methodology invariants

Code/protocol facts, not empirical claims.

- **Deployable supervision is trace-only.** The hidden evaluator runs
  once, post-termination, identically in every condition; no deployable
  condition can call it earlier. Code:
  `research/runner/benchmark_runner.py`. Scope: does not by itself
  prove the *repair* path carries no hidden information — that is
  pinned separately by the diagnosis-path test.
- **Oracle supervision is evaluation-only.** `oracle_supervisor` is
  gated and excluded from deployable claims. Code:
  `research/runner/interventions.py`.
- **Support and correctness are separate objects.** Support oracle
  (`research/runner/support_oracle.py`) vs hidden validator; they share
  no final-label logic.
- **Raw and enforced verifier decisions are distinct.** Non-blocking
  arms still record what the supervisor would have done, which is what
  makes the observe-only measurement possible.
- **Prompt-matched control exists.** `observe_only` carries the
  evidence-citation prompt with the gate disabled and emits zero
  worker-visible feedback events (verified in-trace).
- **A confounded contrast cannot be silently reported as a gate
  effect.** `matrix_analysis.supervision_decomposition` returns None
  when the prompt-matched arm is absent.
- **Multi-seed real-runtime matrices at temperature 0.0 are refused**
  (pseudoreplication guard), with a regression test.
- **Freeze integrity.** Verifier-policy files are byte-identical across
  `heldout-v1-freeze`, `.1`, `.2`; each campaign protocol records
  matching hashes (independently re-verified 2026-08-20).
- **Artifact bundles are relocatable.** Integrity audits pass from a
  copied location for six of seven campaigns; see OPEN-001.

## Held-out empirical findings

### N1 — Truncation does not detectably induce false claims (NULL)

Baseline unsupported completion on trap fixtures by severity
(intact→low→medium→high): 1/15, 1/15, 1/15, 0/15. Reported as a
non-detection at modest power, not invariance: Wilson intervals at 15
runs per cell span ≈0.01–0.30, so effects under ~30 points are
unresolvable. The preregistered null branch applies. Capability was
also robust (≈60–73% finish rates across severities).

### N2 — Regime-specific summarization effect, decomposed

Over ten matched cells in the resume-summary regime, unsupported
proposals: baseline 5, observe_only 3, verification_only 2. Paired
discordants for the prompt contrast are 3 vs 1 (exact McNemar
p = 0.625). The further 3→2 is sampling noise since the gate cannot
influence a worker's first proposal. The gate's contribution is a
different fate for such proposals, not fewer of them: both it saw were
blocked and both episodes recovered.

### N3 — Measurement without power (observe-only)

In the arm that judges but cannot act, would-block decisions fired in
exactly the 3 unsupported cells and none of the other 7 (TP=3, FP=0,
FN=0) — immune to the circularity objection a blocking arm invites.

### N4 — Power calibration

With every discordant pair in one direction, the exact McNemar test
requires b ≥ 6 (one more than this campaign could produce). At the
observed discordant rates (p10 = 0.3, p01 = 0.1) ~84 matched cells are
needed for 80% power — exact enumeration, `mcnemar_exact_power`, pinned
by test. This is why E6 is framed as replication, not significance.

## Development-only observations

> DEVELOPMENT ONLY: verifier rules were iterated against the
> development suite; its behavior supports no generalization claim and
> no number from it appears in the paper.

## Negative results

Preserved deliberately; none removed for weakening the narrative.

- **Repair never fired.** `verification_and_repair`'s 40 runs produced
  no unsupported proposal, so the repair path was never exercised — an
  uninformative cell, not evidence that repair works.
- **The truncation dose–response is flat** (N1) — the predeclared null
  branch, reported as a robustness finding rather than reframed.
- **No comparison reaches p < .05**, and the campaign is one discordant
  pair short of significance by construction (N4).
- **Unsupported claims were usually correct work** (F3) — the
  construct's honest limit.
- **The designed provenance blind spot never fired**: both
  supported∧incorrect completions arose on a negative-control and a
  requirement fixture instead.
- **A fixture family is censored by task weight**: requirement-family
  trap runs exhaust the action budget in 3/5 runs in every arm, and
  raising the budget from 24 to 40 left that unchanged.
- **Classifier/oracle divergence under heavy degradation**: the shared
  claim classifier reads the worker's degraded view and degrades with
  it; the oracle reads the canonical trace. All endpoints are
  oracle-anchored.

## Invalidated apparent findings

- **The historical five-model LangGraph study is deprecated for
  empirical claims**: its aggregates folded unparsed rows in as
  perfectly healthy (health = 1.0, drift = 0.0), and it predates the
  fixture-backed suite. Never cited as current evidence.
- **Pre-fix runs with evaluator leakage**: the online finish gate once
  consulted the hidden evaluator, so any "verification reduces false
  completions" result from that period is an artifact of running the
  answer key mid-episode. Superseded by the post-termination-only
  design.
- **Circular confidence metric**: verifier consistency once scored both
  support_status and a confidence value derived from support_status —
  double-counting one signal under two names; removed.
- **"0 false blocks / 314 supported" (denominator inflation)**: counted
  110 proposals in arms with no verifier that could not have been
  blocked; corrected to 0/204.
- **"25 of 27 unsupported proposals passed hidden evaluation"
  (criterion drift)**: a real count of a different criterion (fresh
  passing test before the proposal). Under the stated hidden-evaluation
  criterion the figure is 27/27; the paper now states the
  Table-1-pinned "all 18 accepted unsupported completions passed hidden
  evaluation."
- **Prompt-effect discordants b=2, c=0, p=0.50**: hand-derived from
  marginals rather than paired cells, silently dropping a
  reverse-direction cell. Corrected to b=3, c=1, p=0.625 (and the
  Bayesian reading from 7:1 to ≈4:1). Found by artifact tracing,
  independently re-derived, ledgered as a correction.
- **"16 matched cells for 80% power"**: computed under the superseded
  all-one-direction model; corrected to ~84 (N4).
