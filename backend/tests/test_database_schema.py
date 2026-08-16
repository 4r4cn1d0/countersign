"""Tests for database schema implementation.

This module tests the PostgreSQL + TimescaleDB schema including:
- Table creation and structure
- Indexes for query optimization
- TimescaleDB hypertables
- Constraints and relationships
- Retention policies
"""

import pytest
import asyncpg
import os

pytestmark = pytest.mark.integration


# Database connection URL for testing
TEST_DATABASE_URL = os.getenv(
    "TEST_DATABASE_URL",
    "postgresql://postgres:postgres@localhost:5432/agent_observability"
)


@pytest.fixture
async def db_connection():
    """Create a database connection for testing."""
    conn = await asyncpg.connect(TEST_DATABASE_URL)
    yield conn
    await conn.close()


class TestSessionsTable:
    """Tests for the sessions table."""
    
    @pytest.mark.asyncio
    async def test_sessions_table_exists(self, db_connection):
        """Test that sessions table exists."""
        result = await db_connection.fetchval(
            """
            SELECT EXISTS (
                SELECT FROM information_schema.tables 
                WHERE table_name = 'sessions'
            )
            """
        )
        assert result is True, "sessions table should exist"
    
    @pytest.mark.asyncio
    async def test_sessions_columns(self, db_connection):
        """Test that sessions table has all required columns."""
        columns = await db_connection.fetch(
            """
            SELECT column_name, data_type, is_nullable
            FROM information_schema.columns
            WHERE table_name = 'sessions'
            ORDER BY ordinal_position
            """
        )
        
        column_names = [col['column_name'] for col in columns]
        
        required_columns = [
            'session_id', 'user_id', 'agent_type', 'goal', 'status',
            'created_at', 'completed_at', 'duration_ms',
            'total_reasoning_steps', 'total_tool_calls', 'total_memory_accesses',
            'total_tokens', 'total_cost', 'error_count',
            'metadata', 'tags', 'coordination_id'
        ]
        
        for col in required_columns:
            assert col in column_names, f"Column {col} should exist in sessions table"
    
    @pytest.mark.asyncio
    async def test_sessions_primary_key(self, db_connection):
        """Test that sessions table has correct primary key."""
        result = await db_connection.fetch(
            """
            SELECT a.attname
            FROM pg_index i
            JOIN pg_attribute a ON a.attrelid = i.indrelid AND a.attnum = ANY(i.indkey)
            WHERE i.indrelid = 'sessions'::regclass AND i.indisprimary
            """
        )
        
        pk_columns = [row['attname'] for row in result]
        assert pk_columns == ['session_id'], "Primary key should be session_id"
    
    @pytest.mark.asyncio
    async def test_sessions_indexes(self, db_connection):
        """Test that sessions table has required indexes."""
        indexes = await db_connection.fetch(
            """
            SELECT indexname
            FROM pg_indexes
            WHERE tablename = 'sessions'
            """
        )
        
        index_names = [idx['indexname'] for idx in indexes]
        
        required_indexes = [
            'idx_sessions_user_created',
            'idx_sessions_status',
            'idx_sessions_coordination',
            'idx_sessions_tags',
            'idx_sessions_created_at'
        ]
        
        for idx in required_indexes:
            assert idx in index_names, f"Index {idx} should exist on sessions table"
    
    @pytest.mark.asyncio
    async def test_sessions_status_constraint(self, db_connection):
        """Test that sessions table has status check constraint."""
        constraints = await db_connection.fetch(
            """
            SELECT conname, pg_get_constraintdef(oid) as definition
            FROM pg_constraint
            WHERE conrelid = 'sessions'::regclass AND contype = 'c'
            """
        )
        
        # Check if there's a constraint on status column
        status_constraint_exists = any(
            'status' in constraint['definition'].lower()
            for constraint in constraints
        )
        
        assert status_constraint_exists, "Status column should have a check constraint"


