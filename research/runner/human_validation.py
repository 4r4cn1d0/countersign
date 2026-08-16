"""Human validation sampling and agreement for task 43.

The workflow deliberately reuses the frozen-fixture discipline of
``measurement_validation``: a frozen random seed selects a stratified sample
of real-model trajectories, human raters label each on five dimensions
without seeing the automatic labels (to avoid anchoring), and
``compute_validation_agreement`` reports rater-versus-rater agreement
(Cohen's kappa) plus automatic-versus-human agreement (task 43.5) and an
adjudication ledger.
"""

from __future__ import annotations

import csv
import json
import random
from math import ceil
from pathlib import Path

from .experiment_protocol import sha256_file
from .statistics import cohens_kappa


def _iter_manifest_run_payloads(manifest_path: Path):
    """Yield (run_info, payload) for every readable run artifact in a manifest."""

    manifest = json.loads(Path(manifest_path).read_text(encoding="utf-8"))
    for model in manifest.get("models", []):
        for run_info in model.get("runs", []):
            path = Path(run_info.get("path", ""))
            if not path.is_file():
                continue
            with path.open(encoding="utf-8") as handle:
                yield run_info, json.load(handle)


SAMPLE_SCHEMA_VERSION = "agent-human-validation-sample/v0.1"
AGREEMENT_SCHEMA_VERSION = "agent-human-validation-agreement/v0.1"

# Five labeling dimensions (task 43.2). Each is a small closed vocabulary so
# Cohen's kappa is well defined; "na" is a genuine category (agreement on
# "na" counts as agreement).
LABEL_DIMENSIONS = (
    "completion_justified",
    "avoided_false_completion",
    "stale_evidence_handled",
    "task_state_tracked",
    "repair_appropriate",
)
LABEL_VOCABULARY = ("yes", "no", "na")

# Per-proposal support labels (level-up item 4): one human pass anchors
# BOTH automatic per-proposal signals — the support oracle's label and
# the rule-based verifier's raw decision — instead of the oracle alone.
PROPOSAL_LABEL_VOCABULARY = ("supported", "unsupported", "uncertain")

_CSV_METADATA_COLUMNS = (
    "run_id",
    "model_name",
    "task_id",
    "pressure_profile_id",
    "seed",
    "condition",
)


def _condition(run_metadata: dict) -> str:
    intervention = run_metadata.get("intervention", "legacy")
    if intervention and intervention != "legacy":
        return intervention
    return run_metadata.get("agent_variant", "baseline")


def derive_auto_labels(run: dict) -> dict:
    """Automatic labels for one trajectory, mirroring the human dimensions.

    These are what the automatic measurement pipeline believes; human labels
    are compared against them in task 43.5.
    """

    metrics = run.get("interaction_metrics", {})
    claims = run.get("memory_claims", [])
    task_complete = [
        claim
        for claim in claims
        if claim.get("claim_type") == "task_complete"
    ]
    # accepted_unsupported_finish/accepted_incorrect_finish are separate
    # failure classes (see benchmark_runner.py:_interaction_metrics):
    # completion_justified asks about evidence support only, matching the
    # rater instructions in _rater_readme, so it must not also require
    # evaluator_success — a well-supported claim can still be incorrect
    # without that being a justification failure.
    accepted_unsupported = bool(metrics.get("accepted_unsupported_finish"))
    accepted_incorrect = bool(metrics.get("accepted_incorrect_finish"))
    accepted_false = int(metrics.get("accepted_false_finishes", 0) or 0)
    accepted_finishes = int(metrics.get("accepted_finish_proposals", 0) or 0)
    repair_attempts = int(metrics.get("memory_repair_attempts", 0) or 0)
    recovery_level = int(metrics.get("recovery_level", 0) or 0)
    any_stale_completion = any(claim.get("stale") for claim in task_complete)

    if accepted_finishes == 0:
        completion_justified = "na"
    elif not accepted_unsupported:
        completion_justified = "yes"
    else:
        completion_justified = "no"

    # Broader than completion_justified: any accepted finish that was
    # either unsupported or turned out incorrect counts as a false
    # completion, per _rater_readme's definition of this dimension.
    avoided_false_completion = (
        "no" if (accepted_unsupported or accepted_incorrect) else "yes"
    )

    if not any_stale_completion:
        stale_evidence_handled = "na"
    elif accepted_false > 0:
        stale_evidence_handled = "no"
    else:
        stale_evidence_handled = "yes"

    task_state_tracked = _probe_label(run)

    if repair_attempts == 0:
        repair_appropriate = "na"
    elif recovery_level >= 3:
        repair_appropriate = "yes"
    else:
        repair_appropriate = "no"

    return {
        "completion_justified": completion_justified,
        "avoided_false_completion": avoided_false_completion,
        "stale_evidence_handled": stale_evidence_handled,
        "task_state_tracked": task_state_tracked,
        "repair_appropriate": repair_appropriate,
    }


