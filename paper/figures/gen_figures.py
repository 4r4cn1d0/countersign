#!/usr/bin/env python3
"""Countersign paper figures, generated from AUDITED run manifests.

Every plotted value is recomputed from the run artifacts at plot time,
so a figure cannot drift from the data it claims to show.
"""
import json
from math import sqrt
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch

ROOT = Path(__file__).resolve().parents[2]
RUNS = ROOT / "runs" / "pod-sync"
OUT = Path(__file__).resolve().parent

plt.rcParams.update({
    "font.family": "serif", "font.serif": ["Times New Roman", "DejaVu Serif"],
    "font.size": 9, "axes.titlesize": 9, "axes.titleweight": "bold",
    "axes.labelsize": 8.5, "xtick.labelsize": 8, "ytick.labelsize": 8,
    "legend.fontsize": 7, "legend.frameon": False,
    "figure.dpi": 300, "savefig.dpi": 300, "savefig.bbox": "tight",
    "axes.spines.top": False, "axes.spines.right": False,
    "axes.spines.left": True, "axes.spines.bottom": True,
    "axes.edgecolor": "#8A98A0", "axes.linewidth": 0.8,
    "axes.grid": True, "grid.alpha": 0.13, "grid.linewidth": 0.6,
    "axes.axisbelow": True, "xtick.color": "#55666E", "ytick.color": "#55666E",
})
INK, GATE, MID = "#24424E", "#D9613C", "#3D8C7C"
BLOCKED, NEUTRAL = "#F0BFA6", "#DDE4E7"


def wilson(k, n, z=1.96):
    if n == 0:
        return 0.0, 0.0
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    m = z * sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return max(0.0, c - m), min(1.0, c + m)


def load(base):
    d = RUNS / base / "runs"
    return [json.loads(f.read_text()) for f in sorted(d.rglob("*.json"))] if d.exists() else []


def unsup_rate(runs, profile, arm):
    k = n = 0
    for run in runs:
        ctx = run.get("experiment_context", {})
        if ctx.get("pressure_profile_id") != profile or ctx.get("variant") != arm:
            continue
        if not any(t in run.get("task_id", "") for t in ("stale", "legacy", "lost")):
            continue
        n += 1
        k += bool(run.get("interaction_metrics", {}).get("accepted_oracle_unsupported_finish"))
    return k, n


# ============================================================ Figure 2
grad = load("final-matrix") + load("pressure-a") + load("pressure-b")
regimes = [("full_history", "intact"), ("lossy_low", "low"),
           ("lossy_medium", "medium"), ("lossy_high", "high")]
ks, ns = zip(*[unsup_rate(grad, prof, "memory_baseline") for prof, _ in regimes])

fig, (axA, axB) = plt.subplots(1, 2, figsize=(5.5, 2.15),
                               gridspec_kw={"wspace": 0.45})

xs = np.arange(len(regimes))
rates = np.array([k / n for k, n in zip(ks, ns)])
los = np.array([wilson(k, n)[0] for k, n in zip(ks, ns)])
his = np.array([wilson(k, n)[1] for k, n in zip(ks, ns)])
axA.errorbar(xs, rates, yerr=[rates - los, his - rates], fmt="o-", color=INK,
             ecolor="#AEBBC1", elinewidth=1.1, capsize=3, linewidth=1.4,
             markersize=5, markerfacecolor="white", markeredgewidth=1.3, zorder=3)
for x, k, n, hi in zip(xs, ks, ns, his):
    axA.annotate(f"{k}/{n}", (x, hi), textcoords="offset points", xytext=(0, 4),
                 ha="center", fontsize=7, color="#55666E")
axA.set_xticks(xs); axA.set_xticklabels([l for _, l in regimes])
axA.set_xlabel("history-truncation severity")
axA.set_ylabel("unsupported completion rate")
axA.set_ylim(-0.015, 0.38); axA.set_xlim(-0.45, 3.45)
axA.set_yticks([0.0, 0.1, 0.2, 0.3])
axA.set_title("(a) No increase detected", loc="left", pad=5)

res = load("substrate-resume") + load("e5-observe")
arms = [("memory_baseline", "baseline"), ("observe_only", "observe-only"),
        ("verification_only", "Countersign")]
acc, blk, clean, lbls = [], [], [], []
for arm, lab in arms:
    a = b = c = 0
    for run in res:
        ctx = run.get("experiment_context", {})
        if ctx.get("variant") != arm or "provenance" not in run.get("task_id", ""):
            continue
        m = run.get("interaction_metrics", {})
        n_unsup = sum(1 for x in m.get("oracle_proposal_scores", [])
                      if x["support_label"] == "unsupported")
        if m.get("accepted_oracle_unsupported_finish"):
            a += 1
        elif n_unsup:
            b += 1
        else:
            c += 1
    acc.append(a); blk.append(b); clean.append(c); lbls.append(lab)
