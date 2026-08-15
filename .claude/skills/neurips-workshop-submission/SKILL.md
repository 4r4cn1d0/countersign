---
name: neurips-workshop-submission
description: Venue requirements, framing, and submission checklist for this project's NeurIPS 2026 workshop paper. Use whenever drafting, revising, planning, or packaging the paper or its anonymized artifact, or when deciding what a section/figure/claim must satisfy for submission.
---

# NeurIPS 2026 workshop submission (Agent Memory Observatory)

Both candidate venues were fetched from their CFP pages on 2026-08-16.
Facts below are from those pages; do not silently contradict them.

## Primary target: AgentWild (preferred)

**Third Workshop on Agents in the Wild: Safety, Security, and Beyond**
(NeurIPS 2026) — https://agentwild-workshop.github.io/neurips2026/

- Track: **Short Paper, 4 pages**. There is **no demo track** — never
  call the submission a "demo paper" in AgentWild materials.
- References and supplementary materials do not count against the limit.
- Templates: NeurIPS, ICLR, or ICML LaTeX (top-venue templates accepted).
- No NeurIPS paper checklist required.
- **Deadline: August 29, 2026 AoE. Notification: September 29, 2026.**
- OpenReview; non-archival; work under review elsewhere is welcome.
- Anonymization: fully double-blind, and **explicitly extends to "any
  supplementary or linked material as well, including code."**
- Topic fit: agent safety, evaluation/benchmarking, trustworthiness.

## Fallback: Who Verifies the Agents?

**"Who Verifies the Agents? Toward Reliable Agent Development"**
(NeurIPS 2026, Sydney, Dec 11–12) —
https://verify-agents-workshop.github.io/

- Tracks: regular papers 4–9 pages; **demo papers ≤ 4 pages**.
- NeurIPS 2026 template required; double-blind; OpenReview;
  non-archival. Same deadline and notification dates as AgentWild.
- Do **not** submit the same paper to both workshops.

## Framing per venue

- AgentWild: lead with deployment safety — unsupported completion claims
  as a concrete in-the-wild failure of autonomous coding agents; runtime
  verification as the guardrail. Verification mechanics support the
  safety story.
- Verify-agents (fallback): lead with the verification discipline — the
  justified-vs-correct distinction (trace-only online verifier vs
  post-termination hidden evaluation) is the core contribution.

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
- Terminology: "operational memory," "self-hosted open-weight models" —
  no literal dementia claims, no "local-only" claims that break on
  rented GPUs.

## Anonymized artifact checklist (both venues)

Build from the relocatable bundle machinery (`resolve_bundle_path`,
artifact index), never by hand:

1. No git history, no `.git/`.
2. No author-identifying strings: `spiderishi`, `4r4cn1d0`, real name,
   email, machine paths (`/Users/...`) — grep the whole artifact.
3. No links to the public repository or its issues/commits.
4. Frozen protocol + manifest + run artifacts pass `matrix-audit`
   (`valid: true`) from inside the copied bundle.
5. Non-anonymized historical reports (five-model comparison) excluded.

## Sequencing with installed user skills

experimental-design (done: pre-freeze review) → statistical-analysis
(results honesty at small n) → academic-plotting (system figure, results
figures) → ml-paper-writing + paper-lookup (draft + related work) →
academic-paper-reviewer / peer-review (pre-submission panel, ~Aug 28).
