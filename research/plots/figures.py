"""Scientific figure builders for tasks 44.1-44.8.

Every builder takes the paired analysis report (and, where needed, the
manifest) and returns a matplotlib Figure. Figures degrade gracefully on
small or probe-free datasets: they render an explanatory note instead of
crashing, so deterministic smoke runs and full real-model matrices share
one code path.
"""

from __future__ import annotations

from collections import Counter
from pathlib import Path

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt  # noqa: E402

from ..runner.statistics import survival_curve, wilson_interval  # noqa: E402
from .loaders import select_walkthrough_pair  # noqa: E402


# Validated categorical palette (fixed slot order, never cycled).
CATEGORICAL = [
    "#2a78d6",  # 1 blue
    "#1baf7a",  # 2 aqua
    "#eda100",  # 3 yellow
    "#008300",  # 4 green
    "#4a3aa7",  # 5 violet
    "#e34948",  # 6 red
    "#e87ba4",  # 7 magenta
    "#eb6834",  # 8 orange
]
# Single-hue sequential ramp, light -> dark, for severity ordinals 0-3.
SEVERITY_RAMP = ["#9ec5f4", "#5598e7", "#256abf", "#104281"]
BASELINE_COLOR = CATEGORICAL[0]
VERIFIED_COLOR = CATEGORICAL[1]
TEXT_MUTED = "#6b6b6b"


def _style_axes(ax) -> None:
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.grid(axis="y", alpha=0.25, linewidth=0.8)
    ax.set_axisbelow(True)


def _note(ax, message: str) -> None:
    ax.text(
        0.5,
        0.5,
        message,
        transform=ax.transAxes,
        ha="center",
        va="center",
        color=TEXT_MUTED,
        wrap=True,
    )
    ax.set_xticks([])
    ax.set_yticks([])


def figure_success_vs_trajectory_length(report: dict, manifest: dict) -> plt.Figure:
    """44.1: task success versus trajectory length (model action count)."""

    rows = report.get("tasks", [])
    fig, ax = plt.subplots(figsize=(7, 4.5))
    _style_axes(ax)
    if not rows:
        _note(ax, "No paired rows available.")
        return fig
    buckets: dict[str, dict[int, list[bool]]] = {
        "baseline": {},
        "verified": {},
    }
    for row in rows:
        for variant in ("baseline", "verified"):
            actions = row.get(f"{variant}_model_action_count")
            success = row.get(f"{variant}_evaluator_success")
            if actions is None or success is None:
                continue
            buckets[variant].setdefault(int(actions), []).append(
                bool(success)
            )
    for variant, color in (
        ("baseline", BASELINE_COLOR),
        ("verified", VERIFIED_COLOR),
    ):
        points = sorted(buckets[variant].items())
        if not points:
            continue
        xs = [actions for actions, _ in points]
        ys = [sum(values) / len(values) for _, values in points]
        ax.plot(
            xs,
            ys,
            marker="o",
            markersize=8,
            linewidth=2,
            color=color,
            label=variant,
        )
    ax.set_xlabel("Model actions used (trajectory length)")
    ax.set_ylabel("Independent evaluator success rate")
    ax.set_ylim(-0.05, 1.05)
    ax.set_title("Task success versus trajectory length")
    ax.legend(frameon=False)
    fig.tight_layout()
    return fig


def figure_accuracy_vs_action(report: dict, manifest: dict) -> plt.Figure:
    """44.2: memory probe accuracy versus action number, by severity."""

    severities = report.get("dose_response", {}).get("severities", [])
    fig, ax = plt.subplots(figsize=(7, 4.5))
    _style_axes(ax)
    plotted = False
    for entry in severities:
        curve = entry.get("mean_probe_accuracy_by_action", [])
        if not curve:
            continue
        ordinal = int(entry.get("pressure_severity_ordinal", 0))
        color = SEVERITY_RAMP[min(ordinal, len(SEVERITY_RAMP) - 1)]
        ax.plot(
            [point["action_count"] for point in curve],
            [point["mean_overall_accuracy"] for point in curve],
            marker="o",
            markersize=8,
            linewidth=2,
            color=color,
            label=(
                f"severity {ordinal} "
                f"({entry.get('pressure_severity', 'unspecified')})"
            ),
        )
        plotted = True
    if not plotted:
        _note(
            ax,
            "No task-state probe trajectories in this manifest\n"
            "(deterministic adapters cannot answer probes).",
        )
        ax.set_title("Memory accuracy versus action number")
        return fig
    ax.set_xlabel("Action number")
    ax.set_ylabel("Mean task-state probe accuracy")
    ax.set_ylim(-0.05, 1.05)
    ax.set_title("Memory accuracy versus action number, by pressure severity")
    ax.legend(frameon=False)
    fig.tight_layout()
    return fig


