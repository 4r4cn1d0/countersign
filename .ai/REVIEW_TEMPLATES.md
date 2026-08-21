# Countersign Review Templates

Reusable prompts for independent Codex review. Copy the relevant block
into the Codex request; Codex writes results to `.ai/HANDOFF.md`.

## A. Evaluator-boundary review

```text
Independently review Countersign's evaluator boundary.

Do not trust Claude's framing.

Inspect the actual controller, verifier, repair path, oracle-supervisor path,
hidden-validator calls, trace events, prompts, tests, and protocol.

Check:

1. whether any deployable condition can call hidden validation before termination;
2. whether hidden status or output can enter model-visible memory;
3. whether repair feedback can contain hidden-evaluator information;
4. whether the oracle-supervisor exception is explicitly gated and isolated;
5. whether baseline and deployable supervisor arms use the same post-termination evaluator;
6. whether raw verifier judgment and enforced action are distinct;
7. whether every call site is pinned by regression tests;
8. whether documentation accurately distinguishes deployable and oracle supervision.

Do not modify files.

Write blockers, exact paths, and falsifying tests to `.ai/HANDOFF.md`.
```

## B. Condition-parity review

```text
Independently audit intervention parity.

Compare memory_baseline, observe_only, verification_only,
verification_and_repair, repair_only, and oracle_supervisor.

Check:

1. prompt hash;
2. action-schema hash;
3. tool set;
4. task and acceptance criteria;
5. memory-pressure profile;
6. worker model and sampler settings;
7. action budget;
8. controller policies unrelated to supervision;
9. workspace/checkpoint isolation;
10. only the intended verifier/blocking/repair/oracle flags differ.

Report every hidden treatment difference.
```

## C. Support-oracle review

```text
Independently review the completion-support oracle.

Inspect support_oracle.py, fixture completion_policy metadata, requirement
updates, trace chronology, tests, and human-validation integration.

Check:

1. no imports or shared final-label logic from claims.py or verification.py;
2. supported / unsupported / uncertain are handled distinctly;
3. cited events must exist and precede the proposal;
4. relevant mutation logic uses fixture-authored ground truth;
5. requirement-update timing uses trace sequence numbers correctly;
6. authoritative and legacy sources are handled correctly;
7. no hidden-evaluator correctness leaks into support labels;
8. no-change tasks and negative controls are represented;
9. oracle labels are compared with blinded human judgments;
10. the primary endpoint does not overstate oracle validity.

Attempt to construct a case where verifier and oracle agree for the wrong reason.
Propose the cheapest decisive test.
```

## D. Held-out-fixture review

```text
Independently review heldout_v1 before any real model run.

Check:

1. every task is marked heldout_v1 from creation;
2. no held-out outcome informed verifier, oracle, prompt, or repair logic;
3. matched pairs isolate only the intended evidence relationship;
4. repository size, file count, action count, event count, visible-test count,
   difficulty, and hidden-validator difficulty are matched;
5. temporal, provenance, and requirement families are genuinely distinct;
6. negative controls expose documentation edits, unrelated edits, no-change
   completion, and irrelevant clarification;
7. targeted versus full test coverage is appropriate;
8. hidden validators do not make one pair member easier;
9. all fixture and validator hashes are frozen;
10. the freeze rule requires heldout_v2 after any outcome-informed logic change.

Do not run the real models.
Do not inspect held-out generations.
```

## E. Final-protocol freeze review

```text
Independently audit the proposed final Countersign protocol before launch.

Check:

1. clean Git revision and frozen tag;
2. development and held-out tree hashes;
3. verifier, controller, oracle, repair, intervention, prompt, and schema hashes;
4. exact model digests;
5. temperature and sampler seeds;
6. action budget and max tokens;
7. calibration threshold and fallback ladder;
8. primary endpoint and comparison;
9. pairwise statistics and task-level sensitivity analysis;
10. negative-control arms and exclusions;
11. oracle-supervisor evaluation-only status;
12. LLM-judge information diet and post-hoc-only status;
13. artifact paths and relocation audit;
14. no final output has already been inspected;
15. no unresolved Codex blocker remains.

Return GO / NO-GO with exact blockers.
Do not modify files.
```

## F. Results and statistics review

```text
Independently audit Countersign's frozen results.

Check:

1. planned versus completed run accounting;
2. reused, failed, skipped, and excluded artifacts;
3. protocol and artifact audit validity;
4. no outcome-informed model or seed changes;
5. accepted unsupported finish is separate from accepted incorrect finish;
6. oracle uncertain labels are not forced into binary outcomes;
7. primary comparison is memory_baseline vs verification_only;
8. no pooled multi-arm inference;
9. exact McNemar implementation and p-value floor;
10. task/family clustering and cluster bootstrap;
11. per-model and per-family results;
12. false-positive behavior on negative controls;
13. liveness failures after intervention;
14. worker adaptation and redundant testing;
15. repair increment versus verification_only;
16. support-oracle versus human agreement;
17. judge-supervisor versus oracle and rule supervisor;
18. every headline number maps to an exact artifact path.

Separate:

- directly supported conclusions;
- reasonable inference;
- alternative explanation;
- speculation;
- untested generalization.
```

## G. Paper review

```text
Review the Countersign paper as a skeptical reviewer for the repository's
currently locked NeurIPS 2026 workshop.

First verify the target venue from the canonical venue skill and paper README.

Focus on:

1. whether Countersign is framed consistently as a supervisory meta-agent;
2. novelty relative to runtime verification, agent monitors, trace replay,
   completion verification, and supervising-agent systems;
3. whether the deployable verifier is confused with the oracle supervisor;
4. whether justified completion is confused with correctness;
5. whether the development/held-out split supports the stated generalization;
6. whether over-blocking, liveness failure, and worker adaptation are reported;
7. whether negative or null repair results are preserved;
8. whether the statistical unit and clustering limitations are explicit;
9. whether every result is generated from the frozen held-out manifest;
10. whether the historical five-model report is excluded as evidence;
11. whether the responsible-use statement is present and adequate;
12. whether the four-page main text is self-contained;
13. whether every claim has an exact evidence path;
14. whether double-blind rules are satisfied.

Return:

- summary;
- strengths;
- fatal weaknesses;
- required revisions;
- likely reviewer score;
- questions the paper must answer;
- claims that must be weakened or removed.
```

## H. Anonymized-artifact review

```text
Audit the Countersign submission artifact.

Check:

1. no .git directory or Git history;
2. no author name, username, email, affiliation, machine path, or public-repo link;
3. no non-anonymized historical reports;
4. prior work is cited in the third person;
5. protocol, manifest, artifact index, and run paths are relocatable;
6. matrix-audit passes from the copied location;
7. hashes match;
8. no secret or credential file exists;
9. paper and artifact use the same protocol ID and result version;
10. the artifact contains enough information to reproduce the displayed claims.

Return PASS / FAIL with exact offending paths.
```