class TestTraceEventsTable:
    """Tests for the trace_events table (TimescaleDB hypertable)."""
    
    @pytest.mark.asyncio
    async def test_trace_events_table_exists(self, db_connection):
        """Test that trace_events table exists."""
        result = await db_connection.fetchval(
            """
            SELECT EXISTS (
                SELECT FROM information_schema.tables 
                WHERE table_name = 'trace_events'
            )
            """
        )
        assert result is True, "trace_events table should exist"
    
    @pytest.mark.asyncio
    async def test_trace_events_is_hypertable(self, db_connection):
        """Test that trace_events is a TimescaleDB hypertable."""
        result = await db_connection.fetchval(
            """
            SELECT EXISTS (
                SELECT FROM timescaledb_information.hypertables
                WHERE hypertable_name = 'trace_events'
            )
            """
        )
        assert result is True, "trace_events should be a TimescaleDB hypertable"
    
    @pytest.mark.asyncio
    async def test_trace_events_columns(self, db_connection):
        """Test that trace_events table has all required columns."""
        columns = await db_connection.fetch(
            """
            SELECT column_name, data_type
            FROM information_schema.columns
            WHERE table_name = 'trace_events'
            ORDER BY ordinal_position
            """
        )
        
        column_names = [col['column_name'] for col in columns]
        
        required_columns = [
            'event_id', 'session_id', 'event_type', 'timestamp',
            'sequence_number', 'parent_event_id', 'duration_ms',
            'status', 'event_data', 'error_type', 'error_message'
        ]
        
        for col in required_columns:
            assert col in column_names, f"Column {col} should exist in trace_events table"
    
    @pytest.mark.asyncio
    async def test_trace_events_indexes(self, db_connection):
        """Test that trace_events table has required indexes."""
        indexes = await db_connection.fetch(
            """
            SELECT indexname
            FROM pg_indexes
            WHERE tablename = 'trace_events'
            """
        )
        
        index_names = [idx['indexname'] for idx in indexes]
        
        required_indexes = [
            'idx_trace_events_session',
            'idx_trace_events_type',
            'idx_trace_events_parent',
            'idx_trace_events_data'
        ]
        
        for idx in required_indexes:
            assert idx in index_names, f"Index {idx} should exist on trace_events table"
    
    @pytest.mark.asyncio
    async def test_trace_events_foreign_key(self, db_connection):
        """Test that trace_events has foreign key to sessions."""
        constraints = await db_connection.fetch(
            """
            SELECT conname, pg_get_constraintdef(oid) as definition
            FROM pg_constraint
            WHERE conrelid = 'trace_events'::regclass AND contype = 'f'
            """
        )
        
        # Check if there's a foreign key to sessions
        fk_to_sessions = any(
            'sessions' in constraint['definition'].lower()
            for constraint in constraints
        )
        
        assert fk_to_sessions, "trace_events should have foreign key to sessions"
    
    @pytest.mark.asyncio
    async def test_trace_events_compression_policy(self, db_connection):
        """Test that trace_events has compression policy."""
        result = await db_connection.fetchval(
            """
            SELECT EXISTS (
                SELECT FROM timescaledb_information.jobs
                WHERE hypertable_name = 'trace_events'
                AND proc_name = 'policy_compression'
            )
            """
        )
        assert result is True, "trace_events should have compression policy"
    
    @pytest.mark.asyncio
    async def test_trace_events_retention_policy(self, db_connection):
        """Test that trace_events has retention policy."""
        result = await db_connection.fetchval(
            """
            SELECT EXISTS (
                SELECT FROM timescaledb_information.jobs
                WHERE hypertable_name = 'trace_events'
                AND proc_name = 'policy_retention'
            )
            """
        )
        assert result is True, "trace_events should have retention policy"