def figure_false_completion_vs_severity(report: dict, manifest: dict) -> plt.Figure:
    """44.3: accepted-false-completion rate versus pressure severity."""

    severities = report.get("dose_response", {}).get("severities", [])
    fig, ax = plt.subplots(figsize=(7, 4.5))
    _style_axes(ax)
    if not severities:
        _note(ax, "No severity rows available.")
        return fig
    ordinals = [
        int(entry["pressure_severity_ordinal"]) for entry in severities
    ]
    width = 0.38
    ax.bar(
        [ordinal - width / 2 for ordinal in ordinals],
        [
            entry["baseline_accepted_false_finish_rate"]
            for entry in severities
        ],
        width=width,
        color=BASELINE_COLOR,
        label="baseline",
        edgecolor="white",
        linewidth=2,
    )
    ax.bar(
        [ordinal + width / 2 for ordinal in ordinals],
        [
            entry["verified_accepted_false_finish_rate"]
            for entry in severities
        ],
        width=width,
        color=VERIFIED_COLOR,
        label="verified",
        edgecolor="white",
        linewidth=2,
    )
    ax.set_xticks(ordinals)
    ax.set_xticklabels(
        [
            f"{entry['pressure_severity_ordinal']}\n"
            f"{entry.get('pressure_severity', '')}"
            for entry in severities
        ]
    )
    ax.set_xlabel("Pressure severity")
    ax.set_ylabel("Accepted false-completion rate")
    ax.set_ylim(0, 1.05)
    ax.set_title("False completion versus pressure severity")
    ax.legend(frameon=False)
    fig.tight_layout()
    return fig


def figure_recovery_after_detection(report: dict, manifest: dict) -> plt.Figure:
    """44.4: recovery probability after corruption detection, with Wilson CIs."""

    rows = [
        row
        for row in report.get("tasks", [])
        if int(row.get("verified_memory_corruption_detections") or 0) > 0
    ]
    fig, ax = plt.subplots(figsize=(6, 4.5))
    _style_axes(ax)
    if not rows:
        _note(ax, "No runs with corruption detections.")
        ax.set_title("Recovery probability after detection")
        return fig
    total = len(rows)
    contained = wilson_interval(
        sum(1 for row in rows if row.get("verified_contained_recovery")),
        total,
    )
    strict = wilson_interval(
        sum(
            1
            for row in rows
            if row.get("verified_memory_repair_recovery")
        ),
        total,
    )
    labels = ["contained recovery\n(level >= 3)", "verified recovery\n(strict)"]
    for index, (interval, color) in enumerate(
        [(contained, VERIFIED_COLOR), (strict, CATEGORICAL[4])]
    ):
        rate = interval["rate"] or 0.0
        lower, upper = interval["ci95"]
        ax.bar(
            index,
            rate,
            width=0.55,
            color=color,
            edgecolor="white",
            linewidth=2,
        )
        ax.errorbar(
            index,
            rate,
            yerr=[[rate - (lower or 0.0)], [(upper or 0.0) - rate]],
            fmt="none",
            ecolor="#333333",
            capsize=6,
            linewidth=1.5,
        )
        ax.annotate(
            f"{interval['successes']}/{interval['total']}",
            (index, rate),
            textcoords="offset points",
            xytext=(0, 8),
            ha="center",
            color=TEXT_MUTED,
        )
    ax.set_xticks(range(len(labels)))
    ax.set_xticklabels(labels)
    ax.set_ylabel("Probability given a detection")
    ax.set_ylim(0, 1.1)
    ax.set_title(f"Recovery probability after detection (n={total})")
    fig.tight_layout()
    return fig


def figure_success_vs_verification_overhead(
    report: dict,
    manifest: dict,
) -> plt.Figure:
    """44.5: verified success versus verification overhead in extra actions."""

    rows = [
        row
        for row in report.get("tasks", [])
        if row.get("extra_model_actions") is not None
        and row.get("verified_evaluator_success") is not None
    ]
    fig, ax = plt.subplots(figsize=(7, 4.5))
    _style_axes(ax)
    if not rows:
        _note(ax, "No paired rows with overhead data.")
        ax.set_title("Success versus verification overhead")
        return fig
    for success, label, color in (
        (True, "verified success", VERIFIED_COLOR),
        (False, "verified failure", CATEGORICAL[5]),
    ):
        group = [
            row
            for row in rows
            if bool(row.get("verified_evaluator_success")) is success
        ]
        if not group:
            continue
        ax.scatter(
            [row["extra_model_actions"] for row in group],
            [
                1.0 if success else 0.0
                for _ in group
            ],
            s=80,
            color=color,
            label=f"{label} (n={len(group)})",
            alpha=0.75,
            edgecolors="white",
            linewidths=1.5,
        )
    ax.set_yticks([0, 1])
    ax.set_yticklabels(["failure", "success"])
    ax.set_xlabel(
        "Verification overhead (verified minus baseline model actions)"
    )
    ax.set_title("Verified outcome versus verification overhead")
    ax.legend(frameon=False, loc="center right")
    fig.tight_layout()
    return fig


