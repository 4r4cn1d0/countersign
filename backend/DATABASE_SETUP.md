# Database Setup Guide

This guide walks you through setting up the PostgreSQL + TimescaleDB database for the Agent Memory Observatory.

## Prerequisites

- Docker and Docker Compose (for local development)
- Python 3.11+ with virtual environment
- PostgreSQL client tools (optional, for manual inspection)

## Quick Start

### 1. Start the Database

```bash
# Start PostgreSQL with TimescaleDB
docker-compose up -d postgres

# Verify it's running
docker-compose ps postgres

# Check logs
docker-compose logs -f postgres
```

The database will be available at:
- **Host**: localhost
- **Port**: 5432
- **Database**: agent_observability
- **User**: postgres
- **Password**: postgres

### 2. Run Migrations

```bash
# Activate virtual environment
source venv/bin/activate

# Run migrations
python migrations/run_migrations.py
```

Expected output:
```
============================================================
🔄 Running Database Migrations
============================================================

Running migration: 001_initial_schema.sql
✅ Migration 001_initial_schema.sql completed successfully

✅ All migrations completed successfully!
```

### 3. Validate Schema

```bash
# Run validation script
python validate_database_schema.py
```

Expected output:
```
============================================================
🔍 Validating Database Schema
============================================================

Checking TimescaleDB Extension... ✅
Checking Sessions Table... ✅
Checking Trace Events Table... ✅
Checking Tool Call Metrics Table... ✅
Checking Alert Rules Table... ✅
Checking Alert History Table... ✅
Checking Indexes... ✅
Checking Foreign Keys... ✅
Checking Hypertables... ✅
Checking Compression Policies... ✅
Checking Retention Policies... ✅

============================================================
✅ All Validation Checks Passed!
============================================================
```

### 4. Run Tests

```bash
# Run all database tests
pytest tests/test_database_schema.py -v

# Run specific test class
pytest tests/test_database_schema.py::TestSessionsTable -v

# Run with coverage
pytest tests/test_database_schema.py --cov=. --cov-report=html
```

## Manual Database Inspection

### Connect to Database

```bash
# Using psql
psql -U postgres -h localhost -d agent_observability

# Using Docker
docker-compose exec postgres psql -U postgres -d agent_observability
```

### Useful Commands

```sql
-- List all tables
\dt

-- Describe a table
\d sessions
\d trace_events

-- List all indexes
\di

-- List all foreign keys
SELECT
    tc.table_name, 
    kcu.column_name, 
    ccu.table_name AS foreign_table_name,
    ccu.column_name AS foreign_column_name 
FROM information_schema.table_constraints AS tc 
JOIN information_schema.key_column_usage AS kcu
  ON tc.constraint_name = kcu.constraint_name
JOIN information_schema.constraint_column_usage AS ccu
  ON ccu.constraint_name = tc.constraint_name
WHERE tc.constraint_type = 'FOREIGN KEY';

-- Check TimescaleDB hypertables
SELECT * FROM timescaledb_information.hypertables;

-- Check compression policies
SELECT * FROM timescaledb_information.jobs 
WHERE proc_name = 'policy_compression';

-- Check retention policies
SELECT * FROM timescaledb_information.jobs 
WHERE proc_name = 'policy_retention';

-- Check chunks
SELECT * FROM timescaledb_information.chunks;

-- Check database size
SELECT pg_size_pretty(pg_database_size('agent_observability'));

-- Check table sizes
SELECT 
    schemaname,
    tablename,
    pg_size_pretty(pg_total_relation_size(schemaname||'.'||tablename)) AS size
FROM pg_tables
WHERE schemaname = 'public'
ORDER BY pg_total_relation_size(schemaname||'.'||tablename) DESC;
```

## Configuration

### Environment Variables

Create a `.env` file in the `backend/` directory:

```bash
# Database
DATABASE_URL=postgresql://postgres:postgres@localhost:5432/agent_observability
DB_POOL_SIZE=20
DB_MAX_OVERFLOW=10

# Retention
HOT_STORAGE_DAYS=30
WARM_STORAGE_DAYS=90
ARCHIVE_ENABLED=true
```

### Docker Compose Configuration

The `docker-compose.yml` file configures:
- PostgreSQL 15 with TimescaleDB extension
- Persistent volume for data
- Health checks
- Port mapping (5432:5432)

To customize:

```yaml
services:
  postgres:
    image: timescale/timescaledb:latest-pg15
    environment:
      POSTGRES_DB: agent_observability
      POSTGRES_USER: postgres
      POSTGRES_PASSWORD: postgres  # Change in production!
    ports:
      - "5432:5432"
    volumes:
      - postgres_data:/var/lib/postgresql/data
```

## Troubleshooting

### Database Won't Start

**Issue**: `docker-compose up -d postgres` fails

**Solutions**:
```bash
# Check if port 5432 is already in use
lsof -i :5432

# Stop any existing PostgreSQL instances
brew services stop postgresql  # macOS
sudo systemctl stop postgresql  # Linux

# Remove old volumes and restart
docker-compose down -v
docker-compose up -d postgres
```

### Migration Fails

**Issue**: `python migrations/run_migrations.py` fails

**Solutions**:
```bash
# Check database connection
psql -U postgres -h localhost -d agent_observability -c "SELECT version();"

# Check if TimescaleDB extension is available
psql -U postgres -h localhost -d agent_observability -c "SELECT * FROM pg_available_extensions WHERE name = 'timescaledb';"

# Manually run migration
psql -U postgres -h localhost -d agent_observability -f migrations/001_initial_schema.sql
```

### Connection Refused

**Issue**: `asyncpg.exceptions.ConnectionRefusedError`

