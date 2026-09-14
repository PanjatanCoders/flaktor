"""
Parser for test results.

Supports multiple test report formats:
- JUnit/xUnit XML (pytest, JUnit, NUnit, Jest, PHPUnit, etc.)
- Cucumber JSON (BDD frameworks)
- Playwright JSON (Playwright test runner)
"""

from pathlib import Path
from datetime import datetime
from typing import List, Optional, Tuple, Dict, Any
from dataclasses import dataclass
import uuid
import json

from lxml import etree

from .models import TestResult, TestRun, TestStatus


# Supported file formats
SUPPORTED_FORMATS = ["junit", "cucumber", "playwright"]

# Hardened XML parser: disables external entity resolution and network
# access to prevent XXE (XML external entity) attacks from untrusted
# test report files.
_XML_PARSER = etree.XMLParser(
    resolve_entities=False,
    no_network=True,
    dtd_validation=False,
    load_dtd=False,
    huge_tree=False,
)


class ParserError(Exception):
    """Custom exception for parsing errors with helpful context."""
    pass


@dataclass
class ParsedResults:
    """Container for parsed test results."""
    test_run: TestRun
    results: List[TestResult]
    total_tests: int
    passed: int
    failed: int
    skipped: int
    errors: int
    total_duration: float


def parse_junit_xml(
    file_path: Path,
    run_id: Optional[str] = None,
    branch: Optional[str] = None,
    commit_hash: Optional[str] = None,
    environment: Optional[str] = None,
) -> ParsedResults:
    """
    Parse a JUnit/xUnit XML file into TestRun and TestResult objects.

    Args:
        file_path: Path to the XML file
        run_id: Optional run identifier (auto-generated if not provided)
        branch: Optional git branch name
        commit_hash: Optional git commit hash
        environment: Optional environment name

    Returns:
        ParsedResults containing the test run and all test results

    Raises:
        ParserError: If the file cannot be parsed
    """
    if not file_path.exists():
        raise ParserError(f"File not found: {file_path}")

    try:
        tree = etree.parse(str(file_path), parser=_XML_PARSER)
        root = tree.getroot()
    except etree.XMLSyntaxError as e:
        raise ParserError(f"Invalid XML syntax in {file_path}: {e}")
    except Exception as e:
        raise ParserError(f"Failed to parse {file_path}: {e}")

    # Generate run_id if not provided
    if not run_id:
        run_id = f"run-{uuid.uuid4().hex[:12]}"

    # Determine timestamp from file or current time
    timestamp = _extract_timestamp(root) or datetime.now()

    # Create TestRun
    test_run = TestRun(
        run_id=run_id,
        timestamp=timestamp,
        branch=branch,
        commit_hash=commit_hash,
        environment=environment,
    )

    # Parse test cases
    results: List[TestResult] = []

    # Handle both single testsuite and testsuites root elements
    if root.tag == "testsuites":
        testsuites = root.findall("testsuite")
    elif root.tag == "testsuite":
        testsuites = [root]
    else:
        raise ParserError(
            f"Unexpected root element '{root.tag}'. "
            f"Expected 'testsuites' or 'testsuite'."
        )

    for testsuite in testsuites:
        suite_name = testsuite.get("name", "")
        suite_timestamp = _parse_timestamp(testsuite.get("timestamp"))

        for testcase in testsuite.findall("testcase"):
            result = _parse_testcase(
                testcase,
                run_id,
                suite_name,
                suite_timestamp or timestamp
            )
            results.append(result)

    # Calculate statistics
    passed = sum(1 for r in results if r.status == TestStatus.PASSED)
    failed = sum(1 for r in results if r.status == TestStatus.FAILED)
    skipped = sum(1 for r in results if r.status == TestStatus.SKIPPED)
    errors = sum(1 for r in results if r.status == TestStatus.ERROR)
    total_duration = sum(r.duration for r in results)

    return ParsedResults(
        test_run=test_run,
        results=results,
        total_tests=len(results),
        passed=passed,
        failed=failed,
        skipped=skipped,
        errors=errors,
        total_duration=total_duration,
    )


