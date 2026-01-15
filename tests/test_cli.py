"""Tests for the CLI module."""

import pytest
from pathlib import Path
from typer.testing import CliRunner
from datetime import datetime

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
    xml_content = """<?xml version="1.0" encoding="UTF-8"?>
    <testsuite name="test_suite" tests="3" failures="1" timestamp="2026-01-15T10:00:00">
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
        assert "No valid XML files found" in result.stdout

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
