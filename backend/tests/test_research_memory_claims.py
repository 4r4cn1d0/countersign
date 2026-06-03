"""Tests for memory claim extraction and provenance tracking."""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from research.runner import BenchmarkRunner, extract_memory_claims, find_stale_claims


def test_runner_attaches_normalized_memory_claims():
    run = BenchmarkRunner().run_all()[0]

    assert run["memory_claims"]
    for claim in run["memory_claims"]:
        assert claim["claim_id"]
        assert claim["event_id"]
        assert claim["claim_type"] in {"tests_pass", "task_complete"}
        assert claim["subject"]
        assert claim["predicate"]
        assert claim["object"]
        assert claim["text"]
        assert claim["confidence"] > 0


def test_memory_claims_preserve_provenance_sequence_numbers():
    run = BenchmarkRunner().run_all()[0]

    for claim in run["memory_claims"]:
        assert claim["source_event_ids"]
        assert claim["source_event_sequence_numbers"]
        assert claim["lost_provenance"] is False
        assert claim["support_status"] == "inferred"


def test_memory_claims_flag_lost_provenance():
    run = {
        "trace_events": [
            {
                "event_id": "claim-1",
                "event_type": "completion_claim",
                "sequence_number": 2,
                "claim": "The task is complete.",
                "source_type": "agent_inference",
                "source_event_ids": [],
            }
        ],
        "high_risk_labels": [
            {
                "label_id": "claim-1:task_complete",
                "event_id": "claim-1",
                "claim_type": "task_complete",
                "claim_text": "the task is complete.",
                "source_event_ids": [],
                "freshness_rule": "must include implementation evidence",
            }
        ],
    }

    claims = extract_memory_claims(run)

    assert claims[0]["lost_provenance"] is True
    assert claims[0]["support_status"] == "unsupported"
    assert claims[0]["confidence"] < 0.75


def test_memory_claims_cover_supported_summarized_inferred_and_contradicted():
    run = {
        "trace_events": [
            {
                "event_id": "test-output",
                "event_type": "tool_call",
                "sequence_number": 1,
                "content": "pytest passed",
                "source_type": "tool_output",
                "source_event_ids": [],
            },
            {
                "event_id": "summary-1",
                "event_type": "summary",
                "sequence_number": 2,
                "summary": "The tests pass for the current task state.",
                "source_type": "agent_summary",
                "source_event_ids": ["test-output"],
            },
            {
                "event_id": "claim-complete",
                "event_type": "completion_claim",
                "sequence_number": 3,
                "claim": "The task is complete and ready to report as done.",
                "source_type": "agent_inference",
                "source_event_ids": ["summary-1"],
            },
            {
                "event_id": "source-1",
                "event_type": "memory_access",
                "sequence_number": 4,
                "content": "Retrieved source initially appears relevant.",
                "source_type": "retrieved_source",
                "source_event_ids": [],
            },
            {
                "event_id": "source-correction",
                "event_type": "source_update",
                "sequence_number": 5,
                "content": "The cited source does not support the major claim.",
                "source_type": "retrieved_source",
                "source_event_ids": ["source-1"],
                "contradicts_claim_types": ["source_supports_claim"],
            },
            {
                "event_id": "claim-source",
                "event_type": "agent_claim",
                "sequence_number": 6,
                "claim": "The source supports the major claim.",
                "source_type": "agent_inference",
                "source_event_ids": ["source-1"],
            },
        ],
        "high_risk_labels": [
            {
                "label_id": "summary-1:tests_pass",
                "event_id": "summary-1",
                "claim_type": "tests_pass",
                "claim_text": "the tests pass for the current task state.",
                "source_event_ids": ["test-output"],
                "minimum_source_type": "tool_output",
            },
            {
                "label_id": "claim-complete:task_complete",
                "event_id": "claim-complete",
                "claim_type": "task_complete",
                "claim_text": "the task is complete and ready to report as done.",
                "source_event_ids": ["summary-1"],
                "minimum_source_type": "tool_output",
            },
            {
                "label_id": "claim-source:source_supports_claim",
                "event_id": "claim-source",
                "claim_type": "source_supports_claim",
                "claim_text": "the source supports the major claim.",
                "source_event_ids": ["source-1"],
                "minimum_source_type": "retrieved_source",
            },
        ],
    }

    claims = {
        claim["claim_id"]: claim
        for claim in extract_memory_claims(run)
    }

    assert claims["summary-1:tests_pass"]["support_status"] == "supported"
    assert claims["summary-1:tests_pass"]["source_event_sequence_numbers"] == [1]
    assert claims["summary-1:tests_pass"]["confidence"] > 0.75
    assert claims["claim-complete:task_complete"]["support_status"] == "inferred"
    assert claims["claim-complete:task_complete"]["source_event_ids"] == ["summary-1"]
    assert claims["claim-source:source_supports_claim"]["support_status"] == "contradicted"
    assert claims["claim-source:source_supports_claim"]["confidence"] < 0.75


def test_staleness_detection_marks_claims_after_invalidating_changes():
    run = {
        "trace_events": [
            {
                "event_id": "test-run-1",
                "event_type": "tool_call",
                "sequence_number": 1,
                "content": "pytest passed",
                "source_type": "tool_output",
                "source_event_ids": [],
            },
            {
                "event_id": "edit-1",
                "event_type": "file_state_change",
                "sequence_number": 2,
                "content": "parser.py changed",
                "invalidates_claim_types": ["tests_pass", "task_complete"],
            },
            {
                "event_id": "claim-1",
                "event_type": "completion_claim",
                "sequence_number": 3,
                "claim": "The tests pass for the current task state.",
                "source_type": "agent_inference",
                "source_event_ids": ["test-run-1"],
            },
        ],
        "high_risk_labels": [
            {
                "label_id": "claim-1:tests_pass",
                "event_id": "claim-1",
                "claim_type": "tests_pass",
                "claim_text": "the tests pass for the current task state.",
                "source_event_ids": ["test-run-1"],
                "freshness_rule": "must occur after latest relevant file change",
            }
        ],
    }

    claims = extract_memory_claims(run)

    assert claims[0]["stale"] is True
    assert find_stale_claims(claims) == claims


def test_recent_evidence_is_not_marked_stale():
    run = {
        "trace_events": [
            {
                "event_id": "edit-1",
                "event_type": "file_state_change",
                "sequence_number": 1,
                "content": "parser.py changed",
                "invalidates_claim_types": ["tests_pass"],
            },
            {
                "event_id": "test-run-1",
                "event_type": "tool_call",
                "sequence_number": 2,
                "content": "pytest passed",
                "source_type": "tool_output",
                "source_event_ids": [],
            },
            {
                "event_id": "claim-1",
                "event_type": "completion_claim",
                "sequence_number": 3,
                "claim": "The tests pass for the current task state.",
                "source_type": "agent_inference",
                "source_event_ids": ["test-run-1"],
            },
        ],
        "high_risk_labels": [
            {
                "label_id": "claim-1:tests_pass",
                "event_id": "claim-1",
                "claim_type": "tests_pass",
                "claim_text": "the tests pass for the current task state.",
                "source_event_ids": ["test-run-1"],
                "freshness_rule": "must occur after latest relevant file change",
            }
        ],
    }

    claims = extract_memory_claims(run)

    assert claims[0]["stale"] is False
    assert find_stale_claims(claims) == []
