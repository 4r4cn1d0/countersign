"""Tests for verification gates and terminal CLI workflows."""

import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from research.runner import (
    BenchmarkRunConfig,
    BenchmarkRunner,
    VerificationPolicy,
    compare_runs,
    extract_memory_claims,
    retrieval_consistency_score,
    verify_claim,
    verify_run,
)


def _stale_completion_run() -> dict:
    run = {
        "run_id": "stale-run",
        "task_id": "stale-task",
        "task_goal": "Fix parser tests and verify completion.",
        "ground_truth_checkpoints": [
            {"claim": "Parser changes require a fresh passing test run."}
        ],
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
                "source_type": "file_state",
                "source_event_ids": [],
                "invalidates_claim_types": ["task_complete"],
            },
            {
                "event_id": "claim-1",
                "event_type": "completion_claim",
                "sequence_number": 3,
                "claim": "The task is complete and ready to report as done.",
                "source_type": "agent_inference",
                "source_event_ids": ["test-run-1"],
            },
        ],
        "high_risk_labels": [
            {
                "label_id": "claim-1:task_complete",
                "event_id": "claim-1",
                "claim_type": "task_complete",
                "claim_text": "the task is complete and ready to report as done.",
                "source_event_ids": ["test-run-1"],
                "freshness_rule": "must include fresh verification evidence",
            }
        ],
    }
    run["memory_claims"] = extract_memory_claims(run)
    return run


