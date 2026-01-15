"""
Data models for Flaktor.

Defines the core data structures used throughout the application.
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional, Dict, Any


class TestStatus(Enum):
    """Possible outcomes for a test execution."""
    PASSED = "passed"
    FAILED = "failed"
    SKIPPED = "skipped"
    ERROR = "error"


@dataclass
class TestRun:
    """
    Represents a CI/CD test run (build).

    Attributes:
        run_id: Unique identifier for this run (e.g., CI build ID)
        timestamp: When the test run occurred
        branch: Git branch name (optional)
        commit_hash: Git commit hash (optional)
        environment: Environment name like 'ci', 'staging' (optional)
        metadata: Additional key-value data (optional)
    """
    run_id: str
    timestamp: datetime
    branch: Optional[str] = None
    commit_hash: Optional[str] = None
    environment: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = field(default_factory=dict)


@dataclass
class TestResult:
    """
    Represents an individual test case result.

    Attributes:
        test_name: Full test identifier (e.g., 'test_module.TestClass.test_method')
        status: Test outcome (passed, failed, skipped, error)
        duration: Test execution time in seconds
        run_id: Reference to the parent TestRun
        timestamp: When this test executed
        class_name: Test class name (optional)
        failure_message: Error message if test failed (optional)
        failure_type: Exception type if test failed (optional)
        stack_trace: Full stack trace if test failed (optional)
    """
    test_name: str
    status: TestStatus
    duration: float
    run_id: str
    timestamp: datetime
    class_name: Optional[str] = None
    failure_message: Optional[str] = None
    failure_type: Optional[str] = None
    stack_trace: Optional[str] = None
