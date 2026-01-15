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
import glob as glob_module

from .database import Database, DatabaseError
from .parser import parse_junit_xml, parse_multiple_files, ParserError

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
        
        # Create info table
        table = Table(show_header=False, box=None, padding=(0, 2))
        table.add_column("Key", style="cyan")
        table.add_column("Value", style="green")
        
        table.add_row("📍 Database Path", str(db_path))
        table.add_row("📦 Database Size", f"{stats['database_size_mb']} MB")
        table.add_row("🏃 Total Test Runs", f"{stats['total_runs']:,}")
        table.add_row("📝 Total Test Results", f"{stats['total_results']:,}")
        table.add_row("🧪 Unique Tests", f"{stats['unique_tests']:,}")
        
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
        
    except DatabaseError as e:
        console.print(
            Panel.fit(
                f"[bold red]❌ Failed to read database[/bold red]\n\n{str(e)}",
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
def upload(
    files: List[Path] = typer.Argument(
        ...,
        help="Path(s) to JUnit/xUnit XML file(s). Supports glob patterns."
    ),
    db_path: Optional[Path] = typer.Option(
        None,
        "--db",
        "-d",
        help="Database path (default: auto-detect)"
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
    📤 Upload test results from XML files.

    Parse JUnit/xUnit XML files and store results in the database.
    Supports glob patterns to upload multiple files at once.

    Examples:
        # Upload a single file
        $ flaktor upload results.xml

        # Upload multiple files
        $ flaktor upload test-results/*.xml

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

    # Filter to only existing XML files
    xml_files = [f for f in all_files if f.exists() and f.suffix.lower() == ".xml"]

    if not xml_files:
        console.print(
            Panel.fit(
                "[bold red]❌ No valid XML files found[/bold red]\n\n"
                f"Found {len(all_files)} file(s), but none are existing XML files.",
                border_style="red",
                title="Error"
            )
        )
        raise typer.Exit(code=1)

    try:
        with console.status(f"[bold blue]Parsing {len(xml_files)} file(s)...", spinner="dots"):
            if len(xml_files) == 1:
                parsed = parse_junit_xml(
                    xml_files[0],
                    run_id=run_id,
                    branch=branch,
                    commit_hash=commit,
                    environment=environment,
                )
                parse_errors: List[str] = []
            else:
                parsed, parse_errors = parse_multiple_files(
                    xml_files,
                    run_id=run_id,
                    branch=branch,
                    commit_hash=commit,
                    environment=environment,
                )

        # Show parse errors if any
        if parse_errors:
            console.print()
            for err in parse_errors:
                console.print(f"[yellow]⚠️  {err}[/yellow]")

        if parsed.total_tests == 0:
            console.print(
                Panel.fit(
                    "[bold yellow]⚠️  No test cases found[/bold yellow]\n\n"
                    "The XML file(s) were parsed but contained no test cases.",
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

        console.print()
        console.print(
            Panel.fit(
                f"[bold green]✅ Upload successful![/bold green]\n\n"
                f"📁 Files processed: [cyan]{len(xml_files)}[/cyan]\n"
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