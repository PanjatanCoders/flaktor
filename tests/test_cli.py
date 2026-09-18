"""Tests for the CLI module."""

import csv
import json
import pytest
from pathlib import Path
from typer.testing import CliRunner
from datetime import datetime, timedelta

from flaktor.cli import app
from flaktor.database import Database
from flaktor.models import TestRun, TestResult, TestStatus


runner = CliRunner()


@pytest.fixture
def db_path(tmp_path: Path) -> Path:
    """Create a temporary database path."""
    return tmp_path / ".flaktor" / "flaktor.db"


@pytest.fixture
def initialized_db(db_path: Path) -> Path:
    """Initialize a database and return its path."""
    db_path.parent.mkdir(parents=True, exist_ok=True)
    with Database(db_path) as db:
        db.initialize_schema()
    return db_path


@pytest.fixture
def sample_xml(tmp_path: Path) -> Path:
    """Create a sample JUnit XML file."""
    timestamp = datetime.now().isoformat(timespec="seconds")
    xml_content = f"""<?xml version="1.0" encoding="UTF-8"?>
    <testsuite name="test_suite" tests="3" failures="1" timestamp="{timestamp}">
        <testcase name="test_pass" classname="TestClass" time="0.5"/>
        <testcase name="test_fail" classname="TestClass" time="0.3">
            <failure message="AssertionError">Failed</failure>
        </testcase>
        <testcase name="test_skip" classname="TestClass" time="0.0">
            <skipped message="Skipped"/>
        </testcase>
    </testsuite>
    """
    xml_file = tmp_path / "results.xml"
    xml_file.write_text(xml_content)
    return xml_file


class TestInitCommand:
    """Tests for the init command."""

    def test_init_creates_database(self, tmp_path: Path):
        """Test that init creates the database."""
        db_path = tmp_path / "test.db"

        result = runner.invoke(app, ["init", "--db", str(db_path)])

        assert result.exit_code == 0
        assert db_path.exists()
        assert "initialized successfully" in result.stdout

    def test_init_already_exists(self, initialized_db: Path):
        """Test init when database already exists."""
        result = runner.invoke(app, ["init", "--db", str(initialized_db)])

        assert result.exit_code == 0
        assert "already initialized" in result.stdout

    def test_init_force_reinitialize(self, initialized_db: Path):
        """Test force reinitializing database."""
        result = runner.invoke(app, ["init", "--db", str(initialized_db), "--force"])

        assert result.exit_code == 0
        assert "initialized successfully" in result.stdout


class TestInfoCommand:
    """Tests for the info command."""

    def test_info_shows_stats(self, initialized_db: Path):
        """Test info command shows database stats."""
        result = runner.invoke(app, ["info", "--db", str(initialized_db)])

        assert result.exit_code == 0
        assert "Database Path" in result.stdout
        assert "Total Test Runs" in result.stdout

    def test_info_shows_schema_version(self, initialized_db: Path):
        """Test info command shows the schema version."""
        result = runner.invoke(app, ["info", "--db", str(initialized_db)])

        assert result.exit_code == 0
        assert "Schema Version" in result.stdout

    def test_info_database_not_found(self, tmp_path: Path):
        """Test info with non-existent database."""
        db_path = tmp_path / "nonexistent.db"

        result = runner.invoke(app, ["info", "--db", str(db_path)])

        assert result.exit_code == 1
        assert "Database not found" in result.stdout


class TestUploadCommand:
    """Tests for the upload command."""

    def test_upload_xml_file(self, initialized_db: Path, sample_xml: Path):
        """Test uploading an XML file."""
        result = runner.invoke(
            app, ["upload", str(sample_xml), "--db", str(initialized_db)]
        )

        assert result.exit_code == 0
        assert "Upload successful" in result.stdout
        assert "3" in result.stdout  # 3 tests

    def test_upload_with_metadata(self, initialized_db: Path, sample_xml: Path):
        """Test uploading with branch and commit."""
        result = runner.invoke(
            app,
            [
                "upload",
                str(sample_xml),
                "--db", str(initialized_db),
                "--branch", "main",
                "--commit", "abc123",
                "--env", "ci",
            ],
        )

        assert result.exit_code == 0
        assert "Upload successful" in result.stdout

    def test_upload_with_run_id(self, initialized_db: Path, sample_xml: Path):
        """Test uploading with custom run ID."""
        result = runner.invoke(
            app,
            [
                "upload",
                str(sample_xml),
                "--db", str(initialized_db),
                "--run-id", "my-custom-run",
            ],
        )

        assert result.exit_code == 0
        assert "my-custom-run" in result.stdout

    def test_upload_file_not_found(self, initialized_db: Path, tmp_path: Path):
        """Test upload with non-existent file."""
        result = runner.invoke(
            app, ["upload", str(tmp_path / "nonexistent.xml"), "--db", str(initialized_db)]
        )

        assert result.exit_code == 1
        assert "No valid test result files found" in result.stdout

    def test_upload_database_not_initialized(self, tmp_path: Path, sample_xml: Path):
        """Test upload with uninitialized database."""
        db_path = tmp_path / "uninit.db"

        result = runner.invoke(
            app, ["upload", str(sample_xml), "--db", str(db_path)]
        )

        assert result.exit_code == 1
        assert "Database not initialized" in result.stdout


