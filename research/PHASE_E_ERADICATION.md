# Phase E: weakness-eradication sprint (predeclared 2026-08-19, before any run)

Targets three named review weaknesses (single model; censored family /
author-only fixtures; synthetic-only pressure). Predeclared here before
any Phase E run executes. Frozen tag: heldout-v1-freeze.2 — no
verifier/oracle/fixture logic changes. All prior interpretation
commitments carry over.

## E1 + E2: worker generality and capability scaling (kills W1)

Run the COMPLETE existing campaign (v1 pairs 150 + negative controls
40 + pressure gradient 180 = 370 runs per model) for two additional
predeclared workers:

- devstral-small-2:24b — the predeclared second model (family
  generality: mistral vs qwen).
- qwen2.5-coder:32b — the predeclared fallback-ladder probe, used here
  as the CAPABILITY-SCALING arm (same family as the 14B, scaled): does
  false claiming emerge with capability headroom?

Predeclared readouts: per-model replicas of every existing table; the
capability contrast is qwen-14B vs qwen-32B on identical seeds/tasks.
Interpretation commitments: (a) if 32B slips MORE, capability headroom
is a candidate driver of unsupported termination (motivates FSE Study
1); (b) if all three models are flat, the robustness finding
generalizes across family and scale AT THIS TASK SCALE, stated with
that scope; (c) per-model results reported separately, never pooled
across models.

## E3: uncensor the requirement family (kills the W2 censoring clause)

The predeclared budget-40 fallback is hereby invoked AS A SUPPLEMENT
(the budget-24 cells remain the primary, protocol-consistent data):
requirement pair × 5 arms × 5 seeds × budget 40, for all three
workers (50 runs/model). Reported as "requirement family, extended
budget" alongside — never replacing — the censored budget-24 cells, with
the censoring itself still reported as a finding about task-weight vs
budget calibration.

## E4: real-pattern memory degradation (kills W5's synthetic-only clause)

Two additions, both predeclared:

1. The FROZEN registry's `resume_medium` profile (condition
   resume_summary — the agent proceeds from a session-resumption
   summary, the deployed pattern in production scaffolds): 6 pair
   fixtures × 2 arms (baseline, verification_only) × 5 seeds × 3
   models = 180 runs. This profile predates the freeze and was never
   cherry-picked against results.
2. STRETCH (only if wall-clock permits before writing freeze,
   ~Aug 24): an `llm_condenser` profile that summarizes older visible
   events with a small LLM — mimicking deployed condenser policies —
   implemented in the (unhashed) pressure machinery, predeclared
   before its first run in an addendum here. If it does not run by
   Aug 24 it moves to the FSE version.

Full ecological W5 eradication (a real scaffold's own condenser in
situ) is explicitly scoped to FSE Study 3.

## What Phase E does NOT claim to fix

W2's fixture-realism clause ("author-built micro-repos") is only
PARTIALLY addressed before Aug 29: the prevalence pilot over public
real-repository trajectories (adapter already in progress) brings real
repos into the paper as observational evidence, and heldout_v2
(real-repo fixtures with history-mined traps) is the October
eradication. The workshop paper states this scope plainly.

## Budget and schedule (predeclared estimates)

- ~920 additional runs across two H100 pods; ~$180–260; ~30–40
  pod-hours wall-clock split across pods; launch 2026-08-19, data
  complete by ~2026-08-21, leaving Aug 22–27 for validation, figures,
  writing (paper may return to the 9-page Full track given three
  models × two degradation regimes — decided after E-data).
- Kill condition: if E-runs threaten the Aug 27 writing freeze, E4.2
  is dropped first, then E3's 32B leg; E1/E2's v1 pairs are never
  dropped.

## Sequencing amendment (user decision, 2026-08-19, before any E-run)

Model expansion (E1 devstral, E2 qwen-32b) is GATED on a substrate
validation checkpoint — no second-model spend until the test substrate
itself is shown adequate. The checkpoint runs on qwen only:

1. E3 (budget-40 requirement supplement, qwen): does the heaviest
   family ENGAGE its trap when given room? (50 runs)
2. E4.1 (resume_summary regime, qwen): does the real-pattern
   degradation regime produce interpretable behavior? (60 runs)
3. The prevalence pilot over public real-repository trajectories
   (free, local): does the failure class exist OUTSIDE the fixtures at
   a nontrivial, measurable rate?

Substrate verdict criteria (predeclared): the substrate is "good
enough" to justify model scaling iff (a) the requirement family
engages (finishes occur; trap either bites or is defused — either is
informative), AND (c) the pilot shows the construct is measurable on
real trajectories with nontrivial coverage (per the FSE plan's
abstention rules). If (c) fails, model scaling is deprioritized in
favor of substrate work (heldout_v2), per the standing kill
conditions.