def _parse_testcase(
    testcase: etree._Element,
    run_id: str,
    suite_name: str,
    timestamp: datetime,
) -> TestResult:
    """Parse a single testcase element into a TestResult."""

    # Extract test identifiers
    test_name = testcase.get("name", "unknown")
    class_name = testcase.get("classname", suite_name) or None

    # Build full test name
    if class_name:
        full_name = f"{class_name}.{test_name}"
    else:
        full_name = test_name

    # Extract duration
    time_str = testcase.get("time", "0")
    try:
        duration = float(time_str)
    except ValueError:
        duration = 0.0

    # Determine status and failure info
    status = TestStatus.PASSED
    failure_message = None
    failure_type = None
    stack_trace = None

    # Check for failure
    failure = testcase.find("failure")
    if failure is not None:
        status = TestStatus.FAILED
        failure_message = failure.get("message", "")
        failure_type = failure.get("type", "")
        stack_trace = failure.text

    # Check for error
    error = testcase.find("error")
    if error is not None:
        status = TestStatus.ERROR
        failure_message = error.get("message", "")
        failure_type = error.get("type", "")
        stack_trace = error.text

    # Check for skipped
    skipped = testcase.find("skipped")
    if skipped is not None:
        status = TestStatus.SKIPPED
        failure_message = skipped.get("message", "")

    return TestResult(
        test_name=full_name,
        class_name=class_name,
        status=status,
        duration=duration,
        run_id=run_id,
        timestamp=timestamp,
        failure_message=failure_message,
        failure_type=failure_type,
        stack_trace=stack_trace,
    )


def _extract_timestamp(root: etree._Element) -> Optional[datetime]:
    """Extract timestamp from root element or first testsuite."""
    # Try root element
    ts = root.get("timestamp")
    if ts:
        return _parse_timestamp(ts)

    # Try first testsuite
    if root.tag == "testsuites":
        first_suite = root.find("testsuite")
        if first_suite is not None:
            ts = first_suite.get("timestamp")
            if ts:
                return _parse_timestamp(ts)

    return None


def _parse_timestamp(ts: Optional[str]) -> Optional[datetime]:
    """Parse various timestamp formats."""
    if not ts:
        return None

    # Common formats
    formats = [
        "%Y-%m-%dT%H:%M:%S",      # ISO format without microseconds
        "%Y-%m-%dT%H:%M:%S.%f",   # ISO format with microseconds
        "%Y-%m-%d %H:%M:%S",      # Space separator
        "%Y-%m-%dT%H:%M:%SZ",     # ISO with Z suffix
    ]

    for fmt in formats:
        try:
            return datetime.strptime(ts.split("+")[0].split("Z")[0], fmt)
        except ValueError:
            continue

    return None


def parse_multiple_files(
    file_paths: List[Path],
    run_id: Optional[str] = None,
    branch: Optional[str] = None,
    commit_hash: Optional[str] = None,
    environment: Optional[str] = None,
) -> Tuple[ParsedResults, List[str]]:
    """
    Parse multiple XML files and combine results.

    Args:
        file_paths: List of paths to XML files
        run_id: Optional run identifier (shared across all files)
        branch: Optional git branch name
        commit_hash: Optional git commit hash
        environment: Optional environment name

    Returns:
        Tuple of (combined ParsedResults, list of error messages)
    """
    if not run_id:
        run_id = f"run-{uuid.uuid4().hex[:12]}"

    all_results: List[TestResult] = []
    errors_list: List[str] = []
    timestamp = datetime.now()

    for file_path in file_paths:
        try:
            parsed = parse_junit_xml(
                file_path,
                run_id=run_id,
                branch=branch,
                commit_hash=commit_hash,
                environment=environment,
            )
            all_results.extend(parsed.results)
            if parsed.test_run.timestamp < timestamp:
                timestamp = parsed.test_run.timestamp
        except ParserError as e:
            errors_list.append(str(e))

    test_run = TestRun(
        run_id=run_id,
        timestamp=timestamp,
        branch=branch,
        commit_hash=commit_hash,
        environment=environment,
    )

    passed = sum(1 for r in all_results if r.status == TestStatus.PASSED)
    failed = sum(1 for r in all_results if r.status == TestStatus.FAILED)
    skipped = sum(1 for r in all_results if r.status == TestStatus.SKIPPED)
    errors = sum(1 for r in all_results if r.status == TestStatus.ERROR)
    total_duration = sum(r.duration for r in all_results)

    return ParsedResults(
        test_run=test_run,
        results=all_results,
        total_tests=len(all_results),
        passed=passed,
        failed=failed,
        skipped=skipped,
        errors=errors,
        total_duration=total_duration,
    ), errors_list


