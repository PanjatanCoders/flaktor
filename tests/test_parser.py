"""Tests for the parser module."""

import pytest
from pathlib import Path
from datetime import datetime
import tempfile
import json

from flaktor.parser import (
    parse_junit_xml,
    parse_multiple_files,
    parse_cucumber_json,
    parse_playwright_json,
    parse_test_report,
    detect_format,
    ParserError,
    SUPPORTED_FORMATS,
)
from flaktor.models import TestStatus


class TestParseJunitXml:
    """Tests for parse_junit_xml function."""

    def test_parse_simple_testsuite(self, tmp_path: Path):
        """Test parsing a simple testsuite with passing tests."""
        xml_content = """<?xml version="1.0" encoding="UTF-8"?>
        <testsuite name="test_suite" tests="2" failures="0" time="1.5">
            <testcase name="test_one" classname="TestClass" time="0.5"/>
            <testcase name="test_two" classname="TestClass" time="1.0"/>
        </testsuite>
        """
        xml_file = tmp_path / "results.xml"
        xml_file.write_text(xml_content)

        result = parse_junit_xml(xml_file)

        assert result.total_tests == 2
        assert result.passed == 2
        assert result.failed == 0
        assert result.skipped == 0
        assert result.errors == 0
        assert len(result.results) == 2

    def test_parse_testsuites_root(self, tmp_path: Path):
        """Test parsing XML with testsuites as root element."""
        xml_content = """<?xml version="1.0" encoding="UTF-8"?>
        <testsuites name="All Tests" tests="3">
            <testsuite name="suite1" tests="2">
                <testcase name="test_a" classname="Suite1" time="0.1"/>
                <testcase name="test_b" classname="Suite1" time="0.2"/>
            </testsuite>
            <testsuite name="suite2" tests="1">
                <testcase name="test_c" classname="Suite2" time="0.3"/>
            </testsuite>
        </testsuites>
        """
        xml_file = tmp_path / "results.xml"
        xml_file.write_text(xml_content)

        result = parse_junit_xml(xml_file)

        assert result.total_tests == 3
        assert result.passed == 3

    def test_parse_with_failures(self, tmp_path: Path):
        """Test parsing tests with failures."""
        xml_content = """<?xml version="1.0" encoding="UTF-8"?>
        <testsuite name="test_suite" tests="2" failures="1">
            <testcase name="test_pass" classname="TestClass" time="0.5"/>
            <testcase name="test_fail" classname="TestClass" time="0.3">
                <failure message="AssertionError" type="AssertionError">
                    Traceback here
                </failure>
            </testcase>
        </testsuite>
        """
        xml_file = tmp_path / "results.xml"
        xml_file.write_text(xml_content)

        result = parse_junit_xml(xml_file)

        assert result.total_tests == 2
        assert result.passed == 1
        assert result.failed == 1

        # Check the failed test details
        failed_test = next(r for r in result.results if r.status == TestStatus.FAILED)
        assert failed_test.test_name == "TestClass.test_fail"
        assert failed_test.failure_message == "AssertionError"
        assert failed_test.failure_type == "AssertionError"
        assert "Traceback" in failed_test.stack_trace

    def test_parse_with_errors(self, tmp_path: Path):
        """Test parsing tests with errors."""
        xml_content = """<?xml version="1.0" encoding="UTF-8"?>
        <testsuite name="test_suite" tests="1" errors="1">
            <testcase name="test_error" classname="TestClass" time="0.1">
                <error message="RuntimeError" type="RuntimeError">
                    Error traceback
                </error>
            </testcase>
        </testsuite>
        """
        xml_file = tmp_path / "results.xml"
        xml_file.write_text(xml_content)

        result = parse_junit_xml(xml_file)

        assert result.total_tests == 1
        assert result.errors == 1
        assert result.results[0].status == TestStatus.ERROR

    def test_parse_with_skipped(self, tmp_path: Path):
        """Test parsing tests with skipped status."""
        xml_content = """<?xml version="1.0" encoding="UTF-8"?>
        <testsuite name="test_suite" tests="1" skipped="1">
            <testcase name="test_skip" classname="TestClass" time="0.0">
                <skipped message="Not implemented yet"/>
            </testcase>
        </testsuite>
        """
        xml_file = tmp_path / "results.xml"
        xml_file.write_text(xml_content)

        result = parse_junit_xml(xml_file)

        assert result.total_tests == 1
        assert result.skipped == 1
        assert result.results[0].status == TestStatus.SKIPPED
        assert result.results[0].failure_message == "Not implemented yet"

    def test_parse_with_custom_run_id(self, tmp_path: Path):
        """Test parsing with custom run_id."""
        xml_content = """<?xml version="1.0" encoding="UTF-8"?>
        <testsuite name="test_suite" tests="1">
            <testcase name="test_one" classname="TestClass" time="0.1"/>
        </testsuite>
        """
        xml_file = tmp_path / "results.xml"
        xml_file.write_text(xml_content)

        result = parse_junit_xml(xml_file, run_id="my-custom-run-123")

        assert result.test_run.run_id == "my-custom-run-123"
        assert result.results[0].run_id == "my-custom-run-123"

    def test_parse_with_metadata(self, tmp_path: Path):
        """Test parsing with branch, commit, and environment."""
        xml_content = """<?xml version="1.0" encoding="UTF-8"?>
        <testsuite name="test_suite" tests="1">
            <testcase name="test_one" classname="TestClass" time="0.1"/>
        </testsuite>
        """
        xml_file = tmp_path / "results.xml"
        xml_file.write_text(xml_content)

        result = parse_junit_xml(
            xml_file,
            branch="feature/test",
            commit_hash="abc123",
            environment="ci"
        )

        assert result.test_run.branch == "feature/test"
        assert result.test_run.commit_hash == "abc123"
        assert result.test_run.environment == "ci"

    def test_parse_with_timestamp(self, tmp_path: Path):
        """Test parsing XML with timestamp attribute."""
        xml_content = """<?xml version="1.0" encoding="UTF-8"?>
        <testsuite name="test_suite" tests="1" timestamp="2026-01-15T10:30:00">
            <testcase name="test_one" classname="TestClass" time="0.1"/>
        </testsuite>
        """
        xml_file = tmp_path / "results.xml"
        xml_file.write_text(xml_content)

        result = parse_junit_xml(xml_file)

        assert result.test_run.timestamp == datetime(2026, 1, 15, 10, 30, 0)

    def test_parse_file_not_found(self):
        """Test error when file doesn't exist."""
        with pytest.raises(ParserError, match="File not found"):
            parse_junit_xml(Path("/nonexistent/file.xml"))

    def test_parse_invalid_xml(self, tmp_path: Path):
        """Test error on invalid XML syntax."""
        xml_file = tmp_path / "invalid.xml"
        xml_file.write_text("not valid xml <><>")

        with pytest.raises(ParserError, match="Invalid XML syntax"):
            parse_junit_xml(xml_file)

    def test_parse_rejects_external_entity_file_read(self, tmp_path: Path):
        """A SYSTEM entity pointing at a local file must never be resolved.

        Modern libxml2 already refuses external SYSTEM entities by default
        (it raises rather than resolving), so this mainly guards against
        that default changing or differing across environments.
        """
        secret_file = tmp_path / "secret.txt"
        secret_file.write_text("super-secret-contents")

        xml_content = f"""<?xml version="1.0" encoding="UTF-8"?>
        <!DOCTYPE testsuite [
            <!ENTITY xxe SYSTEM "file://{secret_file}">
        ]>
        <testsuite name="test_suite" tests="1">
            <testcase name="test_one" classname="TestClass" time="0.1">
                <failure>&xxe;</failure>
            </testcase>
        </testsuite>
        """
        xml_file = tmp_path / "results.xml"
        xml_file.write_text(xml_content)

        try:
            result = parse_junit_xml(xml_file)
        except ParserError:
            return  # Refusing to parse is also an acceptable, safe outcome

        for test_result in result.results:
            assert "super-secret-contents" not in (test_result.failure_message or "")

    def test_parse_rejects_billion_laughs_entity_expansion(self, tmp_path: Path):
        """Internal entity expansion (the 'billion laughs' DoS) must be blocked.

        Unlike external SYSTEM entities, libxml2 expands internal entities
        by default - this only stays safe because we set resolve_entities=False.
        """
        xml_content = """<?xml version="1.0" encoding="UTF-8"?>
        <!DOCTYPE testsuite [
            <!ENTITY a "lol">
            <!ENTITY b "&a;&a;&a;&a;&a;&a;&a;&a;&a;&a;">
            <!ENTITY c "&b;&b;&b;&b;&b;&b;&b;&b;&b;&b;">
        ]>
        <testsuite name="test_suite" tests="1">
            <testcase name="test_one" classname="TestClass" time="0.1">
                <failure>&c;</failure>
            </testcase>
        </testsuite>
        """
        xml_file = tmp_path / "results.xml"
        xml_file.write_text(xml_content)

        try:
            result = parse_junit_xml(xml_file)
        except ParserError:
            return  # Refusing to parse is also an acceptable, safe outcome

        for test_result in result.results:
            expanded = (test_result.failure_message or "") + (test_result.stack_trace or "")
            assert "lol" * 10 not in expanded

    def test_parse_unexpected_root_element(self, tmp_path: Path):
        """Test error on unexpected root element."""
        xml_content = """<?xml version="1.0" encoding="UTF-8"?>
        <unexpected_root>
            <something/>
        </unexpected_root>
        """
        xml_file = tmp_path / "results.xml"
        xml_file.write_text(xml_content)

        with pytest.raises(ParserError, match="Unexpected root element"):
            parse_junit_xml(xml_file)

    def test_parse_test_name_construction(self, tmp_path: Path):
        """Test that test names are constructed correctly."""
        xml_content = """<?xml version="1.0" encoding="UTF-8"?>
        <testsuite name="test_suite" tests="2">
            <testcase name="test_with_class" classname="my.module.TestClass" time="0.1"/>
            <testcase name="test_without_class" time="0.1"/>
        </testsuite>
        """
        xml_file = tmp_path / "results.xml"
        xml_file.write_text(xml_content)

        result = parse_junit_xml(xml_file)

        names = [r.test_name for r in result.results]
        assert "my.module.TestClass.test_with_class" in names
        # When classname is missing, parser uses testsuite name as fallback
        assert "test_suite.test_without_class" in names

    def test_parse_duration_calculation(self, tmp_path: Path):
        """Test total duration calculation."""
        xml_content = """<?xml version="1.0" encoding="UTF-8"?>
        <testsuite name="test_suite" tests="3">
            <testcase name="test_a" classname="Test" time="1.5"/>
            <testcase name="test_b" classname="Test" time="2.5"/>
            <testcase name="test_c" classname="Test" time="1.0"/>
        </testsuite>
        """
        xml_file = tmp_path / "results.xml"
        xml_file.write_text(xml_content)

        result = parse_junit_xml(xml_file)

        assert result.total_duration == 5.0


