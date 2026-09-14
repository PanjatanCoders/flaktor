"""
MCP server for Flaktor.

Exposes flaky-test data as read-only MCP tools so AI coding agents can check
whether a failing test is a known flake before treating it as a real bug.
Mutating operations (upload, init, clean) stay CLI-only on purpose - an
agent debugging a failure should be able to look, not touch.
"""

from pathlib import Path
from typing import Optional

from mcp.server.mcpserver import MCPServer

from .database import Database


def build_server(db_path: Path) -> MCPServer:
    """Build the Flaktor MCP server bound to a specific database file."""
    server = MCPServer(
        name="flaktor",
        instructions=(
            "Query Flaktor's flaky-test history for this project. Use "
            "check_test_flakiness before debugging a failing test - if it's "
            "already a known flake, the failure likely isn't your change."
        ),
    )

    @server.tool()
    def list_flaky_tests(
        min_runs: int = 5,
        lookback_days: int = 30,
        min_flip_rate: float = 0.1,
    ) -> list[dict]:
        """
        List tests currently flagged as flaky.

        Args:
            min_runs: Minimum number of runs a test needs before it's evaluated.
            lookback_days: How many days of history to consider.
            min_flip_rate: Minimum flip rate (0.0-1.0) to count as flaky.
        """
        with Database(db_path) as db:
            return db.get_flaky_tests(
                min_runs=min_runs,
                lookback_days=lookback_days,
                min_flip_rate=min_flip_rate,
            )

    @server.tool()
    def check_test_flakiness(test_name: str, lookback_days: int = 30) -> dict:
        """
        Check whether a specific test is a known flake, with its recent history.

        Args:
            test_name: Full test identifier (e.g. "test_api.TestAuth.test_token_refresh").
            lookback_days: How many days of history to consider.
        """
        with Database(db_path) as db:
            flaky = db.get_flaky_tests(min_runs=1, lookback_days=lookback_days, min_flip_rate=0.0)
            match = next((t for t in flaky if t["test_name"] == test_name), None)
            history = [dict(row) for row in db.get_test_history(test_name, limit=10)]

        if not history:
            return {
                "test_name": test_name,
                "known": False,
                "message": "No history found for this test.",
            }

        return {
            "test_name": test_name,
            "known": True,
            "is_flaky": match is not None,
            "flip_rate": match["flip_rate"] if match else 0.0,
            "recent_history": history,
        }

    @server.tool()
    def get_test_history(test_name: str, limit: int = 30) -> list[dict]:
        """
        Get recent pass/fail history for a specific test, newest first.

        Args:
            test_name: Full test identifier.
            limit: Maximum number of results to return.
        """
        with Database(db_path) as db:
            return [dict(row) for row in db.get_test_history(test_name, limit=limit)]

    @server.tool()
    def get_test_summary(
        lookback_days: int = 30,
        status_filter: Optional[str] = None,
    ) -> list[dict]:
        """
        Get summary statistics for every test (runs, pass/fail counts, last status).

        Args:
            lookback_days: How many days of history to consider.
            status_filter: Optionally restrict to tests whose last status matches
                (one of: passed, failed, skipped, error).
        """
        with Database(db_path) as db:
            return db.get_test_summary(lookback_days=lookback_days, status_filter=status_filter)

    @server.tool()
    def get_database_stats() -> dict:
        """Get Flaktor database health: run/result counts, date range, size."""
        with Database(db_path) as db:
            return db.get_database_stats()

    return server
