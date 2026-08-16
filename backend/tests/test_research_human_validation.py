"""Tests for the human validation sampling and agreement layer (task 43)."""

import csv
import json
from pathlib import Path

import pytest

from research.runner.human_validation import (
    LABEL_DIMENSIONS,
    build_validation_sample,
    compute_validation_agreement,
    derive_auto_labels,
    write_validation_sample,
)
from research.runner.model_matrix import run_model_matrix


def _run_matrix(tmp_path: Path) -> Path:
    pytest.importorskip("langgraph")
    matrix_path = tmp_path / "matrix.json"
    matrix_path.write_text(
        json.dumps(
            {
                "runtime": "deterministic",
                "minimum_successful_models": 1,
                "models": [
                    {
                        "model_family": "qwen",
                        "model_name": "qwen2.5-coder:7b",
                        "enabled": True,
                    }
                ],
            }
        )
    )
    manifest = run_model_matrix(
        tmp_path / "out",
        matrix_path=matrix_path,
        framework="langgraph_tools",
        task_ids=[
            "coding_easy_flag_default_001",
            "coding_easy_greeting_format_001",
        ],
        variants=["baseline", "verified"],
        seeds=[0, 1],
        minimum_successful_models=1,
        trace_mode="model_driven",
    )
    return Path(manifest["manifest_path"])


def test_derive_auto_labels_uses_closed_vocabulary():
    run = {
        "interaction_metrics": {
            "evaluator_success": True,
            "accepted_false_finishes": 0,
            "accepted_unsupported_finish": False,
            "accepted_incorrect_finish": False,
            "accepted_finish_proposals": 1,
            "memory_repair_attempts": 1,
            "recovery_level": 4,
        },
        "memory_claims": [
            {
                "claim_type": "task_complete",
                "support_status": "supported",
                "stale": True,
            }
        ],
    }
    labels = derive_auto_labels(run)
    assert set(labels) == set(LABEL_DIMENSIONS)
    assert labels["completion_justified"] == "yes"
    assert labels["avoided_false_completion"] == "yes"
    # A stale completion belief that was never accepted counts as handled.
    assert labels["stale_evidence_handled"] == "yes"
    assert labels["repair_appropriate"] == "yes"
    # No probes in this synthetic run.
    assert labels["task_state_tracked"] == "na"

    false_run = {
        "interaction_metrics": {
            "evaluator_success": False,
            "accepted_false_finishes": 1,
            "accepted_unsupported_finish": True,
            "accepted_incorrect_finish": True,
            "accepted_finish_proposals": 1,
            "memory_repair_attempts": 0,
            "recovery_level": 0,
        },
        "memory_claims": [
            {"claim_type": "task_complete", "stale": True},
        ],
    }
    false_labels = derive_auto_labels(false_run)
    assert false_labels["completion_justified"] == "no"
    assert false_labels["avoided_false_completion"] == "no"
    assert false_labels["stale_evidence_handled"] == "no"
    assert false_labels["repair_appropriate"] == "na"


def test_build_sample_is_frozen_and_stratified(tmp_path: Path):
    manifest_path = _run_matrix(tmp_path)

    sample_a = build_validation_sample(
        manifest_path,
        fraction=0.5,
        seed=7,
    )
    sample_b = build_validation_sample(
        manifest_path,
        fraction=0.5,
        seed=7,
    )
    assert [r["run_id"] for r in sample_a["sampled"]] == [
        r["run_id"] for r in sample_b["sampled"]
    ]
    assert sample_a["population_size"] == 8  # 2 tasks x 2 seeds x 2 variants
    assert sample_a["sample_size"] >= 1
    # Every sampled run carries auto labels over the closed vocabulary.
    for record in sample_a["sampled"]:
        assert set(record["auto_labels"]) == set(LABEL_DIMENSIONS)
    assert set(sample_a["overlap_run_ids"]).issubset(
        {r["run_id"] for r in sample_a["sampled"]}
    )

    different_seed = build_validation_sample(
        manifest_path,
        fraction=0.5,
        seed=99,
    )
    # Same population and size, frozen seed governs membership.
    assert different_seed["population_size"] == 8


