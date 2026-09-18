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
        assert "quarantined_tests" in tables

    def test_initialize_schema_stores_version(self, initialized_db: Database):
        """Test that schema version is stored in metadata."""
        from flaktor.database import CURRENT_SCHEMA_VERSION

        cursor = initialized_db.conn.cursor()
        cursor.execute("SELECT value FROM metadata WHERE key = 'schema_version'")
        result = cursor.fetchone()

        assert result is not None
        assert result[0] == str(CURRENT_SCHEMA_VERSION)

    def test_initialize_schema_idempotent(self, initialized_db: Database):
        """Test that initialize_schema can be called multiple times."""
        # Should not raise an error
        initialized_db.initialize_schema()
        initialized_db.initialize_schema()


class TestSchemaMigration:
    """Tests for schema versioning and migrations."""

    def test_get_schema_version_uninitialized(self, db_path: Path):
        """Test that an uninitialized database reports version 0."""
        db = Database(db_path)
        db.connect()
        try:
            assert db.get_schema_version() == 0
        finally:
            db.close()

    def test_get_schema_version_initialized(self, initialized_db: Database):
        """Test that a freshly initialized database reports the current version."""
        from flaktor.database import CURRENT_SCHEMA_VERSION

        assert initialized_db.get_schema_version() == CURRENT_SCHEMA_VERSION

    def test_get_schema_version_parses_legacy_format(self, initialized_db: Database):
        """Test that a legacy '1.0'-style version string is parsed as an int."""
        cursor = initialized_db.conn.cursor()
        cursor.execute(
            "INSERT OR REPLACE INTO metadata (key, value) VALUES ('schema_version', '1.0')"
        )
        initialized_db.conn.commit()

        assert initialized_db.get_schema_version() == 1

    def test_needs_migration_false_when_current(self, initialized_db: Database):
        """Test that a fresh database needs no migration."""
        assert initialized_db.needs_migration() is False

    def test_migrate_noop_when_current(self, initialized_db: Database):
        """Test that migrate() is a no-op on an up-to-date database."""
        assert initialized_db.migrate() == []

    def test_migrate_raises_on_uninitialized_database(self, db_path: Path):
        """Test that migrate() refuses to run on an uninitialized database."""
        db = Database(db_path)
        db.connect()
        try:
            with pytest.raises(DatabaseError):
                db.migrate()
        finally:
            db.close()

    def test_migrate_applies_pending_migrations(self, initialized_db: Database, monkeypatch):
        """Test that migrate() applies and records a pending migration."""
        import flaktor.database as database_module

        def _add_marker_column(cursor):
            cursor.execute("ALTER TABLE metadata ADD COLUMN marker TEXT")

        next_version = database_module.CURRENT_SCHEMA_VERSION + 1
        monkeypatch.setattr(
            database_module,
            "_MIGRATIONS",
            [(next_version, "add marker column", _add_marker_column)],
        )

        applied = initialized_db.migrate()

        assert applied == [next_version]
        assert initialized_db.get_schema_version() == next_version
        assert initialized_db.needs_migration() is False

        cursor = initialized_db.conn.cursor()
        cursor.execute("PRAGMA table_info(metadata)")
        columns = {row[1] for row in cursor.fetchall()}
        assert "marker" in columns


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

    def test_get_flaky_tests_excludes_quarantined_by_default(self, initialized_db: Database):
        """Test that quarantined tests are hidden from flaky results by default."""
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

        initialized_db.quarantine_test("flaky_test", reason="known flake")

        assert initialized_db.get_flaky_tests(min_runs=5) == []

        included = initialized_db.get_flaky_tests(min_runs=5, include_quarantined=True)
        assert len(included) == 1
        assert included[0]["test_name"] == "flaky_test"


class TestQuarantine:
    """Tests for quarantine/unquarantine and lookup methods."""

    def test_quarantine_test(self, initialized_db: Database):
        """Test quarantining a test records it with a reason."""
        initialized_db.quarantine_test("flaky_test", reason="known flake")

        assert initialized_db.is_quarantined("flaky_test") is True

        rows = initialized_db.get_quarantined_tests()
        assert len(rows) == 1
        assert rows[0]["test_name"] == "flaky_test"
        assert rows[0]["reason"] == "known flake"

    def test_quarantine_test_without_reason(self, initialized_db: Database):
        """Test quarantining without a reason is allowed."""
        initialized_db.quarantine_test("flaky_test")

        rows = initialized_db.get_quarantined_tests()
        assert rows[0]["reason"] is None

    def test_quarantine_test_updates_reason(self, initialized_db: Database):
        """Test re-quarantining an already-quarantined test updates its reason."""
        initialized_db.quarantine_test("flaky_test", reason="first reason")
        initialized_db.quarantine_test("flaky_test", reason="updated reason")

        rows = initialized_db.get_quarantined_tests()
        assert len(rows) == 1
        assert rows[0]["reason"] == "updated reason"

    def test_is_quarantined_false_when_not_quarantined(self, initialized_db: Database):
        """Test is_quarantined returns False for an untouched test."""
        assert initialized_db.is_quarantined("some_test") is False

    def test_unquarantine_test(self, initialized_db: Database):
        """Test removing a test from quarantine."""
        initialized_db.quarantine_test("flaky_test")

        removed = initialized_db.unquarantine_test("flaky_test")

        assert removed is True
        assert initialized_db.is_quarantined("flaky_test") is False

    def test_unquarantine_test_not_quarantined(self, initialized_db: Database):
        """Test unquarantining a test that isn't quarantined returns False."""
        assert initialized_db.unquarantine_test("never_quarantined") is False

    def test_get_quarantined_tests_empty(self, initialized_db: Database):
        """Test get_quarantined_tests returns an empty list when nothing is quarantined."""
        assert initialized_db.get_quarantined_tests() == []


