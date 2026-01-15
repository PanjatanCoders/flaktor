"""Tests for the database module."""

import pytest
from pathlib import Path
from datetime import datetime, timedelta

from flaktor.database import Database, DatabaseError
from flaktor.models import TestRun, TestResult, TestStatus


@pytest.fixture
def db_path(tmp_path: Path) -> Path:
    """Create a temporary database path."""
    return tmp_path / "test_flaktor.db"


@pytest.fixture
def initialized_db(db_path: Path) -> Database:
    """Create and initialize a database."""
    db = Database(db_path)
    db.connect()
    db.initialize_schema()
    yield db
    db.close()


@pytest.fixture
def sample_test_run() -> TestRun:
    """Create a sample test run."""
    return TestRun(
        run_id="run-001",
        timestamp=datetime.now(),
        branch="main",
        commit_hash="abc123",
        environment="ci",
    )


@pytest.fixture
def sample_test_results(sample_test_run: TestRun) -> list[TestResult]:
    """Create sample test results."""
    return [
        TestResult(
            test_name="test_module.TestClass.test_pass",
            status=TestStatus.PASSED,
            duration=0.5,
            run_id=sample_test_run.run_id,
            timestamp=sample_test_run.timestamp,
            class_name="test_module.TestClass",
        ),
        TestResult(
            test_name="test_module.TestClass.test_fail",
            status=TestStatus.FAILED,
            duration=0.3,
            run_id=sample_test_run.run_id,
            timestamp=sample_test_run.timestamp,
            class_name="test_module.TestClass",
            failure_message="AssertionError",
            failure_type="AssertionError",
            stack_trace="Traceback...",
        ),
        TestResult(
            test_name="test_module.TestClass.test_skip",
            status=TestStatus.SKIPPED,
            duration=0.0,
            run_id=sample_test_run.run_id,
            timestamp=sample_test_run.timestamp,
            class_name="test_module.TestClass",
            failure_message="Skipped for now",
        ),
    ]


class TestDatabaseConnection:
    """Tests for database connection handling."""

    def test_connect_creates_file(self, db_path: Path):
        """Test that connect creates the database file."""
        db = Database(db_path)
        db.connect()

        assert db_path.exists()
        db.close()

    def test_close_connection(self, db_path: Path):
        """Test that close properly closes the connection."""
        db = Database(db_path)
        db.connect()
        db.close()

        assert db.conn is None

    def test_context_manager(self, db_path: Path):
        """Test using database as context manager."""
        with Database(db_path) as db:
            db.initialize_schema()
            assert db.conn is not None

        # Connection should be closed after exiting context
        assert db.conn is None

    def test_operations_without_connection_raise_error(self, db_path: Path):
        """Test that operations without connection raise DatabaseError."""
        db = Database(db_path)

        with pytest.raises(DatabaseError, match="not connected"):
            db.initialize_schema()


class TestDatabaseSchema:
    """Tests for schema initialization."""

    def test_initialize_schema_creates_tables(self, initialized_db: Database):
        """Test that initialize_schema creates required tables."""
        cursor = initialized_db.conn.cursor()

        # Check tables exist
        cursor.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        )
        tables = [row[0] for row in cursor.fetchall()]

        assert "metadata" in tables
        assert "test_runs" in tables
        assert "test_results" in tables

    def test_initialize_schema_stores_version(self, initialized_db: Database):
        """Test that schema version is stored in metadata."""
        cursor = initialized_db.conn.cursor()
        cursor.execute("SELECT value FROM metadata WHERE key = 'schema_version'")
        result = cursor.fetchone()

        assert result is not None
        assert result[0] == "1.0"

    def test_initialize_schema_idempotent(self, initialized_db: Database):
        """Test that initialize_schema can be called multiple times."""
        # Should not raise an error
        initialized_db.initialize_schema()
        initialized_db.initialize_schema()


