"""
CLI interface for Flaktor.

Built with Typer for professional, user-friendly command-line experience.
"""

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from pathlib import Path
from typing import Optional, List
from datetime import datetime
import csv
import glob as glob_module
import json

from .database import Database, DatabaseError, latest_schema_version
from .parser import (
    parse_junit_xml,
    parse_multiple_files,
    parse_test_report,
    detect_format,
    ParserError,
    SUPPORTED_FORMATS,
)

# Initialize Rich console for beautiful output
console = Console()

# Create Typer app
app = typer.Typer(
    name="flaktor",
    help="🔍 Flaky test detection made simple - Track, analyze, and fix flaky tests in your CI/CD pipeline.",
    add_completion=False,
    rich_markup_mode="rich",
)


def get_default_db_path() -> Path:
    """
    Get the default database path.
    
    Priority:
    1. FLAKTOR_DB environment variable
    2. .flaktor/flaktor.db in current directory
    3. ~/.flaktor/flaktor.db (user home)
    """
    import os
    
    # Check environment variable
    env_path = os.environ.get("FLAKTOR_DB")
    if env_path:
        return Path(env_path)
    
    # Check local directory
    local_path = Path(".flaktor/flaktor.db")
    if local_path.parent.exists():
        return local_path
    
    # Default to user home
    home_path = Path.home() / ".flaktor" / "flaktor.db"
    return home_path


def ensure_database_exists(db_path: Path) -> bool:
    """
    Check if database exists and is initialized.
    
    Returns:
        True if database exists and is ready, False otherwise
    """
    if not db_path.exists():
        return False
    
    try:
        with Database(db_path) as db:
            # Try to query metadata to verify it's initialized
            cursor = db.conn.cursor()
            cursor.execute("SELECT value FROM metadata WHERE key = 'schema_version'")
            result = cursor.fetchone()
            return result is not None
    except Exception:
        return False


@app.command()
def init(
    db_path: Optional[Path] = typer.Option(
        None,
        "--db",
        "-d",
        help="Custom database path (default: .flaktor/flaktor.db or ~/.flaktor/flaktor.db)"
    ),
    force: bool = typer.Option(
        False,
        "--force",
        "-f",
        help="Reinitialize even if database already exists"
    )
):
    """
    🚀 Initialize Flaktor database and configuration.
    
    This command sets up everything you need to start tracking flaky tests.
    Run this once before using other Flaktor commands.
    
    Examples:
        # Initialize in current directory
        $ flaktor init
        
        # Initialize with custom path
        $ flaktor init --db /path/to/my-tests.db
        
        # Reinitialize existing database
        $ flaktor init --force
    """
    
    # Determine database path
    if db_path is None:
        db_path = get_default_db_path()
    
    # Check if already exists
    if db_path.exists() and not force:
        if ensure_database_exists(db_path):
            console.print(
                Panel.fit(
                    f"✅ [green]Database already initialized![/green]\n\n"
                    f"📍 Location: [cyan]{db_path}[/cyan]\n\n"
                    f"💡 Use [yellow]--force[/yellow] to reinitialize",
                    border_style="green",
                    title="Already Set Up"
                )
            )
            return
    
    # Create parent directory if needed
    db_path.parent.mkdir(parents=True, exist_ok=True)
    
    try:
        # Initialize database
        with console.status("[bold blue]Initializing database...", spinner="dots"):
            with Database(db_path) as db:
                db.initialize_schema()
                stats = db.get_database_stats()
        
        # Success message with helpful next steps
        console.print()
        console.print(
            Panel.fit(
                f"[bold green]✨ Flaktor initialized successfully![/bold green]\n\n"
                f"📍 Database: [cyan]{db_path}[/cyan]\n"
                f"📊 Size: [yellow]{stats['database_size_mb']} MB[/yellow]\n\n"
                f"[bold]Next steps:[/bold]\n"
                f"  1. Upload test results:  [cyan]flaktor upload path/to/results.xml[/cyan]\n"
                f"  2. View flaky tests:     [cyan]flaktor list --flaky[/cyan]\n"
                f"  3. Generate report:      [cyan]flaktor report[/cyan]\n\n"
                f"💡 Need help? Run [yellow]flaktor --help[/yellow]",
                border_style="green",
                title="🎉 Ready to Go!"
            )
        )
        
        # Show environment hint if using custom path
        if db_path != get_default_db_path():
            console.print()
            console.print(
                "[dim]💡 Tip: Set FLAKTOR_DB environment variable to avoid "
                f"using --db flag:\n   export FLAKTOR_DB={db_path}[/dim]"
            )
        
    except DatabaseError as e:
        console.print()
        console.print(
            Panel.fit(
                f"[bold red]❌ Initialization failed[/bold red]\n\n"
                f"{str(e)}\n\n"
                f"💡 Need help? Check the documentation or file an issue:\n"
                f"   https://github.com/PanjatanCoders/flaktor/issues",
                border_style="red",
                title="Error"
            )
        )
        raise typer.Exit(code=1)