# =============================================================================
# Cucumber JSON Parser
# =============================================================================

def parse_cucumber_json(
    file_path: Path,
    run_id: Optional[str] = None,
    branch: Optional[str] = None,
    commit_hash: Optional[str] = None,
    environment: Optional[str] = None,
) -> ParsedResults:
    """
    Parse a Cucumber JSON report file into TestRun and TestResult objects.

    Cucumber JSON format contains features with scenarios, each scenario
    having multiple steps. We treat each scenario as a test case.

    Args:
        file_path: Path to the Cucumber JSON file
        run_id: Optional run identifier (auto-generated if not provided)
        branch: Optional git branch name
        commit_hash: Optional git commit hash
        environment: Optional environment name

    Returns:
        ParsedResults containing the test run and all test results

    Raises:
        ParserError: If the file cannot be parsed
    """
    if not file_path.exists():
        raise ParserError(f"File not found: {file_path}")

    try:
        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except json.JSONDecodeError as e:
        raise ParserError(f"Invalid JSON syntax in {file_path}: {e}")
    except Exception as e:
        raise ParserError(f"Failed to read {file_path}: {e}")

    if not isinstance(data, list):
        raise ParserError(
            f"Expected Cucumber JSON to be an array of features, got {type(data).__name__}"
        )

    # Generate run_id if not provided
    if not run_id:
        run_id = f"run-{uuid.uuid4().hex[:12]}"

    timestamp = datetime.now()
    results: List[TestResult] = []

    for feature in data:
        feature_name = feature.get("name", "Unknown Feature")
        feature_uri = feature.get("uri", "")

        elements = feature.get("elements", [])
        for element in elements:
            # Only process scenarios (not background)
            if element.get("type") not in ("scenario", "scenario_outline"):
                continue

            scenario_name = element.get("name", "Unknown Scenario")
            full_name = f"{feature_name}.{scenario_name}"

            # Parse steps to determine status and duration
            steps = element.get("steps", [])
            scenario_status = TestStatus.PASSED
            scenario_duration = 0.0
            failure_message = None
            failure_type = None
            stack_trace = None

            for step in steps:
                result = step.get("result", {})
                step_status = result.get("status", "passed")
                step_duration = result.get("duration", 0)

                # Duration in Cucumber is in nanoseconds
                scenario_duration += step_duration / 1_000_000_000

                if step_status == "failed":
                    scenario_status = TestStatus.FAILED
                    failure_message = result.get("error_message", "")
                    failure_type = "StepFailure"
                    # Extract first line as type, rest as trace
                    if failure_message:
                        lines = failure_message.split("\n")
                        if len(lines) > 1:
                            failure_type = lines[0][:100]
                            stack_trace = "\n".join(lines[1:])
                elif step_status == "skipped" and scenario_status == TestStatus.PASSED:
                    scenario_status = TestStatus.SKIPPED
                elif step_status == "pending" and scenario_status == TestStatus.PASSED:
                    scenario_status = TestStatus.SKIPPED
                elif step_status == "undefined" and scenario_status == TestStatus.PASSED:
                    scenario_status = TestStatus.SKIPPED
                    failure_message = "Undefined step"

            # Extract timestamp if available
            scenario_timestamp = timestamp
            if "start_timestamp" in element:
                parsed_ts = _parse_timestamp(element["start_timestamp"])
                if parsed_ts:
                    scenario_timestamp = parsed_ts

            results.append(TestResult(
                test_name=full_name,
                class_name=feature_name,
                status=scenario_status,
                duration=scenario_duration,
                run_id=run_id,
                timestamp=scenario_timestamp,
                failure_message=failure_message,
                failure_type=failure_type,
                stack_trace=stack_trace,
            ))

    test_run = TestRun(
        run_id=run_id,
        timestamp=timestamp,
        branch=branch,
        commit_hash=commit_hash,
        environment=environment,
    )

    passed = sum(1 for r in results if r.status == TestStatus.PASSED)
    failed = sum(1 for r in results if r.status == TestStatus.FAILED)
    skipped = sum(1 for r in results if r.status == TestStatus.SKIPPED)
    errors = sum(1 for r in results if r.status == TestStatus.ERROR)
    total_duration = sum(r.duration for r in results)

    return ParsedResults(
        test_run=test_run,
        results=results,
        total_tests=len(results),
        passed=passed,
        failed=failed,
        skipped=skipped,
        errors=errors,
        total_duration=total_duration,
    )


