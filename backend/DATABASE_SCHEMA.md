# Database Schema Documentation

## Overview

The Agent Memory Observatory uses **PostgreSQL 15+** with the **TimescaleDB** extension for efficient time-series trace storage and querying. This document describes the observability schema used to capture long-horizon agent sessions, including tables, indexes, constraints, and optimization strategies.

## Technology Stack

- **Database**: PostgreSQL 15+
- **Time-Series Extension**: TimescaleDB
- **Connection Pool**: asyncpg with connection pooling
- **Migration Tool**: Custom Python migration runner

## Schema Architecture

### Core Tables

1. **sessions** - Agent execution sessions with aggregated metrics
2. **trace_events** - Time-series trace events (TimescaleDB hypertable)
3. **tool_call_metrics** - Aggregated tool call metrics (TimescaleDB hypertable)
4. **alert_rules** - User-defined alert rules
5. **alert_history** - History of triggered alerts

## Table Definitions

### 1. sessions

Stores metadata and aggregated metrics for agent execution sessions.

**Schema**:
```sql
CREATE TABLE sessions (
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
    total_tokens INTEGER DEFAULT 0,
    total_cost DECIMAL(10, 6) DEFAULT 0,
    error_count INTEGER DEFAULT 0,
    
    -- Metadata
    metadata JSONB,
    tags TEXT[],
    coordination_id UUID
);
```

**Indexes**:
- `idx_sessions_user_created` - Composite index on (user_id, created_at DESC) for user session queries
- `idx_sessions_status` - Index on status for filtering by session state
- `idx_sessions_coordination` - Partial index on coordination_id for multi-agent sessions
- `idx_sessions_tags` - GIN index on tags array for tag-based filtering
- `idx_sessions_created_at` - Index on created_at for time-based queries

**Purpose**:
- Fast retrieval of session metadata
- Efficient filtering by user, status, and time range
- Support for multi-agent coordination tracking
- Tag-based session organization

**Requirements Satisfied**:
- Requirement 2.1: Session creation and tracking
- Requirement 10.1: Session history and search

---

### 2. trace_events (TimescaleDB Hypertable)

Stores all trace events in a time-series optimized format.

**Schema**:
```sql
CREATE TABLE trace_events (
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

-- Convert to TimescaleDB hypertable
SELECT create_hypertable(
    'trace_events',
    'timestamp',
    chunk_time_interval => INTERVAL '1 day'
);
```

**Indexes**:
- `idx_trace_events_session` - Composite index on (session_id, sequence_number) for ordered event retrieval
- `idx_trace_events_type` - Composite index on (event_type, timestamp DESC) for filtering by event type
- `idx_trace_events_parent` - Partial index on parent_event_id for hierarchical queries
- `idx_trace_events_data` - GIN index on event_data JSONB for flexible querying

**TimescaleDB Features**:
- **Hypertable**: Automatically partitions data by time (1-day chunks)
- **Compression**: Enabled after 7 days to reduce storage costs
- **Retention**: Automatically drops chunks older than 90 days

**Purpose**:
- Efficient storage and querying of time-series trace data
- Support for all event types with flexible JSONB schema
- Hierarchical event relationships via parent_event_id
- Automatic data lifecycle management

**Requirements Satisfied**:
- Requirement 2.2: Real-time trace event capture
- Requirement 2.3: Tool call execution tracking
- Requirement 20.1: Optimized time-series queries
- Requirement 20.2: Efficient data retention

---

### 3. tool_call_metrics (TimescaleDB Hypertable)

Stores pre-aggregated metrics for tool call performance analysis.

**Schema**:
```sql
CREATE TABLE tool_call_metrics (
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
    chunk_time_interval => INTERVAL '1 hour'
);
```

**TimescaleDB Features**:
- **Hypertable**: Partitions data by time (1-hour chunks)
- **Compression**: Enabled after 1 day
- **Retention**: Automatically drops chunks older than 180 days

**Purpose**:
- Fast aggregation queries for tool performance dashboards
- Pre-computed metrics to avoid expensive real-time calculations
- Historical trend analysis

**Requirements Satisfied**:
- Requirement 5.6: Tool call aggregate statistics
- Requirement 11.2: Tool call success rate metrics
- Requirement 20.5: Materialized views for aggregations