@app.command()
def info(
    db_path: Optional[Path] = typer.Option(
        None,
        "--db",
        "-d",
        help="Database path (default: auto-detect)"
    )
):
    """
    📊 Show database information and statistics.
    
    Display useful information about your Flaktor database including
    test counts, date ranges, and storage size.
    
    Example:
        $ flaktor info
    """
    
    if db_path is None:
        db_path = get_default_db_path()
    
    if not db_path.exists():
        console.print(
            Panel.fit(
                "[bold red]❌ Database not found[/bold red]\n\n"
                f"Expected location: [cyan]{db_path}[/cyan]\n\n"
                f"💡 Initialize first: [yellow]flaktor init[/yellow]",
                border_style="red",
                title="Not Initialized"
            )
        )
        raise typer.Exit(code=1)
    
    try:
        with Database(db_path) as db:
            stats = db.get_database_stats()
            schema_version = db.get_schema_version()

        # Create info table
        table = Table(show_header=False, box=None, padding=(0, 2))
        table.add_column("Key", style="cyan")
        table.add_column("Value", style="green")

        table.add_row("📍 Database Path", str(db_path))
        table.add_row("📦 Database Size", f"{stats['database_size_mb']} MB")
        table.add_row("🏃 Total Test Runs", f"{stats['total_runs']:,}")
        table.add_row("📝 Total Test Results", f"{stats['total_results']:,}")
        table.add_row("🧪 Unique Tests", f"{stats['unique_tests']:,}")
        latest_version = latest_schema_version()
        if schema_version < latest_version:
            table.add_row(
                "🔧 Schema Version",
                f"[yellow]{schema_version} (update available: v{latest_version})[/yellow]"
            )
        else:
            table.add_row("🔧 Schema Version", str(schema_version))

        if stats['earliest_run']:
            table.add_row("📅 Earliest Run", stats['earliest_run'])
            table.add_row("📅 Latest Run", stats['latest_run'])
        else:
            table.add_row("📅 Data Range", "[dim]No data yet[/dim]")
        
        console.print()
        console.print(Panel(table, title="[bold]Flaktor Database Info[/bold]", border_style="blue"))
        console.print()
        
        # Show helpful tips if no data
        if stats['total_runs'] == 0:
            console.print(
                "[dim]💡 No test data yet. Upload results with:[/dim] "
                "[cyan]flaktor upload path/to/results.xml[/cyan]"
            )

        if schema_version < latest_version:
            console.print(
                "[dim]💡 A schema update is available. Run:[/dim] "
                "[cyan]flaktor migrate[/cyan]"
            )

    except DatabaseError as e:
        console.print(
            Panel.fit(
                f"[bold red]❌ Failed to read database[/bold red]\n\n{str(e)}",
                border_style="red",
                title="Error"
            )
        )
        raise typer.Exit(code=1)


@app.command()
def migrate(
    db_path: Optional[Path] = typer.Option(
        None,
        "--db",
        "-d",
        help="Database path (default: auto-detect)"
    ),
):
    """
    🔧 Apply pending database schema migrations.

    Safe to run anytime - it's a no-op if the database is already on the
    latest schema version. Run this after upgrading Flaktor if a command
    or `flaktor info` reports that an update is available.

    Example:
        $ flaktor migrate
    """
    if db_path is None:
        db_path = get_default_db_path()

    if not db_path.exists():
        console.print(
            Panel.fit(
                "[bold red]❌ Database not found[/bold red]\n\n"
                f"Expected location: [cyan]{db_path}[/cyan]\n\n"
                f"💡 Initialize first: [yellow]flaktor init[/yellow]",
                border_style="red",
                title="Not Initialized"
            )
        )
        raise typer.Exit(code=1)

    try:
        with Database(db_path) as db:
            before = db.get_schema_version()

            if not db.needs_migration():
                console.print(
                    f"[green]✅ Database already up to date[/green] "
                    f"[dim](schema version {before})[/dim]"
                )
                return

            applied = db.migrate()

        console.print(
            Panel.fit(
                f"[bold green]✨ Migration complete![/bold green]\n\n"
                f"Schema version: [cyan]{before}[/cyan] → [green]{applied[-1]}[/green]\n"
                f"Applied: {', '.join(f'v{v}' for v in applied)}",
                border_style="green",
                title="Migrated"
            )
        )

    except DatabaseError as e:
        console.print(
            Panel.fit(
                f"[bold red]❌ Migration failed[/bold red]\n\n{str(e)}",
                border_style="red",
                title="Error"
            )
        )
        raise typer.Exit(code=1)


