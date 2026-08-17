# FSE expansion plan (adopted 2026-08-18, from external strategy review)

Target: FSE Research Papers track (check exact 2027-cycle deadline at
conf.researchr.org/track/fse-2027/fse-2027-papers), with a
Demonstrations-track tool paper and Artifact Evaluation badges as
adjacent submissions. This plan supersedes the earlier "FSE needs
100K-scale" framing: FSE evaluates originality, importance, soundness,
evaluation quality, and comparison to prior work — small-n work wins
awards there when the design is right. Observatory's actual gap is
EXTERNAL EVIDENCE, not raw scale: the core claim currently rests on
controlled fixtures the authors designed.

## Terminology (binding for all FSE-facing text)

- Observatory is an **evidence oracle for agent termination** / an
  **evidence-grounded quality gate for coding-agent completion** —
  NEVER "a test oracle": a test oracle judges output correctness;
  Observatory explicitly judges whether the agent had sufficient
  evidence to claim correctness. Lineage to cite: runtime verification,
  test adequacy, CI quality gates, provenance, reliability.
- The public-trajectory corpus is "coding-agent execution trajectories
  on real-repository software tasks" — NOT "wild" trajectories (most
  were generated for training/evaluation, not organic deployment).

## The three-study structure

| Study | RQ | Evidence |
|---|---|---|
| 1. Observational | How often do agents terminate without adequate supporting evidence, under what conditions? | 50K–200K public trajectories (NVIDIA Open-SWE-Traces 200K+, Nebius SWE-agent 80K, SWE-Hero 34K, swe-bench/experiments leaderboard logs) |
| 2. Controlled mechanism | Can the gate distinguish supported from unsupported termination under isolated failure modes? | The frozen heldout_v1 matched pairs + negative controls (+ pressure gradient) — already running |
| 3. Real-scaffold intervention | Does blocking unsupported termination improve real agent outcomes, at what cost? | OpenHands/SWE-agent on 100–200 predeclared SWE-bench tasks |

Complementarity sentence (use it): public trajectories establish
prevalence; fixtures establish causality/mechanism; the scaffold
intervention establishes utility.

## The non-negotiable middle piece: validate the detector FIRST

No prevalence number from Study 1 is publishable until the verifier is
a VALIDATED measurement instrument — otherwise "Observatory found X%
unsupported completions" is circular. Protocol:

- Stratified sample of 400–800 termination events; strata crossed over
  model/scaffold, solved/unsolved, verifier-positive/negative,
  short/long trajectory, evidence-failure class.
- TWO independent human annotators, blinded to verifier output
  (the existing proposal-label machinery in human_validation.py is the
  seed of this; it scales by adding the second annotator and the
  trajectory-event sampler).
- Report annotator agreement, then verifier precision/recall/F1
  against adjudicated human labels. These numbers gate Study 1.

## Study 1 analysis requirements

- Clustered/mixed-effects analysis (trajectories share tasks, repos,
  models) — extends the existing pseudoreplication discipline.
- Covariates: model family, scaffold, task, trajectory length, edits
  after last test, tool-call count, failed-test repetitions, files
  modified, exit mechanism, provenance loss.
- Novelty positioning: adjacent work already studies coding-agent
  failure trajectories at scale (e.g., "Failure as a Process,"
  arXiv 2607.09510 — 1,794 trajectories, 7 models, 3 scaffolds;
  failures begin early and stay latent). Our claim must therefore be
  SPECIFICALLY: agents' epistemic justification for termination, and
  whether runtime evidence verification can intervene on it.

## Study 3 arms (predeclare before running)

Baseline agent
vs. + simple "re-run tests before finishing" gate   <- the killer
                                                        ablation: does
                                                        Observatory beat
                                                        a dumb rule?
vs. + LLM judge gate
vs. + Observatory
vs. + Observatory with bounded repair

on 100–200 predeclared SWE-bench(-Verified) tasks, two model families.
Report per arm: resolution rate, unsupported completions accepted,
supported completions falsely blocked, recovery after block, extra
steps, token cost, wall-clock overhead, supervision-induced liveness
failures. This is the quality-gate cost story SE reviewers natively
understand. FSE precedent: FSE 2026 Distinguished Paper modified an
autonomous debugging agent and evaluated on SWE-bench Verified.

## Target abstract shape

"We present the first large-scale study of evidence support for
coding-agent completion claims. Across N trajectories from multiple
scaffolds, X% of termination claims lack fresh evidence sufficient to
justify completion, and unsupported completion predicts task failure.
We introduce [Observatory], a trace-only runtime supervisor; a blinded
two-annotator study establishes its precision/recall as a measurement
instrument. Controlled matched experiments isolate temporal,
provenance, and requirement-state failure modes; an intervention study
on SWE-bench shows runtime verification reduces unsupported
termination by X% at Y% false blocks and Z% overhead."

## Sequencing

Workshop submission (Aug 29) -> detector-validation sample + adapter
over public trajectories (Sept) -> Study 1 analysis (Sept-Oct) ->
OpenHands integration + Study 3 (Oct) -> FSE research-track submission
per the 2027 cycle deadline; Demonstrations + artifact badging
alongside.