class TestInsertTestRun:
    """Tests for inserting test runs."""

    def test_insert_test_run(self, initialized_db: Database, sample_test_run: TestRun):
        """Test inserting a test run."""
        initialized_db.insert_test_run(sample_test_run)

        cursor = initialized_db.conn.cursor()
        cursor.execute("SELECT * FROM test_runs WHERE run_id = ?", (sample_test_run.run_id,))
        row = cursor.fetchone()

        assert row is not None

    def test_insert_duplicate_run_id_ignored(
        self, initialized_db: Database, sample_test_run: TestRun
    ):
        """Test that duplicate run_ids are silently ignored."""
        initialized_db.insert_test_run(sample_test_run)
        # Should not raise
        initialized_db.insert_test_run(sample_test_run)

        cursor = initialized_db.conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM test_runs WHERE run_id = ?", (sample_test_run.run_id,))
        count = cursor.fetchone()[0]

        assert count == 1


class TestInsertTestResults:
    """Tests for inserting test results."""

    def test_insert_test_results(
        self,
        initialized_db: Database,
        sample_test_run: TestRun,
        sample_test_results: list[TestResult],
    ):
        """Test inserting test results."""
        initialized_db.insert_test_run(sample_test_run)
        successful, failed = initialized_db.insert_test_results(sample_test_results)

        assert successful == 3
        assert failed == 0

        cursor = initialized_db.conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM test_results")
        count = cursor.fetchone()[0]

        assert count == 3

    def test_insert_empty_results(self, initialized_db: Database):
        """Test inserting empty results list."""
        successful, failed = initialized_db.insert_test_results([])

        assert successful == 0
        assert failed == 0

    def test_insert_results_stores_failure_info(
        self,
        initialized_db: Database,
        sample_test_run: TestRun,
        sample_test_results: list[TestResult],
    ):
        """Test that failure information is stored correctly."""
        initialized_db.insert_test_run(sample_test_run)
        initialized_db.insert_test_results(sample_test_results)

        cursor = initialized_db.conn.cursor()
        cursor.execute(
            "SELECT failure_message, failure_type, stack_trace FROM test_results WHERE status = 'failed'"
        )
        row = cursor.fetchone()

        assert row[0] == "AssertionError"
        assert row[1] == "AssertionError"
        assert row[2] == "Traceback..."


class TestGetTestHistory:
    """Tests for getting test history."""

    def test_get_test_history(
        self,
        initialized_db: Database,
        sample_test_run: TestRun,
        sample_test_results: list[TestResult],
    ):
        """Test retrieving test history."""
        initialized_db.insert_test_run(sample_test_run)
        initialized_db.insert_test_results(sample_test_results)

        history = initialized_db.get_test_history("test_module.TestClass.test_pass")

        assert len(history) == 1
        assert history[0]["test_name"] == "test_module.TestClass.test_pass"

    def test_get_test_history_limit(self, initialized_db: Database):
        """Test that history respects limit parameter."""
        # Insert multiple results for same test
        run = TestRun(run_id="run-001", timestamp=datetime.now())
        initialized_db.insert_test_run(run)

        results = [
            TestResult(
                test_name="test_repeated",
                status=TestStatus.PASSED,
                duration=0.1,
                run_id="run-001",
                timestamp=datetime.now() - timedelta(hours=i),
            )
            for i in range(10)
        ]
        initialized_db.insert_test_results(results)

        history = initialized_db.get_test_history("test_repeated", limit=5)

        assert len(history) == 5


class TestGetAllTestNames:
    """Tests for getting all test names."""

    def test_get_all_test_names(
        self,
        initialized_db: Database,
        sample_test_run: TestRun,
        sample_test_results: list[TestResult],
    ):
        """Test retrieving all unique test names."""
        initialized_db.insert_test_run(sample_test_run)
        initialized_db.insert_test_results(sample_test_results)

        names = initialized_db.get_all_test_names()

        assert len(names) == 3
        assert "test_module.TestClass.test_pass" in names