**Solutions**:
```bash
# Check if PostgreSQL is running
docker-compose ps postgres

# Check PostgreSQL logs
docker-compose logs postgres

# Restart PostgreSQL
docker-compose restart postgres

# Wait for health check
docker-compose ps postgres  # Should show "healthy"
```

### TimescaleDB Extension Not Found

**Issue**: `ERROR: could not open extension control file`

**Solutions**:
```bash
# Use the correct Docker image
docker-compose down
# Edit docker-compose.yml to use: timescale/timescaledb:latest-pg15
docker-compose up -d postgres

# Verify TimescaleDB is available
docker-compose exec postgres psql -U postgres -d agent_observability -c "CREATE EXTENSION IF NOT EXISTS timescaledb CASCADE;"
```

### Slow Queries

**Issue**: Queries are taking too long

**Solutions**:
```sql
-- Check query execution plan
EXPLAIN ANALYZE SELECT * FROM trace_events 
WHERE session_id = 'some-uuid' 
ORDER BY sequence_number;

-- Check if indexes are being used
SELECT schemaname, tablename, indexname, idx_scan 
FROM pg_stat_user_indexes 
ORDER BY idx_scan;

-- Check for missing indexes
SELECT schemaname, tablename, attname, n_distinct, correlation
FROM pg_stats
WHERE schemaname = 'public'
ORDER BY abs(correlation) DESC;

-- Analyze tables
ANALYZE sessions;
ANALYZE trace_events;
```

### High Storage Usage

**Issue**: Database is using too much disk space

**Solutions**:
```sql
-- Check compression status
SELECT * FROM timescaledb_information.compression_settings;

-- Manually compress chunks
SELECT compress_chunk(chunk_name) 
FROM timescaledb_information.chunks 
WHERE hypertable_name = 'trace_events' 
AND NOT is_compressed;

-- Check retention policies
SELECT * FROM timescaledb_information.jobs 
WHERE proc_name = 'policy_retention';

-- Manually drop old chunks
SELECT drop_chunks('trace_events', INTERVAL '90 days');
```

## Production Deployment

### Security Hardening

1. **Change default passwords**:
```yaml
environment:
  POSTGRES_PASSWORD: ${POSTGRES_PASSWORD}  # Use secrets
```

2. **Enable SSL/TLS**:
```yaml
volumes:
  - ./certs:/var/lib/postgresql/certs
command: >
  postgres
  -c ssl=on
  -c ssl_cert_file=/var/lib/postgresql/certs/server.crt
  -c ssl_key_file=/var/lib/postgresql/certs/server.key
```

3. **Restrict network access**:
```yaml
ports:
  - "127.0.0.1:5432:5432"  # Only localhost
```

4. **Use connection pooling**:
```python
# In application code
pool = await asyncpg.create_pool(
    DATABASE_URL,
    min_size=10,
    max_size=20,
    command_timeout=60
)
```

### Performance Tuning

**PostgreSQL Configuration** (`postgresql.conf`):
```ini
# Memory
shared_buffers = 4GB
effective_cache_size = 12GB
work_mem = 64MB
maintenance_work_mem = 1GB

# Connections
max_connections = 100

# WAL
wal_buffers = 16MB
checkpoint_completion_target = 0.9

# Query Planning
random_page_cost = 1.1  # For SSD
effective_io_concurrency = 200

# TimescaleDB
timescaledb.max_background_workers = 8
```

**Apply configuration**:
```bash
# Edit postgresql.conf in Docker volume
docker-compose exec postgres vi /var/lib/postgresql/data/postgresql.conf

# Restart PostgreSQL
docker-compose restart postgres
```

### Backup Strategy

**Automated Backups**:
```bash
#!/bin/bash
# backup.sh

BACKUP_DIR="/backups"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
BACKUP_FILE="$BACKUP_DIR/agent_observability_$TIMESTAMP.dump"

# Create backup
docker-compose exec -T postgres pg_dump -U postgres -Fc agent_observability > "$BACKUP_FILE"

# Compress
gzip "$BACKUP_FILE"

# Upload to S3 (optional)
aws s3 cp "$BACKUP_FILE.gz" s3://my-backups/database/

# Clean up old backups (keep last 7 days)
find "$BACKUP_DIR" -name "*.dump.gz" -mtime +7 -delete
```

**Restore from Backup**:
```bash
# Restore from dump
gunzip -c backup.dump.gz | docker-compose exec -T postgres pg_restore -U postgres -d agent_observability
```

### Monitoring

**Key Metrics to Monitor**:
- Connection count
- Query execution time
- Cache hit ratio
- Disk usage
- Replication lag (if using replicas)
- Chunk compression ratio

**Monitoring Queries**:
```sql
-- Active connections
SELECT count(*) FROM pg_stat_activity;

-- Slow queries
SELECT pid, now() - query_start AS duration, query 
FROM pg_stat_activity 
WHERE state = 'active' 
AND now() - query_start > interval '5 seconds';

-- Cache hit ratio
SELECT 
    sum(heap_blks_read) as heap_read,
    sum(heap_blks_hit) as heap_hit,
    sum(heap_blks_hit) / (sum(heap_blks_hit) + sum(heap_blks_read)) as ratio
FROM pg_statio_user_tables;

-- Database size
SELECT pg_size_pretty(pg_database_size('agent_observability'));
```

## Additional Resources

- [PostgreSQL Documentation](https://www.postgresql.org/docs/)
- [TimescaleDB Documentation](https://docs.timescale.com/)
- [asyncpg Documentation](https://magicstack.github.io/asyncpg/)
- [Database Schema Documentation](./DATABASE_SCHEMA.md)
- [Task 1.2 Summary](./TASK_1.2_SUMMARY.md)
