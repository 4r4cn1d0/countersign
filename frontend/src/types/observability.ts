export type SessionStatus = "running" | "completed" | "failed" | "timeout" | "cancelled";

export type TraceEventType =
  | "reasoning_step"
  | "tool_call"
  | "memory_access"
  | "decision_point"
  | "planning_phase"
  | "custom_metric"
  | "annotation";

export interface Session {
  session_id: string;
  user_id: string;
  agent_type: string;
  goal: string;
  status: SessionStatus;
  created_at: string;
  completed_at: string | null;
  duration_ms: number | null;
  total_reasoning_steps: number;
  total_tool_calls: number;
  total_memory_accesses: number;
  total_memory_hits?: number;
  total_tokens: number;
  total_cost: number;
  error_count: number;
  metadata: Record<string, unknown> | null;
  tags: string[];
  coordination_id: string | null;
}

export interface SessionListResponse {
  sessions: Session[];
  total: number;
  limit: number;
  offset: number;
  has_more: boolean;
}

export interface SessionSearchFilters {
  status?: SessionStatus[];
  date_range?: {
    start?: string;
    end?: string;
  };
  cost_range?: {
    min?: number;
    max?: number;
  };
  duration_range?: {
    min?: number;
    max?: number;
  };
  tags?: string[];
  agent_type?: string;
}

export interface SessionSearchRequest {
  query?: string;
  filters?: SessionSearchFilters;
  sort?: string;
  limit?: number;
  offset?: number;
}

export interface TraceEvent {
  event_id: string;
  session_id: string;
  event_type: TraceEventType;
  timestamp: string;
  sequence_number: number;
  parent_event_id?: string | null;
  duration_ms?: number | null;
  status?: string | null;
  error_type?: string | null;
  error_message?: string | null;
  event_data: Record<string, unknown>;
}

export interface TraceResponse {
  session_id: string;
  total_events: number;
  events: TraceEvent[];
  page: number;
  page_size: number;
  has_more: boolean;
}

export interface ExecutionGraphNode {
  event_id: string;
  event_type: TraceEventType;
  label: string;
  duration_ms?: number | null;
  status?: string | null;
  timestamp: string;
}

export interface ExecutionGraphEdge {
  source_event_id: string;
  target_event_id: string;
}

export interface ExecutionGraphResponse {
  session_id: string;
  nodes: ExecutionGraphNode[];
  edges: ExecutionGraphEdge[];
}

export interface SessionMetrics {
  session_id: string;
  goal: string;
  status: SessionStatus;
  created_at: string;
  completed_at: string | null;
  duration_ms: number | null;
  total_reasoning_steps: number;
  total_tool_calls: number;
  total_memory_accesses: number;
  total_decision_points: number;
  total_planning_phases: number;
  error_count: number;
  total_tokens: number;
  total_cost: number;
}

export interface AggregateMetrics {
  time_period_start: string;
  time_period_end: string;
  total_sessions: number;
  completed_sessions: number;
  failed_sessions: number;
  success_rate: number;
  avg_duration_ms: number;
  median_duration_ms: number;
  p95_duration_ms: number;
  total_tokens_used: number;
  avg_tokens_per_session: number;
  total_cost: number;
  avg_cost_per_session: number;
  total_reasoning_steps: number;
  avg_reasoning_steps_per_session: number;
  total_tool_calls: number;
  avg_tool_calls_per_session: number;
  error_count: number;
}

export interface TimeSeriesDataPoint {
  timestamp: string;
  value: number;
  metric_name: string;
}

export interface TimeSeriesMetrics {
  metric_name: string;
  time_period_start: string;
  time_period_end: string;
  data_points: TimeSeriesDataPoint[];
}