class TestGetDatabaseStats:
    """Tests for database statistics."""

    def test_get_database_stats_empty(self, initialized_db: Database):
        """Test stats on empty database."""
        stats = initialized_db.get_database_stats()

        assert stats["total_runs"] == 0
        assert stats["total_results"] == 0
        assert stats["unique_tests"] == 0

    def test_get_database_stats_with_data(
        self,
        initialized_db: Database,
        sample_test_run: TestRun,
        sample_test_results: list[TestResult],
    ):
        """Test stats with data."""
        initialized_db.insert_test_run(sample_test_run)
        initialized_db.insert_test_results(sample_test_results)

        stats = initialized_db.get_database_stats()

        assert stats["total_runs"] == 1
        assert stats["total_results"] == 3
        assert stats["unique_tests"] == 3


class TestGetFlakyTests:
    """Tests for flaky test detection."""

    def test_get_flaky_tests_no_flaky(self, initialized_db: Database):
        """Test when there are no flaky tests."""
        # Insert consistently passing tests
        for i in range(5):
            run = TestRun(run_id=f"run-{i}", timestamp=datetime.now())
            initialized_db.insert_test_run(run)

            result = TestResult(
                test_name="always_pass",
                status=TestStatus.PASSED,
                duration=0.1,
                run_id=f"run-{i}",
                timestamp=datetime.now(),
            )
            initialized_db.insert_test_results([result])

        flaky = initialized_db.get_flaky_tests(min_runs=5)

        assert len(flaky) == 0

    def test_get_flaky_tests_detects_flaky(self, initialized_db: Database):
        """Test detection of flaky tests."""
        # Insert alternating pass/fail
        for i in range(6):
            run = TestRun(run_id=f"run-{i}", timestamp=datetime.now())
            initialized_db.insert_test_run(run)

            status = TestStatus.PASSED if i % 2 == 0 else TestStatus.FAILED
            result = TestResult(
                test_name="flaky_test",
                status=status,
                duration=0.1,
                run_id=f"run-{i}",
                timestamp=datetime.now(),
            )
            initialized_db.insert_test_results([result])

        flaky = initialized_db.get_flaky_tests(min_runs=5)

        assert len(flaky) == 1
        assert flaky[0]["test_name"] == "flaky_test"
        assert flaky[0]["flip_rate"] == 1.0  # 50/50 split = max flip rate

    def test_get_flaky_tests_respects_min_runs(self, initialized_db: Database):
        """Test that min_runs parameter is respected."""
        # Insert only 3 runs
        for i in range(3):
            run = TestRun(run_id=f"run-{i}", timestamp=datetime.now())
            initialized_db.insert_test_run(run)

            status = TestStatus.PASSED if i % 2 == 0 else TestStatus.FAILED
            result = TestResult(
                test_name="few_runs_test",
                status=status,
                duration=0.1,
                run_id=f"run-{i}",
                timestamp=datetime.now(),
            )
            initialized_db.insert_test_results([result])

        flaky = initialized_db.get_flaky_tests(min_runs=5)

        assert len(flaky) == 0  # Not enough runs


class TestGetTestSummary:
    """Tests for test summary."""

    def test_get_test_summary(
        self,
        initialized_db: Database,
        sample_test_run: TestRun,
        sample_test_results: list[TestResult],
    ):
        """Test getting test summary."""
        initialized_db.insert_test_run(sample_test_run)
        initialized_db.insert_test_results(sample_test_results)

        summary = initialized_db.get_test_summary()

        assert len(summary) == 3

    def test_get_test_summary_with_status_filter(
        self,
        initialized_db: Database,
        sample_test_run: TestRun,
        sample_test_results: list[TestResult],
    ):
        """Test filtering summary by status."""
        initialized_db.insert_test_run(sample_test_run)
        initialized_db.insert_test_results(sample_test_results)

        summary = initialized_db.get_test_summary(status_filter="failed")

        assert len(summary) == 1
        assert summary[0]["last_status"] == "failed"
