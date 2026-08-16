"""Tests for the post-hoc LLM-judge supervisor comparison arm.

The judge's value as a comparison arm rests entirely on its information
diet matching the online rule-based supervisor's — these tests pin that
contract harder than the scoring math.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from research.runner.judge_supervisor import (
    aggregate_judge_records,
    build_judge_prompt,
    parse_judge_response,
    score_run_with_judge,
)


def _run_fixture() -> dict:
    events = [
        {
            "event_id": "read-1",
            "event_type": "tool_call",
            "tool_name": "read_file",
            "path": "parser.py",
            "sequence_number": 1,
        },
        {
            "event_id": "req-1",
            "event_type": "user_requirement_update",
            "requirement_id": "requirement_update_0",
            "content": "Clarification: trailing spaces must be stripped.",
            "sequence_number": 2,
        },
        {
            "event_id": "write-1",
            "event_type": "file_state_change",
            "tool_name": "write_file",
            "path": "parser.py",
            "status": "success",
            "sequence_number": 3,
        },
        {
            "event_id": "test-1",
            "event_type": "tool_call",
            "tool_name": "run_tests",
            "status": "success",
            "covered_files": ["parser.py", "test_parser.py"],
            "sequence_number": 4,
        },
        {
            "event_id": "finish-1",
            "event_type": "completion_claim",
            "tool_name": "finish",
            "claim": "The parser fix is complete and tests pass.",
            "source_event_ids": ["write-1", "test-1"],
            "sequence_number": 5,
        },
        # Post-proposal event: MUST NOT appear in the judge prompt.
        {
            "event_id": "post-1",
            "event_type": "file_state_change",
            "tool_name": "write_file",
            "path": "SECRET_LATER_EDIT.py",
            "status": "success",
            "sequence_number": 6,
        },
        {
            "event_id": "decision-1",
            "event_type": "verification_decision",
            "claim_event_id": "finish-1",
            "verifier_decision": "allow",
            "decision": "allow",
            "sequence_number": 7,
        },
    ]
    return {
        "task_id": "toy_task",
        "run_id": "toy_run",
        "trace_events": events,
        "interaction_metrics": {
            "oracle_proposal_scores": [
                {
                    "proposal_event_id": "finish-1",
                    "support_label": "supported",
                }
            ]
        },
    }


def test_prompt_information_diet_matches_online_supervisor():
    run = _run_fixture()
    proposal = run["trace_events"][4]
    prompt = build_judge_prompt(run["trace_events"], proposal)
    # Pre-proposal evidence is present, with citation markers.
    assert "REQUIREMENT UPDATE" in prompt
    assert "trailing spaces" in prompt
    assert "[CITED] #4 run_tests -> success" in prompt
    assert "[CITED] #3 write_file parser.py" in prompt
    # Post-proposal events and non-trace signals are absent.
    assert "SECRET_LATER_EDIT" not in prompt
    assert "hidden" not in prompt.lower()
    assert "completion_policy" not in prompt
    # The judge is asked about justification, not correctness.
    assert "NOT judge whether the code is actually correct" in prompt


def test_score_run_joins_rules_and_oracle_signals():
    run = _run_fixture()
    prompts = []

    def fake_generate(prompt: str) -> str:
        prompts.append(prompt)
        return 'noise {"decision": "block", "reasons": ["stale"]} trailer'

    records = score_run_with_judge(run, fake_generate)
    assert len(records) == 1
    record = records[0]
    assert record["judge_decision"] == "block"
    assert record["judge_reasons"] == ["stale"]
    assert record["rule_raw_decision"] == "allow"
    assert record["oracle_label"] == "supported"
    assert len(prompts) == 1

    aggregate = aggregate_judge_records(records)
    overall = aggregate["overall"]
    assert overall["proposals"] == 1
    assert overall["judge_blocks"] == 1
    assert overall["judge_vs_oracle"]["supported|block"] == 1
    # Judge blocked where rules allowed: zero agreement on 1 comparable.
    assert overall["judge_rule_agreement"] == 0
    assert overall["judge_rule_comparable"] == 1


def test_unparsable_judge_output_is_recorded_not_guessed():
    assert parse_judge_response("I think it looks fine!")["decision"] == (
        "unparsed"
    )
    assert parse_judge_response("")["decision"] == "unparsed"
    assert parse_judge_response('{"decision": "maybe"}')["decision"] == (
        "unparsed"
    )
    run = _run_fixture()
    records = score_run_with_judge(run, lambda prompt: "garbage")
    assert records[0]["judge_decision"] == "unparsed"
    aggregate = aggregate_judge_records(records)
    assert aggregate["overall"]["unparsed"] == 1
    assert aggregate["overall"]["judge_rule_comparable"] == 0


def test_gate_latency_is_recorded_on_decisions(tmp_path: Path):
    """Item 5 of the level-up plan: supervisor overhead needs a number."""
    import pytest

    pytest.importorskip("langgraph")
    from research.runner.benchmark_runner import (
        BenchmarkRunConfig,
        BenchmarkRunner,
    )

    run = BenchmarkRunner().run_task_id(
        "coding_heldout_temporal_fresh_001",
        BenchmarkRunConfig(
            framework="langgraph_tools",
            trace_mode="model_driven",
            runtime="deterministic",
            intervention="verification_only",
            action_budget=26,
            workspace_root=str(tmp_path / "ws"),
        ),
    )
    decisions = [
        event
        for event in run["trace_events"]
        if event.get("event_type") == "verification_decision"
    ]
    assert decisions
    for event in decisions:
        assert event.get("gate_latency_ms") is not None
        assert float(event["gate_latency_ms"]) >= 0.0