class TestGetTrendingTests:
    """Tests for flakiness trend detection."""

    def _insert_result(
        self, db: Database, test_name: str, status: TestStatus, days_ago: int, run_id: str
    ):
        timestamp = datetime.now() - timedelta(days=days_ago)
        db.insert_test_run(TestRun(run_id=run_id, timestamp=timestamp))
        db.insert_test_results([
            TestResult(
                test_name=test_name,
                status=status,
                duration=0.1,
                run_id=run_id,
                timestamp=timestamp,
            )
        ])

    def test_detects_worsening_test(self, initialized_db: Database):
        """Test a test that was stable but is now flaky shows as worsening."""
        for i in range(5):
            self._insert_result(initialized_db, "test_a", TestStatus.PASSED, 31 + i, f"prev-{i}")

        for i in range(6):
            status = TestStatus.PASSED if i % 2 == 0 else TestStatus.FAILED
            self._insert_result(initialized_db, "test_a", status, i, f"cur-{i}")

        trends = initialized_db.get_trending_tests(days=30, min_runs=5)

        assert len(trends) == 1
        assert trends[0]["test_name"] == "test_a"
        assert trends[0]["trend"] == "worsening"
        assert trends[0]["flip_rate_delta"] > 0

    def test_detects_improving_test(self, initialized_db: Database):
        """Test a test that was flaky but is now stable shows as improving."""
        for i in range(6):
            status = TestStatus.PASSED if i % 2 == 0 else TestStatus.FAILED
            self._insert_result(initialized_db, "test_b", status, 31 + i, f"prev-{i}")

        for i in range(5):
            self._insert_result(initialized_db, "test_b", TestStatus.PASSED, i, f"cur-{i}")

        trends = initialized_db.get_trending_tests(days=30, min_runs=5)

        assert len(trends) == 1
        assert trends[0]["trend"] == "improving"
        assert trends[0]["flip_rate_delta"] < 0

    def test_new_test_has_no_previous_window(self, initialized_db: Database):
        """Test a test with only current-window data is marked new."""
        for i in range(5):
            self._insert_result(initialized_db, "test_new", TestStatus.PASSED, i, f"cur-{i}")

        trends = initialized_db.get_trending_tests(days=30, min_runs=5)

        assert len(trends) == 1
        assert trends[0]["trend"] == "new"
        assert trends[0]["flip_rate_delta"] is None
        assert trends[0]["previous"] is None

    def test_respects_min_runs(self, initialized_db: Database):
        """Test that tests below min_runs in the current window are excluded."""
        for i in range(2):
            self._insert_result(initialized_db, "test_few", TestStatus.PASSED, i, f"cur-{i}")

        trends = initialized_db.get_trending_tests(days=30, min_runs=5)

        assert trends == []

    def test_worsening_only_filter(self, initialized_db: Database):
        """Test that worsening_only excludes stable/improving/new tests."""
        for i in range(5):
            self._insert_result(
                initialized_db, "test_stable", TestStatus.PASSED, 31 + i, f"stable-prev-{i}"
            )
            self._insert_result(
                initialized_db, "test_stable", TestStatus.PASSED, i, f"stable-cur-{i}"
            )

        for i in range(5):
            self._insert_result(
                initialized_db, "test_worse", TestStatus.PASSED, 31 + i, f"worse-prev-{i}"
            )
        for i in range(6):
            status = TestStatus.PASSED if i % 2 == 0 else TestStatus.FAILED
            self._insert_result(initialized_db, "test_worse", status, i, f"worse-cur-{i}")

        trends = initialized_db.get_trending_tests(days=30, min_runs=5, worsening_only=True)

        assert len(trends) == 1
        assert trends[0]["test_name"] == "test_worse"