def _stale_tests_run() -> dict:
    run = {
        "run_id": "stale-tests-run",
        "task_id": "stale-tests-task",
        "task_goal": "Fix parser tests and verify completion.",
        "ground_truth_checkpoints": [
            {"claim": "Tests must run after the latest file change."}
        ],
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
                "source_type": "file_state",
                "source_event_ids": [],
                "invalidates_claim_types": ["tests_pass"],
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
    run["memory_claims"] = extract_memory_claims(run)
    return run


def test_verifier_allows_seed_run_claims_with_consistent_provenance():
    run = BenchmarkRunner().run_all()[0]
    verified = verify_run(run)

    assert verified["verification_report"]["decision_counts"]["allow"] >= 1
    assert verified["verification_report"]["decision_counts"]["block"] == 0
    assert any(
        event["event_type"] == "verification_decision"
        for event in verified["trace_events"]
    )


def test_verifier_blocks_stale_high_risk_completion_claims():
    verified = verify_run(_stale_completion_run())

    assert verified["verification_report"]["decision_counts"]["block"] == 1
    assert verified["blocked_actions"][0]["blocked_action"] == "mark_task_complete"
    assert verified["effective_memory_health_report"]["claim_counts"]["false_completion"] == 0


def test_retrieval_consistency_scores_required_source_chain():
    run = BenchmarkRunner().run_all()[0]
    claim = run["memory_claims"][0]
    events_by_id = {event["event_id"]: event for event in run["trace_events"]}
    chain = [events_by_id[event_id] for event_id in claim["source_event_ids"]]

    score_without_chain = retrieval_consistency_score(
        claim,
        [],
        {"tool_output"},
        VerificationPolicy(),
    )
    score_with_chain = retrieval_consistency_score(
        claim,
        chain,
        set(),
        VerificationPolicy(),
    )

    assert score_without_chain == 0.0
    assert score_with_chain > score_without_chain


def test_retrieval_consistency_scores_wrong_source_stale_and_contradiction():
    claim = {
        "claim_id": "claim-1",
        "event_id": "claim-event",
        "claim_type": "tests_pass",
        "confidence": 0.95,
        "stale": False,
        "support_status": "supported",
        "lost_provenance": False,
        "source_event_ids": ["test-run"],
    }
    correct_chain = [{"event_id": "test-run", "source_type": "tool_output"}]
    wrong_chain = [{"event_id": "summary", "source_type": "agent_summary"}]

    correct = retrieval_consistency_score(
        claim,
        correct_chain,
        {"tool_output"},
        VerificationPolicy(),
    )
    wrong_source = retrieval_consistency_score(
        claim,
        wrong_chain,
        {"tool_output"},
        VerificationPolicy(),
    )
    missing = retrieval_consistency_score(
        claim,
        [],
        {"tool_output"},
        VerificationPolicy(),
    )
    stale = retrieval_consistency_score(
        {**claim, "stale": True},
        correct_chain,
        {"tool_output"},
        VerificationPolicy(),
    )
    contradicted = retrieval_consistency_score(
        {**claim, "support_status": "contradicted"},
        correct_chain,
        {"tool_output"},
        VerificationPolicy(),
    )

    assert correct == 1.0
    assert wrong_source < correct
    assert missing == 0.0
    assert stale < correct
    assert contradicted < correct


def test_strict_policy_blocks_missing_source_type_but_lenient_only_flags():
    claim = {
        "claim_id": "claim-complete",
        "event_id": "claim-event",
        "claim_type": "task_complete",
        "confidence": 0.95,
        "stale": False,
        "support_status": "supported",
        "lost_provenance": False,
        "source_event_ids": ["test-run"],
    }
    trace_events = [
        {
            "event_id": "test-run",
            "event_type": "tool_call",
            "sequence_number": 1,
            "source_type": "tool_output",
        }
    ]

    strict_decision = verify_claim(claim, trace_events, VerificationPolicy())
    lenient_decision = verify_claim(
        claim,
        trace_events,
        VerificationPolicy(mode="lenient"),
    )

    assert strict_decision["decision"] == "block"
    assert "missing required source type" in strict_decision["reasons"]
    assert lenient_decision["decision"] == "needs_verification"


def test_tests_pass_requires_recent_test_run_after_changes():
    verified = verify_run(_stale_tests_run())

    decision = verified["verification_report"]["decisions"][0]
    assert decision["claim_type"] == "tests_pass"
    assert decision["decision"] == "block"
    assert "stale evidence" in decision["reasons"]
    assert verified["blocked_actions"][0]["blocked_action"] == "report_tests_pass"


def test_compare_does_not_treat_posthoc_filtering_as_behavioral_improvement():
    baseline = _stale_completion_run()
    baseline["memory_health_report"] = {
        "metrics": {"false_completion_rate": 1.0, "memory_health_score": 0.25},
        "claim_counts": {"false_completion": 1},
    }
    verified = verify_run(baseline)

    comparison = compare_runs(baseline, verified)

    assert comparison["verification_overhead"]["blocked_actions"] == 1
    assert comparison["metric_deltas"]["false_completion_rate"] == 0.0
    assert comparison["behavioral_evidence_available"] is False
    assert comparison["behavioral_outcomes"]["available"] is False
    assert "post-hoc claim filtering" in comparison["behavioral_outcomes"]["reason"]


def test_compare_reports_in_loop_block_and_recovery_without_erasing_raw_claims(
    tmp_path: Path,
):
    pytest.importorskip("langgraph")

    baseline = BenchmarkRunner().run_task_id(
        "coding_stale_tests_001",
        BenchmarkRunConfig(
            framework="langgraph_tools",
            trace_mode="model_driven",
            agent_variant="baseline",
            workspace_root=str(tmp_path),
        ),
    )
    verified = BenchmarkRunner().run_task_id(
        "coding_stale_tests_001",
        BenchmarkRunConfig(
            framework="langgraph_tools",
            trace_mode="model_driven",
            agent_variant="verified",
            workspace_root=str(tmp_path),
        ),
    )

    comparison = compare_runs(baseline, verified)
    outcomes = comparison["behavioral_outcomes"]

    assert comparison["behavioral_evidence_available"] is True
    assert comparison["verified_raw_claim_counts"]["false_completion"] == 1
    assert comparison["verified_accepted_claim_counts"]["false_completion"] == 0
    assert outcomes["baseline_accepted_false_finishes"] == 1
    assert outcomes["verified_false_finish_proposals"] == 1
    assert outcomes["verified_blocked_false_finishes"] == 1
    assert outcomes["verified_accepted_false_finishes"] == 0
    assert outcomes["baseline_accepted_finish_evaluator_failures"] == 0
    assert outcomes["verified_accepted_finish_evaluator_failures"] == 0
    assert outcomes["verified_recovery_after_block"] is True
    assert comparison["verification_overhead"]["extra_model_actions"] == 1
    assert verified["interaction_metrics"]["memory_repair_attempts"] == 1
    assert verified["interaction_metrics"]["memory_repair_recovery"] is True


def test_later_file_evidence_does_not_make_old_test_evidence_fresh():
    run = {
        "trace_events": [
            {
                "event_id": "old-tests",
                "event_type": "tool_call",
                "tool_name": "run_tests",
                "sequence_number": 1,
                "status": "success",
                "source_type": "tool_output",
                "source_event_ids": [],
            },
            {
                "event_id": "later-edit",
                "event_type": "file_state_change",
                "sequence_number": 2,
                "source_type": "file_state",
                "source_event_ids": [],
                "invalidates_claim_types": ["tests_pass", "task_complete"],
            },
            {
                "event_id": "finish",
                "event_type": "completion_claim",
                "tool_name": "finish",
                "sequence_number": 3,
                "claim": "The tests pass and the task is complete.",
                "source_type": "agent_inference",
                "source_event_ids": ["old-tests", "later-edit"],
            },
        ],
        "high_risk_labels": [
            {
                "label_id": "finish:tests_pass",
                "event_id": "finish",
                "claim_type": "tests_pass",
                "claim_text": "The tests pass and the task is complete.",
                "source_event_ids": ["old-tests", "later-edit"],
                "freshness_rule": "test evidence must follow the latest edit",
                "minimum_source_type": "tool_output",
            },
            {
                "label_id": "finish:task_complete",
                "event_id": "finish",
                "claim_type": "task_complete",
                "claim_text": "The tests pass and the task is complete.",
                "source_event_ids": ["old-tests", "later-edit"],
                "freshness_rule": "completion evidence must be current",
                "minimum_source_type": "tool_output",
            },
        ],
    }

    claims = extract_memory_claims(run)

    assert {claim["claim_type"] for claim in claims} == {
        "tests_pass",
        "task_complete",
    }
    assert all(claim["stale"] for claim in claims)


def test_semantic_drift_delta_uses_same_task_context_for_verified_runs():
    baseline = _stale_completion_run()
    verified = verify_run(baseline)

    comparison = compare_runs(baseline, verified)

    assert comparison["metric_deltas"]["semantic_drift_score"] == 0.0


def test_cli_verify_table_output_surfaces_blocked_decisions(tmp_path: Path):
    run_path = tmp_path / "stale-run.json"
    run_path.write_text(json.dumps(_stale_completion_run()))

    result = subprocess.run(
        [
            sys.executable,
            "scripts/agent_memory.py",
            "verify",
            "--run",
            str(run_path),
            "--format",
            "table",
        ],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )

    assert "block" in result.stdout
    assert "1" in result.stdout


def test_cli_resume_materializes_completed_tool_run_checkpoint(
    tmp_path: Path,
):
    pytest.importorskip("langgraph")

    run = BenchmarkRunner().run_task_id(
        "coding_stale_tests_001",
        BenchmarkRunConfig(
            framework="langgraph_tools",
            trace_mode="model_driven",
            action_budget=8,
            workspace_root=str(tmp_path / "workspaces"),
        ),
    )
    checkpoint_path = run["run_metadata"]["run_checkpoint_path"]
    output_path = tmp_path / "resumed.json"

    result = subprocess.run(
        [
            sys.executable,
            "scripts/agent_memory.py",
            "resume",
            "--checkpoint",
            checkpoint_path,
            "--out",
            str(output_path),
            "--format",
            "json",
        ],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )

    resumed = json.loads(output_path.read_text(encoding="utf-8"))
    assert resumed["task_id"] == run["task_id"]
    assert resumed["trace_events"] == run["trace_events"]
    assert resumed["interaction_metrics"] == run["interaction_metrics"]
    assert "Resumed Benchmark Run" not in result.stderr


def test_cli_run_score_verify_and_compare_write_artifacts(tmp_path: Path):
    run_path = tmp_path / "baseline.json"
    score_path = tmp_path / "score.md"
    verified_path = tmp_path / "verified.json"
    compare_path = tmp_path / "compare.json"

    subprocess.run(
        [
            sys.executable,
            "scripts/agent_memory.py",
            "run",
            "--task",
            "coding_stale_tests_001",
            "--out",
            str(run_path),
            "--format",
            "json",
        ],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    assert run_path.exists()
    run_payload = json.loads(run_path.read_text())
    assert run_payload["task_id"] == "coding_stale_tests_001"

    subprocess.run(
        [
            sys.executable,
            "scripts/agent_memory.py",
            "score",
            "--run",
            str(run_path),
            "--out",
            str(score_path),
            "--format",
            "markdown",
        ],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    assert "Memory Health Report" in score_path.read_text()

    subprocess.run(
        [
            sys.executable,
            "scripts/agent_memory.py",
            "verify",
            "--run",
            str(run_path),
            "--out",
            str(verified_path),
            "--format",
            "json",
        ],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    verified_payload = json.loads(verified_path.read_text())
    assert "verification_report" in verified_payload

    subprocess.run(
        [
            sys.executable,
            "scripts/agent_memory.py",
            "compare",
            "--baseline",
            str(run_path),
            "--verified",
            str(verified_path),
            "--out",
            str(compare_path),
            "--format",
            "json",
        ],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    comparison = json.loads(compare_path.read_text())
    assert comparison["schema_version"] == "agent-memory-comparison/v0.2"