class TestListCommand:
    """Tests for the list command."""

    def test_list_empty_database(self, initialized_db: Path):
        """Test list on empty database."""
        result = runner.invoke(app, ["list", "--db", str(initialized_db)])

        assert result.exit_code == 0
        assert "No tests found" in result.stdout

    def test_list_with_data(self, initialized_db: Path, sample_xml: Path):
        """Test list with test data."""
        # First upload some data
        runner.invoke(app, ["upload", str(sample_xml), "--db", str(initialized_db)])

        result = runner.invoke(app, ["list", "--db", str(initialized_db)])

        assert result.exit_code == 0
        assert "TestClass" in result.stdout

    def test_list_flaky_no_flaky_tests(self, initialized_db: Path, sample_xml: Path):
        """Test list --flaky when no flaky tests exist."""
        runner.invoke(app, ["upload", str(sample_xml), "--db", str(initialized_db)])

        result = runner.invoke(
            app, ["list", "--flaky", "--min-runs", "1", "--db", str(initialized_db)]
        )

        assert result.exit_code == 0
        # With only 1 run per test, none should be flaky
        assert "No flaky tests detected" in result.stdout

    def test_list_failed_filter(self, initialized_db: Path, sample_xml: Path):
        """Test list --failed filter."""
        runner.invoke(app, ["upload", str(sample_xml), "--db", str(initialized_db)])

        result = runner.invoke(app, ["list", "--failed", "--db", str(initialized_db)])

        assert result.exit_code == 0
        assert "Failed Tests" in result.stdout

    def test_list_with_limit(self, initialized_db: Path, sample_xml: Path):
        """Test list with --limit option."""
        runner.invoke(app, ["upload", str(sample_xml), "--db", str(initialized_db)])

        result = runner.invoke(
            app, ["list", "--limit", "1", "--db", str(initialized_db)]
        )

        assert result.exit_code == 0

    def test_list_quarantined_empty(self, initialized_db: Path):
        """Test list --quarantined when nothing is quarantined."""
        result = runner.invoke(
            app, ["list", "--quarantined", "--db", str(initialized_db)]
        )

        assert result.exit_code == 0
        assert "No quarantined tests" in result.stdout