export type RealtimeMessage =
  | { type: "ping" }
  | { type: "pong" }
  | { type: "error"; message: string }
  | { type: "snapshot"; session_id: string; events: TraceEvent[] }
  | { type: "event"; session_id: string; event: TraceEvent }
  | { type: "events"; session_id: string; events: TraceEvent[] }
  | { type: "unsubscribed" };

export interface ReconnectPolicy {
  initialDelayMs: number;
  maxDelayMs: number;
  multiplier: number;
  maxAttempts: number;
}

export interface MemoryClaim {
  claim_id: string;
  event_id: string;
  claim_type: string;
  subject: string;
  predicate: string;
  object: string;
  text: string;
  confidence: number;
  source_type: string;
  source_event_ids: string[];
  source_event_sequence_numbers: number[];
  support_status: "supported" | "unsupported" | "stale" | "contradicted" | "inferred" | string;
  stale: boolean;
  lost_provenance: boolean;
  freshness_rule?: string | null;
}

export interface MemoryHealthMetrics {
  semantic_drift_score: number;
  goal_fidelity: number;
  task_state_accuracy: number;
  attribution_accuracy: number;
  temporal_accuracy: number;
  false_completion_rate: number;
  memory_health_score: number;
}

export interface MemoryClaimCounts {
  total: number;
  unsupported: number;
  stale: number;
  contradicted: number;
  lost_provenance: number;
  false_completion: number;
}

export interface RecoveryOpportunity {
  claim_id: string;
  claim_type: string;
  reasons: string[];
  recommended_action: string;
}

export interface MemoryHealthReport {
  schema_version: "agent-memory-health/v0.1" | string;
  run_id?: string | null;
  task_id?: string | null;
  metrics: MemoryHealthMetrics;
  claim_counts: MemoryClaimCounts;
  unsupported_claims: MemoryClaim[];
  stale_claims: MemoryClaim[];
  contradicted_claims: MemoryClaim[];
  recovery_opportunities: RecoveryOpportunity[];
  trace_event_count: number;
}

export interface VerificationDecision {
  decision_id: string;
  claim_id: string;
  event_id: string;
  claim_type: string;
  risk_level: string;
  decision: "allow" | "needs_verification" | "block" | string;
  consistency_score: number;
  reasons: string[];
  required_source_types: string[];
  observed_source_types: string[];
  source_event_ids: string[];
  inspected_event_ids: string[];
  recommended_action: string;
}

export interface BlockedAction {
  claim_id: string;
  claim_type: string;
  blocked_action: string;
  reasons: string[];
  recommended_action: string;
}

export interface VerificationReport {
  schema_version: "agent-memory-verification/v0.1" | string;
  run_id?: string | null;
  task_id?: string | null;
  policy: {
    mode: string;
    min_confidence: number;
    min_consistency_score: number;
  };
  decision_counts: {
    allow: number;
    needs_verification: number;
    block: number;
  };
  decisions: VerificationDecision[];
  blocked_actions: BlockedAction[];
  effective_memory_health_report?: MemoryHealthReport | null;
}

export interface ComparisonReport {
  schema_version: "agent-memory-comparison/v0.1" | string;
  baseline_run_id?: string | null;
  verified_run_id?: string | null;
  task_id?: string | null;
  baseline_metrics: MemoryHealthMetrics;
  verified_metrics: MemoryHealthMetrics;
  metric_deltas: MemoryHealthMetrics;
  baseline_claim_counts: MemoryClaimCounts;
  verified_claim_counts: MemoryClaimCounts;
  verification_decision_counts: {
    allow?: number;
    needs_verification?: number;
    block?: number;
  };
  verification_overhead: {
    extra_trace_events: number;
    blocked_actions: number;
  };
}

export interface ResearchReportBundle {
  health: MemoryHealthReport;
  verification: VerificationReport;
  comparison: ComparisonReport;
  source: "fixture" | "uploaded" | "api";
  runtime: "deterministic" | "ollama" | "llama_cpp" | string;
  variant: "baseline" | "verified" | string;
}
