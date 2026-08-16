"""Validation script for database schema.

This script validates that the database schema is correctly implemented
according to the design specifications.
"""

import asyncio
import asyncpg
import sys
from typing import List
from config import settings


class SchemaValidator:
    """Validates database schema implementation."""
    
    def __init__(self, connection: asyncpg.Connection):
        self.conn = connection
        self.errors: List[str] = []
        self.warnings: List[str] = []
    
    async def validate_all(self) -> bool:
        """Run all validation checks."""
        print("\n" + "="*60)
        print("🔍 Validating Database Schema")
        print("="*60 + "\n")
        
        checks = [
            ("TimescaleDB Extension", self.check_timescaledb_extension),
            ("Sessions Table", self.check_sessions_table),
            ("Trace Events Table", self.check_trace_events_table),
            ("Tool Call Metrics Table", self.check_tool_call_metrics_table),
            ("Alert Rules Table", self.check_alert_rules_table),
            ("Alert History Table", self.check_alert_history_table),
            ("Indexes", self.check_indexes),
            ("Foreign Keys", self.check_foreign_keys),
            ("Hypertables", self.check_hypertables),
            ("Compression Policies", self.check_compression_policies),
            ("Retention Policies", self.check_retention_policies),
        ]
        
        for check_name, check_func in checks:
            print(f"Checking {check_name}...", end=" ")
            try:
                await check_func()
                print("✅")
            except Exception as e:
                print(f"❌ {e}")
                self.errors.append(f"{check_name}: {e}")
        
        # Print summary
        print("\n" + "="*60)
        if self.errors:
            print(f"❌ Validation Failed: {len(self.errors)} error(s)")
            for error in self.errors:
                print(f"  - {error}")
        else:
            print("✅ All Validation Checks Passed!")
        
        if self.warnings:
            print(f"\n⚠️  {len(self.warnings)} warning(s):")
            for warning in self.warnings:
                print(f"  - {warning}")
        
        print("="*60 + "\n")
        
        return len(self.errors) == 0
    
    async def check_timescaledb_extension(self):
        """Check that TimescaleDB extension is installed."""
        result = await self.conn.fetchval(
            "SELECT EXISTS (SELECT FROM pg_extension WHERE extname = 'timescaledb')"
        )
        if not result:
            raise Exception("TimescaleDB extension not installed")
    
    async def check_sessions_table(self):
        """Check sessions table structure."""
        # Check table exists
        exists = await self.conn.fetchval(
            "SELECT EXISTS (SELECT FROM information_schema.tables WHERE table_name = 'sessions')"
        )
        if not exists:
            raise Exception("sessions table does not exist")
        
        # Check required columns
        columns = await self.conn.fetch(
            """
            SELECT column_name, data_type, is_nullable
            FROM information_schema.columns
            WHERE table_name = 'sessions'
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
        
        missing = [col for col in required_columns if col not in column_names]
        if missing:
            raise Exception(f"Missing columns: {', '.join(missing)}")
    
    async def check_trace_events_table(self):
        """Check trace_events table structure."""
        # Check table exists
        exists = await self.conn.fetchval(
            "SELECT EXISTS (SELECT FROM information_schema.tables WHERE table_name = 'trace_events')"
        )
        if not exists:
            raise Exception("trace_events table does not exist")
        
        # Check required columns
        columns = await self.conn.fetch(
            """
            SELECT column_name, data_type
            FROM information_schema.columns
            WHERE table_name = 'trace_events'
            """
        )
        column_names = [col['column_name'] for col in columns]
        
        required_columns = [
            'event_id', 'session_id', 'event_type', 'timestamp',
            'sequence_number', 'parent_event_id', 'duration_ms',
            'status', 'event_data', 'error_type', 'error_message'
        ]
        
        missing = [col for col in required_columns if col not in column_names]
        if missing:
            raise Exception(f"Missing columns: {', '.join(missing)}")
    
    async def check_tool_call_metrics_table(self):
        """Check tool_call_metrics table structure."""
        # Check table exists
        exists = await self.conn.fetchval(
            "SELECT EXISTS (SELECT FROM information_schema.tables WHERE table_name = 'tool_call_metrics')"
        )
        if not exists:
            raise Exception("tool_call_metrics table does not exist")
        
        # Check required columns
        columns = await self.conn.fetch(
            """
            SELECT column_name, data_type
            FROM information_schema.columns
            WHERE table_name = 'tool_call_metrics'
            """
        )
        column_names = [col['column_name'] for col in columns]
        
        required_columns = [
            'timestamp', 'tool_name', 'success_count', 'failure_count',
            'total_duration_ms', 'avg_duration_ms', 'p95_duration_ms'
        ]
        
        missing = [col for col in required_columns if col not in column_names]
        if missing:
            raise Exception(f"Missing columns: {', '.join(missing)}")
    
    async def check_alert_rules_table(self):
        """Check alert_rules table structure."""
        # Check table exists
        exists = await self.conn.fetchval(
            "SELECT EXISTS (SELECT FROM information_schema.tables WHERE table_name = 'alert_rules')"
        )
        if not exists:
            raise Exception("alert_rules table does not exist")
        
        # Check required columns
        columns = await self.conn.fetch(
            """
            SELECT column_name, data_type
            FROM information_schema.columns
            WHERE table_name = 'alert_rules'
            """
        )
        column_names = [col['column_name'] for col in columns]
        
        required_columns = [
            'rule_id', 'user_id', 'name', 'description', 'enabled',
            'condition_type', 'condition_config', 'notification_channels',
            'severity', 'suppression_window_minutes', 'created_at', 'updated_at'
        ]
        
        missing = [col for col in required_columns if col not in column_names]
        if missing:
            raise Exception(f"Missing columns: {', '.join(missing)}")
    
    async def check_alert_history_table(self):
        """Check alert_history table structure."""
        # Check table exists
        exists = await self.conn.fetchval(
            "SELECT EXISTS (SELECT FROM information_schema.tables WHERE table_name = 'alert_history')"
        )
        if not exists:
            raise Exception("alert_history table does not exist")
        
        # Check required columns
        columns = await self.conn.fetch(
            """
            SELECT column_name, data_type
            FROM information_schema.columns
            WHERE table_name = 'alert_history'
            """
        )
        column_names = [col['column_name'] for col in columns]
        
        required_columns = [
            'alert_id', 'rule_id', 'session_id', 'triggered_at',
            'resolved_at', 'status', 'message', 'context'
        ]
        
        missing = [col for col in required_columns if col not in column_names]
        if missing:
            raise Exception(f"Missing columns: {', '.join(missing)}")
    
    async def check_indexes(self):
        """Check that all required indexes exist."""
        required_indexes = {
            'sessions': [
                'idx_sessions_user_created',
                'idx_sessions_status',
                'idx_sessions_coordination',
                'idx_sessions_tags',
                'idx_sessions_created_at'
            ],
            'trace_events': [
                'idx_trace_events_session',
                'idx_trace_events_type',
                'idx_trace_events_parent',
                'idx_trace_events_data'
            ],
            'alert_rules': [
                'idx_alert_rules_user',
                'idx_alert_rules_enabled'
            ],
            'alert_history': [
                'idx_alert_history_rule',
                'idx_alert_history_session',
                'idx_alert_history_triggered'
            ]
        }
        
        missing_indexes = []
        
        for table, indexes in required_indexes.items():
            existing = await self.conn.fetch(
                "SELECT indexname FROM pg_indexes WHERE tablename = $1",
                table
            )
            existing_names = [idx['indexname'] for idx in existing]
            
            for idx in indexes:
                if idx not in existing_names:
                    missing_indexes.append(f"{table}.{idx}")
        
        if missing_indexes:
            raise Exception(f"Missing indexes: {', '.join(missing_indexes)}")
    
    async def check_foreign_keys(self):
        """Check that all required foreign keys exist."""
        # Check trace_events -> sessions
        fk_exists = await self.conn.fetchval(
            """
            SELECT EXISTS (
                SELECT FROM pg_constraint
                WHERE conrelid = 'trace_events'::regclass
                AND contype = 'f'
                AND confrelid = 'sessions'::regclass
            )
            """
        )
        if not fk_exists:
            raise Exception("Foreign key trace_events -> sessions missing")
        
        # Check alert_history -> alert_rules
        fk_exists = await self.conn.fetchval(
            """
            SELECT EXISTS (
                SELECT FROM pg_constraint
                WHERE conrelid = 'alert_history'::regclass
                AND contype = 'f'
                AND confrelid = 'alert_rules'::regclass
            )
            """
        )
        if not fk_exists:
            raise Exception("Foreign key alert_history -> alert_rules missing")
        
        # Check alert_history -> sessions
        fk_exists = await self.conn.fetchval(
            """
            SELECT EXISTS (
                SELECT FROM pg_constraint
                WHERE conrelid = 'alert_history'::regclass
                AND contype = 'f'
                AND confrelid = 'sessions'::regclass
            )
            """
        )
        if not fk_exists:
            raise Exception("Foreign key alert_history -> sessions missing")
    
    async def check_hypertables(self):
        """Check that TimescaleDB hypertables are configured."""
        hypertables = await self.conn.fetch(
            "SELECT hypertable_name FROM timescaledb_information.hypertables"
        )
        hypertable_names = [ht['hypertable_name'] for ht in hypertables]
        
        required_hypertables = ['trace_events', 'tool_call_metrics']
        
        missing = [ht for ht in required_hypertables if ht not in hypertable_names]
        if missing:
            raise Exception(f"Missing hypertables: {', '.join(missing)}")
    
    async def check_compression_policies(self):
        """Check that compression policies are configured."""
        policies = await self.conn.fetch(
            """
            SELECT hypertable_name
            FROM timescaledb_information.jobs
            WHERE proc_name = 'policy_compression'
            """
        )
        policy_tables = [p['hypertable_name'] for p in policies]
        
        required_policies = ['trace_events', 'tool_call_metrics']
        
        missing = [ht for ht in required_policies if ht not in policy_tables]
        if missing:
            self.warnings.append(f"Missing compression policies: {', '.join(missing)}")
    
    async def check_retention_policies(self):
        """Check that retention policies are configured."""
        policies = await self.conn.fetch(
            """
            SELECT hypertable_name
            FROM timescaledb_information.jobs
            WHERE proc_name = 'policy_retention'
            """
        )
        policy_tables = [p['hypertable_name'] for p in policies]
        
        required_policies = ['trace_events', 'tool_call_metrics']
        
        missing = [ht for ht in required_policies if ht not in policy_tables]
        if missing:
            self.warnings.append(f"Missing retention policies: {', '.join(missing)}")


async def main():
    """Main validation function."""
    print(f"Connecting to database: {settings.DATABASE_URL}")
    
    try:
        conn = await asyncpg.connect(settings.DATABASE_URL)
    except Exception as e:
        print(f"\n❌ Failed to connect to database: {e}")
        print("\nMake sure:")
        print("  1. PostgreSQL is running (docker-compose up -d postgres)")
        print("  2. Database URL is correct in .env file")
        print("  3. Migrations have been run (python migrations/run_migrations.py)")
        sys.exit(1)
    
    try:
        validator = SchemaValidator(conn)
        success = await validator.validate_all()
        
        if success:
            print("✅ Database schema validation successful!")
            sys.exit(0)
        else:
            print("❌ Database schema validation failed!")
            sys.exit(1)
    
    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(main())