class TestQuarantineCommand:
    """Tests for the quarantine and unquarantine commands."""

    def test_quarantine_database_not_initialized(self, tmp_path: Path):
        """Test quarantine with uninitialized database."""
        db_path = tmp_path / "uninit.db"

        result = runner.invoke(app, ["quarantine", "test_x", "--db", str(db_path)])

        assert result.exit_code == 1
        assert "Database not initialized" in result.stdout

    def test_quarantine_test_not_found(self, initialized_db: Path, sample_xml: Path):
        """Test quarantine with a name that matches nothing."""
        runner.invoke(app, ["upload", str(sample_xml), "--db", str(initialized_db)])

        result = runner.invoke(
            app, ["quarantine", "nonexistent_test", "--db", str(initialized_db)]
        )

        assert result.exit_code == 1
        assert "No tests found matching" in result.stdout

    def test_quarantine_ambiguous_match(self, initialized_db: Path, sample_xml: Path):
        """Test quarantine with a name matching multiple tests."""
        runner.invoke(app, ["upload", str(sample_xml), "--db", str(initialized_db)])

        result = runner.invoke(
            app, ["quarantine", "test", "--db", str(initialized_db)]
        )

        assert result.exit_code == 1
        assert "Multiple Matches" in result.stdout

    def test_quarantine_success(self, initialized_db: Path, sample_xml: Path):
        """Test quarantining a test with a reason, and seeing it listed."""
        runner.invoke(app, ["upload", str(sample_xml), "--db", str(initialized_db)])

        result = runner.invoke(
            app,
            [
                "quarantine", "test_fail",
                "--db", str(initialized_db),
                "--reason", "tracked in JIRA-123",
            ],
        )

        assert result.exit_code == 0
        assert "Quarantined" in result.stdout
        assert "TestClass.test_fail" in result.stdout

        list_result = runner.invoke(
            app, ["list", "--quarantined", "--db", str(initialized_db)]
        )
        assert "TestClass.test_fail" in list_result.stdout
        assert "JIRA-123" in list_result.stdout

    def test_unquarantine_not_found(self, initialized_db: Path):
        """Test unquarantine when nothing is quarantined."""
        result = runner.invoke(
            app, ["unquarantine", "test_x", "--db", str(initialized_db)]
        )

        assert result.exit_code == 1
        assert "No quarantined test matches" in result.stdout

    def test_unquarantine_success(self, initialized_db: Path, sample_xml: Path):
        """Test removing a test from quarantine."""
        runner.invoke(app, ["upload", str(sample_xml), "--db", str(initialized_db)])
        runner.invoke(app, ["quarantine", "test_fail", "--db", str(initialized_db)])

        result = runner.invoke(
            app, ["unquarantine", "test_fail", "--db", str(initialized_db)]
        )

        assert result.exit_code == 0
        assert "Removed from quarantine" in result.stdout

        list_result = runner.invoke(
            app, ["list", "--quarantined", "--db", str(initialized_db)]
        )
        assert "No quarantined tests" in list_result.stdout

    def test_flaky_excludes_quarantined_by_default(self, initialized_db: Path, tmp_path: Path):
        """Test that --flaky hides a quarantined test unless --include-quarantined is set."""
        timestamp = datetime.now().isoformat(timespec="seconds")

        pass_xml = tmp_path / "pass.xml"
        pass_xml.write_text(f"""<?xml version="1.0" encoding="UTF-8"?>
        <testsuite name="s" tests="1" timestamp="{timestamp}">
            <testcase name="test_x" classname="T" time="0.1"/>
        </testsuite>
        """)

        fail_xml = tmp_path / "fail.xml"
        fail_xml.write_text(f"""<?xml version="1.0" encoding="UTF-8"?>
        <testsuite name="s" tests="1" failures="1" timestamp="{timestamp}">
            <testcase name="test_x" classname="T" time="0.1">
                <failure message="boom">boom</failure>
            </testcase>
        </testsuite>
        """)

        runner.invoke(app, ["upload", str(pass_xml), "--db", str(initialized_db)])
        runner.invoke(app, ["upload", str(fail_xml), "--db", str(initialized_db)])

        result = runner.invoke(
            app, ["list", "--flaky", "--min-runs", "1", "--db", str(initialized_db)]
        )
        assert "T.test_x" in result.stdout

        runner.invoke(app, ["quarantine", "T.test_x", "--db", str(initialized_db)])

        result_excluded = runner.invoke(
            app, ["list", "--flaky", "--min-runs", "1", "--db", str(initialized_db)]
        )
        assert "T.test_x" not in result_excluded.stdout
        assert "No flaky tests detected" in result_excluded.stdout

        result_included = runner.invoke(
            app,
            [
                "list", "--flaky", "--min-runs", "1",
                "--include-quarantined", "--db", str(initialized_db),
            ],
        )
        assert "T.test_x" in result_included.stdout


class TestReportCommand:
    """Tests for the report command."""

    def test_report_empty_database(self, initialized_db: Path):
        """Test report on empty database."""
        result = runner.invoke(app, ["report", "--db", str(initialized_db)])

        assert result.exit_code == 0
        assert "TEST HEALTH REPORT" in result.stdout
        assert "Total Unique Tests:    0" in result.stdout

    def test_report_with_data(self, initialized_db: Path, sample_xml: Path):
        """Test report with test data."""
        runner.invoke(app, ["upload", str(sample_xml), "--db", str(initialized_db)])

        result = runner.invoke(app, ["report", "--db", str(initialized_db)])

        assert result.exit_code == 0
        assert "TEST HEALTH REPORT" in result.stdout
        assert "Total Unique Tests:    3" in result.stdout

    def test_report_save_to_file(self, initialized_db: Path, tmp_path: Path):
        """Test saving report to file."""
        output_file = tmp_path / "report.txt"

        result = runner.invoke(
            app, ["report", "--db", str(initialized_db), "--output", str(output_file)]
        )

        assert result.exit_code == 0
        assert output_file.exists()
        assert "Report saved" in result.stdout

        content = output_file.read_text()
        assert "TEST HEALTH REPORT" in content

    def test_report_custom_days(self, initialized_db: Path):
        """Test report with custom days parameter."""
        result = runner.invoke(
            app, ["report", "--db", str(initialized_db), "--days", "7"]
        )

        assert result.exit_code == 0
        assert "Last 7 days" in result.stdout


