#!/usr/bin/env python3
"""Generate Countersign paper figures from AUDITED run manifests.

Every number is recomputed from run artifacts at plot time — no hand-typed
values — so a figure can never drift from the data it claims to show.
"""
import json
import sys
from collections import defaultdict
from math import sqrt
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

ROOT = Path(__file__).resolve().parents[2]
RUNS = ROOT / "runs" / "pod-sync"
OUT = Path(__file__).resolve().parent

plt.rcParams.update({
    "font.family": "serif", "font.serif": ["Times New Roman", "DejaVu Serif"],
    "font.size": 9, "axes.titlesize": 9.5, "axes.titleweight": "bold",
    "axes.labelsize": 9, "legend.fontsize": 8, "legend.frameon": False,
    "figure.dpi": 300, "savefig.dpi": 300, "savefig.bbox": "tight",
    "axes.spines.top": False, "axes.spines.right": False,
    "axes.grid": True, "grid.alpha": 0.15, "axes.axisbelow": True,
})
GATE = "#E76F51"      # Countersign (ours)
BASE = "#B0BEC5"      # baseline / CI gate
MID  = "#2A9D8F"      # observe-only
INK  = "#264653"

TEST_TOOLS = {"run_tests", "run_full_tests", "run_targeted_tests"}


def wilson(k, n, z=1.96):
    if n == 0:
        return 0.0, 0.0
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    m = z * sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return max(0.0, c - m), min(1.0, c + m)


def load(base):
    p = RUNS / base / "runs"
    if not p.exists():
        return []
    return [json.loads(f.read_text()) for f in sorted(p.rglob("*.json"))]


def simple_gate_blocks(events, prop_seq):
    """CI practice: a successful test run after the last successful edit."""
    last_edit, last_green = 0, None
    for e in events:
        seq = e.get("sequence_number", 0)
        if seq >= prop_seq:
            continue
        if e.get("tool_name") in {"write_file", "apply_patch"} and e.get("status") == "success":
            last_edit = max(last_edit, seq)
        if e.get("tool_name") in TEST_TOOLS and e.get("status") == "success":
            last_green = max(last_green or 0, seq)
    return True if last_green is None else last_green < last_edit


# ---------------------------------------------------------------- figure 1
ABLATION_PHASES = ["final-matrix", "fm-negctrl-qwen", "pressure-a", "pressure-b"]
cs_catch = cs_judged = sg_catch = n_unsup = 0
sg_fp = cs_fp = n_sup = 0
for base in ABLATION_PHASES:
    for run in load(base):
        events = run.get("trace_events", [])
        oracle = {s["proposal_event_id"]: s["support_label"]
                  for s in run.get("interaction_metrics", {}).get("oracle_proposal_scores", [])}
        raw = {}
        for e in events:
            if e.get("event_type") == "verification_decision":
                cid, d = e.get("claim_event_id"), e.get("verifier_decision", e.get("decision"))
                if cid and d in ("allow", "block"):
                    raw[cid] = d
        for e in events:
            if e.get("event_type") != "completion_claim" or e.get("tool_name") != "finish":
                continue
            pid, lab = e["event_id"], oracle.get(e["event_id"])
            sg = simple_gate_blocks(events, e.get("sequence_number", 0))
            if lab == "unsupported":
                n_unsup += 1
                sg_catch += sg
                if pid in raw:
                    cs_judged += 1
                    cs_catch += raw[pid] == "block"
            elif lab == "supported":
                n_sup += 1
                sg_fp += sg
                cs_fp += raw.get(pid) == "block"

fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(5.5, 2.1))
labels = ["CI gate\n(fresh test)", "Countersign\n(evidence audit)"]
caught = [sg_catch, cs_catch]
totals = [n_unsup, cs_judged]
bars = ax1.bar(labels, caught, color=[BASE, GATE], width=0.55,
               edgecolor="white", linewidth=0.6)
for b, c, t in zip(bars, caught, totals):
    ax1.text(b.get_x() + b.get_width() / 2, c + 0.35, f"{c}/{t}",
             ha="center", fontsize=8.5, color=INK, weight="bold")
ax1.set_ylabel("unsupported claims caught")
ax1.set_ylim(0, max(totals) + 2.5)
ax1.set_title("(a) What each gate catches", loc="left")

fp = [sg_fp, cs_fp]
sup_tot = [n_sup, n_sup]
bars2 = ax2.bar(labels, fp, color=[BASE, GATE], width=0.55,
                edgecolor="white", linewidth=0.6)