class TestToolCallMetricsTable:
    """Tests for the tool_call_metrics table (TimescaleDB hypertable)."""
    
    @pytest.mark.asyncio
    async def test_tool_call_metrics_table_exists(self, db_connection):
        """Test that tool_call_metrics table exists."""
        result = await db_connection.fetchval(
            """
            SELECT EXISTS (
                SELECT FROM information_schema.tables 
                WHERE table_name = 'tool_call_metrics'
            )
            """
        )
        assert result is True, "tool_call_metrics table should exist"
    
    @pytest.mark.asyncio
    async def test_tool_call_metrics_is_hypertable(self, db_connection):
        """Test that tool_call_metrics is a TimescaleDB hypertable."""
        result = await db_connection.fetchval(
            """
            SELECT EXISTS (
                SELECT FROM timescaledb_information.hypertables
                WHERE hypertable_name = 'tool_call_metrics'
            )
            """
        )
        assert result is True, "tool_call_metrics should be a TimescaleDB hypertable"
    
    @pytest.mark.asyncio
    async def test_tool_call_metrics_columns(self, db_connection):
        """Test that tool_call_metrics table has all required columns."""
        columns = await db_connection.fetch(
            """
            SELECT column_name, data_type
            FROM information_schema.columns
            WHERE table_name = 'tool_call_metrics'
            ORDER BY ordinal_position
            """
        )
        
        column_names = [col['column_name'] for col in columns]
        
        required_columns = [
            'timestamp', 'tool_name', 'success_count', 'failure_count',
            'total_duration_ms', 'avg_duration_ms', 'p95_duration_ms'
        ]
        
        for col in required_columns:
            assert col in column_names, f"Column {col} should exist in tool_call_metrics table"
    
    @pytest.mark.asyncio
    async def test_tool_call_metrics_compression_policy(self, db_connection):
        """Test that tool_call_metrics has compression policy."""
        result = await db_connection.fetchval(
            """
            SELECT EXISTS (
                SELECT FROM timescaledb_information.jobs
                WHERE hypertable_name = 'tool_call_metrics'
                AND proc_name = 'policy_compression'
            )
            """
        )
        assert result is True, "tool_call_metrics should have compression policy"
    
    @pytest.mark.asyncio
    async def test_tool_call_metrics_retention_policy(self, db_connection):
        """Test that tool_call_metrics has retention policy."""
        result = await db_connection.fetchval(
            """
            SELECT EXISTS (
                SELECT FROM timescaledb_information.jobs
                WHERE hypertable_name = 'tool_call_metrics'
                AND proc_name = 'policy_retention'
            )
            """
        )
        assert result is True, "tool_call_metrics should have retention policy"


class TestAlertRulesTable:
    """Tests for the alert_rules table."""
    
    @pytest.mark.asyncio
    async def test_alert_rules_table_exists(self, db_connection):
        """Test that alert_rules table exists."""
        result = await db_connection.fetchval(
            """
            SELECT EXISTS (
                SELECT FROM information_schema.tables 
                WHERE table_name = 'alert_rules'
            )
            """
        )
        assert result is True, "alert_rules table should exist"
    
    @pytest.mark.asyncio
    async def test_alert_rules_columns(self, db_connection):
        """Test that alert_rules table has all required columns."""
        columns = await db_connection.fetch(
            """
            SELECT column_name, data_type
            FROM information_schema.columns
            WHERE table_name = 'alert_rules'
            ORDER BY ordinal_position
            """
        )
        
        column_names = [col['column_name'] for col in columns]
        
        required_columns = [
            'rule_id', 'user_id', 'name', 'description', 'enabled',
            'condition_type', 'condition_config', 'notification_channels',
            'severity', 'suppression_window_minutes', 'created_at', 'updated_at'
        ]
        
        for col in required_columns:
            assert col in column_names, f"Column {col} should exist in alert_rules table"
    
    @pytest.mark.asyncio
    async def test_alert_rules_indexes(self, db_connection):
        """Test that alert_rules table has required indexes."""
        indexes = await db_connection.fetch(
            """
            SELECT indexname
            FROM pg_indexes
            WHERE tablename = 'alert_rules'
            """
        )
        
        index_names = [idx['indexname'] for idx in indexes]
        
        required_indexes = [
            'idx_alert_rules_user',
            'idx_alert_rules_enabled'
        ]
        
        for idx in required_indexes:
            assert idx in index_names, f"Index {idx} should exist on alert_rules table"