@app.command("list")
def list_tests(
    db_path: Optional[Path] = typer.Option(
        None,
        "--db",
        "-d",
        help="Database path (default: auto-detect)"
    ),
    flaky: bool = typer.Option(
        False,
        "--flaky",
        "-f",
        help="Show only flaky tests"
    ),
    failed: bool = typer.Option(
        False,
        "--failed",
        help="Show only tests that failed in their last run"
    ),
    days: int = typer.Option(
        30,
        "--days",
        help="Number of days to look back"
    ),
    min_runs: int = typer.Option(
        5,
        "--min-runs",
        help="Minimum runs required for flaky detection"
    ),
    limit: int = typer.Option(
        50,
        "--limit",
        "-n",
        help="Maximum number of tests to display"
    ),
):
    """
    📋 List tests with statistics and flakiness info.

    View all tests, filter by flaky tests, or see recent failures.

    Examples:
        # List all tests
        $ flaktor list

        # Show only flaky tests
        $ flaktor list --flaky

        # Show recent failures
        $ flaktor list --failed

        # Look back 7 days with minimum 3 runs
        $ flaktor list --flaky --days 7 --min-runs 3
    """
    if db_path is None:
        db_path = get_default_db_path()

    if not ensure_database_exists(db_path):
        console.print(
            Panel.fit(
                "[bold red]❌ Database not initialized[/bold red]\n\n"
                f"💡 Run first: [yellow]flaktor init[/yellow]",
                border_style="red",
                title="Error"
            )
        )
        raise typer.Exit(code=1)

    try:
        with Database(db_path) as db:
            if flaky:
                tests = db.get_flaky_tests(
                    min_runs=min_runs,
                    lookback_days=days,
                )
                title = f"Flaky Tests (last {days} days)"
            elif failed:
                tests = db.get_test_summary(
                    lookback_days=days,
                    status_filter="failed",
                )
                title = f"Failed Tests (last {days} days)"
            else:
                tests = db.get_test_summary(lookback_days=days)
                title = f"All Tests (last {days} days)"

        if not tests:
            console.print()
            if flaky:
                console.print(
                    Panel.fit(
                        "[green]✅ No flaky tests detected![/green]\n\n"
                        f"Analyzed tests from the last {days} days\n"
                        f"with at least {min_runs} runs.",
                        border_style="green",
                        title="Good News"
                    )
                )
            else:
                console.print(
                    Panel.fit(
                        "[yellow]No tests found[/yellow]\n\n"
                        f"💡 Upload test results: [cyan]flaktor upload results.xml[/cyan]",
                        border_style="yellow",
                        title="Empty"
                    )
                )
            return

        # Limit results
        tests = tests[:limit]

        # Create table
        table = Table(title=title, show_lines=False)

        if flaky:
            table.add_column("Test Name", style="cyan", no_wrap=False)
            table.add_column("Flip Rate", justify="right", style="red")
            table.add_column("Pass Rate", justify="right")
            table.add_column("Runs", justify="right")
            table.add_column("P/F", justify="right")
            table.add_column("Avg Time", justify="right")

            for test in tests:
                flip_pct = f"{test['flip_rate']*100:.0f}%"
                pass_pct = f"{test['pass_rate']*100:.0f}%"
                pf = f"[green]{test['passed']}[/green]/[red]{test['failed']}[/red]"

                table.add_row(
                    _truncate_test_name(test["test_name"]),
                    flip_pct,
                    pass_pct,
                    str(test["total_runs"]),
                    pf,
                    f"{test['avg_duration']:.2f}s",
                )
        else:
            table.add_column("Test Name", style="cyan", no_wrap=False)
            table.add_column("Status", justify="center")
            table.add_column("Runs", justify="right")
            table.add_column("Pass Rate", justify="right")
            table.add_column("Avg Time", justify="right")

            for test in tests:
                status = test.get("last_status", "unknown")
                if status == "passed":
                    status_display = "[green]PASS[/green]"
                elif status == "failed":
                    status_display = "[red]FAIL[/red]"
                elif status == "error":
                    status_display = "[red]ERROR[/red]"
                elif status == "skipped":
                    status_display = "[yellow]SKIP[/yellow]"
                else:
                    status_display = "[dim]?[/dim]"

                total = test["total_runs"]
                passed = test["passed"]
                pass_rate = f"{(passed/total)*100:.0f}%" if total > 0 else "-"

                table.add_row(
                    _truncate_test_name(test["test_name"]),
                    status_display,
                    str(total),
                    pass_rate,
                    f"{test['avg_duration']:.2f}s",
                )

        console.print()
        console.print(table)
        console.print()

        if len(tests) == limit:
            console.print(f"[dim]Showing {limit} of potentially more results. Use --limit to see more.[/dim]")

    except DatabaseError as e:
        console.print(
            Panel.fit(
                f"[bold red]❌ Database error[/bold red]\n\n{str(e)}",
                border_style="red",
                title="Error"
            )
        )
        raise typer.Exit(code=1)


def _truncate_test_name(name: str, max_length: int = 60) -> str:
    """Truncate long test names for display."""
    if len(name) <= max_length:
        return name
    return "..." + name[-(max_length - 3):]


def _format_status(status: str) -> str:
    """Format status with color."""
    if status == "passed":
        return "[green]PASS[/green]"
    elif status == "failed":
        return "[red]FAIL[/red]"
    elif status == "error":
        return "[red]ERROR[/red]"
    elif status == "skipped":
        return "[yellow]SKIP[/yellow]"
    return "[dim]?[/dim]"


