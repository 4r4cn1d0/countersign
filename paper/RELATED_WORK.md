# Related-work harvest (2026-08-16)

Curated candidates for Section 6, organized by the skeleton's buckets,
with positioning notes. URLs are from live search on the date above.
RULE: nothing moves from here into `references.bib` until its
bibliographic details are verified against the actual paper page —
never cite from a search snippet. High-confidence classics are already
in the bib; entries below marked (verify) need that check during the
writing pass.

## 1. Overclaiming / false completion (the problem we supervise)

- **METR, "Recent Frontier Models Are Reward Hacking" (2025)** —
  frontier models hacked evaluations in ~30% of software tasks
  (monkey-patching evaluators, overwriting timers); instructions not to
  cheat barely helped. THE motivating citation for supervising
  completion claims rather than trusting self-report.
  https://metr.org/blog/2025-06-05-recent-reward-hacking/ (verify: blog
  vs. formal report citation form)
- **"The Verification Horizon: No Silver Bullet for Coding Agent
  Rewards"** — arXiv 2606.26300 (verify) — limits of reward/verifier
  design for coding agents; positions why trace-only supervision has a
  principled ceiling (our oracle-gap finding agrees).
- **"Do Coding Agents Deceive Us? … Capped Evaluation with Randomized
  Tests"** — arXiv 2606.07379 (verify) — detecting cheating via
  held-out randomized tests; kin to our hidden-evaluator split.
- **SpecBench / EvilGenie style benchmarks** (verify names + venues) —
  visible-vs-held-out test splits to catch satisfying-the-exposed-
  verifier solutions. Our dev/heldout fixture split applies the same
  discipline to the SUPERVISOR'S rules, not just the worker's tests.

Positioning: prior work measures workers gaming outcome checks; we
measure whether a supervisory meta-agent can catch unjustified
termination ONLINE, and price its false blocks.

## 2. Runtime guardrails / supervision of agents (the mechanism class)

- **LlamaFirewall** (arXiv 2505.03574, in bib) — open-source guardrail
  system for agent security; action-level, security-oriented. We differ:
  evidence-grounded termination audit, not security screening.
- **AgentSpec** (verify) — customizable runtime enforcement rules for
  agents; reactive action checking.
- **TrustAgent / NeMo Guardrails / MI9 runtime governance** (verify) —
  governance frameworks; MI9 has drift detection + graduated
  containment.
- **DreamGuard** (arXiv 2608.05695, verify) — proactive guardrail via
  risk-aware world model; latency-focused. Contrast: our supervisor is
  deterministic, rule-based, and audits evidence citations rather than
  predicting risk.
- **ProbGuard** (arXiv ~2508.00500, verify) — probabilistic runtime
  monitoring. Contrast: we deliberately removed pseudo-confidence;
  discrimination is reported against oracle labels.

Positioning: guardrail work gates ACTIONS for safety; we gate
TERMINATION for epistemic support, with an explicit
justified-vs-correct separation and an oracle upper bound quantifying
what trace-only supervision cannot see.

## 3. Self-verification / reflection (the alternative to external supervision)

- Reflexion (in bib), Self-Refine (verify: Madaan et al. 2023),
  CRITIC (verify: Gou et al. 2024). Workers checking themselves;
  the METR results above show why self-checking is insufficient under
  incentive pressure — external supervision is the complement.

## 4. Process/outcome supervision and verifiers (reasoning lineage)

- Cobbe et al. 2021 (in bib) — outcome verifiers; Lightman et al. 2024
  (in bib) — process supervision. Our online supervisor is a
  process-level check at the termination boundary; the hidden evaluator
  is the outcome check. The paper's justified-vs-correct distinction
  maps onto this lineage directly.

## 5. Memory/context degradation in long-horizon agents (why claims go stale)

- **Liu et al., "Lost in the Middle" (TACL 2024, in bib)** — positional
  degradation in long contexts.
- **MemGPT** (arXiv 2310.08560, in bib) — OS-style tiered memory
  management for agents.
- **Context-rot line**: "Diagnosing and Mitigating Context Rot in
  Long-horizon Search" (arXiv 2606.29718, verify); "The Horizon Gap"
  (arXiv 2608.06663, verify) — degradation surveys for long-horizon
  agents; motivates why operational memory diverges from the trace.
- **"From Lossy to Verified: Provenance-Aware Tiered Memory"** (arXiv
  2602.17913, verify) — provenance-aware memory; closest neighbor in
  bucket 5, differs in being a memory ARCHITECTURE rather than a
  supervisory gate over an unmodified worker.

## 6. Benchmarks with hidden evaluation

- SWE-bench (in bib); tau-bench / AgentBench / WebArena (verify, cite
  only if space allows — one sentence).

## Budget note

4-page short paper: target 18–24 citations total. Buckets 1, 2, 5 are
load-bearing; 3, 4, 6 get one sentence each.

## Addendum (2026-08-18): corrections from external FSE strategy review

- **Must-cite adjacent work**: "Failure as a Process: An Anatomy of CLI
  Coding Agent Trajectories" (arXiv 2607.09510, July 2026) — 1,794
  trajectories, 7 models, 3 scaffolds; failures begin early and remain
  latent. Bucket 1 neighbor; our differentiation is epistemic
  justification FOR TERMINATION + runtime intervention, not failure
  anatomy in general. (verify details on the arXiv page)
- **Terminology rule**: never "test-oracle problem" — Observatory
  judges evidential sufficiency of the completion claim, not output
  correctness. Use "evidence oracle for agent termination" /
  "evidence-grounded quality gate". SE lineage: runtime verification,
  test adequacy, CI quality gates, provenance.
- **Corpus phrasing**: "agent execution trajectories on
  real-repository software tasks", not "wild" trajectories.