class TestCompareCommand:
    """Tests for the compare command."""

    def test_compare_database_not_initialized(self, tmp_path: Path):
        """Test compare with uninitialized database."""
        db_path = tmp_path / "uninit.db"

        result = runner.invoke(
            app, ["compare", "main", "feature", "--db", str(db_path)]
        )

        assert result.exit_code == 1
        assert "Database not initialized" in result.stdout

    def test_compare_no_data(self, initialized_db: Path):
        """Test compare when neither branch has data."""
        result = runner.invoke(
            app, ["compare", "main", "feature", "--db", str(initialized_db)]
        )

        assert result.exit_code == 0
        assert "No differences found" in result.stdout

    def test_compare_identical_branches(self, initialized_db: Path, sample_xml: Path):
        """Test comparing a branch against itself shows the same stats."""
        runner.invoke(
            app,
            ["upload", str(sample_xml), "--db", str(initialized_db), "--branch", "main"],
        )

        result = runner.invoke(
            app, ["compare", "main", "main", "--db", str(initialized_db)]
        )

        assert result.exit_code == 0
        assert "main vs main" in result.stdout

    def test_compare_shows_regression(self, initialized_db: Path, tmp_path: Path):
        """Test compare surfaces a test that regressed on the second branch."""
        timestamp = datetime.now().isoformat(timespec="seconds")

        main_xml = tmp_path / "main.xml"
        main_xml.write_text(f"""<?xml version="1.0" encoding="UTF-8"?>
        <testsuite name="s" tests="1" failures="0" timestamp="{timestamp}">
            <testcase name="test_login" classname="TestAuth" time="0.1"/>
        </testsuite>
        """)

        feature_xml = tmp_path / "feature.xml"
        feature_xml.write_text(f"""<?xml version="1.0" encoding="UTF-8"?>
        <testsuite name="s" tests="1" failures="1" timestamp="{timestamp}">
            <testcase name="test_login" classname="TestAuth" time="0.1">
                <failure message="boom">boom</failure>
            </testcase>
        </testsuite>
        """)

        runner.invoke(
            app,
            ["upload", str(main_xml), "--db", str(initialized_db), "--branch", "main"],
        )
        runner.invoke(
            app,
            ["upload", str(feature_xml), "--db", str(initialized_db), "--branch", "feature"],
        )

        result = runner.invoke(
            app, ["compare", "main", "feature", "--db", str(initialized_db)]
        )

        assert result.exit_code == 0
        assert "TestAuth" in result.stdout
        assert "100%" in result.stdout
        assert "0%" in result.stdout

    def test_compare_only_diff_filters_identical(self, initialized_db: Path, sample_xml: Path):
        """Test --only-diff hides tests with no change between branches."""
        runner.invoke(
            app,
            ["upload", str(sample_xml), "--db", str(initialized_db), "--branch", "main"],
        )

        result = runner.invoke(
            app,
            ["compare", "main", "main", "--db", str(initialized_db), "--only-diff"],
        )

        assert result.exit_code == 0
        assert "No differences found" in result.stdout

    def test_compare_min_runs_filter(self, initialized_db: Path, sample_xml: Path):
        """Test --min-runs excludes tests below the run threshold."""
        runner.invoke(
            app,
            ["upload", str(sample_xml), "--db", str(initialized_db), "--branch", "main"],
        )

        result = runner.invoke(
            app,
            ["compare", "main", "feature", "--db", str(initialized_db), "--min-runs", "5"],
        )

        assert result.exit_code == 0
        assert "No differences found" in result.stdout


