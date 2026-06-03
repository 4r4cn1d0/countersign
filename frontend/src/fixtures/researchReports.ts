import type { ResearchReportBundle } from "../types/observability";

export const demoResearchReportBundle: ResearchReportBundle = {
  source: "fixture",
  runtime: "deterministic",
  variant: "verified",
  health: {
    schema_version: "agent-memory-health/v0.1",
    run_id: "demo-baseline-run",
    task_id: "coding_stale_tests_001",
    trace_event_count: 12,
    metrics: {
      semantic_drift_score: 0.42,
      goal_fidelity: 0.58,
      task_state_accuracy: 0.5,
      attribution_accuracy: 0.67,
      temporal_accuracy: 0.5,
      false_completion_rate: 0.5,
      memory_health_score: 0.56
    },
    claim_counts: {
      total: 4,
      unsupported: 1,
      stale: 1,
      contradicted: 0,
      lost_provenance: 1,
      false_completion: 1
    },
    unsupported_claims: [
      {
        claim_id: "claim-user-approved",
        event_id: "event-approval",
        claim_type: "user_approved",
        subject: "user",
        predicate: "approved",
        object: "action",
        text: "the user approved this action.",
        confidence: 0.5,
        source_type: "agent_inference",
        source_event_ids: [],
        source_event_sequence_numbers: [],
        support_status: "unsupported",
        stale: false,
        lost_provenance: true,
        freshness_rule: "must cite user instruction history"
      }
    ],
    stale_claims: [
      {
        claim_id: "claim-task-complete",
        event_id: "event-complete",
        claim_type: "task_complete",
        subject: "task",
        predicate: "is_complete",
        object: "reported_work",
        text: "the task is complete and ready to report as done.",
        confidence: 0.75,
        source_type: "agent_inference",
        source_event_ids: ["event-old-tests"],
        source_event_sequence_numbers: [8],
        support_status: "inferred",
        stale: true,
        lost_provenance: false,
        freshness_rule: "must include implementation evidence and post-edit test evidence"
      }
    ],
    contradicted_claims: [],
    recovery_opportunities: [
      {
        claim_id: "claim-task-complete",
        claim_type: "task_complete",
        reasons: ["refresh stale evidence"],
        recommended_action: "collect implementation evidence and fresh verification output"
      },
      {
        claim_id: "claim-user-approved",
        claim_type: "user_approved",
        reasons: ["verify provenance", "resolve unsupported claim"],
        recommended_action: "confirm approval in the user instruction history"
      }
    ]
  },
  verification: {
    schema_version: "agent-memory-verification/v0.1",
    run_id: "demo-verified-run",
    task_id: "coding_stale_tests_001",
    policy: {
      mode: "strict",
      min_confidence: 0.75,
      min_consistency_score: 0.75
    },
    decision_counts: {
      allow: 1,
      needs_verification: 1,
      block: 1
    },
    decisions: [
      {
        decision_id: "claim-tests-pass:verification",
        claim_id: "claim-tests-pass",
        event_id: "event-tests",
        claim_type: "tests_pass",
        risk_level: "high",
        decision: "allow",
        consistency_score: 0.95,
        reasons: [],
        required_source_types: ["tool_output"],
        observed_source_types: ["tool_output", "agent_inference"],
        source_event_ids: ["event-fresh-tests"],
        inspected_event_ids: ["event-fresh-tests", "event-final-edit"],
        recommended_action: "rerun relevant tests and attach fresh tool output"
      },
      {
        decision_id: "claim-user-approved:verification",
        claim_id: "claim-user-approved",
        event_id: "event-approval",
        claim_type: "user_approved",
        risk_level: "high",
        decision: "needs_verification",
        consistency_score: 0.4,
        reasons: ["lost provenance", "low retrieval consistency"],
        required_source_types: ["user_instruction"],
        observed_source_types: ["agent_inference"],
        source_event_ids: [],
        inspected_event_ids: [],
        recommended_action: "confirm approval in the user instruction history"
      },
      {
        decision_id: "claim-task-complete:verification",
        claim_id: "claim-task-complete",
        event_id: "event-complete",
        claim_type: "task_complete",
        risk_level: "high",
        decision: "block",
        consistency_score: 0.45,
        reasons: ["stale evidence", "missing required source type"],
        required_source_types: ["file_state", "tool_output"],
        observed_source_types: ["tool_output"],
        source_event_ids: ["event-old-tests"],
        inspected_event_ids: ["event-old-tests", "event-final-edit"],
        recommended_action: "collect implementation evidence and fresh verification output"
      }
    ],
    blocked_actions: [
      {
        claim_id: "claim-task-complete",
        claim_type: "task_complete",
        blocked_action: "mark_task_complete",
        reasons: ["stale evidence", "missing required source type"],
        recommended_action: "collect implementation evidence and fresh verification output"
      }
    ],
    effective_memory_health_report: {
      schema_version: "agent-memory-health/v0.1",
      run_id: "demo-verified-run",
      task_id: "coding_stale_tests_001",
      trace_event_count: 15,
      metrics: {
        semantic_drift_score: 0.42,
        goal_fidelity: 0.58,
        task_state_accuracy: 1,
        attribution_accuracy: 0.75,
        temporal_accuracy: 1,
        false_completion_rate: 0,
        memory_health_score: 0.83
      },
      claim_counts: {
        total: 3,
        unsupported: 1,
        stale: 0,
        contradicted: 0,
        lost_provenance: 1,
        false_completion: 0
      },
      unsupported_claims: [],
      stale_claims: [],
      contradicted_claims: [],
      recovery_opportunities: []
    }
  },
  comparison: {
    schema_version: "agent-memory-comparison/v0.1",
    baseline_run_id: "demo-baseline-run",
    verified_run_id: "demo-verified-run",
    task_id: "coding_stale_tests_001",
    baseline_metrics: {
      semantic_drift_score: 0.42,
      goal_fidelity: 0.58,
      task_state_accuracy: 0.5,
      attribution_accuracy: 0.67,
      temporal_accuracy: 0.5,
      false_completion_rate: 0.5,
      memory_health_score: 0.56
    },
    verified_metrics: {
      semantic_drift_score: 0.42,
      goal_fidelity: 0.58,
      task_state_accuracy: 1,
      attribution_accuracy: 0.75,
      temporal_accuracy: 1,
      false_completion_rate: 0,
      memory_health_score: 0.83
    },
    metric_deltas: {
      semantic_drift_score: 0,
      goal_fidelity: 0,
      task_state_accuracy: 0.5,
      attribution_accuracy: 0.08,
      temporal_accuracy: 0.5,
      false_completion_rate: -0.5,
      memory_health_score: 0.27
    },
    baseline_claim_counts: {
      total: 4,
      unsupported: 1,
      stale: 1,
      contradicted: 0,
      lost_provenance: 1,
      false_completion: 1
    },
    verified_claim_counts: {
      total: 3,
      unsupported: 1,
      stale: 0,
      contradicted: 0,
      lost_provenance: 1,
      false_completion: 0
    },
    verification_decision_counts: {
      allow: 1,
      needs_verification: 1,
      block: 1
    },
    verification_overhead: {
      extra_trace_events: 3,
      blocked_actions: 1
    }
  }
};