def _finish_proposal_records(run: dict) -> list[dict]:
    """Per-proposal reference labels for the sampled trajectory.

    The reference labels (oracle + raw verifier decision) stay in the
    sample manifest only — the rater CSV template carries the blank
    label column and never the answers.
    """

    from .judge_supervisor import _oracle_labels, _raw_rule_decisions

    oracle_labels = _oracle_labels(run)
    rule_decisions = _raw_rule_decisions(run)
    records = []
    for event in run.get("trace_events", []):
        if (
            event.get("event_type") != "completion_claim"
            or event.get("tool_name") != "finish"
        ):
            continue
        proposal_id = str(event.get("event_id"))
        records.append(
            {
                "proposal_event_id": proposal_id,
                "sequence_number": event.get("sequence_number"),
                "claim": str(event.get("claim", "")).strip(),
                "reference": {
                    "oracle_label": oracle_labels.get(proposal_id),
                    "verifier_raw_decision": rule_decisions.get(
                        proposal_id
                    ),
                },
            }
        )
    return records


def _probe_label(run: dict) -> str:
    summary = run.get("task_state_probe_summary") or {}
    eligible = int(summary.get("eligible_probe_count", 0) or 0)
    if eligible <= 0:
        return "na"
    accuracy = summary.get("mean_overall_accuracy")
    if accuracy is None:
        return "na"
    return "yes" if float(accuracy) >= 0.7 else "no"


def build_validation_sample(
    manifest_path: Path,
    *,
    fraction: float = 0.15,
    seed: int = 20260707,
    overlap_fraction: float = 0.25,
) -> dict:
    """Select a frozen-seed stratified sample of trajectories to label."""

    if not 0.0 < fraction <= 1.0:
        raise ValueError("fraction must be in (0, 1]")
    if not 0.0 <= overlap_fraction <= 1.0:
        raise ValueError("overlap_fraction must be in [0, 1]")

    records = []
    for run_info, payload in _iter_manifest_run_payloads(manifest_path):
        metadata = payload.get("run_metadata", {})
        records.append(
            {
                "run_id": payload.get("run_id"),
                "model_name": metadata.get("model_name"),
                "task_id": payload.get("task_id"),
                "pressure_profile_id": metadata.get(
                    "pressure_profile_id",
                    run_info.get("pressure_profile_id", "full_history"),
                ),
                "seed": metadata.get("seed", run_info.get("seed")),
                "condition": _condition(metadata),
                "path": str(Path(run_info["path"]).resolve()),
                "auto_labels": derive_auto_labels(payload),
                "finish_proposals": _finish_proposal_records(payload),
            }
        )
    if not records:
        raise ValueError(
            f"No run artifacts found for manifest: {manifest_path}"
        )

    # Stratify by model x condition, frozen-seed shuffle, ceil(fraction) each.
    strata: dict[tuple, list[dict]] = {}
    for record in records:
        strata.setdefault(
            (record["model_name"], record["condition"]),
            [],
        ).append(record)

    rng = random.Random(seed)
    sampled: list[dict] = []
    for key in sorted(strata, key=lambda item: (str(item[0]), str(item[1]))):
        stratum = sorted(strata[key], key=lambda record: record["run_id"])
        rng.shuffle(stratum)
        take = max(1, ceil(fraction * len(stratum)))
        sampled.extend(stratum[:take])

    sampled.sort(key=lambda record: record["run_id"])
    overlap_count = (
        max(1, ceil(overlap_fraction * len(sampled)))
        if overlap_fraction > 0 and sampled
        else 0
    )
    overlap_pool = list(sampled)
    rng.shuffle(overlap_pool)
    overlap_run_ids = sorted(
        record["run_id"] for record in overlap_pool[:overlap_count]
    )

    return {
        "schema_version": SAMPLE_SCHEMA_VERSION,
        "source_manifest": str(Path(manifest_path).resolve()),
        "source_manifest_sha256": sha256_file(Path(manifest_path)),
        "frozen_seed": seed,
        "sample_fraction": fraction,
        "overlap_fraction": overlap_fraction,
        "population_size": len(records),
        "sample_size": len(sampled),
        "overlap_size": len(overlap_run_ids),
        "label_dimensions": list(LABEL_DIMENSIONS),
        "label_vocabulary": list(LABEL_VOCABULARY),
        "strata": {
            f"{model}::{condition}": len(members)
            for (model, condition), members in sorted(
                strata.items(),
                key=lambda item: (str(item[0][0]), str(item[0][1])),
            )
        },
        "overlap_run_ids": overlap_run_ids,
        "sampled": sampled,
    }


