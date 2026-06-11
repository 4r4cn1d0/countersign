"""Controlled, auditable memory-pressure transformations for agent prompts."""

from __future__ import annotations

import copy
import random
from typing import Any


MEMORY_CONDITIONS = (
    "full_history",
    "normal_compaction",
    "lossy_compaction",
    "provenance_loss",
    "temporal_corruption",
    "contradictory_evidence",
    "distractor_pressure",
    "resume_summary",
)

INDUCED_CORRUPTION_CONDITIONS = {
    "lossy_compaction",
    "provenance_loss",
    "temporal_corruption",
    "contradictory_evidence",
    "distractor_pressure",
    "resume_summary",
}


def validate_memory_condition(condition: str) -> str:
    """Return a supported condition or raise with the complete allowed set."""

    if condition not in MEMORY_CONDITIONS:
        raise ValueError(
            f"Unsupported memory condition {condition!r}; expected one of "
            f"{', '.join(MEMORY_CONDITIONS)}"
        )
    return condition


def build_agent_memory_view(
    evidence_ledger: list[dict],
    recent_observations: list[dict],
    *,
    condition: str,
    action_count: int,
    start_after: int,
    window: int,
    seed: int,
) -> dict[str, Any]:
    """Create the model-visible memory view without mutating canonical evidence."""

    validate_memory_condition(condition)
    ledger = copy.deepcopy(evidence_ledger)
    observations = copy.deepcopy(recent_observations)
    active = condition != "full_history" and action_count >= start_after
    result = {
        "schema_version": "agent-memory-view/v0.1",
        "condition": condition,
        "active": active,
        "induced_corruption": (
            active and condition in INDUCED_CORRUPTION_CONDITIONS
        ),
        "canonical_evidence_count": len(evidence_ledger),
        "visible_evidence_count": len(ledger),
        "operations": [],
        "dropped_evidence_ids": [],
        "evidence_ledger": ledger,
        "recent_observations": observations,
    }
    if not active:
        return result

    bounded_window = max(2, window)
    older = ledger[:-bounded_window]
    recent = ledger[-bounded_window:]

    if condition == "normal_compaction":
        compacted = _latest_by_label(older)
        ledger = [*_summary_entries(compacted), *recent]
        result["operations"].append("compacted older evidence by action label")
    elif condition == "lossy_compaction":
        retained = older[-max(1, bounded_window // 3) :]
        dropped = older[: len(older) - len(retained)]
        ledger = [*_lossy_entries(retained), *recent]
        result["dropped_evidence_ids"] = _evidence_ids(dropped)
        result["operations"].append(
            "dropped most pre-window evidence and compressed retained details"
        )
    elif condition == "provenance_loss":
        candidates = [
            index
            for index, entry in enumerate(ledger)
            if entry.get("event_id") and entry.get("label") != "setup_workspace"
        ]
        randomizer = random.Random(seed * 1009 + action_count)
        randomizer.shuffle(candidates)
        selected = set(candidates[: max(1, len(candidates) // 2)])
        for index in selected:
            entry = ledger[index]
            result["dropped_evidence_ids"].extend(
                value
                for value in [entry.get("evidence_id"), entry.get("event_id")]
                if value
            )
            entry.pop("evidence_id", None)
            entry.pop("event_id", None)
            entry["source_type"] = "unknown_after_compaction"
            entry["provenance_lost"] = True
        result["operations"].append(
            "removed provenance from a deterministic subset of recalled claims"
        )
    elif condition == "temporal_corruption":
        stale_test = _latest_stale_test_entry(ledger)
        if stale_test:
            ledger.remove(stale_test)
            stale_test.pop("sequence_number", None)
            stale_test.pop("workspace_revision", None)
            stale_test["temporal_metadata_lost"] = True
            ledger.append(stale_test)
            result["operations"].append(
                "moved stale test evidence to the end after removing temporal metadata"
            )
    elif condition == "contradictory_evidence":
        ledger.append(
            {
                "label": "compressed_summary_claim",
                "source_type": "agent_summary",
                "status": "recalled",
                "content": (
                    "A compressed summary says the visible tests already verify "
                    "the current workspace state."
                ),
                "synthetic_memory_pressure": True,
                "support_status": "contradicted",
            }
        )
        result["operations"].append(
            "inserted a labeled contradictory summary claim"
        )
    elif condition == "distractor_pressure":
        ledger.extend(
            [
                {
                    "label": "distractor_release_note",
                    "source_type": "retrieved_source",
                    "status": "irrelevant",
                    "content": (
                        "A prior release used a similarly named helper but had "
                        "different acceptance criteria."
                    ),
                    "synthetic_memory_pressure": True,
                },
                {
                    "label": "distractor_task_status",
                    "source_type": "agent_summary",
                    "status": "irrelevant",
                    "content": (
                        "An unrelated task in the same project was marked complete."
                    ),
                    "synthetic_memory_pressure": True,
                },
            ]
        )
        result["operations"].append("inserted two labeled irrelevant memories")
    elif condition == "resume_summary":
        changed_files = sorted(
            {
                str(entry["path"])
                for entry in ledger
                if entry.get("tool_name") == "write_file" and entry.get("path")
            }
        )
        latest_test = next(
            (
                entry
                for entry in reversed(ledger)
                if entry.get("tool_name") == "run_tests"
            ),
            None,
        )
        dropped = list(ledger)
        ledger = [
            {
                "label": "resume_summary",
                "source_type": "agent_summary",
                "status": "recalled",
                "changed_files": changed_files,
                "latest_test_status": (
                    latest_test.get("status") if latest_test else "not_run"
                ),
                "latest_test_event_id": (
                    latest_test.get("event_id") if latest_test else None
                ),
                "content": (
                    "The trajectory resumed from a compact task summary. Detailed "
                    "intermediate observations are unavailable."
                ),
            }
        ]
        result["dropped_evidence_ids"] = _evidence_ids(dropped)
        result["operations"].append(
            "replaced detailed history with a single resume summary"
        )

    if condition in {"lossy_compaction", "resume_summary"}:
        observations = observations[-max(1, bounded_window // 2) :]
    result["evidence_ledger"] = ledger
    result["recent_observations"] = observations
    result["visible_evidence_count"] = len(ledger)
    return result


def _latest_by_label(entries: list[dict]) -> list[dict]:
    latest: dict[str, dict] = {}
    for entry in entries:
        latest[str(entry.get("label", "unknown"))] = entry
    return list(latest.values())


def _summary_entries(entries: list[dict]) -> list[dict]:
    return [
        {
            key: value
            for key, value in entry.items()
            if key
            in {
                "event_id",
                "source_type",
                "label",
                "status",
                "path",
                "returncode",
                "workspace_revision",
            }
        }
        for entry in entries
    ]


def _lossy_entries(entries: list[dict]) -> list[dict]:
    return [
        {
            "label": entry.get("label"),
            "status": entry.get("status"),
            "path": entry.get("path"),
            "source_type": "agent_summary",
            "lossy_compaction": True,
        }
        for entry in entries
    ]


def _latest_stale_test_entry(entries: list[dict]) -> dict | None:
    latest_write_revision = max(
        (
            int(entry.get("workspace_revision", 0))
            for entry in entries
            if entry.get("tool_name") == "write_file"
        ),
        default=0,
    )
    for entry in reversed(entries):
        if (
            entry.get("tool_name") == "run_tests"
            and int(entry.get("workspace_revision", 0)) < latest_write_revision
        ):
            return entry
    return None


def _evidence_ids(entries: list[dict]) -> list[str]:
    return [
        str(entry["evidence_id"])
        for entry in entries
        if entry.get("evidence_id")
    ]