class TestTrendCommand:
    """Tests for the trend command."""

    def _upload_at(
        self, db_path: Path, tmp_path: Path, name: str, failed: bool, days_ago: int, seq: int
    ):
        """Upload a single result for `name` timestamped `days_ago` days in the past."""
        timestamp = (datetime.now() - timedelta(days=days_ago)).isoformat(timespec="seconds")
        xml_file = tmp_path / f"{name}-{seq}.xml"
        failure_block = (
            '<failure message="boom">boom</failure>' if failed else ""
        )
        xml_file.write_text(f"""<?xml version="1.0" encoding="UTF-8"?>
        <testsuite name="s" tests="1" failures="{1 if failed else 0}" timestamp="{timestamp}">
            <testcase name="{name}" classname="T" time="0.1">{failure_block}</testcase>
        </testsuite>
        """)
        runner.invoke(app, ["upload", str(xml_file), "--db", str(db_path)])

    def test_trend_database_not_initialized(self, tmp_path: Path):
        """Test trend with uninitialized database."""
        db_path = tmp_path / "uninit.db"

        result = runner.invoke(app, ["trend", "--db", str(db_path)])

        assert result.exit_code == 1
        assert "Database not initialized" in result.stdout

    def test_trend_no_data(self, initialized_db: Path):
        """Test trend on an empty database."""
        result = runner.invoke(app, ["trend", "--db", str(initialized_db)])

        assert result.exit_code == 0
        assert "No trend data" in result.stdout

    def test_trend_detects_worsening(self, initialized_db: Path, tmp_path: Path):
        """Test that a test which turned flaky recently shows as worsening."""
        for i in range(5):
            self._upload_at(initialized_db, tmp_path, "test_x", False, 31 + i, i)

        for i in range(6):
            self._upload_at(initialized_db, tmp_path, "test_x", i % 2 == 1, i, 100 + i)

        result = runner.invoke(
            app, ["trend", "--db", str(initialized_db), "--min-runs", "5"]
        )

        assert result.exit_code == 0
        assert "T.test_x" in result.stdout
        assert "worsening" in result.stdout

    def test_trend_worsening_only_filter(self, initialized_db: Path, tmp_path: Path):
        """Test --worsening-only hides stable tests and keeps regressing ones."""
        for i in range(5):
            self._upload_at(initialized_db, tmp_path, "test_stable", False, 31 + i, i)
            self._upload_at(initialized_db, tmp_path, "test_stable", False, i, 100 + i)

        for i in range(5):
            self._upload_at(initialized_db, tmp_path, "test_worse", False, 31 + i, 200 + i)
        for i in range(6):
            self._upload_at(initialized_db, tmp_path, "test_worse", i % 2 == 1, i, 300 + i)

        result = runner.invoke(
            app,
            ["trend", "--db", str(initialized_db), "--min-runs", "5", "--worsening-only"],
        )

        assert result.exit_code == 0
        assert "T.test_worse" in result.stdout
        assert "T.test_stable" not in result.stdout

    def test_trend_min_runs_filter(self, initialized_db: Path, tmp_path: Path):
        """Test --min-runs excludes tests without enough history."""
        self._upload_at(initialized_db, tmp_path, "test_rare", False, 0, 1)

        result = runner.invoke(
            app, ["trend", "--db", str(initialized_db), "--min-runs", "5"]
        )

        assert result.exit_code == 0
        assert "No trend data" in result.stdout