def figure_model_task_heatmap(report: dict, manifest: dict) -> plt.Figure:
    """44.6: per-model heatmap and failure-mode distribution."""

    rows = report.get("tasks", [])
    fig, (ax_heat, ax_modes) = plt.subplots(
        1,
        2,
        figsize=(12, 4.8),
        gridspec_kw={"width_ratios": [3, 2]},
    )
    if not rows:
        _note(ax_heat, "No paired rows available.")
        _note(ax_modes, "No failure attributions available.")
        return fig

    models = sorted({row["model_name"] for row in rows})
    tasks = sorted({row["task_id"] for row in rows})
    matrix = []
    for model in models:
        line = []
        for task in tasks:
            cell_rows = [
                row
                for row in rows
                if row["model_name"] == model and row["task_id"] == task
            ]
            if not cell_rows:
                line.append(float("nan"))
            else:
                line.append(
                    sum(
                        1
                        for row in cell_rows
                        if row.get("verified_evaluator_success")
                    )
                    / len(cell_rows)
                )
        matrix.append(line)
    image = ax_heat.imshow(
        matrix,
        cmap=matplotlib.colors.LinearSegmentedColormap.from_list(
            "seq_blue",
            ["#cde2fb", "#104281"],
        ),
        vmin=0.0,
        vmax=1.0,
        aspect="auto",
    )
    ax_heat.set_xticks(range(len(tasks)))
    ax_heat.set_xticklabels(tasks, rotation=45, ha="right", fontsize=8)
    ax_heat.set_yticks(range(len(models)))
    ax_heat.set_yticklabels(models, fontsize=8)
    for row_index, line in enumerate(matrix):
        for col_index, value in enumerate(line):
            if value == value:  # not NaN
                ax_heat.text(
                    col_index,
                    row_index,
                    f"{value:.2f}",
                    ha="center",
                    va="center",
                    fontsize=8,
                    color="#ffffff" if value > 0.55 else "#1a1a19",
                )
    fig.colorbar(
        image,
        ax=ax_heat,
        label="Verified evaluator success rate",
        shrink=0.85,
    )
    ax_heat.set_title("Verified success by model and task")

    _style_axes(ax_modes)
    outcome_counts = Counter(
        (row.get("baseline_failure_attribution") or {}).get(
            "outcome_class",
            "unclassified",
        )
        for row in rows
    )
    labels = sorted(outcome_counts)
    ax_modes.barh(
        range(len(labels)),
        [outcome_counts[label] for label in labels],
        color=CATEGORICAL[0],
        edgecolor="white",
        linewidth=2,
    )
    ax_modes.set_yticks(range(len(labels)))
    ax_modes.set_yticklabels(
        [label.replace("_", " ") for label in labels],
        fontsize=8,
    )
    ax_modes.set_xlabel("Baseline runs")
    ax_modes.set_title("Baseline failure-mode distribution")
    fig.tight_layout()
    return fig


def figure_time_to_first_corrupted_belief(
    report: dict,
    manifest: dict,
) -> plt.Figure:
    """44.7: survival-style time to first corrupted belief."""

    rows = report.get("tasks", [])
    fig, ax = plt.subplots(figsize=(7, 4.5))
    _style_axes(ax)
    durations = []
    observed = []
    for row in rows:
        sequence = row.get("baseline_first_stale_claim_sequence")
        if sequence is not None:
            durations.append(float(sequence))
            observed.append(True)
        else:
            # Right-censor corruption-free runs at their final action count.
            actions = row.get("baseline_model_action_count")
            if actions:
                durations.append(float(actions))
                observed.append(False)
    curve = survival_curve(durations, observed)
    if not curve["points"]:
        _note(ax, "No corrupted beliefs observed; survival stays at 1.0.")
        ax.set_title("Time to first corrupted belief")
        return fig
    times = [0.0] + [point["time"] for point in curve["points"]]
    values = [1.0] + [point["survival"] for point in curve["points"]]
    ax.step(
        times,
        values,
        where="post",
        color=CATEGORICAL[0],
        linewidth=2,
    )
    ax.set_xlabel("Trace sequence number")
    ax.set_ylabel("P(no corrupted belief yet)")
    ax.set_ylim(-0.05, 1.05)
    ax.set_title(
        "Survival: time to first corrupted belief "
        f"(events {curve['events']}/{curve['subjects']})"
    )
    fig.tight_layout()
    return fig


