"""
XML Parser for test results.

Supports JUnit and xUnit XML formats from various test frameworks:
- pytest (Python)
- JUnit (Java)
- NUnit (C#)
- Jest (JavaScript)
- PHPUnit (PHP)
- And many more...
"""

from pathlib import Path
from datetime import datetime
from typing import List, Optional, Tuple
from dataclasses import dataclass
import uuid

from lxml import etree

from .models import TestResult, TestRun, TestStatus


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
        tree = etree.parse(str(file_path))
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