---

### 4. alert_rules

Stores user-defined alert rules for monitoring agent behavior.

**Schema**:
```sql
CREATE TABLE alert_rules (
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
```

**Indexes**:
- `idx_alert_rules_user` - Index on user_id for user-specific rule queries
- `idx_alert_rules_enabled` - Partial index on enabled rules for active rule evaluation

**Purpose**:
- Store flexible alert conditions using JSONB
- Support multiple notification channels
- Alert suppression to prevent notification spam

**Requirements Satisfied**:
- Requirement 15.1: User-defined alert rules
- Requirement 15.3: Alert configuration interface

---

### 5. alert_history

Stores the history of triggered alerts.

**Schema**:
```sql
CREATE TABLE alert_history (
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
```

**Indexes**:
- `idx_alert_history_rule` - Composite index on (rule_id, triggered_at DESC) for rule-specific history
- `idx_alert_history_session` - Partial index on session_id for session-related alerts
- `idx_alert_history_triggered` - Index on triggered_at DESC for recent alerts

**Purpose**:
- Track alert lifecycle (triggered → resolved)
- Link alerts to specific sessions
- Store alert context for debugging

**Requirements Satisfied**:
- Requirement 15.2: Alert notification delivery
- Requirement 15.6: Active alerts display

---

## Indexes and Query Optimization

### Index Strategy

1. **Composite Indexes**: Used for common query patterns (e.g., user_id + created_at)
2. **Partial Indexes**: Used for filtered queries (e.g., WHERE enabled = TRUE)
3. **GIN Indexes**: Used for JSONB and array columns
4. **Time-Based Indexes**: Optimized for time-range queries on hypertables

### Query Optimization Features

**TimescaleDB Optimizations**:
- Automatic chunk pruning for time-range queries
- Parallel query execution across chunks
- Compression for older data (7+ days)
- Continuous aggregates for real-time metrics

**PostgreSQL Optimizations**:
- Connection pooling (20 connections, 10 overflow)
- Prepared statements for common queries
- JSONB indexing for flexible schema queries
- Array GIN indexes for tag-based filtering

---

## Data Lifecycle Management

### Hot Storage (0-30 days)
- **Location**: PostgreSQL + TimescaleDB
- **Compression**: Enabled after 7 days
- **Purpose**: Fast queries for recent sessions
- **Access Pattern**: Real-time and interactive queries

### Warm Storage (30-90 days)
- **Location**: PostgreSQL (compressed chunks)
- **Compression**: Fully compressed
- **Purpose**: Historical analysis
- **Access Pattern**: Analytical queries

### Cold Storage (90+ days)
- **Location**: S3/MinIO (archived)
- **Format**: Compressed JSON
- **Purpose**: Long-term archival and compliance
- **Access Pattern**: On-demand retrieval

### Retention Policies

**trace_events**:
```sql
SELECT add_retention_policy('trace_events', INTERVAL '90 days');
```
- Automatically drops chunks older than 90 days
- Data is archived to S3 before deletion

**tool_call_metrics**:
```sql
SELECT add_retention_policy('tool_call_metrics', INTERVAL '180 days');
```
- Retains aggregated metrics for 180 days
- Longer retention for trend analysis

---

## Migration Management

### Migration Files

Migrations are stored in `/backend/migrations/` with sequential numbering:
- `001_initial_schema.sql` - Initial schema creation
- `002_*.sql` - Future migrations

### Running Migrations

**Automated**:
```bash
python migrations/run_migrations.py
```

**Manual**:
```bash
psql -U postgres -d agent_observability -f migrations/001_initial_schema.sql
```

### Migration Best Practices

1. **Idempotent**: Use `IF NOT EXISTS` and `if_not_exists => TRUE`
2. **Transactional**: Wrap DDL in transactions where possible
3. **Reversible**: Document rollback procedures
4. **Tested**: Test on staging before production

---

## Performance Considerations

### Expected Load

- **Concurrent Sessions**: 100+
- **Events per Second**: 1,000+
- **Query Latency**: <500ms for 100K sessions
- **Storage Growth**: ~1GB per 10K sessions

### Scaling Strategies