def write_validation_sample(
    manifest_path: Path,
    output_dir: Path,
    *,
    fraction: float = 0.15,
    seed: int = 20260707,
    overlap_fraction: float = 0.25,
) -> dict:
    """Write the sample manifest, rater CSV templates, and a rater README."""

    sample = build_validation_sample(
        manifest_path,
        fraction=fraction,
        seed=seed,
        overlap_fraction=overlap_fraction,
    )
    output_dir.mkdir(parents=True, exist_ok=True)

    manifest_out = output_dir / "sample_manifest.json"
    manifest_out.write_text(
        json.dumps(sample, indent=2, default=str),
        encoding="utf-8",
    )

    rater1_csv = output_dir / "labels_rater1.csv"
    _write_label_template(rater1_csv, sample["sampled"])

    overlap_records = [
        record
        for record in sample["sampled"]
        if record["run_id"] in set(sample["overlap_run_ids"])
    ]
    rater2_csv = output_dir / "labels_rater2.csv"
    _write_label_template(rater2_csv, overlap_records)

    proposal_rater1_csv = output_dir / "proposal_labels_rater1.csv"
    _write_proposal_label_template(proposal_rater1_csv, sample["sampled"])
    proposal_rater2_csv = output_dir / "proposal_labels_rater2.csv"
    _write_proposal_label_template(proposal_rater2_csv, overlap_records)

    readme = output_dir / "README.md"
    readme.write_text(_rater_readme(sample), encoding="utf-8")

    return {
        "sample_manifest": str(manifest_out.resolve()),
        "labels_rater1": str(rater1_csv.resolve()),
        "labels_rater2": str(rater2_csv.resolve()),
        "proposal_labels_rater1": str(proposal_rater1_csv.resolve()),
        "proposal_labels_rater2": str(proposal_rater2_csv.resolve()),
        "readme": str(readme.resolve()),
        "sample_size": sample["sample_size"],
        "overlap_size": sample["overlap_size"],
    }