_WALKTHROUGH_EVENT_STYLE = {
    "completion_claim": (CATEGORICAL[2], "finish proposal"),
    "verification_decision": (CATEGORICAL[0], "verification decision"),
    "memory_corruption_detection": (CATEGORICAL[5], "corruption detection"),
    "memory_repair_result": (CATEGORICAL[1], "repair result"),
    "memory_replan": (CATEGORICAL[4], "replan"),
    "evaluation_result": (CATEGORICAL[7], "final evaluation"),
}


def figure_walkthrough_timeline(report: dict, manifest: dict) -> plt.Figure:
    """44.8: one baseline-versus-repair trajectory walkthrough."""

    fig, ax = plt.subplots(figsize=(10, 4.5))
    _style_axes(ax)
    pair = select_walkthrough_pair(manifest)
    if pair is None:
        _note(ax, "No complete baseline/verified pair in this manifest.")
        ax.set_title("Baseline versus repair walkthrough")
        return fig
    baseline, verified = pair
    lanes = [("baseline", baseline, 0.0), ("verified", verified, 1.0)]
    seen_labels = set()
    max_sequence = 1
    for _, payload, lane_y in lanes:
        events = payload.get("trace_events", [])
        if events:
            max_sequence = max(
                max_sequence,
                max(
                    int(event.get("sequence_number", 0))
                    for event in events
                ),
            )
        ax.hlines(
            lane_y,
            0,
            max_sequence,
            color="#d9d9d9",
            linewidth=1.5,
            zorder=1,
        )
        for event in events:
            style = _WALKTHROUGH_EVENT_STYLE.get(
                event.get("event_type")
            )
            if not style:
                continue
            color, label = style
            display_label = (
                label if label not in seen_labels else None
            )
            seen_labels.add(label)
            ax.scatter(
                int(event.get("sequence_number", 0)),
                lane_y,
                s=90,
                color=color,
                label=display_label,
                zorder=3,
                edgecolors="white",
                linewidths=1.5,
            )
    ax.set_yticks([0.0, 1.0])
    ax.set_yticklabels(["baseline", "verified"])
    ax.set_ylim(-0.6, 1.6)
    ax.set_xlabel("Trace sequence number")
    ax.set_title(
        "Walkthrough: {task} (seed {seed})".format(
            task=baseline.get("task_id", "unknown task"),
            seed=baseline.get("run_metadata", {}).get("seed", "?"),
        )
    )
    ax.legend(frameon=False, loc="upper left", ncol=3, fontsize=8)
    fig.tight_layout()
    return fig


FIGURE_REGISTRY = {
    "success_vs_trajectory_length": figure_success_vs_trajectory_length,
    "accuracy_vs_action": figure_accuracy_vs_action,
    "false_completion_vs_severity": figure_false_completion_vs_severity,
    "recovery_after_detection": figure_recovery_after_detection,
    "success_vs_verification_overhead": (
        figure_success_vs_verification_overhead
    ),
    "model_task_heatmap": figure_model_task_heatmap,
    "time_to_first_corrupted_belief": (
        figure_time_to_first_corrupted_belief
    ),
    "walkthrough_timeline": figure_walkthrough_timeline,
}


def generate_figures(
    manifest_path: Path,
    output_dir: Path,
    *,
    figures: list[str] | None = None,
    dpi: int = 150,
) -> dict:
    """Render the requested figures for a manifest and return their paths."""

    from .loaders import load_analysis_report, load_manifest

    names = figures or list(FIGURE_REGISTRY)
    unknown = [name for name in names if name not in FIGURE_REGISTRY]
    if unknown:
        raise ValueError(
            f"Unknown figures: {', '.join(unknown)}; expected "
            f"{sorted(FIGURE_REGISTRY)}"
        )
    manifest = load_manifest(manifest_path)
    report = load_analysis_report(manifest_path)
    output_dir.mkdir(parents=True, exist_ok=True)
    written = {}
    for name in names:
        figure = FIGURE_REGISTRY[name](report, manifest)
        path = output_dir / f"{name}.png"
        figure.savefig(path, dpi=dpi)
        plt.close(figure)
        written[name] = str(path.resolve())
    return {
        "schema_version": "agent-memory-figures/v0.1",
        "manifest_path": str(Path(manifest_path).resolve()),
        "output_dir": str(output_dir.resolve()),
        "figures": written,
    }
