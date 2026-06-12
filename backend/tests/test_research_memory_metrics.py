"""Tests for memory corruption metrics and report API."""

import sys
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from research.runner import (
    BenchmarkRunner,
    build_memory_health_report,
    compute_attribution_accuracy,
    compute_false_completion_rate,
    compute_semantic_drift_score,
    compute_structured_memory_metrics,
    compute_task_state_accuracy,
    compute_temporal_accuracy,
)
from services.auth import TokenData


def make_token(user_id: str = "research_user") -> TokenData:
    return TokenData(
        user_id=user_id,
        permissions=["admin"],
        exp=datetime.utcnow() + timedelta(hours=1),
    )


def test_memory_health_report_contains_core_metrics():
    run = BenchmarkRunner().run_all()[0]
    report = build_memory_health_report(run)

    assert report["schema_version"] == "agent-memory-health/v0.3"
    assert report["run_id"] == run["run_id"]
    assert report["task_id"] == run["task_id"]
    assert report["claim_counts"]["total"] == len(run["memory_claims"])
    assert set(report["metrics"]) == {
        "task_state_accuracy",
        "attribution_accuracy",
        "temporal_accuracy",
        "false_completion_rate",
        "memory_health_score",
    }
    assert report["exploratory_metrics"]["method"] == "lexical_jaccard"
    assert report["exploratory_metrics"]["confirmatory"] is False
    assert "structured_memory_score" in report["headline_metrics"]
    assert report["headline_metrics"]["confirmatory"] is True
    assert report["headline_metrics"][
        "lexical_or_embedding_similarity_included"
    ] is False
    assert "decision_belief_summary" in report


def test_metric_scores_handle_unsupported_and_stale_completion_claims():
    claims = [
        {
            "claim_id": "c1",
            "claim_type": "task_complete",
            "stale": True,
            "lost_provenance": False,
            "support_status": "inferred",
            "source_event_ids": ["e1"],
        },
        {
            "claim_id": "c2",
            "claim_type": "task_complete",
            "stale": False,
            "lost_provenance": True,
            "support_status": "unsupported",
            "source_event_ids": [],
        },
        {
            "claim_id": "c3",
            "claim_type": "tests_pass",
            "stale": False,
            "lost_provenance": False,
            "support_status": "inferred",
            "source_event_ids": ["e2"],
        },
    ]

    assert compute_task_state_accuracy(claims) == 0.0
    assert compute_false_completion_rate(claims) == 1.0
    assert compute_attribution_accuracy(claims) == 0.6667
    assert compute_temporal_accuracy(claims) == 0.6667


def test_memory_health_report_surfaces_contradicted_claims():
    run = {
        "run_id": "contradicted-run",
        "task_id": "source-task",
        "trace_events": [],
        "memory_claims": [
            {
                "claim_id": "source-claim",
                "claim_type": "source_supports_claim",
                "stale": False,
                "lost_provenance": False,
                "support_status": "contradicted",
                "source_event_ids": ["source-1"],
            }
        ],
    }

    report = build_memory_health_report(run)

    assert report["claim_counts"]["contradicted"] == 1
    assert report["contradicted_claims"][0]["claim_id"] == "source-claim"
    assert report["recovery_opportunities"][0]["reasons"] == [
        "resolve contradicted claim"
    ]


def test_semantic_drift_score_increases_when_summary_leaves_goal():
    aligned_run = {
        "trace_events": [
            {
                "event_id": "goal",
                "event_type": "prompt",
                "sequence_number": 1,
                "prompt": "Fix parser tests and verify completion.",
            },
            {
                "event_id": "summary",
                "event_type": "summary",
                "sequence_number": 2,
                "summary": "Fix parser tests and verify completion.",
            },
        ]
    }
    drifted_run = {
        "trace_events": [
            {
                "event_id": "goal",
                "event_type": "prompt",
                "sequence_number": 1,
                "prompt": "Fix parser tests and verify completion.",
            },
            {
                "event_id": "summary",
                "event_type": "summary",
                "sequence_number": 2,
                "summary": "Write a marketing landing page for a dashboard.",
            },
        ]
    }

    assert compute_semantic_drift_score(aligned_run) == 0.0
    assert compute_semantic_drift_score(drifted_run) > 0.5


def test_memory_health_report_api_scores_submitted_run():
    from main import create_app

    run = BenchmarkRunner().run_all()[0]

    with patch("services.auth.AuthService.verify_jwt_token", return_value=make_token()):
        app = create_app()
        client = TestClient(app)
        response = client.post(
            "/api/v1/research/memory-health",
            json={"run": run},
            headers={"Authorization": "Bearer token"},
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["schema_version"] == "agent-memory-health/v0.3"
    assert payload["run_id"] == run["run_id"]
    assert payload["metrics"]["memory_health_score"] <= 1.0


def test_structured_metrics_count_explicit_stale_decision_evidence():
    run = {
        "memory_claims": [],
        "operational_memory": [
            {
                "event_id": "test-old",
                "stale": True,
                "support_status": "stale",
            },
            {
                "event_id": "write-current",
                "stale": False,
                "support_status": "supported",
            },
        ],
        "trace_events": [
            {
                "event_type": "completion_claim",
                "tool_name": "finish",
                "source_event_ids": ["test-old", "write-current"],
            }
        ],
    }

    metrics = compute_structured_memory_metrics(run)

    assert metrics["stale_observations_used_after_invalidation"] == 1
    assert metrics["stale_decision_use_rate"] == 0.5