class TestParseMultipleFiles:
    """Tests for parse_multiple_files function."""

    def test_parse_multiple_files(self, tmp_path: Path):
        """Test parsing multiple XML files."""
        xml1 = """<?xml version="1.0" encoding="UTF-8"?>
        <testsuite name="suite1" tests="2">
            <testcase name="test_a" classname="Suite1" time="0.1"/>
            <testcase name="test_b" classname="Suite1" time="0.2"/>
        </testsuite>
        """
        xml2 = """<?xml version="1.0" encoding="UTF-8"?>
        <testsuite name="suite2" tests="1">
            <testcase name="test_c" classname="Suite2" time="0.3"/>
        </testsuite>
        """

        file1 = tmp_path / "results1.xml"
        file2 = tmp_path / "results2.xml"
        file1.write_text(xml1)
        file2.write_text(xml2)

        result, errors = parse_multiple_files([file1, file2])

        assert result.total_tests == 3
        assert result.passed == 3
        assert len(errors) == 0

    def test_parse_multiple_with_shared_run_id(self, tmp_path: Path):
        """Test that multiple files share the same run_id."""
        xml1 = """<?xml version="1.0" encoding="UTF-8"?>
        <testsuite name="suite1" tests="1">
            <testcase name="test_a" classname="Suite1" time="0.1"/>
        </testsuite>
        """
        xml2 = """<?xml version="1.0" encoding="UTF-8"?>
        <testsuite name="suite2" tests="1">
            <testcase name="test_b" classname="Suite2" time="0.1"/>
        </testsuite>
        """

        file1 = tmp_path / "results1.xml"
        file2 = tmp_path / "results2.xml"
        file1.write_text(xml1)
        file2.write_text(xml2)

        result, _ = parse_multiple_files([file1, file2], run_id="shared-run")

        assert result.test_run.run_id == "shared-run"
        assert all(r.run_id == "shared-run" for r in result.results)

    def test_parse_multiple_with_errors(self, tmp_path: Path):
        """Test parsing continues when some files have errors."""
        valid_xml = """<?xml version="1.0" encoding="UTF-8"?>
        <testsuite name="suite1" tests="1">
            <testcase name="test_a" classname="Suite1" time="0.1"/>
        </testsuite>
        """
        invalid_xml = "not valid xml"

        valid_file = tmp_path / "valid.xml"
        invalid_file = tmp_path / "invalid.xml"
        valid_file.write_text(valid_xml)
        invalid_file.write_text(invalid_xml)

        result, errors = parse_multiple_files([valid_file, invalid_file])

        assert result.total_tests == 1
        assert len(errors) == 1
        assert "Invalid XML syntax" in errors[0]

    def test_parse_multiple_combines_stats(self, tmp_path: Path):
        """Test that stats are combined correctly from multiple files."""
        xml1 = """<?xml version="1.0" encoding="UTF-8"?>
        <testsuite name="suite1" tests="2" failures="1">
            <testcase name="test_pass" classname="Suite1" time="0.1"/>
            <testcase name="test_fail" classname="Suite1" time="0.1">
                <failure message="Failed"/>
            </testcase>
        </testsuite>
        """
        xml2 = """<?xml version="1.0" encoding="UTF-8"?>
        <testsuite name="suite2" tests="2" skipped="1">
            <testcase name="test_pass2" classname="Suite2" time="0.1"/>
            <testcase name="test_skip" classname="Suite2" time="0.0">
                <skipped/>
            </testcase>
        </testsuite>
        """

        file1 = tmp_path / "results1.xml"
        file2 = tmp_path / "results2.xml"
        file1.write_text(xml1)
        file2.write_text(xml2)

        result, _ = parse_multiple_files([file1, file2])

        assert result.total_tests == 4
        assert result.passed == 2
        assert result.failed == 1
        assert result.skipped == 1