acc, blk, clean = map(np.array, (acc, blk, clean))

x = np.arange(3); W = 0.56
axB.bar(x, acc, W, color=GATE, edgecolor="white", linewidth=1.5, zorder=3,
        label="accepted unsupported")
axB.bar(x, blk, W, bottom=acc, color=BLOCKED, edgecolor="white", linewidth=1.5,
        zorder=3, label="blocked, then recovered")
axB.bar(x, clean, W, bottom=acc + blk, color=NEUTRAL, edgecolor="white",
        linewidth=1.5, zorder=3, label="no unsupported proposal")
for xi, (a, b) in enumerate(zip(acc, blk)):
    if a:
        axB.text(xi, a / 2, str(a), ha="center", va="center", fontsize=8,
                 color="white", weight="bold", zorder=4)
    if b:
        axB.text(xi, a + b / 2, str(b), ha="center", va="center", fontsize=8,
                 color=INK, weight="bold", zorder=4)
axB.set_xticks(x); axB.set_xticklabels(lbls, fontsize=7.5)
axB.set_ylabel("episodes (of 10)")
axB.set_ylim(0, 10.3); axB.set_xlim(-0.6, 2.6); axB.set_yticks([0, 5, 10])
axB.set_title("(b) Resume-summary outcomes", loc="left", pad=5)
handles, labels = axB.get_legend_handles_labels()
fig.legend(handles, labels, loc="lower center", bbox_to_anchor=(0.5, -0.10),
           ncol=3, handlelength=1.0, handleheight=0.85, columnspacing=1.4,
           borderpad=0.0)
fig.savefig(OUT / "fig_regimes.pdf"); fig.savefig(OUT / "fig_regimes.png")
print("fig_regimes:", list(zip(ks, ns)), "| acc", list(acc), "blk", list(blk), "clean", list(clean))

# ============================================================ Figure 1 (loop)
fig, ax = plt.subplots(figsize=(5.5, 1.52))
ax.set_xlim(0, 10.4); ax.set_ylim(0.42, 3.00); ax.axis("off")


def box(x, y, w, h, label, fc, ec, fs=8.5):
    ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0.05,rounding_size=0.10",
                                facecolor=fc, edgecolor=ec, linewidth=1.1, zorder=3))
    ax.text(x + w / 2, y + h / 2, label, ha="center", va="center", fontsize=fs,
            color=INK, weight="bold", linespacing=1.2, zorder=4)


def arrow(x1, y1, x2, y2, color=INK, ls="-", lw=1.1, rad=0.0):
    ax.add_patch(FancyArrowPatch((x1, y1), (x2, y2), arrowstyle="-|>", color=color,
                                 linewidth=lw, linestyle=ls, mutation_scale=8,
                                 shrinkA=0, shrinkB=0, zorder=2,
                                 connectionstyle=f"arc3,rad={rad}"))


# upper band: the loop itself
box(0.10, 1.42, 2.15, 0.86, "worker\nagent", "#EDF1F3", INK)
box(3.75, 1.42, 2.45, 0.86, "Countersign\nsupervisor", "#FBE7DE", GATE)
box(7.55, 1.98, 2.75, 0.56, "accept", "#E6F1EE", MID, fs=8)
box(7.55, 1.16, 2.75, 0.56, "block + guidance", "#FBE7DE", GATE, fs=8)

# worker -> supervisor, label given its own clear band above the arrow
arrow(2.32, 1.72, 3.70, 1.72)
ax.text(3.01, 1.86, "claim +\ncited events", ha="center", va="bottom",
        fontsize=6.1, color="#55666E", linespacing=1.1)

# supervisor -> outcomes
arrow(6.26, 1.95, 7.50, 2.22)
arrow(6.26, 1.66, 7.50, 1.44, color=GATE)

# feedback path: routed BELOW every box, never through one
ax.plot([7.55, 7.55], [1.14, 0.92], color=GATE, linewidth=1.1,
        linestyle=(0, (3.2, 2.2)), zorder=2)
ax.plot([7.55, 1.18], [0.92, 0.92], color=GATE, linewidth=1.1,
        linestyle=(0, (3.2, 2.2)), zorder=2)
arrow(1.18, 0.92, 1.18, 1.40, color=GATE, ls=(0, (3.2, 2.2)))
ax.text(4.36, 0.62, "gather fresh evidence, re-propose", ha="center",
        fontsize=6.3, color=GATE)

# the hidden evaluator sits outside the loop, and is labelled as such
ax.plot([0.10, 10.30], [2.70, 2.70], color="#D6DEE1", linewidth=0.7, zorder=0)
ax.text(5.20, 2.78, "hidden evaluator: runs once after termination, never consulted by the supervisor",
        ha="center", fontsize=6.2, color="#93A1A8", style="italic")
fig.savefig(OUT / "fig_loop.pdf"); fig.savefig(OUT / "fig_loop.png")
print("fig_loop: written")