# =============================================================================
# Playwright JSON Parser
# =============================================================================

def parse_playwright_json(
    file_path: Path,
    run_id: Optional[str] = None,
    branch: Optional[str] = None,
    commit_hash: Optional[str] = None,
    environment: Optional[str] = None,
) -> ParsedResults:
    """
    Parse a Playwright JSON report file into TestRun and TestResult objects.

    Playwright JSON reporter outputs a structure with suites containing
    specs (test files) which contain tests.

    Args:
        file_path: Path to the Playwright JSON file
        run_id: Optional run identifier (auto-generated if not provided)
        branch: Optional git branch name
        commit_hash: Optional git commit hash
        environment: Optional environment name

    Returns:
        ParsedResults containing the test run and all test results

    Raises:
        ParserError: If the file cannot be parsed
    """
    if not file_path.exists():
        raise ParserError(f"File not found: {file_path}")

    try:
        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except json.JSONDecodeError as e:
        raise ParserError(f"Invalid JSON syntax in {file_path}: {e}")
    except Exception as e:
        raise ParserError(f"Failed to read {file_path}: {e}")

    # Generate run_id if not provided
    if not run_id:
        run_id = f"run-{uuid.uuid4().hex[:12]}"

    # Extract timestamp from config or use current time
    timestamp = datetime.now()
    config = data.get("config", {})
    if "startTime" in config:
        # Playwright uses ISO format
        parsed_ts = _parse_timestamp(config["startTime"])
        if parsed_ts:
            timestamp = parsed_ts

    results: List[TestResult] = []

    # Process all suites recursively
    suites = data.get("suites", [])
    for suite in suites:
        _parse_playwright_suite(suite, run_id, timestamp, results)

    test_run = TestRun(
        run_id=run_id,
        timestamp=timestamp,
        branch=branch,
        commit_hash=commit_hash,
        environment=environment,
    )

    passed = sum(1 for r in results if r.status == TestStatus.PASSED)
    failed = sum(1 for r in results if r.status == TestStatus.FAILED)
    skipped = sum(1 for r in results if r.status == TestStatus.SKIPPED)
    errors = sum(1 for r in results if r.status == TestStatus.ERROR)
    total_duration = sum(r.duration for r in results)

    return ParsedResults(
        test_run=test_run,
        results=results,
        total_tests=len(results),
        passed=passed,
        failed=failed,
        skipped=skipped,
        errors=errors,
        total_duration=total_duration,
    )


def _parse_playwright_suite(
    suite: Dict[str, Any],
    run_id: str,
    timestamp: datetime,
    results: List[TestResult],
    parent_title: str = "",
) -> None:
    """Recursively parse Playwright suite structure."""
    suite_title = suite.get("title", "")

    # Build full path
    if parent_title and suite_title:
        full_title = f"{parent_title} > {suite_title}"
    else:
        full_title = parent_title or suite_title

    # Process specs (test containers)
    specs = suite.get("specs", [])
    for spec in specs:
        spec_title = spec.get("title", "Unknown Test")
        test_name = f"{full_title} > {spec_title}" if full_title else spec_title

        # Process test results (may have multiple if retried)
        tests = spec.get("tests", [])
        for test in tests:
            # Get the last result (final attempt)
            test_results = test.get("results", [])
            if not test_results:
                continue

            # Use the last result (final attempt after retries)
            result = test_results[-1]

            # Determine status
            status_str = result.get("status", "passed")
            if status_str == "passed":
                status = TestStatus.PASSED
            elif status_str == "failed":
                status = TestStatus.FAILED
            elif status_str == "timedOut":
                status = TestStatus.ERROR
            elif status_str in ("skipped", "interrupted"):
                status = TestStatus.SKIPPED
            else:
                status = TestStatus.PASSED

            # Duration in milliseconds
            duration = result.get("duration", 0) / 1000.0

            # Extract failure info
            failure_message = None
            failure_type = None
            stack_trace = None

            if status in (TestStatus.FAILED, TestStatus.ERROR):
                error = result.get("error", {})
                if error:
                    failure_message = error.get("message", "")
                    stack_trace = error.get("stack", "")
                    # Try to extract error type from message
                    if failure_message:
                        first_line = failure_message.split("\n")[0]
                        if ":" in first_line:
                            failure_type = first_line.split(":")[0]

            # Get timestamp from result if available
            result_timestamp = timestamp
            if "startTime" in result:
                parsed_ts = _parse_timestamp(result["startTime"])
                if parsed_ts:
                    result_timestamp = parsed_ts

            # Include project name if available
            project_name = test.get("projectName", "")
            if project_name:
                test_name = f"[{project_name}] {test_name}"

            results.append(TestResult(
                test_name=test_name,
                class_name=full_title or None,
                status=status,
                duration=duration,
                run_id=run_id,
                timestamp=result_timestamp,
                failure_message=failure_message,
                failure_type=failure_type,
                stack_trace=stack_trace,
            ))

    # Process nested suites
    nested_suites = suite.get("suites", [])
    for nested in nested_suites:
        _parse_playwright_suite(nested, run_id, timestamp, results, full_title)