class TestParseCucumberJson:
    """Tests for parse_cucumber_json function."""

    def test_parse_simple_cucumber(self, tmp_path: Path):
        """Test parsing a simple Cucumber JSON report."""
        cucumber_data = [
            {
                "keyword": "Feature",
                "name": "Login Feature",
                "uri": "features/login.feature",
                "elements": [
                    {
                        "type": "scenario",
                        "name": "Valid login",
                        "steps": [
                            {
                                "keyword": "Given",
                                "name": "I am on the login page",
                                "result": {"status": "passed", "duration": 100000000}
                            },
                            {
                                "keyword": "When",
                                "name": "I enter valid credentials",
                                "result": {"status": "passed", "duration": 200000000}
                            },
                            {
                                "keyword": "Then",
                                "name": "I should see the dashboard",
                                "result": {"status": "passed", "duration": 150000000}
                            }
                        ]
                    }
                ]
            }
        ]

        json_file = tmp_path / "cucumber.json"
        json_file.write_text(json.dumps(cucumber_data))

        result = parse_cucumber_json(json_file)

        assert result.total_tests == 1
        assert result.passed == 1
        assert result.failed == 0
        assert result.results[0].test_name == "Login Feature.Valid login"
        assert result.results[0].duration == pytest.approx(0.45, rel=0.01)

    def test_parse_cucumber_with_failure(self, tmp_path: Path):
        """Test parsing Cucumber JSON with failed scenario."""
        cucumber_data = [
            {
                "keyword": "Feature",
                "name": "Search Feature",
                "uri": "features/search.feature",
                "elements": [
                    {
                        "type": "scenario",
                        "name": "Search returns results",
                        "steps": [
                            {
                                "keyword": "Given",
                                "name": "I am on the search page",
                                "result": {"status": "passed", "duration": 100000000}
                            },
                            {
                                "keyword": "When",
                                "name": "I search for something",
                                "result": {
                                    "status": "failed",
                                    "duration": 50000000,
                                    "error_message": "AssertionError: Expected results"
                                }
                            },
                            {
                                "keyword": "Then",
                                "name": "I should see results",
                                "result": {"status": "skipped", "duration": 0}
                            }
                        ]
                    }
                ]
            }
        ]

        json_file = tmp_path / "cucumber.json"
        json_file.write_text(json.dumps(cucumber_data))

        result = parse_cucumber_json(json_file)

        assert result.total_tests == 1
        assert result.failed == 1
        assert result.results[0].status == TestStatus.FAILED
        assert "AssertionError" in result.results[0].failure_message

    def test_parse_cucumber_multiple_scenarios(self, tmp_path: Path):
        """Test parsing Cucumber JSON with multiple scenarios."""
        cucumber_data = [
            {
                "keyword": "Feature",
                "name": "User Feature",
                "uri": "features/user.feature",
                "elements": [
                    {
                        "type": "scenario",
                        "name": "Create user",
                        "steps": [{"result": {"status": "passed", "duration": 100000000}}]
                    },
                    {
                        "type": "scenario",
                        "name": "Delete user",
                        "steps": [{"result": {"status": "passed", "duration": 100000000}}]
                    },
                    {
                        "type": "background",
                        "name": "Setup",
                        "steps": [{"result": {"status": "passed", "duration": 50000000}}]
                    }
                ]
            }
        ]

        json_file = tmp_path / "cucumber.json"
        json_file.write_text(json.dumps(cucumber_data))

        result = parse_cucumber_json(json_file)

        # Background should not be counted as a test
        assert result.total_tests == 2

    def test_parse_cucumber_file_not_found(self, tmp_path: Path):
        """Test error when file doesn't exist."""
        with pytest.raises(ParserError, match="File not found"):
            parse_cucumber_json(tmp_path / "nonexistent.json")

    def test_parse_cucumber_invalid_json(self, tmp_path: Path):
        """Test error on invalid JSON."""
        json_file = tmp_path / "invalid.json"
        json_file.write_text("not valid json")

        with pytest.raises(ParserError, match="Invalid JSON"):
            parse_cucumber_json(json_file)