@app.command()
def clean(
    db_path: Optional[Path] = typer.Option(
        None,
        "--db",
        "-d",
        help="Database path (default: auto-detect)"
    ),
    days: int = typer.Option(
        90,
        "--days",
        help="Number of days of data to keep (older data is deleted)"
    ),
    dry_run: bool = typer.Option(
        False,
        "--dry-run",
        help="Show what would be deleted without actually deleting"
    ),
    force: bool = typer.Option(
        False,
        "--force",
        "-f",
        help="Skip confirmation prompt"
    ),
    vacuum: bool = typer.Option(
        True,
        "--vacuum/--no-vacuum",
        help="Run VACUUM after cleanup to reclaim disk space"
    ),
):
    """
    🧹 Clean up old data from the database.

    Remove test results and runs older than the specified number of days
    to keep the database size manageable.

    Examples:
        # Preview what would be deleted (dry run)
        $ flaktor clean --dry-run

        # Delete data older than 90 days (default)
        $ flaktor clean

        # Delete data older than 30 days
        $ flaktor clean --days 30

        # Delete without confirmation
        $ flaktor clean --force
    """
    if db_path is None:
        db_path = get_default_db_path()

    if not ensure_database_exists(db_path):
        console.print(
            Panel.fit(
                "[bold red]❌ Database not initialized[/bold red]\n\n"
                f"💡 Run first: [yellow]flaktor init[/yellow]",
                border_style="red",
                title="Error"
            )
        )
        raise typer.Exit(code=1)

    try:
        with Database(db_path) as db:
            # Get current stats
            stats_before = db.get_database_stats()
            size_before = stats_before["database_size_mb"]

            # First, do a dry run to see what would be deleted
            preview = db.purge_old_data(days_to_keep=days, dry_run=True)

        results_count = preview["test_results_deleted"]
        runs_count = preview["test_runs_deleted"]

        if results_count == 0 and runs_count == 0:
            console.print()
            console.print(
                Panel.fit(
                    "[green]✅ Database is already clean![/green]\n\n"
                    f"No data older than {days} days found.",
                    border_style="green",
                    title="Nothing to Clean"
                )
            )
            return

        # Show preview
        console.print()
        console.print(
            Panel.fit(
                f"[bold]Data older than {days} days:[/bold]\n\n"
                f"📝 Test results to delete: [yellow]{results_count:,}[/yellow]\n"
                f"🏃 Test runs to delete: [yellow]{runs_count:,}[/yellow]\n"
                f"💾 Current database size: [cyan]{size_before} MB[/cyan]",
                border_style="yellow",
                title="Cleanup Preview"
            )
        )

        if dry_run:
            console.print()
            console.print("[dim]This was a dry run. No data was deleted.[/dim]")
            console.print("[dim]Remove --dry-run to actually delete the data.[/dim]")
            return

        # Confirm unless --force
        if not force:
            console.print()
            confirm = typer.confirm(
                f"Delete {results_count:,} test results and {runs_count:,} test runs?",
                default=False
            )
            if not confirm:
                console.print("[dim]Aborted.[/dim]")
                raise typer.Exit(code=0)

        # Perform the cleanup
        with console.status("[bold blue]Cleaning up old data...", spinner="dots"):
            with Database(db_path) as db:
                result = db.purge_old_data(days_to_keep=days, dry_run=False)

                if vacuum:
                    db.vacuum()

                stats_after = db.get_database_stats()
                size_after = stats_after["database_size_mb"]

        space_saved = size_before - size_after

        console.print()
        console.print(
            Panel.fit(
                f"[bold green]✅ Cleanup complete![/bold green]\n\n"
                f"📝 Test results deleted: [green]{result['test_results_deleted']:,}[/green]\n"
                f"🏃 Test runs deleted: [green]{result['test_runs_deleted']:,}[/green]\n"
                f"💾 Database size: [cyan]{size_before} MB → {size_after} MB[/cyan]\n"
                f"📉 Space saved: [green]{space_saved:.2f} MB[/green]",
                border_style="green",
                title="Cleanup Complete"
            )
        )

    except DatabaseError as e:
        console.print(
            Panel.fit(
                f"[bold red]❌ Database error[/bold red]\n\n{str(e)}",
                border_style="red",
                title="Error"
            )
        )
        raise typer.Exit(code=1)