# =============================================================================
# Auto-detection and unified parser
# =============================================================================

def detect_format(file_path: Path) -> str:
    """
    Auto-detect the format of a test report file.

    Args:
        file_path: Path to the test report file

    Returns:
        Format string: "junit", "cucumber", or "playwright"

    Raises:
        ParserError: If format cannot be detected
    """
    if not file_path.exists():
        raise ParserError(f"File not found: {file_path}")

    suffix = file_path.suffix.lower()

    # XML files are likely JUnit
    if suffix == ".xml":
        return "junit"

    # JSON files need content inspection
    if suffix == ".json":
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                data = json.load(f)

            # Cucumber: array of features with "keyword" and "elements"
            if isinstance(data, list) and len(data) > 0:
                first = data[0]
                if isinstance(first, dict):
                    if "keyword" in first and "elements" in first:
                        return "cucumber"
                    if "uri" in first and "elements" in first:
                        return "cucumber"

            # Playwright: object with "suites" and possibly "config"
            if isinstance(data, dict):
                if "suites" in data:
                    return "playwright"
                if "config" in data and "suites" in data:
                    return "playwright"

            raise ParserError(
                f"Could not determine JSON format for {file_path}. "
                f"Use --format to specify: cucumber or playwright"
            )

        except json.JSONDecodeError:
            raise ParserError(f"Invalid JSON in {file_path}")

    raise ParserError(
        f"Unknown file extension '{suffix}'. "
        f"Supported: .xml (JUnit), .json (Cucumber/Playwright)"
    )


def parse_test_report(
    file_path: Path,
    format: Optional[str] = None,
    run_id: Optional[str] = None,
    branch: Optional[str] = None,
    commit_hash: Optional[str] = None,
    environment: Optional[str] = None,
) -> ParsedResults:
    """
    Parse a test report file, auto-detecting format if not specified.

    Args:
        file_path: Path to the test report file
        format: Optional format hint ("junit", "cucumber", "playwright")
        run_id: Optional run identifier
        branch: Optional git branch name
        commit_hash: Optional git commit hash
        environment: Optional environment name

    Returns:
        ParsedResults containing the test run and all test results

    Raises:
        ParserError: If the file cannot be parsed
    """
    if format is None:
        format = detect_format(file_path)

    format = format.lower()

    if format == "junit" or format == "xml":
        return parse_junit_xml(
            file_path,
            run_id=run_id,
            branch=branch,
            commit_hash=commit_hash,
            environment=environment,
        )
    elif format == "cucumber":
        return parse_cucumber_json(
            file_path,
            run_id=run_id,
            branch=branch,
            commit_hash=commit_hash,
            environment=environment,
        )
    elif format == "playwright":
        return parse_playwright_json(
            file_path,
            run_id=run_id,
            branch=branch,
            commit_hash=commit_hash,
            environment=environment,
        )
    else:
        raise ParserError(
            f"Unknown format '{format}'. "
            f"Supported formats: {', '.join(SUPPORTED_FORMATS)}"
        )