class TestParsePlaywrightJson:
    """Tests for parse_playwright_json function."""

    def test_parse_simple_playwright(self, tmp_path: Path):
        """Test parsing a simple Playwright JSON report."""
        playwright_data = {
            "config": {},
            "suites": [
                {
                    "title": "tests/example.spec.ts",
                    "specs": [
                        {
                            "title": "has title",
                            "tests": [
                                {
                                    "projectName": "chromium",
                                    "results": [
                                        {
                                            "status": "passed",
                                            "duration": 1500
                                        }
                                    ]
                                }
                            ]
                        }
                    ],
                    "suites": []
                }
            ]
        }

        json_file = tmp_path / "playwright.json"
        json_file.write_text(json.dumps(playwright_data))

        result = parse_playwright_json(json_file)

        assert result.total_tests == 1
        assert result.passed == 1
        assert "[chromium]" in result.results[0].test_name
        assert result.results[0].duration == pytest.approx(1.5, rel=0.01)

    def test_parse_playwright_with_failure(self, tmp_path: Path):
        """Test parsing Playwright JSON with failed test."""
        playwright_data = {
            "config": {},
            "suites": [
                {
                    "title": "tests/example.spec.ts",
                    "specs": [
                        {
                            "title": "should fail",
                            "tests": [
                                {
                                    "projectName": "firefox",
                                    "results": [
                                        {
                                            "status": "failed",
                                            "duration": 2000,
                                            "error": {
                                                "message": "Error: expect(received).toBe(expected)",
                                                "stack": "at Object.<anonymous> (test.spec.ts:10:5)"
                                            }
                                        }
                                    ]
                                }
                            ]
                        }
                    ],
                    "suites": []
                }
            ]
        }

        json_file = tmp_path / "playwright.json"
        json_file.write_text(json.dumps(playwright_data))

        result = parse_playwright_json(json_file)

        assert result.total_tests == 1
        assert result.failed == 1
        assert result.results[0].status == TestStatus.FAILED
        assert "expect" in result.results[0].failure_message

    def test_parse_playwright_nested_suites(self, tmp_path: Path):
        """Test parsing Playwright JSON with nested describe blocks."""
        playwright_data = {
            "config": {},
            "suites": [
                {
                    "title": "tests/nested.spec.ts",
                    "specs": [],
                    "suites": [
                        {
                            "title": "outer describe",
                            "specs": [],
                            "suites": [
                                {
                                    "title": "inner describe",
                                    "specs": [
                                        {
                                            "title": "nested test",
                                            "tests": [
                                                {
                                                    "results": [{"status": "passed", "duration": 100}]
                                                }
                                            ]
                                        }
                                    ],
                                    "suites": []
                                }
                            ]
                        }
                    ]
                }
            ]
        }

        json_file = tmp_path / "playwright.json"
        json_file.write_text(json.dumps(playwright_data))

        result = parse_playwright_json(json_file)

        assert result.total_tests == 1
        assert "outer describe" in result.results[0].test_name
        assert "inner describe" in result.results[0].test_name
        assert "nested test" in result.results[0].test_name

    def test_parse_playwright_with_retries(self, tmp_path: Path):
        """Test that last attempt is used when test has retries."""
        playwright_data = {
            "config": {},
            "suites": [
                {
                    "title": "tests/retry.spec.ts",
                    "specs": [
                        {
                            "title": "flaky test",
                            "tests": [
                                {
                                    "results": [
                                        {"status": "failed", "duration": 100},
                                        {"status": "failed", "duration": 100},
                                        {"status": "passed", "duration": 100}
                                    ]
                                }
                            ]
                        }
                    ],
                    "suites": []
                }
            ]
        }

        json_file = tmp_path / "playwright.json"
        json_file.write_text(json.dumps(playwright_data))

        result = parse_playwright_json(json_file)

        # Should use the last result (passed)
        assert result.total_tests == 1
        assert result.passed == 1

    def test_parse_playwright_file_not_found(self, tmp_path: Path):
        """Test error when file doesn't exist."""
        with pytest.raises(ParserError, match="File not found"):
            parse_playwright_json(tmp_path / "nonexistent.json")