@app.command()
def history(
    test_name: str = typer.Argument(
        ...,
        help="Test name (full or partial match)"
    ),
    db_path: Optional[Path] = typer.Option(
        None,
        "--db",
        "-d",
        help="Database path (default: auto-detect)"
    ),
    limit: int = typer.Option(
        20,
        "--limit",
        "-n",
        help="Maximum number of results to show"
    ),
    verbose: bool = typer.Option(
        False,
        "--verbose",
        "-v",
        help="Show failure messages and stack traces"
    ),
):
    """
    📜 View detailed history for a specific test.

    Show the run history of a test including status changes over time,
    durations, and failure details. Supports partial test name matching.

    Examples:
        # View history for a specific test
        $ flaktor history test_auth.TestLogin.test_valid_credentials

        # Search by partial name
        $ flaktor history test_login

        # Show more results with failure details
        $ flaktor history test_login --limit 50 --verbose
    """
    if db_path is None:
        db_path = get_default_db_path()

    if not ensure_database_exists(db_path):
        console.print(
            Panel.fit(
                "[bold red]❌ Database not initialized[/bold red]\n\n"
                f"💡 Run first: [yellow]flaktor init[/yellow]",
                border_style="red",
                title="Error"
            )
        )
        raise typer.Exit(code=1)

    try:
        with Database(db_path) as db:
            # First, find matching test names
            all_tests = db.get_all_test_names()

            # Find exact match first, then partial matches
            exact_match = test_name if test_name in all_tests else None
            partial_matches = [t for t in all_tests if test_name.lower() in t.lower()]

            if exact_match:
                selected_test = exact_match
            elif len(partial_matches) == 1:
                selected_test = partial_matches[0]
            elif len(partial_matches) > 1:
                # Show matching tests and let user choose
                console.print()
                console.print(
                    Panel.fit(
                        f"[yellow]Multiple tests match '{test_name}'[/yellow]\n\n"
                        f"Found {len(partial_matches)} matching tests.\n"
                        f"Please be more specific or use one of these:",
                        border_style="yellow",
                        title="Multiple Matches"
                    )
                )
                console.print()

                table = Table(show_header=True, header_style="bold")
                table.add_column("#", style="dim", width=4)
                table.add_column("Test Name", style="cyan")

                for i, match in enumerate(partial_matches[:15], 1):
                    table.add_row(str(i), match)

                if len(partial_matches) > 15:
                    table.add_row("...", f"[dim]and {len(partial_matches) - 15} more[/dim]")

                console.print(table)
                console.print()
                console.print("[dim]💡 Tip: Copy the full test name and try again[/dim]")
                return
            else:
                console.print(
                    Panel.fit(
                        f"[bold red]❌ No tests found matching '{test_name}'[/bold red]\n\n"
                        f"💡 Use [cyan]flaktor list[/cyan] to see all available tests",
                        border_style="red",
                        title="Not Found"
                    )
                )
                raise typer.Exit(code=1)

            # Get history for the selected test
            history_rows = db.get_test_history(selected_test, limit=limit)

        if not history_rows:
            console.print(
                Panel.fit(
                    f"[yellow]No history found for test[/yellow]\n\n"
                    f"Test: [cyan]{selected_test}[/cyan]",
                    border_style="yellow",
                    title="Empty"
                )
            )
            return

        # Calculate summary statistics
        total = len(history_rows)
        passed = sum(1 for r in history_rows if r[1] == "passed")
        failed = sum(1 for r in history_rows if r[1] in ("failed", "error"))
        skipped = sum(1 for r in history_rows if r[1] == "skipped")
        avg_duration = sum(r[2] for r in history_rows) / total if total > 0 else 0

        # Detect flakiness pattern
        if total >= 2:
            status_changes = sum(
                1 for i in range(1, len(history_rows))
                if history_rows[i][1] != history_rows[i-1][1]
            )
            is_flaky = status_changes >= 2 and passed > 0 and failed > 0
        else:
            status_changes = 0
            is_flaky = False

        # Print header
        console.print()
        header_content = f"[bold cyan]{selected_test}[/bold cyan]\n\n"
        header_content += f"📊 [bold]Statistics[/bold] (last {total} runs):\n"
        header_content += f"   [green]Passed: {passed}[/green] | [red]Failed: {failed}[/red] | [yellow]Skipped: {skipped}[/yellow]\n"
        header_content += f"   Pass Rate: [{'green' if passed/total > 0.8 else 'yellow' if passed/total > 0.5 else 'red'}]{passed/total*100:.0f}%[/{'green' if passed/total > 0.8 else 'yellow' if passed/total > 0.5 else 'red'}]\n"
        header_content += f"   Avg Duration: [cyan]{avg_duration:.3f}s[/cyan]\n"

        if is_flaky:
            header_content += f"\n   ⚠️  [bold red]FLAKY[/bold red] - {status_changes} status changes detected"

        console.print(Panel(header_content, title="Test History", border_style="blue"))

        # Create history table
        table = Table(show_header=True, header_style="bold", show_lines=verbose)
        table.add_column("#", style="dim", width=4)
        table.add_column("Status", justify="center", width=8)
        table.add_column("Duration", justify="right", width=10)
        table.add_column("Run ID", style="dim", width=20)
        table.add_column("Timestamp", width=20)

        if verbose:
            table.add_column("Failure Info", style="red", no_wrap=False)

        for i, row in enumerate(history_rows, 1):
            test_name_col, status, duration, run_id, timestamp, failure_msg, failure_type = row

            status_display = _format_status(status)

            # Format timestamp nicely
            try:
                ts = datetime.fromisoformat(timestamp)
                ts_display = ts.strftime("%Y-%m-%d %H:%M")
            except (ValueError, TypeError):
                ts_display = str(timestamp)[:16] if timestamp else "-"

            # Truncate run_id for display
            run_id_display = run_id[:18] + ".." if len(run_id) > 20 else run_id

            if verbose:
                failure_info = ""
                if failure_msg or failure_type:
                    if failure_type:
                        failure_info = f"[bold]{failure_type}[/bold]\n"
                    if failure_msg:
                        failure_info += failure_msg[:200]
                        if len(failure_msg) > 200:
                            failure_info += "..."

                table.add_row(
                    str(i),
                    status_display,
                    f"{duration:.3f}s",
                    run_id_display,
                    ts_display,
                    failure_info or "[dim]-[/dim]"
                )
            else:
                table.add_row(
                    str(i),
                    status_display,
                    f"{duration:.3f}s",
                    run_id_display,
                    ts_display
                )

        console.print()
        console.print(table)
        console.print()

        # Show visual timeline of recent results
        if total >= 5:
            timeline = "Recent: "
            for row in history_rows[:20]:
                status = row[1]
                if status == "passed":
                    timeline += "[green]●[/green]"
                elif status in ("failed", "error"):
                    timeline += "[red]●[/red]"
                elif status == "skipped":
                    timeline += "[yellow]○[/yellow]"
                else:
                    timeline += "[dim]○[/dim]"
            timeline += " (newest → oldest)"
            console.print(timeline)
            console.print()

        if len(history_rows) == limit:
            console.print(f"[dim]Showing last {limit} runs. Use --limit to see more.[/dim]")

    except DatabaseError as e:
        console.print(
            Panel.fit(
                f"[bold red]❌ Database error[/bold red]\n\n{str(e)}",
                border_style="red",
                title="Error"
            )
        )
        raise typer.Exit(code=1)


