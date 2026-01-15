"""
Database layer for Flaktor.

Handles all SQLite operations with a focus on reliability and helpful error messages.
"""

import sqlite3
from pathlib import Path
from typing import Optional, List, Tuple
from datetime import datetime
import json

from .models import TestRun, TestResult, TestStatus


class DatabaseError(Exception):
    """Custom exception for database operations with helpful context."""
    pass


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
    
    def __enter__(self):
        """Context manager support."""
        self.connect()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager cleanup."""
        self.close()