"""
Database layer for Flaktor.

Handles all SQLite operations with a focus on reliability and helpful error messages.
"""

import sqlite3
from pathlib import Path
from typing import Callable, Optional, List, Tuple
from datetime import datetime
import json

from .models import TestRun, TestResult, TestStatus


class DatabaseError(Exception):
    """Custom exception for database operations with helpful context."""
    pass


# The schema version a fresh `initialize_schema()` produces. To evolve the
# schema, append (target_version, description, migration_fn) to _MIGRATIONS
# below - migrate() applies pending entries in order. The "latest" version
# (see latest_schema_version()) is always derived from this list, so it
# can't drift out of sync with the constant below.
CURRENT_SCHEMA_VERSION = 1

_MIGRATIONS: List[Tuple[int, str, Callable[[sqlite3.Cursor], None]]] = []


def latest_schema_version() -> int:
    """The newest schema version known to this build (baseline + migrations)."""
    return max([CURRENT_SCHEMA_VERSION] + [version for version, _, _ in _MIGRATIONS])


class Database:
    """
    SQLite database manager for Flaktor.
    
    Designed for:
    - Zero-configuration setup
    - Graceful error handling
    - Clear, actionable error messages
    - Support for millions of test results
    """
    
    def __init__(self, db_path: Path):
        """
        Initialize database connection.
        
        Args:
            db_path: Path to SQLite database file
        """
        self.db_path = db_path
        self.conn: Optional[sqlite3.Connection] = None
        
    def connect(self) -> None:
        """Establish database connection with optimizations."""
        try:
            self.conn = sqlite3.connect(
                self.db_path,
                timeout=30.0,  # Prevent immediate locks
                check_same_thread=False
            )
            # Enable WAL mode for better concurrent access
            self.conn.execute("PRAGMA journal_mode=WAL")
            # Optimize for our use case
            self.conn.execute("PRAGMA synchronous=NORMAL")
            self.conn.execute("PRAGMA cache_size=-64000")  # 64MB cache
            self.conn.row_factory = sqlite3.Row  # Access columns by name
        except sqlite3.Error as e:
            raise DatabaseError(
                f"Failed to connect to database at {self.db_path}.\n"
                f"Error: {e}\n"
                f"💡 Try running: flaktor init"
            )
    
    def close(self) -> None:
        """Safely close database connection."""
        if self.conn:
            self.conn.close()
            self.conn = None
    
    def initialize_schema(self) -> None:
        """
        Create database schema if it doesn't exist.
        
        Tables:
        - test_runs: CI/CD build/run metadata
        - test_results: Individual test case results
        - metadata: Version and configuration info
        """
        if not self.conn:
            raise DatabaseError("Database not connected. Call connect() first.")
        
        try:
            cursor = self.conn.cursor()
            
            # Metadata table - stores schema version and config
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS metadata (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            # Test runs table - represents CI/CD builds
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS test_runs (
                    run_id TEXT PRIMARY KEY,
                    timestamp TIMESTAMP NOT NULL,
                    branch TEXT,
                    commit_hash TEXT,
                    environment TEXT,
                    metadata TEXT,  -- JSON
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            # Indexes for common queries
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_runs_timestamp 
                ON test_runs(timestamp DESC)
            """)
            
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_runs_branch 
                ON test_runs(branch)
            """)
            
            # Test results table - individual test outcomes
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS test_results (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    test_name TEXT NOT NULL,
                    class_name TEXT,
                    status TEXT NOT NULL,
                    duration REAL NOT NULL,
                    run_id TEXT NOT NULL,
                    timestamp TIMESTAMP NOT NULL,
                    failure_message TEXT,
                    failure_type TEXT,
                    stack_trace TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (run_id) REFERENCES test_runs(run_id)
                )
            """)
            
            # Critical indexes for performance
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_results_test_name 
                ON test_results(test_name)
            """)
            
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_results_run_id 
                ON test_results(run_id)
            """)
            
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_results_status 
                ON test_results(status)
            """)
            
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_results_timestamp 
                ON test_results(timestamp DESC)
            """)
            
            # Composite index for flakiness queries
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_results_test_timestamp 
                ON test_results(test_name, timestamp DESC)
            """)
            
            # Store schema version
            cursor.execute("""
                INSERT OR REPLACE INTO metadata (key, value) 
                VALUES ('schema_version', '1.0')
            """)
            
            cursor.execute("""
                INSERT OR REPLACE INTO metadata (key, value) 
                VALUES ('initialized_at', ?)
            """, (datetime.now().isoformat(),))
            
            self.conn.commit()
            
        except sqlite3.Error as e:
            self.conn.rollback()
            raise DatabaseError(
                f"Failed to initialize database schema.\n"
                f"Error: {e}\n"
                f"💡 This might indicate database corruption. "
                f"Consider backing up and recreating the database."
            )

    def get_schema_version(self) -> int:
        """
        Get the database's current schema version.

        Returns:
            The schema version, or 0 if the database has not been initialized.
        """
        if not self.conn:
            raise DatabaseError("Database not connected.")

        cursor = self.conn.cursor()
        cursor.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='metadata'"
        )
        if cursor.fetchone() is None:
            return 0

        cursor.execute("SELECT value FROM metadata WHERE key = 'schema_version'")
        row = cursor.fetchone()
        if row is None:
            return 0

        try:
            # Older databases stored the version as "1.0"; normalize to int.
            return int(float(row[0]))
        except (TypeError, ValueError):
            return 0

    def needs_migration(self) -> bool:
        """Check whether pending schema migrations exist."""
        return self.get_schema_version() < latest_schema_version()

    def migrate(self) -> List[int]:
        """
        Apply any pending schema migrations, in order.

        Each migration runs in a single transaction; if one fails, all
        changes from this call are rolled back and the database is left
        untouched.

        Returns:
            The list of versions applied, in order (empty if already current).
        """
        if not self.conn:
            raise DatabaseError("Database not connected.")

        current = self.get_schema_version()
        if current == 0:
            raise DatabaseError(
                "Database not initialized.\n"
                "💡 Run first: flaktor init"
            )

        applied: List[int] = []
        cursor = self.conn.cursor()

        try:
            for target_version, _description, migration_fn in _MIGRATIONS:
                if target_version <= current:
                    continue
                migration_fn(cursor)
                cursor.execute(
                    "INSERT OR REPLACE INTO metadata (key, value) VALUES ('schema_version', ?)",
                    (str(target_version),)
                )
                current = target_version
                applied.append(target_version)

            self.conn.commit()
        except sqlite3.Error as e:
            self.conn.rollback()
            raise DatabaseError(
                f"Migration failed: {e}\n"
                f"💡 No changes were applied (migration rolled back safely)."
            )

        return applied

    def insert_test_run(self, test_run: TestRun) -> None:
        """
        Insert a new test run record.
        
        Args:
            test_run: TestRun object with run metadata
        
        Raises:
            DatabaseError: If insertion fails with helpful context
        """
        if not self.conn:
            raise DatabaseError("Database not connected.")
        
        try:
            metadata_json = json.dumps(test_run.metadata) if test_run.metadata else None
            
            self.conn.execute("""
                INSERT INTO test_runs (run_id, timestamp, branch, commit_hash, environment, metadata)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (
                test_run.run_id,
                test_run.timestamp.isoformat(),
                test_run.branch,
                test_run.commit_hash,
                test_run.environment,
                metadata_json
            ))
            self.conn.commit()
            
        except sqlite3.IntegrityError:
            # Run already exists - this is OK, skip gracefully
            pass
        except sqlite3.Error as e:
            self.conn.rollback()
            raise DatabaseError(
                f"Failed to insert test run '{test_run.run_id}'.\n"
                f"Error: {e}"
            )
    
    def insert_test_results(self, results: List[TestResult]) -> Tuple[int, int]:
        """
        Batch insert test results for efficiency.
        
        Args:
            results: List of TestResult objects
        
        Returns:
            Tuple of (successful_inserts, failed_inserts)
        
        Note:
            Uses transaction for atomicity - all or nothing.
        """
        if not self.conn:
            raise DatabaseError("Database not connected.")
        
        if not results:
            return (0, 0)
        
        successful = 0
        failed = 0
        
        try:
            cursor = self.conn.cursor()
            
            for result in results:
                try:
                    cursor.execute("""
                        INSERT INTO test_results 
                        (test_name, class_name, status, duration, run_id, timestamp,
                         failure_message, failure_type, stack_trace)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, (
                        result.test_name,
                        result.class_name,
                        result.status.value,
                        result.duration,
                        result.run_id,
                        result.timestamp.isoformat(),
                        result.failure_message,
                        result.failure_type,
                        result.stack_trace
                    ))
                    successful += 1
                except sqlite3.Error:
                    failed += 1
            
            self.conn.commit()
            return (successful, failed)
            
        except sqlite3.Error as e:
            self.conn.rollback()
            raise DatabaseError(
                f"Failed to insert test results.\n"
                f"Error: {e}\n"
                f"Successfully inserted: {successful}, Failed: {failed}"
            )
    
    def get_test_history(
        self, 
        test_name: str, 
        limit: int = 30
    ) -> List[sqlite3.Row]:
        """
        Get recent history for a specific test.
        
        Args:
            test_name: Full test identifier
            limit: Maximum number of results to return
        
        Returns:
            List of result rows, newest first
        """
        if not self.conn:
            raise DatabaseError("Database not connected.")
        
        cursor = self.conn.cursor()
        cursor.execute("""
            SELECT 
                test_name,
                status,
                duration,
                run_id,
                timestamp,
                failure_message,
                failure_type
            FROM test_results
            WHERE test_name = ?
            ORDER BY timestamp DESC
            LIMIT ?
        """, (test_name, limit))
        
        return cursor.fetchall()
    
    def get_all_test_names(self) -> List[str]:
        """Get unique list of all test names in database."""
        if not self.conn:
            raise DatabaseError("Database not connected.")
        
        cursor = self.conn.cursor()
        cursor.execute("""
            SELECT DISTINCT test_name 
            FROM test_results 
            ORDER BY test_name
        """)
        
        return [row[0] for row in cursor.fetchall()]
    
    def get_database_stats(self) -> dict:
        """
        Get database statistics for health monitoring.
        
        Returns:
            Dictionary with counts and database size
        """
        if not self.conn:
            raise DatabaseError("Database not connected.")
        
        cursor = self.conn.cursor()
        
        # Get counts
        cursor.execute("SELECT COUNT(*) FROM test_runs")
        total_runs = cursor.fetchone()[0]
        
        cursor.execute("SELECT COUNT(*) FROM test_results")
        total_results = cursor.fetchone()[0]
        
        cursor.execute("SELECT COUNT(DISTINCT test_name) FROM test_results")
        unique_tests = cursor.fetchone()[0]
        
        # Get date range
        cursor.execute("""
            SELECT MIN(timestamp), MAX(timestamp) 
            FROM test_runs
        """)
        date_range = cursor.fetchone()
        
        # Get database file size
        db_size_bytes = self.db_path.stat().st_size if self.db_path.exists() else 0
        db_size_mb = db_size_bytes / (1024 * 1024)
        
        return {
            "total_runs": total_runs,
            "total_results": total_results,
            "unique_tests": unique_tests,
            "earliest_run": date_range[0],
            "latest_run": date_range[1],
            "database_size_mb": round(db_size_mb, 2)
        }
    
    def get_flaky_tests(
        self,
        min_runs: int = 5,
        lookback_days: int = 30,
        min_flip_rate: float = 0.1,
    ) -> List[dict]:
        """
        Identify flaky tests based on status flip rate.

        A test is considered flaky if it has inconsistent results
        (passes sometimes, fails other times) within recent runs.

        Args:
            min_runs: Minimum number of runs required to evaluate
            lookback_days: Number of days to look back
            min_flip_rate: Minimum flip rate to be considered flaky (0.0-1.0)

        Returns:
            List of dicts with test info and flakiness metrics
        """
        if not self.conn:
            raise DatabaseError("Database not connected.")

        cursor = self.conn.cursor()

        # Get tests with their recent results
        cursor.execute("""
            SELECT
                test_name,
                COUNT(*) as total_runs,
                SUM(CASE WHEN status = 'passed' THEN 1 ELSE 0 END) as passed,
                SUM(CASE WHEN status = 'failed' THEN 1 ELSE 0 END) as failed,
                SUM(CASE WHEN status = 'error' THEN 1 ELSE 0 END) as errors,
                SUM(CASE WHEN status = 'skipped' THEN 1 ELSE 0 END) as skipped,
                AVG(duration) as avg_duration,
                MAX(timestamp) as last_run
            FROM test_results
            WHERE timestamp >= datetime('now', ?)
            GROUP BY test_name
            HAVING COUNT(*) >= ?
        """, (f'-{lookback_days} days', min_runs))

        results = []
        for row in cursor.fetchall():
            test_name = row[0]
            total = row[1]
            passed = row[2]
            failed = row[3] + row[4]  # failures + errors

            # Calculate flip rate (how often it changes between pass/fail)
            # A test that always passes or always fails has 0 flip rate
            if total <= 1:
                flip_rate = 0.0
            else:
                # Flip rate approximation: 2 * min(pass_rate, fail_rate)
                pass_rate = passed / total
                fail_rate = failed / total
                flip_rate = 2 * min(pass_rate, fail_rate)

            if flip_rate >= min_flip_rate:
                results.append({
                    "test_name": test_name,
                    "total_runs": total,
                    "passed": passed,
                    "failed": failed,
                    "skipped": row[5],
                    "flip_rate": round(flip_rate, 3),
                    "pass_rate": round(passed / total, 3),
                    "avg_duration": round(row[6], 3),
                    "last_run": row[7],
                })

        # Sort by flip rate descending
        results.sort(key=lambda x: x["flip_rate"], reverse=True)
        return results

    def get_test_summary(
        self,
        lookback_days: int = 30,
        status_filter: Optional[str] = None,
    ) -> List[dict]:
        """
        Get summary statistics for all tests.

        Args:
            lookback_days: Number of days to look back
            status_filter: Optional filter by last status

        Returns:
            List of test summaries
        """
        if not self.conn:
            raise DatabaseError("Database not connected.")

        cursor = self.conn.cursor()

        cursor.execute("""
            WITH latest_results AS (
                SELECT
                    test_name,
                    status,
                    ROW_NUMBER() OVER (PARTITION BY test_name ORDER BY timestamp DESC) as rn
                FROM test_results
                WHERE timestamp >= datetime('now', ?)
            ),
            test_stats AS (
                SELECT
                    test_name,
                    COUNT(*) as total_runs,
                    SUM(CASE WHEN status = 'passed' THEN 1 ELSE 0 END) as passed,
                    SUM(CASE WHEN status = 'failed' THEN 1 ELSE 0 END) as failed,
                    SUM(CASE WHEN status = 'error' THEN 1 ELSE 0 END) as errors,
                    SUM(CASE WHEN status = 'skipped' THEN 1 ELSE 0 END) as skipped,
                    AVG(duration) as avg_duration,
                    MAX(timestamp) as last_run
                FROM test_results
                WHERE timestamp >= datetime('now', ?)
                GROUP BY test_name
            )
            SELECT
                s.test_name,
                s.total_runs,
                s.passed,
                s.failed,
                s.errors,
                s.skipped,
                s.avg_duration,
                s.last_run,
                l.status as last_status
            FROM test_stats s
            LEFT JOIN latest_results l ON s.test_name = l.test_name AND l.rn = 1
            ORDER BY s.test_name
        """, (f'-{lookback_days} days', f'-{lookback_days} days'))

        results = []
        for row in cursor.fetchall():
            last_status = row[8]

            # Apply status filter if specified
            if status_filter and last_status != status_filter:
                continue

            results.append({
                "test_name": row[0],
                "total_runs": row[1],
                "passed": row[2],
                "failed": row[3] + row[4],
                "skipped": row[5],
                "avg_duration": round(row[6], 3) if row[6] else 0,
                "last_run": row[7],
                "last_status": last_status,
            })

        return results

    def purge_old_data(
        self,
        days_to_keep: int = 90,
        dry_run: bool = False,
    ) -> dict:
        """
        Purge old test data from the database.

        Args:
            days_to_keep: Number of days of data to keep (older data is deleted)
            dry_run: If True, only count what would be deleted without actually deleting

        Returns:
            Dictionary with counts of deleted/would-be-deleted records
        """
        if not self.conn:
            raise DatabaseError("Database not connected.")

        cursor = self.conn.cursor()
        cutoff_date = f'-{days_to_keep} days'

        # Count records that will be affected
        cursor.execute("""
            SELECT COUNT(*) FROM test_results
            WHERE timestamp < datetime('now', ?)
        """, (cutoff_date,))
        results_to_delete = cursor.fetchone()[0]

        cursor.execute("""
            SELECT COUNT(*) FROM test_runs
            WHERE timestamp < datetime('now', ?)
        """, (cutoff_date,))
        runs_to_delete = cursor.fetchone()[0]

        if dry_run:
            return {
                "test_results_deleted": results_to_delete,
                "test_runs_deleted": runs_to_delete,
                "dry_run": True,
            }

        # Actually delete the data
        try:
            cursor.execute("""
                DELETE FROM test_results
                WHERE timestamp < datetime('now', ?)
            """, (cutoff_date,))
            deleted_results = cursor.rowcount

            cursor.execute("""
                DELETE FROM test_runs
                WHERE timestamp < datetime('now', ?)
            """, (cutoff_date,))
            deleted_runs = cursor.rowcount

            self.conn.commit()

            return {
                "test_results_deleted": deleted_results,
                "test_runs_deleted": deleted_runs,
                "dry_run": False,
            }
        except sqlite3.Error as e:
            self.conn.rollback()
            raise DatabaseError(f"Failed to purge old data: {e}")

    def vacuum(self) -> int:
        """
        Vacuum the database to reclaim space after deleting data.

        Returns:
            Size of database in bytes after vacuum
        """
        if not self.conn:
            raise DatabaseError("Database not connected.")

        try:
            self.conn.execute("VACUUM")
            # Return new database size
            return self.db_path.stat().st_size
        except sqlite3.Error as e:
            raise DatabaseError(f"Failed to vacuum database: {e}")

    def __enter__(self):
        """Context manager support."""
        self.connect()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager cleanup."""
        self.close()