class TestNotifyCommand:
    """Tests for the notify command."""

    def _make_flaky(self, db_path: Path, tmp_path: Path, name: str = "test_flaky"):
        """Upload alternating pass/fail results to create a flaky test."""
        for i in range(6):
            failed = i % 2 == 1
            failure_block = '<failure message="boom">boom</failure>' if failed else ""
            xml_file = tmp_path / f"{name}-{i}.xml"
            xml_file.write_text(f"""<?xml version="1.0" encoding="UTF-8"?>
            <testsuite name="s" tests="1" failures="{1 if failed else 0}">
                <testcase name="{name}" classname="T" time="0.1">{failure_block}</testcase>
            </testsuite>
            """)
            runner.invoke(app, ["upload", str(xml_file), "--db", str(db_path)])

    def test_notify_database_not_initialized(self, tmp_path: Path):
        """Test notify with uninitialized database."""
        db_path = tmp_path / "uninit.db"

        result = runner.invoke(app, ["notify", "--db", str(db_path)])

        assert result.exit_code == 1
        assert "Database not initialized" in result.stdout

    def test_notify_no_flaky_tests(self, initialized_db: Path, monkeypatch):
        """Test notify when nothing is currently flaky."""
        monkeypatch.delenv("FLAKTOR_WEBHOOK_URL", raising=False)

        result = runner.invoke(app, ["notify", "--db", str(initialized_db)])

        assert result.exit_code == 0
        assert "No new flaky tests" in result.stdout

    def test_notify_no_webhook_configured(
        self, initialized_db: Path, tmp_path: Path, monkeypatch
    ):
        """Test notify warns and doesn't record state when no webhook is set."""
        monkeypatch.delenv("FLAKTOR_WEBHOOK_URL", raising=False)
        self._make_flaky(initialized_db, tmp_path)

        result = runner.invoke(
            app, ["notify", "--db", str(initialized_db), "--min-runs", "5"]
        )

        assert result.exit_code == 0
        assert "No webhook configured" in result.stdout

        with Database(initialized_db) as db:
            assert db.get_alerted_test_names() == []

    def test_notify_dry_run(self, initialized_db: Path, tmp_path: Path, monkeypatch):
        """Test --dry-run previews the alert without sending or recording state."""
        monkeypatch.delenv("FLAKTOR_WEBHOOK_URL", raising=False)
        self._make_flaky(initialized_db, tmp_path)

        result = runner.invoke(
            app,
            ["notify", "--db", str(initialized_db), "--min-runs", "5", "--dry-run"],
        )

        assert result.exit_code == 0
        assert "T.test_flaky" in result.stdout
        assert "Dry run" in result.stdout

        with Database(initialized_db) as db:
            assert db.get_alerted_test_names() == []

    def test_notify_sends_webhook_and_records_state(
        self, initialized_db: Path, tmp_path: Path, monkeypatch
    ):
        """Test a successful send records alert state and isn't repeated next run."""
        import flaktor.cli as cli_module

        self._make_flaky(initialized_db, tmp_path)

        sent = {}

        def fake_send_webhook(url, payload):
            sent["url"] = url
            sent["payload"] = payload

        monkeypatch.setattr(cli_module, "send_webhook", fake_send_webhook)

        result = runner.invoke(
            app,
            [
                "notify", "--db", str(initialized_db), "--min-runs", "5",
                "--webhook", "https://example.com/hook",
            ],
        )

        assert result.exit_code == 0
        assert "Notification Sent" in result.stdout
        assert sent["url"] == "https://example.com/hook"
        assert sent["payload"]["count"] == 1

        with Database(initialized_db) as db:
            assert db.get_alerted_test_names() == ["T.test_flaky"]

        result_again = runner.invoke(
            app,
            [
                "notify", "--db", str(initialized_db), "--min-runs", "5",
                "--webhook", "https://example.com/hook",
            ],
        )
        assert "No new flaky tests" in result_again.stdout

    def test_notify_uses_env_var_webhook(
        self, initialized_db: Path, tmp_path: Path, monkeypatch
    ):
        """Test FLAKTOR_WEBHOOK_URL is used when --webhook isn't passed."""
        import flaktor.cli as cli_module

        self._make_flaky(initialized_db, tmp_path)

        sent = {}
        monkeypatch.setattr(
            cli_module, "send_webhook", lambda url, payload: sent.update(url=url)
        )
        monkeypatch.setenv("FLAKTOR_WEBHOOK_URL", "https://example.com/env-hook")

        result = runner.invoke(
            app, ["notify", "--db", str(initialized_db), "--min-runs", "5"]
        )

        assert result.exit_code == 0
        assert sent["url"] == "https://example.com/env-hook"

    def test_notify_webhook_failure_not_recorded(
        self, initialized_db: Path, tmp_path: Path, monkeypatch
    ):
        """Test a failed send reports an error and leaves alert state untouched."""
        import flaktor.cli as cli_module
        from flaktor.notifier import NotifierError

        self._make_flaky(initialized_db, tmp_path)

        def fake_send_webhook(url, payload):
            raise NotifierError("boom")

        monkeypatch.setattr(cli_module, "send_webhook", fake_send_webhook)

        result = runner.invoke(
            app,
            [
                "notify", "--db", str(initialized_db), "--min-runs", "5",
                "--webhook", "https://example.com/hook",
            ],
        )

        assert result.exit_code == 1
        assert "Failed to send webhook" in result.stdout

        with Database(initialized_db) as db:
            assert db.get_alerted_test_names() == []


