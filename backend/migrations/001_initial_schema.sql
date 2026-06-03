-- Migration 001: Initial schema for Agent Observability Platform
-- Creates sessions, trace_events, tool_call_metrics, alert_rules, and alert_history tables

-- Enable TimescaleDB extension
CREATE EXTENSION IF NOT EXISTS timescaledb CASCADE;

-- ============================================================================
-- Sessions Table
-- ============================================================================

CREATE TABLE IF NOT EXISTS sessions (
    session_id UUID PRIMARY KEY,
    user_id VARCHAR(255) NOT NULL,
    agent_type VARCHAR(50) NOT NULL,
    goal TEXT NOT NULL,
    status VARCHAR(20) NOT NULL CHECK (status IN ('running', 'completed', 'failed', 'timeout', 'cancelled')),
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    completed_at TIMESTAMP,
    duration_ms INTEGER,
    
    -- Aggregated metrics
    total_reasoning_steps INTEGER DEFAULT 0,
    total_tool_calls INTEGER DEFAULT 0,
    total_memory_accesses INTEGER DEFAULT 0,
    total_memory_hits INTEGER DEFAULT 0,
    total_tokens INTEGER DEFAULT 0,
    total_cost DECIMAL(10, 6) DEFAULT 0,
    error_count INTEGER DEFAULT 0,
    
    -- Metadata
    metadata JSONB,
    tags TEXT[],
    coordination_id UUID
);

-- Indexes for sessions
CREATE INDEX idx_sessions_user_created ON sessions(user_id, created_at DESC);
CREATE INDEX idx_sessions_status ON sessions(status);
CREATE INDEX idx_sessions_coordination ON sessions(coordination_id) WHERE coordination_id IS NOT NULL;
CREATE INDEX idx_sessions_tags ON sessions USING GIN(tags);
CREATE INDEX idx_sessions_created_at ON sessions(created_at DESC);
CREATE INDEX idx_sessions_goal_fts ON sessions USING GIN(to_tsvector('english', goal));

-- ============================================================================
-- Trace Events Table (TimescaleDB Hypertable)
-- ============================================================================

CREATE TABLE IF NOT EXISTS trace_events (
    event_id UUID NOT NULL,
    session_id UUID NOT NULL REFERENCES sessions(session_id) ON DELETE CASCADE,
    event_type VARCHAR(50) NOT NULL CHECK (event_type IN (
        'reasoning_step',
        'tool_call',
        'memory_access',
        'decision_point',
        'planning_phase',
        'custom_metric',
        'annotation'
    )),
    timestamp TIMESTAMP NOT NULL,
    sequence_number INTEGER NOT NULL,
    parent_event_id UUID,
    
    -- Common fields
    duration_ms INTEGER,
    status VARCHAR(20),
    
    -- Event-specific data (JSONB for flexibility)
    event_data JSONB NOT NULL,
    
    -- Error info
    error_type VARCHAR(100),
    error_message TEXT,
    
    PRIMARY KEY (session_id, timestamp, event_id)
);

-- Convert to TimescaleDB hypertable for time-series optimization
SELECT create_hypertable(
    'trace_events',
    'timestamp',
    chunk_time_interval => INTERVAL '1 day',
    if_not_exists => TRUE
);

-- Indexes for trace_events
CREATE INDEX idx_trace_events_session ON trace_events(session_id, sequence_number);
CREATE INDEX idx_trace_events_type ON trace_events(event_type, timestamp DESC);
CREATE INDEX idx_trace_events_parent ON trace_events(parent_event_id) WHERE parent_event_id IS NOT NULL;
CREATE INDEX idx_trace_events_data ON trace_events USING GIN(event_data);

-- Move older chunks to columnstore after 7 days
ALTER TABLE trace_events SET (
    timescaledb.enable_columnstore = true,
    timescaledb.segmentby = 'session_id',
    timescaledb.orderby = 'timestamp DESC'
);
CALL add_columnstore_policy('trace_events', after => INTERVAL '7 days', if_not_exists => TRUE);

-- ============================================================================
-- Tool Call Metrics Table (TimescaleDB Hypertable for aggregations)
-- ============================================================================

