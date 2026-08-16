# Workshop paper: Supervisory Runtime Verification

Target: **Managing Agents that Manage Agents** (Meta-Agents), NeurIPS
2026 — 4-page Short Paper + Demo Track. Deadline **Aug 29, 2026 AoE**,
OpenReview, double-blind, non-archival. Venue facts and framing rules:
`.claude/skills/neurips-workshop-submission/SKILL.md`.

## Files

- `main.tex` — the full section skeleton with per-section content plans
  as comments, the locked title/abstract framing, and the mandatory
  responsible-use statement **already drafted** (desk-reject item —
  never remove it).
- `references.bib` — high-confidence seed entries only; extend via the
  related-work harvest and verify every entry before submission.

## Template

Download the official NeurIPS 2026 workshop LaTeX style file and place
it here as `neurips_2026.sty`. Until then, `main.tex` compiles with a
plain-article fallback so structure and length can be iterated.

## Hard rules

1. **Numbers**: every empirical value comes from `matrix-report` over
   the frozen held-out manifest. The red `\RESULT{...}` placeholders
   must never be filled by hand, and a draft with visible placeholders
   must not circulate.
2. **Double-blind**: no names, affiliations, acknowledgments, repo
   links, or machine paths anywhere in the PDF or artifact; prior work
   cited in the third person.
3. **Responsible-use statement stays in** — omitting it warrants desk
   rejection at this venue.
4. Support ("justified") vs hidden-evaluator correctness are distinct
   claims; never blur them in prose, tables, or captions.