class TestFlakyAlerts:
    """Tests for flaky-test alert state (used by webhook notifications)."""

    def test_get_alerted_test_names_empty(self, initialized_db: Database):
        """Test a fresh database has no recorded alerts."""
        assert initialized_db.get_alerted_test_names() == []

    def test_sync_flaky_alerts_records_new(self, initialized_db: Database):
        """Test previously-unseen flaky tests are recorded as newly flaky."""
        newly_flaky, resolved = initialized_db.sync_flaky_alerts(["test_a", "test_b"])

        assert newly_flaky == ["test_a", "test_b"]
        assert resolved == []
        assert set(initialized_db.get_alerted_test_names()) == {"test_a", "test_b"}

    def test_sync_flaky_alerts_no_repeat_alert(self, initialized_db: Database):
        """Test a test already alerted on isn't reported as newly flaky again."""
        initialized_db.sync_flaky_alerts(["test_a"])

        newly_flaky, resolved = initialized_db.sync_flaky_alerts(["test_a"])

        assert newly_flaky == []
        assert resolved == []

    def test_sync_flaky_alerts_clears_resolved(self, initialized_db: Database):
        """Test a test no longer flaky is removed from the alert state."""
        initialized_db.sync_flaky_alerts(["test_a", "test_b"])

        newly_flaky, resolved = initialized_db.sync_flaky_alerts(["test_a"])

        assert newly_flaky == []
        assert resolved == ["test_b"]
        assert initialized_db.get_alerted_test_names() == ["test_a"]

    def test_sync_flaky_alerts_realerts_after_resolution(self, initialized_db: Database):
        """Test a test re-alerts after being cleared and regressing again."""
        initialized_db.sync_flaky_alerts(["test_a"])
        initialized_db.sync_flaky_alerts([])  # test_a resolved, cleared from state

        newly_flaky, resolved = initialized_db.sync_flaky_alerts(["test_a"])

        assert newly_flaky == ["test_a"]
        assert resolved == []


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


class TestPurgeOldData:
    """Tests for purging old data."""

    def test_purge_dry_run(self, initialized_db: Database):
        """Test dry run counts records without deleting."""
        # Insert old data (100 days ago)
        from datetime import timedelta
        old_time = datetime.now() - timedelta(days=100)

        run = TestRun(run_id="old-run", timestamp=old_time)
        initialized_db.insert_test_run(run)

        result = TestResult(
            test_name="old_test",
            status=TestStatus.PASSED,
            duration=0.1,
            run_id="old-run",
            timestamp=old_time,
        )
        initialized_db.insert_test_results([result])

        # Dry run should count but not delete
        preview = initialized_db.purge_old_data(days_to_keep=90, dry_run=True)

        assert preview["dry_run"] is True
        assert preview["test_results_deleted"] == 1
        assert preview["test_runs_deleted"] == 1

        # Data should still exist
        stats = initialized_db.get_database_stats()
        assert stats["total_results"] == 1
        assert stats["total_runs"] == 1

    def test_purge_deletes_old_data(self, initialized_db: Database):
        """Test actual deletion of old data."""
        from datetime import timedelta

        # Insert old data (100 days ago)
        old_time = datetime.now() - timedelta(days=100)
        old_run = TestRun(run_id="old-run", timestamp=old_time)
        initialized_db.insert_test_run(old_run)
        old_result = TestResult(
            test_name="old_test",
            status=TestStatus.PASSED,
            duration=0.1,
            run_id="old-run",
            timestamp=old_time,
        )
        initialized_db.insert_test_results([old_result])

        # Insert recent data
        recent_run = TestRun(run_id="recent-run", timestamp=datetime.now())
        initialized_db.insert_test_run(recent_run)
        recent_result = TestResult(
            test_name="recent_test",
            status=TestStatus.PASSED,
            duration=0.1,
            run_id="recent-run",
            timestamp=datetime.now(),
        )
        initialized_db.insert_test_results([recent_result])

        # Purge old data
        result = initialized_db.purge_old_data(days_to_keep=90, dry_run=False)

        assert result["dry_run"] is False
        assert result["test_results_deleted"] == 1
        assert result["test_runs_deleted"] == 1

        # Only recent data should remain
        stats = initialized_db.get_database_stats()
        assert stats["total_results"] == 1
        assert stats["total_runs"] == 1

    def test_purge_nothing_to_delete(
        self,
        initialized_db: Database,
        sample_test_run: TestRun,
        sample_test_results: list[TestResult],
    ):
        """Test purge when no data is old enough."""
        initialized_db.insert_test_run(sample_test_run)
        initialized_db.insert_test_results(sample_test_results)

        result = initialized_db.purge_old_data(days_to_keep=90, dry_run=False)

        assert result["test_results_deleted"] == 0
        assert result["test_runs_deleted"] == 0


class TestVacuum:
    """Tests for database vacuum."""

    def test_vacuum_returns_size(self, initialized_db: Database):
        """Test vacuum returns database size."""
        size = initialized_db.vacuum()

        assert isinstance(size, int)
        assert size > 0