class TestAlertHistoryTable:
    """Tests for the alert_history table."""
    
    @pytest.mark.asyncio
    async def test_alert_history_table_exists(self, db_connection):
        """Test that alert_history table exists."""
        result = await db_connection.fetchval(
            """
            SELECT EXISTS (
                SELECT FROM information_schema.tables 
                WHERE table_name = 'alert_history'
            )
            """
        )
        assert result is True, "alert_history table should exist"
    
    @pytest.mark.asyncio
    async def test_alert_history_columns(self, db_connection):
        """Test that alert_history table has all required columns."""
        columns = await db_connection.fetch(
            """
            SELECT column_name, data_type
            FROM information_schema.columns
            WHERE table_name = 'alert_history'
            ORDER BY ordinal_position
            """
        )
        
        column_names = [col['column_name'] for col in columns]
        
        required_columns = [
            'alert_id', 'rule_id', 'session_id', 'triggered_at',
            'resolved_at', 'status', 'message', 'context'
        ]
        
        for col in required_columns:
            assert col in column_names, f"Column {col} should exist in alert_history table"
    
    @pytest.mark.asyncio
    async def test_alert_history_indexes(self, db_connection):
        """Test that alert_history table has required indexes."""
        indexes = await db_connection.fetch(
            """
            SELECT indexname
            FROM pg_indexes
            WHERE tablename = 'alert_history'
            """
        )
        
        index_names = [idx['indexname'] for idx in indexes]
        
        required_indexes = [
            'idx_alert_history_rule',
            'idx_alert_history_session',
            'idx_alert_history_triggered'
        ]
        
        for idx in required_indexes:
            assert idx in index_names, f"Index {idx} should exist on alert_history table"
    
    @pytest.mark.asyncio
    async def test_alert_history_foreign_keys(self, db_connection):
        """Test that alert_history has foreign keys."""
        constraints = await db_connection.fetch(
            """
            SELECT conname, pg_get_constraintdef(oid) as definition
            FROM pg_constraint
            WHERE conrelid = 'alert_history'::regclass AND contype = 'f'
            """
        )
        
        # Check if there are foreign keys to alert_rules and sessions
        fk_to_alert_rules = any(
            'alert_rules' in constraint['definition'].lower()
            for constraint in constraints
        )
        fk_to_sessions = any(
            'sessions' in constraint['definition'].lower()
            for constraint in constraints
        )
        
        assert fk_to_alert_rules, "alert_history should have foreign key to alert_rules"
        assert fk_to_sessions, "alert_history should have foreign key to sessions"


class TestTimescaleDBExtension:
    """Tests for TimescaleDB extension."""
    
    @pytest.mark.asyncio
    async def test_timescaledb_extension_installed(self, db_connection):
        """Test that TimescaleDB extension is installed."""
        result = await db_connection.fetchval(
            """
            SELECT EXISTS (
                SELECT FROM pg_extension
                WHERE extname = 'timescaledb'
            )
            """
        )
        assert result is True, "TimescaleDB extension should be installed"
    
    @pytest.mark.asyncio
    async def test_hypertables_exist(self, db_connection):
        """Test that expected hypertables exist."""
        hypertables = await db_connection.fetch(
            """
            SELECT hypertable_name
            FROM timescaledb_information.hypertables
            """
        )
        
        hypertable_names = [ht['hypertable_name'] for ht in hypertables]
        
        expected_hypertables = ['trace_events', 'tool_call_metrics']
        
        for ht in expected_hypertables:
            assert ht in hypertable_names, f"Hypertable {ht} should exist"