@app.command()
def report(
    db_path: Optional[Path] = typer.Option(
        None,
        "--db",
        "-d",
        help="Database path (default: auto-detect)"
    ),
    days: int = typer.Option(
        30,
        "--days",
        help="Number of days to analyze"
    ),
    output: Optional[Path] = typer.Option(
        None,
        "--output",
        "-o",
        help="Output file path (prints to console if not specified)"
    ),
):
    """
    📊 Generate a flakiness report.

    Create a summary report of test health including flaky tests,
    failure rates, and overall statistics.

    Examples:
        # Print report to console
        $ flaktor report

        # Generate report for last 7 days
        $ flaktor report --days 7

        # Save report to file
        $ flaktor report --output report.txt
    """
    if db_path is None:
        db_path = get_default_db_path()

    if not ensure_database_exists(db_path):
        console.print(
            Panel.fit(
                "[bold red]❌ Database not initialized[/bold red]\n\n"
                f"💡 Run first: [yellow]flaktor init[/yellow]",
                border_style="red",
                title="Error"
            )
        )
        raise typer.Exit(code=1)

    try:
        with Database(db_path) as db:
            stats = db.get_database_stats()
            flaky_tests = db.get_flaky_tests(lookback_days=days, min_runs=3)
            all_tests = db.get_test_summary(lookback_days=days)

        # Calculate summary stats
        total_tests = len(all_tests)
        flaky_count = len(flaky_tests)
        failed_count = sum(1 for t in all_tests if t.get("last_status") == "failed")
        passed_count = sum(1 for t in all_tests if t.get("last_status") == "passed")

        # Build report content
        report_lines = []
        report_lines.append("=" * 60)
        report_lines.append("FLAKTOR TEST HEALTH REPORT")
        report_lines.append("=" * 60)
        report_lines.append("")
        report_lines.append(f"Analysis Period: Last {days} days")
        report_lines.append(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        report_lines.append("")
        report_lines.append("-" * 60)
        report_lines.append("SUMMARY")
        report_lines.append("-" * 60)
        report_lines.append(f"Total Unique Tests:    {total_tests}")
        report_lines.append(f"Total Test Runs:       {stats['total_runs']}")
        report_lines.append(f"Total Test Results:    {stats['total_results']}")
        report_lines.append(f"Flaky Tests:           {flaky_count}")
        report_lines.append(f"Currently Failing:     {failed_count}")
        report_lines.append(f"Currently Passing:     {passed_count}")
        report_lines.append("")

        if flaky_tests:
            report_lines.append("-" * 60)
            report_lines.append("FLAKY TESTS (sorted by flip rate)")
            report_lines.append("-" * 60)
            for i, test in enumerate(flaky_tests[:10], 1):
                flip_pct = f"{test['flip_rate']*100:.0f}%"
                pass_pct = f"{test['pass_rate']*100:.0f}%"
                report_lines.append(
                    f"{i}. {test['test_name']}"
                )
                report_lines.append(
                    f"   Flip Rate: {flip_pct} | Pass Rate: {pass_pct} | "
                    f"Runs: {test['total_runs']} ({test['passed']}P/{test['failed']}F)"
                )
            if len(flaky_tests) > 10:
                report_lines.append(f"   ... and {len(flaky_tests) - 10} more flaky tests")
            report_lines.append("")

        # Health score calculation
        if total_tests > 0:
            health_score = ((total_tests - flaky_count - failed_count) / total_tests) * 100
        else:
            health_score = 100

        report_lines.append("-" * 60)
        report_lines.append("HEALTH SCORE")
        report_lines.append("-" * 60)
        report_lines.append(f"Overall Health: {health_score:.0f}%")
        if health_score >= 90:
            report_lines.append("Status: EXCELLENT - Your test suite is healthy!")
        elif health_score >= 70:
            report_lines.append("Status: GOOD - Some attention needed")
        elif health_score >= 50:
            report_lines.append("Status: FAIR - Consider addressing flaky tests")
        else:
            report_lines.append("Status: NEEDS ATTENTION - Many flaky/failing tests")
        report_lines.append("")
        report_lines.append("=" * 60)

        report_content = "\n".join(report_lines)

        # Output report
        if output:
            output.write_text(report_content)
            console.print(f"[green]✅ Report saved to {output}[/green]")
        else:
            console.print()
            console.print(Panel(report_content, title="Test Health Report", border_style="blue"))
            console.print()

    except DatabaseError as e:
        console.print(
            Panel.fit(
                f"[bold red]❌ Database error[/bold red]\n\n{str(e)}",
                border_style="red",
                title="Error"
            )
        )
        raise typer.Exit(code=1)


@app.command()
def export(
    db_path: Optional[Path] = typer.Option(
        None,
        "--db",
        "-d",
        help="Database path (default: auto-detect)"
    ),
    output: Path = typer.Option(
        ...,
        "--output",
        "-o",
        help="Output file path"
    ),
    format: Optional[str] = typer.Option(
        None,
        "--format",
        "-f",
        help="Export format: json or csv (default: inferred from --output extension)"
    ),
    test_name: Optional[str] = typer.Option(
        None,
        "--test",
        "-t",
        help="Export raw run history for a single test instead of the summary"
    ),
    days: int = typer.Option(
        30,
        "--days",
        help="Number of days to include (ignored with --test)"
    ),
    limit: int = typer.Option(
        1000,
        "--limit",
        "-n",
        help="Maximum rows to export when using --test"
    ),
):
    """
    📤 Export test data to JSON or CSV for external analysis.

    Exports a per-test summary by default, or the raw run history for a
    single test when --test is given. Format is inferred from the
    --output file extension unless --format is set.

    Examples:
        # Export a summary of all tests
        $ flaktor export --output tests.json

        # Export as CSV explicitly
        $ flaktor export --output tests.csv --format csv

        # Export raw run history for one test
        $ flaktor export --test test_login --output test_login_history.json
    """
    if db_path is None:
        db_path = get_default_db_path()

    if not ensure_database_exists(db_path):
        console.print(
            Panel.fit(
                "[bold red]❌ Database not initialized[/bold red]\n\n"
                f"💡 Run first: [yellow]flaktor init[/yellow]",
                border_style="red",
                title="Error"
            )
        )
        raise typer.Exit(code=1)

    export_format = (format or output.suffix.lstrip(".") or "json").lower()
    if export_format not in ("json", "csv"):
        console.print(
            Panel.fit(
                f"[bold red]❌ Unsupported format '{export_format}'[/bold red]\n\n"
                f"💡 Use [cyan]--format json[/cyan] or [cyan]--format csv[/cyan]",
                border_style="red",
                title="Error"
            )
        )
        raise typer.Exit(code=1)

    try:
        with Database(db_path) as db:
            if test_name:
                all_tests = db.get_all_test_names()
                exact_match = test_name if test_name in all_tests else None
                partial_matches = [t for t in all_tests if test_name.lower() in t.lower()]

                if exact_match:
                    selected_test = exact_match
                elif len(partial_matches) == 1:
                    selected_test = partial_matches[0]
                elif len(partial_matches) > 1:
                    console.print(
                        Panel.fit(
                            f"[yellow]Multiple tests match '{test_name}'[/yellow]\n\n"
                            f"Found {len(partial_matches)} matching tests. "
                            f"Please be more specific.",
                            border_style="yellow",
                            title="Multiple Matches"
                        )
                    )
                    raise typer.Exit(code=1)
                else:
                    console.print(
                        Panel.fit(
                            f"[bold red]❌ No tests found matching '{test_name}'[/bold red]\n\n"
                            f"💡 Use [cyan]flaktor list[/cyan] to see all available tests",
                            border_style="red",
                            title="Not Found"
                        )
                    )
                    raise typer.Exit(code=1)

                rows = db.get_test_history(selected_test, limit=limit)
                records = [
                    {
                        "test_name": r[0],
                        "status": r[1],
                        "duration": r[2],
                        "run_id": r[3],
                        "timestamp": r[4],
                        "failure_message": r[5],
                        "failure_type": r[6],
                    }
                    for r in rows
                ]
            else:
                records = db.get_test_summary(lookback_days=days)

        if not records:
            console.print(
                Panel.fit(
                    "[yellow]No data to export[/yellow]",
                    border_style="yellow",
                    title="Empty"
                )
            )
            return

        output.parent.mkdir(parents=True, exist_ok=True)

        if export_format == "json":
            output.write_text(json.dumps(records, indent=2))
        else:
            with output.open("w", newline="") as f:
                writer = csv.DictWriter(f, fieldnames=list(records[0].keys()))
                writer.writeheader()
                writer.writerows(records)

        console.print(
            f"[green]✅ Exported {len(records)} record(s) to {output}[/green] "
            f"[dim]({export_format.upper()})[/dim]"
        )

    except DatabaseError as e:
        console.print(
            Panel.fit(
                f"[bold red]❌ Database error[/bold red]\n\n{str(e)}",
                border_style="red",
                title="Error"
            )
        )
        raise typer.Exit(code=1)


@app.command()
def upload(
    files: List[Path] = typer.Argument(
        ...,
        help="Path(s) to test result files. Supports glob patterns."
    ),
    db_path: Optional[Path] = typer.Option(
        None,
        "--db",
        "-d",
        help="Database path (default: auto-detect)"
    ),
    format: Optional[str] = typer.Option(
        None,
        "--format",
        "-f",
        help=f"Report format: {', '.join(SUPPORTED_FORMATS)} (auto-detected if not specified)"
    ),
    run_id: Optional[str] = typer.Option(
        None,
        "--run-id",
        "-r",
        help="Custom run identifier (auto-generated if not provided)"
    ),
    branch: Optional[str] = typer.Option(
        None,
        "--branch",
        "-b",
        help="Git branch name"
    ),
    commit: Optional[str] = typer.Option(
        None,
        "--commit",
        "-c",
        help="Git commit hash"
    ),
    environment: Optional[str] = typer.Option(
        None,
        "--env",
        "-e",
        help="Environment name (e.g., ci, staging, production)"
    ),
):
    """
    📤 Upload test results from various formats.

    Parse test result files and store in the database. Supports:
    - JUnit/xUnit XML (pytest, JUnit, NUnit, Jest, etc.)
    - Cucumber JSON (BDD frameworks)
    - Playwright JSON

    Format is auto-detected from file extension and content.

    Examples:
        # Upload JUnit XML
        $ flaktor upload results.xml

        # Upload Cucumber JSON
        $ flaktor upload cucumber-report.json

        # Upload Playwright JSON
        $ flaktor upload playwright-report.json --format playwright

        # Upload with metadata
        $ flaktor upload results.xml --branch main --commit abc123
    """
    if db_path is None:
        db_path = get_default_db_path()

    if not ensure_database_exists(db_path):
        console.print(
            Panel.fit(
                "[bold red]❌ Database not initialized[/bold red]\n\n"
                f"💡 Run first: [yellow]flaktor init[/yellow]",
                border_style="red",
                title="Error"
            )
        )
        raise typer.Exit(code=1)

    # Expand glob patterns
    all_files: List[Path] = []
    for file_pattern in files:
        pattern_str = str(file_pattern)
        if "*" in pattern_str or "?" in pattern_str:
            matched = glob_module.glob(pattern_str, recursive=True)
            all_files.extend(Path(f) for f in matched)
        else:
            all_files.append(file_pattern)

    if not all_files:
        console.print(
            Panel.fit(
                "[bold red]❌ No files found[/bold red]\n\n"
                f"Pattern(s) matched no files.",
                border_style="red",
                title="Error"
            )
        )
        raise typer.Exit(code=1)

    # Filter to only existing files with supported extensions
    supported_extensions = {".xml", ".json"}
    valid_files = [
        f for f in all_files
        if f.exists() and f.suffix.lower() in supported_extensions
    ]

    if not valid_files:
        console.print(
            Panel.fit(
                "[bold red]❌ No valid test result files found[/bold red]\n\n"
                f"Found {len(all_files)} file(s), but none are .xml or .json files.\n\n"
                f"Supported formats: {', '.join(SUPPORTED_FORMATS)}",
                border_style="red",
                title="Error"
            )
        )
        raise typer.Exit(code=1)

    try:
        parse_errors: List[str] = []
        all_results = []
        detected_format = None

        with console.status(f"[bold blue]Parsing {len(valid_files)} file(s)...", spinner="dots"):
            for file_path in valid_files:
                try:
                    # Detect or use specified format
                    file_format = format
                    if file_format is None:
                        file_format = detect_format(file_path)

                    if detected_format is None:
                        detected_format = file_format

                    parsed = parse_test_report(
                        file_path,
                        format=file_format,
                        run_id=run_id,
                        branch=branch,
                        commit_hash=commit,
                        environment=environment,
                    )
                    all_results.append(parsed)
                except ParserError as e:
                    parse_errors.append(str(e))

        # Show parse errors if any
        if parse_errors:
            console.print()
            for err in parse_errors:
                console.print(f"[yellow]⚠️  {err}[/yellow]")

        if not all_results:
            console.print(
                Panel.fit(
                    "[bold red]❌ Failed to parse any files[/bold red]\n\n"
                    "Check the errors above for details.",
                    border_style="red",
                    title="Error"
                )
            )
            raise typer.Exit(code=1)

        # Combine results if multiple files
        if len(all_results) == 1:
            parsed = all_results[0]
        else:
            # Merge all parsed results
            from .models import TestRun
            import uuid as uuid_module

            combined_run_id = run_id or f"run-{uuid_module.uuid4().hex[:12]}"
            combined_results = []
            for p in all_results:
                combined_results.extend(p.results)

            parsed = type(all_results[0])(
                test_run=TestRun(
                    run_id=combined_run_id,
                    timestamp=min(p.test_run.timestamp for p in all_results),
                    branch=branch,
                    commit_hash=commit,
                    environment=environment,
                ),
                results=combined_results,
                total_tests=sum(p.total_tests for p in all_results),
                passed=sum(p.passed for p in all_results),
                failed=sum(p.failed for p in all_results),
                skipped=sum(p.skipped for p in all_results),
                errors=sum(p.errors for p in all_results),
                total_duration=sum(p.total_duration for p in all_results),
            )

        if parsed.total_tests == 0:
            console.print(
                Panel.fit(
                    "[bold yellow]⚠️  No test cases found[/bold yellow]\n\n"
                    "The file(s) were parsed but contained no test cases.",
                    border_style="yellow",
                    title="Warning"
                )
            )
            raise typer.Exit(code=1)

        # Store in database
        with console.status("[bold blue]Storing results...", spinner="dots"):
            with Database(db_path) as db:
                db.insert_test_run(parsed.test_run)
                successful, failed = db.insert_test_results(parsed.results)

        # Build result summary
        status_parts = []
        if parsed.passed > 0:
            status_parts.append(f"[green]{parsed.passed} passed[/green]")
        if parsed.failed > 0:
            status_parts.append(f"[red]{parsed.failed} failed[/red]")
        if parsed.errors > 0:
            status_parts.append(f"[red]{parsed.errors} errors[/red]")
        if parsed.skipped > 0:
            status_parts.append(f"[yellow]{parsed.skipped} skipped[/yellow]")

        status_line = ", ".join(status_parts) if status_parts else "No results"

        format_display = detected_format.upper() if detected_format else "auto"

        console.print()
        console.print(
            Panel.fit(
                f"[bold green]✅ Upload successful![/bold green]\n\n"
                f"📁 Files processed: [cyan]{len(valid_files)}[/cyan]\n"
                f"📋 Format: [cyan]{format_display}[/cyan]\n"
                f"🏃 Run ID: [cyan]{parsed.test_run.run_id}[/cyan]\n"
                f"🧪 Tests: {status_line}\n"
                f"⏱️  Duration: [cyan]{parsed.total_duration:.2f}s[/cyan]\n"
                f"💾 Stored: [green]{successful}[/green] results"
                + (f", [red]{failed} failed[/red]" if failed > 0 else ""),
                border_style="green",
                title="Upload Complete"
            )
        )

    except ParserError as e:
        console.print(
            Panel.fit(
                f"[bold red]❌ Parse error[/bold red]\n\n{str(e)}",
                border_style="red",
                title="Error"
            )
        )
        raise typer.Exit(code=1)
    except DatabaseError as e:
        console.print(
            Panel.fit(
                f"[bold red]❌ Database error[/bold red]\n\n{str(e)}",
                border_style="red",
                title="Error"
            )
        )
        raise typer.Exit(code=1)


@app.command()
def mcp(
    db_path: Optional[Path] = typer.Option(
        None,
        "--db",
        "-d",
        help="Database path (default: auto-detect)"
    )
):
    """
    🔌 Start the Flaktor MCP server (stdio transport).

    Exposes flaky-test data to AI coding agents (Claude Code, Cursor, etc.)
    as read-only tools, so an agent can check whether a failing test is a
    known flake before debugging it as a real bug. Mutating commands
    (upload, init, clean) stay CLI-only.

    Add to your MCP client config, e.g. for Claude Code:
        $ claude mcp add flaktor -- flaktor mcp

    Example:
        $ flaktor mcp
    """
    if db_path is None:
        db_path = get_default_db_path()

    if not ensure_database_exists(db_path):
        console.print(
            Panel.fit(
                "[bold red]❌ Database not found[/bold red]\n\n"
                f"Expected location: [cyan]{db_path}[/cyan]\n\n"
                f"💡 Initialize first: [yellow]flaktor init[/yellow]",
                border_style="red",
                title="Not Initialized"
            )
        )
        raise typer.Exit(code=1)

    try:
        from .mcp_server import build_server
    except ImportError:
        console.print(
            Panel.fit(
                "[bold red]❌ MCP support not installed[/bold red]\n\n"
                r"💡 Install it with: [yellow]pip install flaktor\[mcp][/yellow]",
                border_style="red",
                title="Missing Dependency"
            )
        )
        raise typer.Exit(code=1)

    build_server(db_path).run()


@app.callback(invoke_without_command=True)
def main(
    ctx: typer.Context,
    version: bool = typer.Option(
        False,
        "--version",
        "-v",
        help="Show Flaktor version"
    )
):
    """
    🔍 Flaktor - Flaky test detection made simple.

    Stop guessing. Start knowing why your tests fail.
    """
    if version:
        console.print("[bold cyan]Flaktor[/bold cyan] version [green]0.1.0[/green]")
        console.print("[dim]Framework-agnostic flaky test intelligence[/dim]")
        raise typer.Exit()
    elif ctx.invoked_subcommand is None:
        console.print(ctx.get_help())


if __name__ == "__main__":
    app()