CREATE TABLE IF NOT EXISTS tool_call_metrics (
    timestamp TIMESTAMP NOT NULL,
    tool_name VARCHAR(100) NOT NULL,
    success_count INTEGER DEFAULT 0,
    failure_count INTEGER DEFAULT 0,
    total_duration_ms BIGINT DEFAULT 0,
    avg_duration_ms INTEGER,
    p95_duration_ms INTEGER,
    
    PRIMARY KEY (timestamp, tool_name)
);

-- Convert to TimescaleDB hypertable
SELECT create_hypertable(
    'tool_call_metrics',
    'timestamp',
    chunk_time_interval => INTERVAL '1 hour',
    if_not_exists => TRUE
);

-- Move older chunks to columnstore after 1 day
ALTER TABLE tool_call_metrics SET (
    timescaledb.enable_columnstore = true,
    timescaledb.segmentby = 'tool_name',
    timescaledb.orderby = 'timestamp DESC'
);
CALL add_columnstore_policy('tool_call_metrics', after => INTERVAL '1 day', if_not_exists => TRUE);

-- ============================================================================
-- Alert Rules Table
-- ============================================================================

CREATE TABLE IF NOT EXISTS alert_rules (
    rule_id UUID PRIMARY KEY,
    user_id VARCHAR(255) NOT NULL,
    name VARCHAR(255) NOT NULL,
    description TEXT,
    enabled BOOLEAN DEFAULT TRUE,
    
    -- Condition
    condition_type VARCHAR(50) NOT NULL CHECK (condition_type IN ('threshold', 'anomaly', 'pattern')),
    condition_config JSONB NOT NULL,
    
    -- Notification
    notification_channels JSONB NOT NULL,
    severity VARCHAR(20) NOT NULL CHECK (severity IN ('info', 'warning', 'critical')),
    
    -- Suppression
    suppression_window_minutes INTEGER DEFAULT 60,
    
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP NOT NULL DEFAULT NOW()
);

-- Indexes for alert_rules
CREATE INDEX idx_alert_rules_user ON alert_rules(user_id);
CREATE INDEX idx_alert_rules_enabled ON alert_rules(enabled) WHERE enabled = TRUE;

-- ============================================================================
-- Alert History Table
-- ============================================================================

CREATE TABLE IF NOT EXISTS alert_history (
    alert_id UUID PRIMARY KEY,
    rule_id UUID NOT NULL REFERENCES alert_rules(rule_id) ON DELETE CASCADE,
    session_id UUID REFERENCES sessions(session_id) ON DELETE SET NULL,
    triggered_at TIMESTAMP NOT NULL,
    resolved_at TIMESTAMP,
    status VARCHAR(20) NOT NULL CHECK (status IN ('triggered', 'resolved', 'suppressed')),
    
    -- Alert details
    message TEXT NOT NULL,
    context JSONB
);

-- Indexes for alert_history
CREATE INDEX idx_alert_history_rule ON alert_history(rule_id, triggered_at DESC);
CREATE INDEX idx_alert_history_session ON alert_history(session_id) WHERE session_id IS NOT NULL;
CREATE INDEX idx_alert_history_triggered ON alert_history(triggered_at DESC);

-- ============================================================================
-- Retention Policy (Automatic data management)
-- ============================================================================

-- Drop chunks older than 90 days for trace_events
SELECT add_retention_policy('trace_events', INTERVAL '90 days', if_not_exists => TRUE);

-- Drop chunks older than 180 days for tool_call_metrics
SELECT add_retention_policy('tool_call_metrics', INTERVAL '180 days', if_not_exists => TRUE);

-- ============================================================================
-- Comments
-- ============================================================================

COMMENT ON TABLE sessions IS 'Agent execution sessions with aggregated metrics';
COMMENT ON TABLE trace_events IS 'Time-series trace events for agent execution (TimescaleDB hypertable)';
COMMENT ON TABLE tool_call_metrics IS 'Aggregated tool call metrics over time (TimescaleDB hypertable)';
COMMENT ON TABLE alert_rules IS 'User-defined alert rules for monitoring';
COMMENT ON TABLE alert_history IS 'History of triggered alerts';