class TestDataIntegrity:
    """Tests for data integrity and relationships."""
    
    @pytest.mark.asyncio
    async def test_insert_and_query_session(self, db_connection):
        """Test inserting and querying a session."""
        import uuid
        from datetime import datetime
        
        session_id = uuid.uuid4()
        
        # Insert a test session
        await db_connection.execute(
            """
            INSERT INTO sessions (
                session_id, user_id, agent_type, goal, status, created_at
            ) VALUES ($1, $2, $3, $4, $5, $6)
            """,
            session_id, 'test_user', 'langchain', 'Test goal', 'running', datetime.now()
        )
        
        # Query the session
        result = await db_connection.fetchrow(
            "SELECT * FROM sessions WHERE session_id = $1",
            session_id
        )
        
        assert result is not None, "Session should be retrievable"
        assert result['user_id'] == 'test_user'
        assert result['agent_type'] == 'langchain'
        assert result['goal'] == 'Test goal'
        assert result['status'] == 'running'
        
        # Clean up
        await db_connection.execute(
            "DELETE FROM sessions WHERE session_id = $1",
            session_id
        )
    
    @pytest.mark.asyncio
    async def test_insert_trace_event_with_session(self, db_connection):
        """Test inserting a trace event linked to a session."""
        import uuid
        from datetime import datetime
        
        session_id = uuid.uuid4()
        event_id = uuid.uuid4()
        
        # Insert a test session
        await db_connection.execute(
            """
            INSERT INTO sessions (
                session_id, user_id, agent_type, goal, status, created_at
            ) VALUES ($1, $2, $3, $4, $5, $6)
            """,
            session_id, 'test_user', 'langchain', 'Test goal', 'running', datetime.now()
        )
        
        # Insert a trace event
        await db_connection.execute(
            """
            INSERT INTO trace_events (
                event_id, session_id, event_type, timestamp, sequence_number, event_data
            ) VALUES ($1, $2, $3, $4, $5, $6)
            """,
            event_id, session_id, 'reasoning_step', datetime.now(), 1, '{"test": "data"}'
        )
        
        # Query the trace event
        result = await db_connection.fetchrow(
            "SELECT * FROM trace_events WHERE event_id = $1",
            event_id
        )
        
        assert result is not None, "Trace event should be retrievable"
        assert result['session_id'] == session_id
        assert result['event_type'] == 'reasoning_step'
        
        # Clean up
        await db_connection.execute(
            "DELETE FROM trace_events WHERE event_id = $1",
            event_id
        )
        await db_connection.execute(
            "DELETE FROM sessions WHERE session_id = $1",
            session_id
        )
    
    @pytest.mark.asyncio
    async def test_cascade_delete_session(self, db_connection):
        """Test that deleting a session cascades to trace events."""
        import uuid
        from datetime import datetime
        
        session_id = uuid.uuid4()
        event_id = uuid.uuid4()
        
        # Insert a test session
        await db_connection.execute(
            """
            INSERT INTO sessions (
                session_id, user_id, agent_type, goal, status, created_at
            ) VALUES ($1, $2, $3, $4, $5, $6)
            """,
            session_id, 'test_user', 'langchain', 'Test goal', 'running', datetime.now()
        )
        
        # Insert a trace event
        await db_connection.execute(
            """
            INSERT INTO trace_events (
                event_id, session_id, event_type, timestamp, sequence_number, event_data
            ) VALUES ($1, $2, $3, $4, $5, $6)
            """,
            event_id, session_id, 'reasoning_step', datetime.now(), 1, '{"test": "data"}'
        )
        
        # Delete the session
        await db_connection.execute(
            "DELETE FROM sessions WHERE session_id = $1",
            session_id
        )
        
        # Verify trace event is also deleted (cascade)
        result = await db_connection.fetchval(
            "SELECT COUNT(*) FROM trace_events WHERE event_id = $1",
            event_id
        )
        
        assert result == 0, "Trace event should be deleted when session is deleted (cascade)"
