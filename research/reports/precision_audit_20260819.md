# Audit of the "perfect precision" result (2026-08-19)

Triggered by a correctness challenge ("these numbers seem too good to
be true"). Four defects found in the first reporting; all corrected in
the paper, the figures, and the figure-generation script.

## 1. Denominator inflation (CORRECTED)

First reported: "zero false blocks across 314 supported proposals."
110 of those 314 occurred in arms with NO verifier running and could
not have been blocked. Counting them as successes inflates apparent
safety. Honest denominator = proposals a verifier actually judged:

- campaign-wide: 0 false blocks / **204** judged supported (95% CI [0, 0.018])
- ablation subset: 0 / **161** judged supported (was reported as 256)

## 2. Near-tautological agreement (CORRECTED — most serious)

13 of the 17 blocks are on proposals citing NO evidence at all. Any
rule detects that case, and the verifier and the independent oracle
cannot meaningfully disagree on it, so most of the "perfect precision"
measures detection of the easiest possible case rather than
discrimination. Only **4 blocks required substantive reasoning**
(staleness / provenance). The paper now says this explicitly, the
ablation figure stacks trivial vs substantive catches, and the
ablation's headline drops from "10 caught only by evidence rules" to
**9**, of which few are substantive.

## 3. Point estimate presented without uncertainty (CORRECTED)

17/17 is not 1.00 with certainty: 95% CI [0.816, 1.0]. Recall was
never reported at all; it is 17/18 = 0.944, 95% CI [0.742, 0.99].
Both now appear in the Results.

## 4. Null result overstated (CORRECTED)

The flat truncation curve rests on 15 runs per cell, where Wilson
intervals span ~0.01-0.30. Effects below ~30 percentage points are not
resolvable. "Flat / no effect" is now stated as **no detectable
increase at modest power**, in the text, the section heading, and the
figure caption.

## Standing rule

Every headline proportion must ship with (a) the denominator that
could actually have produced the event, (b) an interval, and (c) a
statement of how much of the effect is trivially detectable.

## 5. Endpoint suppressed by construction (CORRECTED — found by a second challenge)

Challenge: "why do we have the 0/10, it's not believable."

Correct. The primary endpoint is `accepted_oracle_unsupported_finish`.
In a BLOCKING arm an unsupported finish is blocked and therefore never
accepted, so a rate of zero there is partly a definitional consequence
of the intervention, not an empirical reduction.

Trace-level counts on the ten provenance cells under resume_medium:

| arm | unsupported PROPOSALS | blocked | accepted-unsupported |
|---|---|---|---|
| memory_baseline | 5 | 0 | 5 |
| observe_only | 3 | 0 (no authority) | 3 |
| verification_only | 2 | 2 | 0 |

Honest reading, now in the paper:
- The PROMPT reduces unsupported proposals 5 -> 3.
- The further 3 -> 2 is sampling noise: the gate cannot influence a
  worker's FIRST proposal.
- The gate's own contribution is NOT a lower rate but a different
  OUTCOME: it blocked both unsupported proposals it saw, and both
  episodes recovered and terminated with supported evidence rather
  than exhausting budget.

Figure 2b was rebuilt from an acceptance-rate bar into an OUTCOME
COMPOSITION bar (accepted / blocked-then-recovered / no unsupported
proposal) so the mechanism is visible and the suppression cannot be
mistaken for an effect. The limitations section now names the
suppression explicitly.

## Standing rule (extended)

Never report an endpoint that the intervention suppresses by
construction as evidence for that intervention. Compare at the level
the intervention cannot mechanically control (here: proposals), and
report what the intervention CHANGES (here: post-block outcomes).
