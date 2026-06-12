"""Tests for manual measurement validation and decision-linked beliefs."""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from research.runner import (
    BenchmarkRunner,
    compute_structured_memory_metrics,
    extract_decision_beliefs,
    summarize_decision_beliefs,
    validate_manual_measurements,
)
from research.cli import main as cli_main


def test_frozen_manual_labels_match_automatic_measurements():
    report = validate_manual_measurements()

    assert report["schema_version"] == (
        "agent-measurement-validation/v0.1"
    )
    assert report["probe_case_count"] == 3
    assert report["decision_belief_case_count"] == 5
    assert report["comparison_count"] == 48
    assert report["exact_match_rate"] == 1.0
    assert report["mean_absolute_error"] == 0.0
    assert report["disagreements"] == []


def test_decision_beliefs_link_non_finish_action_to_consumed_evidence():
    run = {
        "trace_events": [
            {
                "event_id": "read-1",
                "event_type": "tool_call",
                "sequence_number": 1,
                "tool_name": "read_file",
                "path": "service.py",
                "status": "success",
            },
            {
                "event_id": "decision-2",
                "event_type": "model_response",
                "graph_node": "choose_action",
                "sequence_number": 2,
                "parsed_action": {
                    "action": "write_file",
                    "path": "service.py",
                    "beliefs": [
                        {
                            "belief_type": "file_state",
                            "claim": "The observed implementation is incomplete.",
                            "source_event_ids": ["read-1"],
                        }
                    ],
                    "source_event_ids": ["read-1"],
                },
            },
        ],
        "operational_memory": [
            {
                "event_id": "read-1",
                "memory_id": "read-1:memory",
                "tool_name": "read_file",
                "path": "service.py",
                "support_status": "supported",
                "stale": False,
                "invalidated_by_event_ids": [],
                "contradictions": [],
            }
        ],
    }

    beliefs = extract_decision_beliefs(run)
    summary = summarize_decision_beliefs(
        beliefs,
        trace_events=run["trace_events"],
    )

    assert beliefs[0]["decision_action"] == "write_file"
    assert beliefs[0]["tool_decision"] is True
    assert beliefs[0]["support_status"] == "supported"
    assert beliefs[0]["source_event_ids"] == ["read-1"]
    assert summary["decision_belief_coverage"] == 1.0


def test_structured_metrics_count_corrupted_tool_decision_beliefs():
    run = {
        "memory_claims": [],
        "trace_events": [
            {
                "event_id": "test-old",
                "event_type": "tool_call",
                "sequence_number": 1,
                "tool_name": "run_tests",
                "status": "success",
            },
            {
                "event_id": "write-2",
                "event_type": "file_state_change",
                "sequence_number": 2,
                "tool_name": "write_file",
                "path": "service.py",
                "status": "success",
            },
            {
                "event_id": "decision-3",
                "event_type": "model_response",
                "graph_node": "choose_action",
                "sequence_number": 3,
                "parsed_action": {
                    "action": "write_file",
                    "path": "service.py",
                    "beliefs": [
                        {
                            "belief_type": "test_state",
                            "claim": "Tests still pass after the write.",
                            "source_event_ids": ["test-old"],
                        },
                        {
                            "belief_type": "requirement_state",
                            "claim": "No further requirement exists.",
                            "source_event_ids": [],
                        },
                    ],
                    "source_event_ids": ["test-old"],
                },
            },
        ],
        "operational_memory": [
            {
                "event_id": "test-old",
                "tool_name": "run_tests",
                "support_status": "stale",
                "stale": True,
                "invalidated_by_event_ids": ["write-2"],
                "contradictions": [],
            }
        ],
    }

    metrics = compute_structured_memory_metrics(run)

    assert metrics["schema_version"] == (
        "agent-structured-memory-metrics/v0.2"
    )
    assert metrics["decision_belief_count"] == 2
    assert metrics["tool_decision_belief_count"] == 2
    assert metrics["stale_beliefs_used_for_tool_decisions"] == 1
    assert metrics["unsupported_beliefs_used_for_tool_decisions"] == 1
    assert metrics["contradicted_beliefs_used_for_tool_decisions"] == 0
    assert metrics["lexical_or_embedding_similarity_included"] is False


def test_action_parser_preserves_declared_decision_beliefs():
    parsed = BenchmarkRunner._parse_tool_action_response(
        json.dumps(
            {
                "action": "write_file",
                "path": "service.py",
                "content": "VALUE = 2\n",
                "source_event_ids": ["read-1"],
                "beliefs": [
                    {
                        "belief_type": "file_state",
                        "claim": "VALUE is currently 1.",
                        "source_event_ids": ["read-1"],
                    }
                ],
            }
        )
    )

    assert parsed["parse_status"] == "json"
    assert parsed["action_payload"]["beliefs"] == [
        {
            "belief_type": "file_state",
            "claim": "VALUE is currently 1.",
            "source_event_ids": ["read-1"],
        }
    ]


def test_measurement_audit_cli_reports_exact_manual_agreement(capsys):
    result = cli_main(["measurement-audit", "--format", "json"])

    assert result == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["exact_match_rate"] == 1.0
    assert payload["disagreements"] == []


def test_measurement_audit_cli_table_is_concise(capsys):
    result = cli_main(["measurement-audit", "--format", "table"])

    assert result == 0
    output = capsys.readouterr().out
    assert "exact_match_rate       1.0" in output
    assert "disagreements          0" in output
    assert '"probe_results"' not in output