for b, f, t in zip(bars2, fp, sup_tot):
    ax2.text(b.get_x() + b.get_width() / 2, 0.06, f"{f}/{t}",
             ha="center", fontsize=8.5, color=INK, weight="bold")
ax2.set_ylabel("false blocks on supported work")
ax2.set_ylim(0, 1.0)
ax2.set_title("(b) What each gate costs", loc="left")
fig.tight_layout(pad=0.4)
fig.savefig(OUT / "fig_ablation.pdf")
fig.savefig(OUT / "fig_ablation.png")
print(f"fig1: CI {sg_catch}/{n_unsup}, CS {cs_catch}/{cs_judged}; "
      f"FP CI {sg_fp} CS {cs_fp} of {n_sup} supported")

# ---------------------------------------------------------------- figure 2
def rate(runs, profile, arm, traps_only=True):
    k = n = 0
    for run in runs:
        ctx = run.get("experiment_context", {})
        if ctx.get("pressure_profile_id") != profile or ctx.get("variant") != arm:
            continue
        task = run.get("task_id", "")
        is_trap = any(t in task for t in ("stale", "legacy", "lost"))
        if traps_only and not is_trap:
            continue
        n += 1
        k += bool(run.get("interaction_metrics", {})
                  .get("accepted_oracle_unsupported_finish"))
    return k, n

grad = load("final-matrix") + load("pressure-a") + load("pressure-b")
regimes = [("full_history", "intact"), ("lossy_low", "lossy\nlow"),
           ("lossy_medium", "lossy\nmed"), ("lossy_high", "lossy\nhigh")]
ks, ns = [], []
for prof, _ in regimes:
    k, n = rate(grad, prof, "memory_baseline")
    ks.append(k); ns.append(n)

fig, (axA, axB) = plt.subplots(1, 2, figsize=(5.5, 2.2),
                               gridspec_kw={"width_ratios": [1.25, 1]})
xs = np.arange(len(regimes))
rates = [k / n if n else 0 for k, n in zip(ks, ns)]
los = [wilson(k, n)[0] for k, n in zip(ks, ns)]
his = [wilson(k, n)[1] for k, n in zip(ks, ns)]
axA.errorbar(xs, rates, yerr=[np.array(rates) - los, np.array(his) - np.array(rates)],
             fmt="o-", color=INK, ecolor="#9AA5AB", elinewidth=1, capsize=2.5,
             markersize=5, zorder=3)
for x, k, n in zip(xs, ks, ns):
    axA.annotate(f"{k}/{n}", (x, k / n), textcoords="offset points",
                 xytext=(0, 9), ha="center", fontsize=7.5, color=INK)
axA.set_xticks(xs); axA.set_xticklabels([l for _, l in regimes])
axA.set_ylabel("unsupported completion rate")
axA.set_ylim(-0.02, 0.75)
axA.set_title("(a) Truncating history: no effect", loc="left")

# resume regime, provenance cells: the three arms
res = load("substrate-resume") + load("e5-observe")
arms = [("memory_baseline", "baseline", BASE), ("observe_only", "observe\nonly", MID),
        ("verification_only", "Countersign", GATE)]
vals, lbls, cols = [], [], []
for arm, lab, col in arms:
    k = n = 0
    for run in res:
        ctx = run.get("experiment_context", {})
        if ctx.get("variant") != arm or "provenance" not in run.get("task_id", ""):
            continue
        n += 1
        k += bool(run.get("interaction_metrics", {})
                  .get("accepted_oracle_unsupported_finish"))
    vals.append((k, n)); lbls.append(lab); cols.append(col)
bars = axB.bar(range(3), [k / n if n else 0 for k, n in vals], color=cols,
               width=0.6, edgecolor="white", linewidth=0.6)
for b, (k, n) in zip(bars, vals):
    axB.text(b.get_x() + b.get_width() / 2, (k / n if n else 0) + 0.02,
             f"{k}/{n}", ha="center", fontsize=8, color=INK, weight="bold")
axB.set_xticks(range(3)); axB.set_xticklabels(lbls)
axB.set_ylim(0, 0.75)
axB.set_ylabel("unsupported completion rate")
axB.set_title("(b) Resume-summary: prompt + gate", loc="left")
fig.tight_layout(pad=0.4)
fig.savefig(OUT / "fig_regimes.pdf")
fig.savefig(OUT / "fig_regimes.png")
print("fig2 lossy:", list(zip(ks, ns)), "| resume arms:", vals)
