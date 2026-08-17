---
name: runpod-compute-runbook
description: Runbook for executing this project's calibration and final 380-run matrix on a rented GPU pod (RunPod or any SSH-able CUDA box). Use whenever provisioning the pod, running calibration or the final matrix, recovering an interrupted run, or pulling artifacts back for analysis.
---

# GPU pod runbook (calibration + final matrix)

Predeclared settings live in `research/ROADMAP_HELD_OUT_EVALUATION.md`
§11 and `research/agents/model_matrix.json` (temperature 0.7, seeds 0–4,
counterbalanced order). The frozen protocol enforces integrity; this
runbook is the operational sequence. **Do not start the final matrix
before the strict freeze commit exists and is tagged.**

## 0. Non-negotiables

- **One environment for everything that gets compared.** Calibration and
  the final matrix run on the same pod image/GPU class. Never mix Mac
  (Metal) runs with pod (CUDA) runs in one dataset — different kernels
  produce different samples even at the same seed.
- Run from a **clean checkout of the frozen tag**, never a dirty tree.
- GPU choice: A100 80GB-class keeps the `qwen2.5-coder:32b` calibration
  fallback viable. A 4090/L40S works for 14B/24B only.
- Spot/community instances are fine — every run writes a durable
  `run-checkpoint.json` and the matrix skips already-completed artifacts
  on re-invocation. Prefer on-demand only if the price gap is trivial.

## 1. Pod bring-up (~15 min)

```bash
# On the pod (Ubuntu CUDA image):
apt-get update && apt-get install -y ripgrep git tmux
curl -fsSL https://ollama.com/install.sh | sh   # official installer
ollama serve &                                   # if not already a service

git clone <repo-url> observer && cd observer
git checkout <FROZEN_TAG>
git status --porcelain                           # MUST be empty

python3 -m venv .venv && . .venv/bin/activate
pip install -r backend/requirements.txt -r research/requirements-analysis.txt
pip install "langgraph==0.6.11"                  # pinned, matches CI

ollama pull qwen2.5-coder:14b
ollama pull devstral-small-2:24b
# Fallback ladder only if calibration demands it:
# ollama pull qwen2.5-coder:32b
ollama list                                      # digests -> recorded in protocol
```

Sanity gate before any long run (should pass in ~2 min):

```bash
python -m pytest backend/tests/test_research_interventions.py -q
```

## 2. Calibration (development fixtures ONLY — never held-out)

Pass criteria (predeclared): ≥50% hidden-evaluator success on dev
controls, ≥90% valid structured actions, no systematic action-budget
exhaustion. Fallback ladder: raise budget to 40 → probe 32B → single
model with stated limitation. No post-hoc model shopping.

```bash
tmux new -s calib
python -m research.cli matrix \
  --out runs/pod-calibration \
  --agent langgraph_tools --trace-mode model_driven \
  --tier easy \
  --model qwen2.5-coder:14b --model devstral-small-2:24b \
  --interventions memory_baseline \
  --seed 0 --seed 1 --seed 2 --seed 3 --seed 4 \
  --temperature 0.7 --max-tokens 1024 \
  --minimum-successful-models 1 --format json
python -m research.cli matrix-report --manifest runs/pod-calibration/model_matrix_manifest.json --format markdown
```

`--tier easy` selects only development easy fixtures — held-out tasks
carry `tier: "heldout"` and are excluded by construction.

## 3. Final matrix (after freeze only)

Two invocations per the predeclared 380-run schedule; split by model
across two pods to halve wall-clock (`--model` selects one).

```bash
tmux new -s matrix
# IMPORTANT: `--tier heldout` selects ALL TEN held-out tasks (pairs AND
# negative controls) — never use it here, or the negative controls run
# under five arms and then again under two. The predeclared 380-run
# schedule requires the explicit task splits below.

# (a) Six matched-pair members x 5 arms (incl. oracle upper bound):
python -m research.cli matrix \
  --out runs/final-matrix \
  --agent langgraph_tools --trace-mode model_driven \
  --task coding_heldout_temporal_fresh_001 \
  --task coding_heldout_temporal_stale_001 \
  --task coding_heldout_provenance_auth_001 \
  --task coding_heldout_provenance_legacy_001 \
  --task coding_heldout_requirement_covered_001 \
  --task coding_heldout_requirement_lost_001 \
  --interventions memory_baseline observe_only verification_only \
                  verification_and_repair oracle_supervisor \
  --seed 0 --seed 1 --seed 2 --seed 3 --seed 4 \
  --temperature 0.7 --max-tokens 1024 --strict-freeze --format json

# (b) Four negative controls x 2 arms (predeclared: baseline +
#     observe_only; passive raw decisions are the false-positive
#     measurement — false-block rate comes from raw would_block on
#     these all-supported finishes):
python -m research.cli matrix \
  --out runs/final-matrix-negctrl \
  --agent langgraph_tools --trace-mode model_driven \
  --task coding_heldout_negctrl_doc_edit_001 \
  --task coding_heldout_negctrl_unrelated_edit_001 \
  --task coding_heldout_negctrl_no_change_001 \
  --task coding_heldout_negctrl_doc_clarification_001 \
  --interventions memory_baseline observe_only \
  --seed 0 --seed 1 --seed 2 --seed 3 --seed 4 \
  --temperature 0.7 --max-tokens 1024 --strict-freeze --format json
```

Notes:
- The runner refuses multi-seed real-runtime matrices at temperature 0.0
  (pseudoreplication guard) — if it raises, the settings are wrong, not
  the guard.
- Progress: watch `runs/final-matrix/workspaces/*.partial-trace.jsonl`
  sizes grow; each completed run lands under `runs/final-matrix/runs/`.
- Interruption/preemption: re-run the same command from the same
  checkout and output dir — completed run artifacts are REUSED as-is
  (`reused_run_count` in the manifest confirms it; verified by
  test_interrupted_matrix_reuses_completed_artifacts). The single
  in-flight run at interruption time is re-executed from scratch (its
  checkpoint serves `python -m research.cli resume <checkpoint>` for
  one-off recovery, but the matrix loop does not consume checkpoints).
  NOTE: if the resuming checkout is at a DIFFERENT commit than the one
  that wrote `experiment_protocol.json`, delete that file first and
  record the old protocol_id in the deviation ledger — the protocol
  embeds the source revision, and write_frozen_protocol correctly
  refuses to reuse a directory whose frozen protocol no longer matches.

## 4. Verify + pull artifacts

```bash
# On the pod:
python -m research.cli matrix-audit --manifest runs/final-matrix/model_matrix_manifest.json --format json   # must be "valid": true
tar czf final-matrix.tgz runs/final-matrix

# On the Mac:
scp <pod>:observer/final-matrix.tgz . && tar xzf final-matrix.tgz
backend/venv/bin/python -m research.cli matrix-audit \
  --manifest runs/final-matrix/model_matrix_manifest.json --format json
```

The bundle is relocatable by design (`protocol_relative_path` etc.) —
the audit must be `valid: true` **from the copied location** before the
pod is terminated. Never delete the pod before that check passes.

## 5. After pulling

- `matrix-report` for pairwise statistics (never the blended aggregate).
- `validation-sample` from the final manifest for the blinded human
  labeling round.
- `plot` for figures.
- Terminate the pod; record total spend in the work log.