def test_write_and_score_validation_round_trip(tmp_path: Path):
    manifest_path = _run_matrix(tmp_path)
    out_dir = tmp_path / "human_validation"
    written = write_validation_sample(
        manifest_path,
        out_dir,
        fraction=1.0,
        overlap_fraction=1.0,
        seed=3,
    )

    for key in ("sample_manifest", "labels_rater1", "labels_rater2", "readme"):
        assert Path(written[key]).is_file()

    sample = json.loads(
        Path(written["sample_manifest"]).read_text(encoding="utf-8")
    )
    auto_by_run = {
        record["run_id"]: record["auto_labels"]
        for record in sample["sampled"]
    }

    # Rater 1 agrees with the automatic labels exactly.
    _fill_labels(
        Path(written["labels_rater1"]),
        lambda run_id: auto_by_run[run_id],
    )
    # Rater 2 flips one dimension on the overlap subset to force a
    # disagreement and a non-trivial kappa.
    def rater2_labels(run_id: str) -> dict:
        labels = dict(auto_by_run[run_id])
        labels["completion_justified"] = (
            "no" if labels["completion_justified"] != "no" else "yes"
        )
        return labels

    _fill_labels(Path(written["labels_rater2"]), rater2_labels)

    report = compute_validation_agreement(
        Path(written["sample_manifest"]),
        Path(written["labels_rater1"]),
        Path(written["labels_rater2"]),
    )

    assert report["labeled_run_count"] == sample["sample_size"]
    assert report["unlabeled_run_ids"] == []
    # Rater 1 mirrors auto labels -> perfect auto-vs-human agreement.
    assert report["auto_vs_human"]["overall_agreement"] == 1.0
    # The forced flip shows up as adjudication entries on one dimension.
    flipped = [
        entry
        for entry in report["adjudication_ledger"]
        if entry["dimension"] == "completion_justified"
    ]
    assert flipped
    assert all(
        entry["adjudicated_label"] == entry["rater1"] for entry in flipped
    )
    assert (
        report["inter_rater"]["by_dimension"]["completion_justified"][
            "agreement"
        ]
        == 0.0
    )


def _fill_labels(csv_path: Path, label_fn) -> None:
    with csv_path.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    fieldnames = [*rows[0].keys()] if rows else []
    with csv_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            labels = label_fn(row["run_id"])
            row.update(labels)
            writer.writerow(row)


def test_proposal_labels_anchor_oracle_and_verifier(tmp_path: Path):
    """Level-up item 4: one human pass over per-proposal support labels
    anchors BOTH automatic signals (oracle label + raw verifier
    decision). The rater CSV must stay blind (no reference labels)."""
    manifest_path = _run_matrix(tmp_path)
    out_dir = tmp_path / "human_validation"
    written = write_validation_sample(
        manifest_path,
        out_dir,
        fraction=1.0,
        overlap_fraction=1.0,
        seed=3,
    )
    for key in ("proposal_labels_rater1", "proposal_labels_rater2"):
        assert Path(written[key]).is_file()

    sample = json.loads(
        Path(written["sample_manifest"]).read_text(encoding="utf-8")
    )
    reference = {}
    for record in sample["sampled"]:
        assert "finish_proposals" in record
        for proposal in record["finish_proposals"]:
            assert proposal["reference"]["oracle_label"] in {
                "supported",
                "unsupported",
                "uncertain",
                None,
            }
            reference[
                (record["run_id"], proposal["proposal_event_id"])
            ] = proposal["reference"]
    assert reference, "sampled runs must contain finish proposals"

    with Path(written["proposal_labels_rater1"]).open(
        encoding="utf-8", newline=""
    ) as handle:
        rows = list(csv.DictReader(handle))
    assert rows
    # Blinding: the rater CSV never carries the answers.
    for row in rows:
        assert "oracle_label" not in row
        assert "verifier_raw_decision" not in row
        assert row["proposal_support"] == ""

    # Fill rater 1 with the oracle's own labels -> perfect human-vs-
    # oracle agreement; human-vs-verifier then measures the verifier
    # against those same human labels.
    def fill(csv_path: Path) -> None:
        with csv_path.open(encoding="utf-8", newline="") as handle:
            filled = list(csv.DictReader(handle))
        for row in filled:
            key = (row["run_id"], row["proposal_event_id"])
            row["proposal_support"] = (
                reference[key]["oracle_label"] or "uncertain"
            )
        with csv_path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(
                handle, fieldnames=list(filled[0].keys())
            )
            writer.writeheader()
            writer.writerows(filled)

    fill(Path(written["proposal_labels_rater1"]))
    fill(Path(written["proposal_labels_rater2"]))

    report = compute_validation_agreement(
        Path(written["sample_manifest"]),
        Path(written["labels_rater1"]),
        Path(written["labels_rater2"]),
        proposal_rater1_csv=Path(written["proposal_labels_rater1"]),
        proposal_rater2_csv=Path(written["proposal_labels_rater2"]),
    )
    proposal_agreement = report["proposal_agreement"]
    assert proposal_agreement is not None
    assert proposal_agreement["labeled_proposals"] == len(reference)
    assert proposal_agreement["unlabeled_proposals"] == 0
    assert proposal_agreement["human_vs_oracle"]["agreement"] == 1.0
    # Verifier comparison excludes human-uncertain rows by design.
    comparable = proposal_agreement["human_vs_verifier_raw"]["compared"]
    assert comparable <= proposal_agreement["labeled_proposals"]
    assert proposal_agreement["inter_rater"]["agreement"] == 1.0
