# Simple-gate counterfactual ablation (2026-08-19)

Computed post hoc over every finish proposal in all 370 stored qwen
runs (v1 pairs, negative controls, pressure gradient). The "simple
gate" is the CI-style rule — require a successful test run after the
last successful edit — i.e., a strict, coverage- and citation-blind
subset of Countersign's temporal rule. Zero new runs; pure
counterfactual replay of stored traces.

## Headline

271 finish proposals; 15 oracle-unsupported.

| Gate | Unsupported caught | False positives (256 supported) |
|---|---|---|
| Simple CI gate | 2 / 15 | 0 |
| Countersign (raw) | 11 / 11 judged | 0 |

**10 of the 15 unsupported proposals are caught ONLY by Countersign**
— the simple gate passes them because the tests WERE green after the
edits; the deficiency was citation, provenance, or consistency,
which test-freshness gating is structurally blind to. Both gates share
the zero false-positive rate, so the comparison is not conservatism
but blindness: same cost, 5.5x the catches.

(4 unsupported proposals occurred in baseline arms where no verifier
judged them: 3 would pass the simple gate too; 1 would have been
caught by either.)

## Countersign block-reason decomposition (all raw blocks)

- 8 missing successful test evidence (citation failure)
- 7 lost provenance / missing required source type / low retrieval
  consistency (the provenance cluster)
- 7 unsupported claim
- 7 missing implementation-change evidence
- 3 unresolved requirement update newer than latest successful tests

## Reading

Every naturally occurring slip observed in this campaign was a
citation/provenance failure — exactly the class the simple gate cannot
see. This is the direct answer to the "why not just require re-running
tests?" review question, computed on the same frozen data the rest of
the paper reports. Caveat carried from the design: Countersign's
catches are scored against the independent oracle (disjoint logic,
shared trace); the human-validation pass anchors this externally.

## CAVEAT added 2026-08-19 (forensic audit)

Of the 15 oracle-unsupported proposals in this ablation, the large
majority are "no source_event_ids cited" with a fresh passing test
present in the trace. The simple CI gate cannot catch these because
the tests genuinely WERE fresh — the deficiency is citation, not test
staleness. The 2/15 vs 11/11 comparison is therefore correct as
stated, but its interpretation is narrower than "Countersign catches
evidence failures a CI gate misses": Countersign catches
UNSUBSTANTIATED (uncited) completion claims, whose underlying work was
usually verified. Report accordingly.
