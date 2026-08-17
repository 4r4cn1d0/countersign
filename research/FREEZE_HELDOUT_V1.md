# heldout_v1 protocol freeze (2026-08-17)

User sign-off received 2026-08-17 ("freeze approved") after the design
review (research/HELDOUT_DESIGN_REVIEW.md) and passed calibration.

## What is frozen

Verifier, oracle, repair logic, and all ten heldout_v1 fixtures, at the
commit this file lands in (tagged `heldout-v1-freeze`). From the first
inspected real held-out run onward, changes to any of these require a
new `heldout_v2` split and fresh runs — no exceptions, including
"obvious bug fixes" discovered by looking at results.

## Calibration outcome (pod runs, A100 80GB, 2026-08-17)

Predeclared criteria: >= 50% hidden-evaluator success on easy dev
controls, >= 90% valid structured actions, no systematic budget
exhaustion. Settings: temperature 0.7, seeds 0-4, max-tokens 1024,
budget 24 — identical to the final matrix.

- qwen2.5-coder:14b — 15/15 evaluator success, 155/155 valid JSON
  actions, 0 budget exhaustions (8-15 actions used). PASS.
- devstral-small-2:24b — 15/15 evaluator success, 148/148 valid JSON
  actions, 0 budget exhaustions (9-15 actions used). PASS.
- deepseek-r1:8b — third-model ladder probe (predeclared §11 item 7)
  in progress at freeze time; joins the matrix iff it passes the same
  criteria. Its inclusion is calibration-determined and does not modify
  frozen logic.

## Locked run decisions

- Action budget 24 (no exhaustion signal; fallback 40 not triggered).
- Worker models: qwen2.5-coder:14b + devstral-small-2:24b (+
  deepseek-r1:8b pending its probe).
- Environment: RunPod A100 80GB PCIe (CUDA), secure cloud, pod image
  runpod/pytorch:2.4.0-py3.11-cuda12.4.1-devel-ubuntu22.04. CUDA runs
  only in the final dataset; Mac/Metal runs are never mixed in.
- Schedule: the predeclared 380-run split (§11), 570 if deepseek joins.
- Matrix launches must pass --strict-freeze and run from a clean
  checkout of the freeze tag.

## Early-signal note (recorded before any held-out run)

Calibration baselines accepted zero unsupported finishes on easy dev
fixtures. Dev-easy tasks contain no designed traps, so this is not
evidence about held-out behavior — but it is recorded now so that a
possible ceiling outcome on held-out baselines cannot be reframed
post hoc as surprising.