class TestDetectFormat:
    """Tests for format detection."""

    def test_detect_xml_format(self, tmp_path: Path):
        """Test detection of XML files as JUnit."""
        xml_file = tmp_path / "results.xml"
        xml_file.write_text("<testsuite/>")

        assert detect_format(xml_file) == "junit"

    def test_detect_cucumber_format(self, tmp_path: Path):
        """Test detection of Cucumber JSON."""
        cucumber_data = [{"keyword": "Feature", "name": "Test", "elements": []}]
        json_file = tmp_path / "cucumber.json"
        json_file.write_text(json.dumps(cucumber_data))

        assert detect_format(json_file) == "cucumber"

    def test_detect_playwright_format(self, tmp_path: Path):
        """Test detection of Playwright JSON."""
        playwright_data = {"config": {}, "suites": []}
        json_file = tmp_path / "playwright.json"
        json_file.write_text(json.dumps(playwright_data))

        assert detect_format(json_file) == "playwright"

    def test_detect_unknown_extension(self, tmp_path: Path):
        """Test error on unknown file extension."""
        txt_file = tmp_path / "results.txt"
        txt_file.write_text("data")

        with pytest.raises(ParserError, match="Unknown file extension"):
            detect_format(txt_file)


class TestParseTestReport:
    """Tests for unified parse_test_report function."""

    def test_parse_junit_auto(self, tmp_path: Path):
        """Test auto-detection and parsing of JUnit XML."""
        xml_content = """<?xml version="1.0"?>
        <testsuite name="suite" tests="1">
            <testcase name="test" classname="Class" time="0.1"/>
        </testsuite>
        """
        xml_file = tmp_path / "results.xml"
        xml_file.write_text(xml_content)

        result = parse_test_report(xml_file)

        assert result.total_tests == 1

    def test_parse_with_explicit_format(self, tmp_path: Path):
        """Test parsing with explicitly specified format."""
        cucumber_data = [{"keyword": "Feature", "name": "Test", "uri": "test.feature", "elements": []}]
        json_file = tmp_path / "report.json"
        json_file.write_text(json.dumps(cucumber_data))

        result = parse_test_report(json_file, format="cucumber")

        assert result.total_tests == 0  # No scenarios

    def test_parse_unknown_format_error(self, tmp_path: Path):
        """Test error on unknown format."""
        json_file = tmp_path / "report.json"
        json_file.write_text("{}")

        with pytest.raises(ParserError, match="Unknown format"):
            parse_test_report(json_file, format="unknown")
