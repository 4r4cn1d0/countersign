"""Database migration runner."""

import asyncio
import asyncpg
from pathlib import Path
import sys

sys.path.append(str(Path(__file__).resolve().parents[1]))
from config import settings


async def run_migration(conn: asyncpg.Connection, migration_file: Path):
    """Run a single migration file."""
    print(f"Running migration: {migration_file.name}")
    
    sql = migration_file.read_text()
    
    try:
        await conn.execute(sql)
        print(f"✅ Migration {migration_file.name} completed successfully")
    except Exception as e:
        print(f"❌ Migration {migration_file.name} failed: {e}")
        raise


async def run_all_migrations():
    """Run all migration files in order."""
    print("\n" + "="*60)
    print("🔄 Running Database Migrations")
    print("="*60 + "\n")
    
    # Connect to database
    conn = await asyncpg.connect(settings.DATABASE_URL)
    
    try:
        # Get all migration files
        migrations_dir = Path(__file__).parent
        migration_files = sorted(migrations_dir.glob("*.sql"))
        
        if not migration_files:
            print("⚠️  No migration files found")
            return
        
        # Run each migration
        for migration_file in migration_files:
            await run_migration(conn, migration_file)
        
        print("\n✅ All migrations completed successfully!\n")
    
    except Exception as e:
        print(f"\n❌ Migration failed: {e}\n")
        raise
    
    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(run_all_migrations())