**Vertical Scaling**:
- Increase PostgreSQL memory (shared_buffers, work_mem)
- Add more CPU cores for parallel queries
- Use faster storage (NVMe SSDs)

**Horizontal Scaling**:
- Read replicas for analytical queries
- Separate OLTP and OLAP workloads
- Distributed TimescaleDB for multi-node setup

### Monitoring

**Key Metrics**:
- Query execution time (pg_stat_statements)
- Index usage (pg_stat_user_indexes)
- Table bloat (pg_stat_user_tables)
- Chunk compression ratio (timescaledb_information.chunks)

**Alerts**:
- Slow queries (>1s)
- High connection count (>80% of max)
- Low cache hit ratio (<95%)
- Chunk compression failures

---

## Security

### Access Control

**Database Users**:
- `postgres` - Superuser (migrations only)
- `app_user` - Application user (read/write)
- `readonly_user` - Analytics user (read-only)

**Row-Level Security**:
```sql
-- Enable RLS on sessions table
ALTER TABLE sessions ENABLE ROW LEVEL SECURITY;

-- Policy: Users can only see their own sessions
CREATE POLICY user_sessions ON sessions
    FOR SELECT
    USING (user_id = current_setting('app.current_user_id'));
```

### Data Protection

**Encryption**:
- TLS for connections (required in production)
- Encrypted storage volumes
- Encrypted backups

**Sensitive Data**:
- API keys stored as hashed values
- PII masked in logs
- JSONB fields sanitized before export

---

## Backup and Recovery

### Backup Strategy

**Continuous Archiving**:
- WAL archiving to S3
- Point-in-time recovery (PITR)
- 30-day retention

**Logical Backups**:
- Daily pg_dump to S3
- 7-day retention
- Compressed and encrypted

**TimescaleDB Backups**:
- Chunk-level backups for efficiency
- Incremental backups for large datasets

### Recovery Procedures

**Full Recovery**:
```bash
# Restore from pg_dump
pg_restore -U postgres -d agent_observability backup.dump

# Restore from WAL archive
pg_basebackup + WAL replay
```

**Partial Recovery**:
```bash
# Restore specific session
COPY sessions FROM 'session_backup.csv';
COPY trace_events FROM 'events_backup.csv';
```

---

## Testing

### Test Coverage

The schema is tested with comprehensive unit tests in `tests/test_database_schema.py`:

**Test Categories**:
1. **Table Existence**: Verify all tables are created
2. **Column Definitions**: Check column names, types, and constraints
3. **Indexes**: Verify all required indexes exist
4. **Foreign Keys**: Test referential integrity
5. **TimescaleDB Features**: Verify hypertables, compression, retention
6. **Data Integrity**: Test insert, update, delete operations
7. **Cascade Behavior**: Test ON DELETE CASCADE

**Running Tests**:
```bash
# Start database
docker-compose up -d postgres

# Run migrations
python migrations/run_migrations.py

# Run tests
pytest tests/test_database_schema.py -v
```

---

## Troubleshooting

### Common Issues

**Issue**: TimescaleDB extension not found
```sql
-- Solution: Install TimescaleDB extension
CREATE EXTENSION IF NOT EXISTS timescaledb CASCADE;
```

**Issue**: Slow queries on trace_events
```sql
-- Solution: Check chunk pruning
EXPLAIN ANALYZE SELECT * FROM trace_events 
WHERE timestamp > NOW() - INTERVAL '1 day';

-- Verify chunks are being pruned
SELECT * FROM timescaledb_information.chunks 
WHERE hypertable_name = 'trace_events';
```

**Issue**: High storage usage
```sql
-- Solution: Check compression status
SELECT * FROM timescaledb_information.compression_settings 
WHERE hypertable_name = 'trace_events';

-- Manually compress chunks
SELECT compress_chunk(chunk_name) 
FROM timescaledb_information.chunks 
WHERE hypertable_name = 'trace_events' 
AND NOT is_compressed;
```

---

## References

- [PostgreSQL Documentation](https://www.postgresql.org/docs/)
- [TimescaleDB Documentation](https://docs.timescale.com/)
- [asyncpg Documentation](https://magicstack.github.io/asyncpg/)
- Design Document: `/specs/agent-observability-platform/design.md`
- Requirements Document: `/specs/agent-observability-platform/requirements.md`