class TestExportCommand:
    """Tests for the export command."""

    def test_export_summary_json(self, initialized_db: Path, sample_xml: Path, tmp_path: Path):
        """Test exporting the test summary as JSON."""
        runner.invoke(app, ["upload", str(sample_xml), "--db", str(initialized_db)])
        output_file = tmp_path / "tests.json"

        result = runner.invoke(
            app, ["export", "--db", str(initialized_db), "--output", str(output_file)]
        )

        assert result.exit_code == 0
        assert output_file.exists()

        data = json.loads(output_file.read_text())
        assert len(data) == 3
        assert {row["test_name"] for row in data} == {
            "TestClass.test_pass", "TestClass.test_fail", "TestClass.test_skip"
        }

    def test_export_summary_csv(self, initialized_db: Path, sample_xml: Path, tmp_path: Path):
        """Test exporting the test summary as CSV."""
        runner.invoke(app, ["upload", str(sample_xml), "--db", str(initialized_db)])
        output_file = tmp_path / "tests.csv"

        result = runner.invoke(
            app, ["export", "--db", str(initialized_db), "--output", str(output_file)]
        )

        assert result.exit_code == 0
        rows = list(csv.DictReader(output_file.open()))
        assert len(rows) == 3
        assert "test_name" in rows[0]

    def test_export_format_overrides_extension(self, initialized_db: Path, sample_xml: Path, tmp_path: Path):
        """Test that --format overrides the inferred extension."""
        runner.invoke(app, ["upload", str(sample_xml), "--db", str(initialized_db)])
        output_file = tmp_path / "tests.txt"

        result = runner.invoke(
            app,
            ["export", "--db", str(initialized_db), "--output", str(output_file), "--format", "csv"],
        )

        assert result.exit_code == 0
        rows = list(csv.DictReader(output_file.open()))
        assert len(rows) == 3

    def test_export_single_test_history(self, initialized_db: Path, sample_xml: Path, tmp_path: Path):
        """Test exporting raw history for a single test."""
        runner.invoke(app, ["upload", str(sample_xml), "--db", str(initialized_db)])
        output_file = tmp_path / "history.json"

        result = runner.invoke(
            app,
            ["export", "--db", str(initialized_db), "--output", str(output_file), "--test", "test_pass"],
        )

        assert result.exit_code == 0
        data = json.loads(output_file.read_text())
        assert len(data) == 1
        assert data[0]["test_name"] == "TestClass.test_pass"
        assert data[0]["status"] == "passed"

    def test_export_unknown_test_fails(self, initialized_db: Path, sample_xml: Path, tmp_path: Path):
        """Test exporting a nonexistent test fails cleanly."""
        runner.invoke(app, ["upload", str(sample_xml), "--db", str(initialized_db)])
        output_file = tmp_path / "history.json"

        result = runner.invoke(
            app,
            ["export", "--db", str(initialized_db), "--output", str(output_file), "--test", "nonexistent_xyz"],
        )

        assert result.exit_code == 1
        assert "No tests found" in result.stdout
        assert not output_file.exists()

    def test_export_unsupported_format(self, initialized_db: Path, tmp_path: Path):
        """Test that an unsupported format is rejected."""
        output_file = tmp_path / "tests.yaml"

        result = runner.invoke(
            app, ["export", "--db", str(initialized_db), "--output", str(output_file)]
        )

        assert result.exit_code == 1
        assert "Unsupported format" in result.stdout

    def test_export_empty_database(self, initialized_db: Path, tmp_path: Path):
        """Test exporting an empty database produces no file."""
        output_file = tmp_path / "tests.json"

        result = runner.invoke(
            app, ["export", "--db", str(initialized_db), "--output", str(output_file)]
        )

        assert result.exit_code == 0
        assert "No data to export" in result.stdout
        assert not output_file.exists()


class TestMigrateCommand:
    """Tests for the migrate command."""

    def test_migrate_already_up_to_date(self, initialized_db: Path):
        """Test migrate on a database that's already current."""
        result = runner.invoke(app, ["migrate", "--db", str(initialized_db)])

        assert result.exit_code == 0
        assert "already up to date" in result.stdout

    def test_migrate_database_not_found(self, tmp_path: Path):
        """Test migrate with non-existent database."""
        db_path = tmp_path / "nonexistent.db"

        result = runner.invoke(app, ["migrate", "--db", str(db_path)])

        assert result.exit_code == 1
        assert "Database not found" in result.stdout

    def test_migrate_applies_pending_migration(self, initialized_db: Path, monkeypatch):
        """Test migrate applies a pending migration and reports it."""
        import flaktor.database as database_module

        def _add_marker_column(cursor):
            cursor.execute("ALTER TABLE metadata ADD COLUMN marker TEXT")

        next_version = database_module.CURRENT_SCHEMA_VERSION + 1
        monkeypatch.setattr(
            database_module,
            "_MIGRATIONS",
            [(next_version, "add marker column", _add_marker_column)],
        )

        result = runner.invoke(app, ["migrate", "--db", str(initialized_db)])

        assert result.exit_code == 0
        assert "Migration complete" in result.stdout
        assert f"v{next_version}" in result.stdout