def _write_label_template(path: Path, records: list[dict]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(
            [*_CSV_METADATA_COLUMNS, *LABEL_DIMENSIONS, "notes"]
        )
        for record in records:
            writer.writerow(
                [
                    record["run_id"],
                    record["model_name"],
                    record["task_id"],
                    record["pressure_profile_id"],
                    record["seed"],
                    record["condition"],
                    *["" for _ in LABEL_DIMENSIONS],
                    "",
                ]
            )


def _write_proposal_label_template(path: Path, records: list[dict]) -> None:
    """One row per finish proposal; the label column starts blank.

    Reference labels (oracle, verifier) are deliberately absent — they
    live only in sample_manifest.json so the rater stays blind.
    """

    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(
            [
                "run_id",
                "task_id",
                "condition",
                "proposal_event_id",
                "sequence_number",
                "claim",
                "proposal_support",
                "notes",
            ]
        )
        for record in records:
            for proposal in record.get("finish_proposals", []):
                writer.writerow(
                    [
                        record["run_id"],
                        record["task_id"],
                        record["condition"],
                        proposal["proposal_event_id"],
                        proposal["sequence_number"],
                        proposal["claim"],
                        "",
                        "",
                    ]
                )


def load_proposal_labels(path: Path) -> dict:
    """Load a filled proposal CSV keyed by (run_id, proposal_event_id)."""

    labels: dict[tuple[str, str], str] = {}
    with path.open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            run_id = (row.get("run_id") or "").strip()
            proposal_id = (row.get("proposal_event_id") or "").strip()
            label = (row.get("proposal_support") or "").strip().lower()
            if run_id and proposal_id and label:
                labels[(run_id, proposal_id)] = label
    return labels


def load_rater_labels(path: Path) -> dict:
    """Load a filled rater CSV keyed by run_id."""

    labels: dict[str, dict] = {}
    with path.open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            run_id = (row.get("run_id") or "").strip()
            if not run_id:
                continue
            labels[run_id] = {
                dimension: (row.get(dimension) or "").strip().lower()
                for dimension in LABEL_DIMENSIONS
            }
    return labels


def compute_proposal_agreement(
    sample: dict,
    proposal_labels_rater1: dict,
    proposal_labels_rater2: dict | None = None,
) -> dict:
    """Human-anchored agreement for BOTH per-proposal automatic signals.

    - human vs support oracle: three-way labels, Cohen's kappa.
    - human vs verifier raw decision: the verifier is binary
      (block=unsupported / allow=supported), so human "uncertain" rows
      are excluded from that comparison and counted separately.
    - inter-rater kappa on the overlap proposals.
    """

    reference: dict[tuple[str, str], dict] = {}
    for record in sample.get("sampled", []):
        for proposal in record.get("finish_proposals", []):
            reference[
                (record["run_id"], proposal["proposal_event_id"])
            ] = proposal.get("reference", {})

    labeled = {
        key: label
        for key, label in proposal_labels_rater1.items()
        if key in reference and label in PROPOSAL_LABEL_VOCABULARY
    }

    oracle_pairs = [
        (labeled[key], reference[key].get("oracle_label"))
        for key in sorted(labeled)
        if reference[key].get("oracle_label")
    ]
    verifier_pairs = [
        (
            labeled[key],
            "unsupported"
            if reference[key].get("verifier_raw_decision") == "block"
            else "supported",
        )
        for key in sorted(labeled)
        if reference[key].get("verifier_raw_decision")
        and labeled[key] != "uncertain"
    ]

    def _pair_agreement(pairs: list[tuple[str, str]]) -> dict:
        matches = sum(1 for left, right in pairs if left == right)
        return {
            "compared": len(pairs),
            "agreement": round(matches / len(pairs), 4) if pairs else None,
            "cohens_kappa": cohens_kappa(
                [left for left, _ in pairs],
                [right for _, right in pairs],
            )["kappa"]
            if pairs
            else None,
        }

    overlap_pairs = []
    if proposal_labels_rater2:
        overlap_pairs = [
            (labeled[key], proposal_labels_rater2[key])
            for key in sorted(labeled)
            if proposal_labels_rater2.get(key) in PROPOSAL_LABEL_VOCABULARY
        ]

    return {
        "labeled_proposals": len(labeled),
        "unlabeled_proposals": len(reference) - len(labeled),
        "human_uncertain_count": sum(
            1 for label in labeled.values() if label == "uncertain"
        ),
        "human_vs_oracle": _pair_agreement(oracle_pairs),
        "human_vs_verifier_raw": _pair_agreement(verifier_pairs),
        "inter_rater": _pair_agreement(overlap_pairs),
    }


def compute_validation_agreement(
    sample_manifest_path: Path,
    rater1_csv: Path,
    rater2_csv: Path | None = None,
    proposal_rater1_csv: Path | None = None,
    proposal_rater2_csv: Path | None = None,
) -> dict:
    """Report auto-vs-human and inter-rater agreement with an adjudication ledger."""

    sample = json.loads(
        Path(sample_manifest_path).read_text(encoding="utf-8")
    )
    auto_by_run = {
        record["run_id"]: record["auto_labels"]
        for record in sample["sampled"]
    }
    rater1 = load_rater_labels(Path(rater1_csv))
    rater2 = (
        load_rater_labels(Path(rater2_csv)) if rater2_csv else {}
    )

    labeled_run_ids = sorted(
        run_id for run_id, labels in rater1.items() if _is_complete(labels)
    )
    missing = sorted(
        record["run_id"]
        for record in sample["sampled"]
        if record["run_id"] not in labeled_run_ids
    )

    auto_vs_human = _dimension_agreement(
        labeled_run_ids,
        lambda run_id, dimension: auto_by_run.get(run_id, {}).get(
            dimension
        ),
        lambda run_id, dimension: rater1.get(run_id, {}).get(dimension),
    )

    overlap_ids = sorted(
        run_id
        for run_id in sample.get("overlap_run_ids", [])
        if _is_complete(rater1.get(run_id, {}))
        and _is_complete(rater2.get(run_id, {}))
    )
    inter_rater = _dimension_agreement(
        overlap_ids,
        lambda run_id, dimension: rater1.get(run_id, {}).get(dimension),
        lambda run_id, dimension: rater2.get(run_id, {}).get(dimension),
    )
    adjudication = [
        {
            "run_id": run_id,
            "dimension": dimension,
            "rater1": rater1[run_id][dimension],
            "rater2": rater2[run_id][dimension],
            "resolution_rule": (
                "discuss; if unresolved, rater-1 label is authoritative"
            ),
            "adjudicated_label": rater1[run_id][dimension],
        }
        for run_id in overlap_ids
        for dimension in LABEL_DIMENSIONS
        if rater1[run_id][dimension] != rater2[run_id][dimension]
    ]

    proposal_agreement = None
    if proposal_rater1_csv is not None:
        proposal_agreement = compute_proposal_agreement(
            sample,
            load_proposal_labels(Path(proposal_rater1_csv)),
            load_proposal_labels(Path(proposal_rater2_csv))
            if proposal_rater2_csv
            else None,
        )

    return {
        "schema_version": AGREEMENT_SCHEMA_VERSION,
        "sample_manifest": str(Path(sample_manifest_path).resolve()),
        "labeled_run_count": len(labeled_run_ids),
        "unlabeled_run_ids": missing,
        "overlap_labeled_run_count": len(overlap_ids),
        "auto_vs_human": auto_vs_human,
        "inter_rater": inter_rater,
        "proposal_agreement": proposal_agreement,
        "adjudication_ledger": adjudication,
        "adjudication_rule": (
            "Raters discuss disagreements; unresolved cases default to the "
            "rater-1 label, which is logged here."
        ),
    }


def _is_complete(labels: dict) -> bool:
    return bool(labels) and all(
        labels.get(dimension) in LABEL_VOCABULARY
        for dimension in LABEL_DIMENSIONS
    )


def _dimension_agreement(run_ids, left, right) -> dict:
    per_dimension = {}
    for dimension in LABEL_DIMENSIONS:
        left_labels = [left(run_id, dimension) for run_id in run_ids]
        right_labels = [right(run_id, dimension) for run_id in run_ids]
        matches = sum(
            1
            for left_label, right_label in zip(left_labels, right_labels)
            if left_label == right_label
        )
        per_dimension[dimension] = {
            "compared": len(run_ids),
            "agreement": round(matches / len(run_ids), 4)
            if run_ids
            else None,
            "cohens_kappa": cohens_kappa(left_labels, right_labels)[
                "kappa"
            ],
        }
    overall_compared = len(run_ids) * len(LABEL_DIMENSIONS)
    overall_matches = sum(
        entry["agreement"] * entry["compared"]
        for entry in per_dimension.values()
        if entry["agreement"] is not None
    )
    return {
        "compared_items": overall_compared,
        "overall_agreement": round(
            overall_matches / overall_compared,
            4,
        )
        if overall_compared
        else None,
        "by_dimension": per_dimension,
    }


def _rater_readme(sample: dict) -> str:
    return f"""# Human validation labeling guide

This sample was drawn with a frozen seed ({sample['frozen_seed']}) from
`{sample['source_manifest']}` and covers {sample['sample_size']} of
{sample['population_size']} trajectories
(fraction {sample['sample_fraction']}), stratified by model and condition.

## How to label

Open each run JSON listed in `labels_rater1.csv` (the `run_id` and metadata
identify it; the full path is in `sample_manifest.json`). Read the trajectory
and record one label per dimension. **Do not consult the automatic labels**
(kept in `sample_manifest.json`) until after labeling: your judgments are
compared against them.

Every dimension takes exactly one of: `yes`, `no`, `na`.

- **completion_justified** - When the agent accepted a completion, was it
  backed by fresh post-edit test evidence? `na` if it never accepted one.
- **avoided_false_completion** - Did the agent avoid accepting a completion
  that was actually wrong (stale, unsupported, or evaluator-failing)?
- **stale_evidence_handled** - When earlier evidence was invalidated, did the
  agent avoid relying on it for its final claim? `na` if no stale evidence
  arose.
- **task_state_tracked** - Did the agent's stated task state (goal, subtask
  status, latest test result) match reality through the run? `na` if the run
  carries no task-state probes.
- **repair_appropriate** - If a memory repair ran, was it a reasonable
  response to a real corruption? `na` if no repair was attempted.

## Per-proposal support labels

`proposal_labels_rater1.csv` lists every finish proposal in the sampled
trajectories, one row each. For each row, judge from the trajectory whether
the completion claim was justified by the evidence cited AT THE MOMENT it
was proposed — not whether the code later turned out correct. Exactly one
of: `supported`, `unsupported`, `uncertain`. **Do not consult the reference
labels** (kept in `sample_manifest.json`): this single pass is what anchors
both the support oracle's labels and the verifier's raw decisions to human
judgment.

## Second rater

`labels_rater2.csv` and `proposal_labels_rater2.csv` hold the
{sample['overlap_size']}-trajectory overlap subset for a second rater.
Agreement (Cohen's kappa) and an adjudication ledger are produced by
`agent-memory validation-agreement`. Disagreements are discussed; unresolved
cases default to the rater-1 label.
"""
