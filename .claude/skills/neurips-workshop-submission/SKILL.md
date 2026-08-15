---
name: neurips-workshop-submission
description: Venue requirements, framing, and submission checklist for this project's NeurIPS 2026 workshop paper. Use whenever drafting, revising, planning, or packaging the paper or its anonymized artifact, or when deciding what a section/figure/claim must satisfy for submission.
---

# NeurIPS 2026 workshop submission (Agent Memory Observatory)

CFPs fetched from the venue pages on 2026-08-16. Facts below are from
those pages; do not silently contradict them.

## Target venue (user-locked 2026-08-16)

**Managing Agents that Manage Agents: Workshop on Responsible Use of
Meta-Agents** (NeurIPS 2026, Sydney, Dec 11–12) —
https://meta-agents-workshop.github.io/

- Tracks: Full Papers (max 9 pages), **Short Papers (max 4 pages)**,
  **Demo Track** ("live demonstrations of meta-agent systems and tools,
  presented alongside the poster sessions"), Position Papers.
- Plan of record: **4-page Short Paper**, plus the demo-track live
  demonstration (the dashboard's side-by-side baseline-vs-verified
  trajectory is exactly a "meta-agent tool" demo).
- Template: **NeurIPS 2026 workshop LaTeX template**, single PDF.
  References and appendices excluded from the page count, but "the main
  text must be self-contained."
- **Deadline: August 29, 2026 AoE. Notification: on or before
  September 29, 2026 AoE.** OpenReview; non-archival; concurrent
  submission elsewhere permitted.
- Double-blind: author names, affiliations, and acknowledgments
  removed; **prior work cited in the third person**.
- **HARD REQUIREMENT: every submission must include "a short
  responsible-use statement covering the potential societal impacts";
  omitting it warrants desk rejection.** Draft this early, never bolt it
  on at the deadline. For this project it writes itself: runtime
  verification that blocks unsupported completion claims is a control on
  agent overclaiming; discuss dual-use (a verifier's allow decision must
  not be marketed as a correctness guarantee), oversight displacement
  risk (humans over-trusting the gate), and open-weight release context.
- Topics of interest matched by this project: **evaluation benchmarks**,
  **misalignment and safety**, **automated agent harness design**,
  optimization of compound agentic systems, governance/human oversight.

## Framing for this venue (supervisory pivot, locked 2026-08-16)

The paper's central object is the **supervision loop**, not the
detector: a worker coding agent proposes actions and termination; the
Observatory is a **supervisory meta-agent** with authority over the
worker's termination — it audits the worker's completion claims against
the execution trace, **halts** unjustified termination, and issues
**bounded corrective guidance** ("your cited test result is stale;
re-run X", "requirement Y has no supporting evidence"). Never describe
it as a passive logger or "runtime verifier for one coding agent."

Bridge diagram (use it): worker agent → Observatory supervisor →
accept / block / repair.

- Title direction: **"Agent Memory Observatory: Supervisory Runtime
  Verification for Long-Horizon Agents"** (or "Supervising Agent
  Completion with Evidence-Grounded Runtime Verification").
- Abstract opens with the supervisor: "Long-horizon agents often
  terminate on stale, misattributed, or missing evidence. We introduce
  Agent Memory Observatory, a supervisory meta-agent that audits a
  worker agent's completion claims against its execution trace and can
  block termination or trigger bounded repair when the evidence is
  insufficient."
- Research question: *Can a lightweight supervisory meta-agent reliably
  distinguish when a worker agent has sufficient evidence to terminate,
  and intervene without inducing over-blocking or new failure modes?*
- The intervention conditions ARE the supervisor ablation — always
  present them as: worker only (`memory_baseline`), passive supervisor
  (`observe_only`), halting supervisor (`verification_only`), halting +
  repairing supervisor (`verification_and_repair`), plus the
  evaluation-only oracle-supervisor upper bound (see roadmap §11).
- The dev/held-out split IS the supervisory-policy generalization
  claim: the supervisor's rules were developed against the development
  fixtures and evaluated on unseen held-out families. Say it that way.
- Include a **supervisor-failure analysis**: over-blocking (false-block
  rate on supported controls), intervention-induced liveness failure
  (action-budget exhaustion after repeated blocks — the historical
  Devstral run is the motivating example), and worker adaptation to the
  gate (post-block behavior, redundant test runs). "Who supervises the
  supervisor" feeds the responsible-use statement directly.
- The supervisor is deterministic and rule-based: report discrimination
  (precision/recall/FPR against oracle labels), not probability
  calibration — pseudo-confidence was deliberately removed.
- Justified-vs-correct (trace-only online supervisor vs
  post-termination hidden evaluation) remains the technical core. Keep
  "operational memory"; no literal dementia claims; "self-hosted
  open-weight models" (final runs execute on rented GPUs).

## Documented alternates (same deadline, not the target)

- **"Who Verifies the Agents?"** (NeurIPS 2026) — regular 4–9pp, demo
  papers ≤4pp, NeurIPS 2026 template, double-blind, OpenReview,
  non-archival. https://verify-agents-workshop.github.io/
- **AgentWild: Agents in the Wild** (NeurIPS 2026) — 9pp regular / 4pp
  short, **no demo track**, NeurIPS/ICLR/ICML templates, double-blind
  explicitly including "any supplementary or linked material as well,
  including code". https://agentwild-workshop.github.io/neurips2026/
- Do not submit the same paper to more than one of these workshops.

## Non-negotiables carried from the project's own protocol

- Numbers come only from `matrix-report` over the frozen held-out
  manifest (`research/ROADMAP_HELD_OUT_EVALUATION.md` §11). No
  placeholder numbers in circulated drafts; the deprecated five-model
  report is never cited as evidence.
- Primary endpoint: accepted-unsupported-finish, predeclared comparison
  `memory_baseline__vs__verification_only`; support ("justified") and
  hidden-evaluator correctness are distinct claims — never blur them.
- State plainly: development fixtures were iterated against (not
  held-out); pairs are clustered by model/task (per-model results +
  task-level bootstrap reported); negative results (e.g., repair rarely
  recovering) are reported as such.

## Anonymized artifact checklist

Build from the relocatable bundle machinery (`resolve_bundle_path`,
artifact index), never by hand:

1. No git history, no `.git/`.
2. No author-identifying strings: `spiderishi`, `4r4cn1d0`, real name,
   email, machine paths (`/Users/...`) — grep the whole artifact.
3. No links to the public repository or its issues/commits.
4. Frozen protocol + manifest + run artifacts pass `matrix-audit`
   (`valid: true`) from inside the copied bundle.
5. Non-anonymized historical reports (five-model comparison) excluded.
6. Prior-work self-citations rewritten in the third person.

## Submission checklist (deadline Aug 29 AoE)

1. NeurIPS 2026 workshop template, single PDF, main text ≤4 pages and
   self-contained.
2. **Responsible-use statement present** (desk-reject item).
3. Fully anonymized (names, affiliations, acknowledgments, third-person
   self-citations, artifact scrubbed).
4. Demo-track material ready: live side-by-side trajectory with hidden
   evaluation revealed only post-termination.
5. Uploaded on OpenReview before AoE cutoff.

## Sequencing with installed user skills

experimental-design (done: pre-freeze review) → statistical-analysis
(results honesty at small n) → academic-plotting (system figure, results
figures) → ml-paper-writing + paper-lookup (draft + related work) →
academic-paper-reviewer / peer-review (pre-submission panel, ~Aug 28).