class TestCleanCommand:
    """Tests for the clean command."""

    def test_clean_nothing_to_delete(self, initialized_db: Path, sample_xml: Path):
        """Test clean when no old data exists."""
        runner.invoke(app, ["upload", str(sample_xml), "--db", str(initialized_db)])

        result = runner.invoke(
            app, ["clean", "--db", str(initialized_db)]
        )

        assert result.exit_code == 0
        assert "already clean" in result.stdout

    def test_clean_dry_run(self, initialized_db: Path, tmp_path: Path):
        """Test clean with dry run option."""
        # Create XML with old timestamps
        old_xml = tmp_path / "old_results.xml"
        old_xml.write_text("""<?xml version="1.0" encoding="UTF-8"?>
        <testsuite name="TestClass" tests="1" timestamp="2025-01-01T10:00:00">
            <testcase name="test_old" classname="TestClass" time="0.1"/>
        </testsuite>
        """)
        runner.invoke(app, ["upload", str(old_xml), "--db", str(initialized_db)])

        result = runner.invoke(
            app, ["clean", "--db", str(initialized_db), "--dry-run", "--days", "30"]
        )

        assert result.exit_code == 0
        assert "dry run" in result.stdout.lower()

    def test_clean_with_force(self, initialized_db: Path, tmp_path: Path):
        """Test clean with force flag skips confirmation."""
        # Create XML with old timestamps
        old_xml = tmp_path / "old_results.xml"
        old_xml.write_text("""<?xml version="1.0" encoding="UTF-8"?>
        <testsuite name="TestClass" tests="1" timestamp="2025-01-01T10:00:00">
            <testcase name="test_old" classname="TestClass" time="0.1"/>
        </testsuite>
        """)
        runner.invoke(app, ["upload", str(old_xml), "--db", str(initialized_db)])

        result = runner.invoke(
            app, ["clean", "--db", str(initialized_db), "--force", "--days", "30"]
        )

        assert result.exit_code == 0
        assert "Cleanup complete" in result.stdout

    def test_clean_database_not_initialized(self, tmp_path: Path):
        """Test clean fails if database not initialized."""
        db_path = tmp_path / ".flaktor" / "flaktor.db"

        result = runner.invoke(app, ["clean", "--db", str(db_path)])

        assert result.exit_code == 1
        assert "not initialized" in result.stdout


class TestHistoryCommand:
    """Tests for the history command."""

    def test_history_exact_match(self, initialized_db: Path, sample_xml: Path):
        """Test history with exact test name."""
        runner.invoke(app, ["upload", str(sample_xml), "--db", str(initialized_db)])

        result = runner.invoke(
            app, ["history", "TestClass.test_pass", "--db", str(initialized_db)]
        )

        assert result.exit_code == 0
        assert "Test History" in result.stdout
        assert "Statistics" in result.stdout

    def test_history_partial_match_single(self, initialized_db: Path, sample_xml: Path):
        """Test history with partial match that finds one test."""
        runner.invoke(app, ["upload", str(sample_xml), "--db", str(initialized_db)])

        result = runner.invoke(
            app, ["history", "test_pass", "--db", str(initialized_db)]
        )

        assert result.exit_code == 0
        assert "Test History" in result.stdout

    def test_history_partial_match_multiple(self, initialized_db: Path, sample_xml: Path):
        """Test history with partial match that finds multiple tests."""
        runner.invoke(app, ["upload", str(sample_xml), "--db", str(initialized_db)])

        result = runner.invoke(
            app, ["history", "test_", "--db", str(initialized_db)]
        )

        assert result.exit_code == 0
        assert "Multiple Matches" in result.stdout

    def test_history_not_found(self, initialized_db: Path, sample_xml: Path):
        """Test history with non-existent test."""
        runner.invoke(app, ["upload", str(sample_xml), "--db", str(initialized_db)])

        result = runner.invoke(
            app, ["history", "nonexistent_test_xyz", "--db", str(initialized_db)]
        )

        assert result.exit_code == 1
        assert "No tests found" in result.stdout

    def test_history_verbose_mode(self, initialized_db: Path, sample_xml: Path):
        """Test history with verbose flag."""
        runner.invoke(app, ["upload", str(sample_xml), "--db", str(initialized_db)])

        result = runner.invoke(
            app, ["history", "test_fail", "--db", str(initialized_db), "--verbose"]
        )

        assert result.exit_code == 0
        # Verbose mode shows failure info - check for AssertionError from sample XML
        assert "AssertionError" in result.stdout or "FAIL" in result.stdout

    def test_history_with_limit(self, initialized_db: Path, sample_xml: Path):
        """Test history with custom limit."""
        runner.invoke(app, ["upload", str(sample_xml), "--db", str(initialized_db)])

        result = runner.invoke(
            app, ["history", "test_pass", "--db", str(initialized_db), "--limit", "5"]
        )

        assert result.exit_code == 0


class TestVersionFlag:
    """Tests for the --version flag."""

    def test_version_flag(self):
        """Test --version shows version info."""
        result = runner.invoke(app, ["--version"])

        assert result.exit_code == 0
        assert "Flaktor" in result.stdout
        assert "0.1.0" in result.stdout


class TestHelpFlag:
    """Tests for help functionality."""

    def test_main_help(self):
        """Test main help output."""
        result = runner.invoke(app, ["--help"])

        assert result.exit_code == 0
        assert "Flaktor" in result.stdout
        assert "init" in result.stdout
        assert "upload" in result.stdout
        assert "list" in result.stdout

    def test_command_help(self):
        """Test command-specific help."""
        result = runner.invoke(app, ["upload", "--help"])

        assert result.exit_code == 0
        assert "Upload test results" in result.stdout
