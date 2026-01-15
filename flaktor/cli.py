"""
CLI interface for Flaktor.

Built with Typer for professional, user-friendly command-line experience.
"""

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from pathlib import Path
from typing import Optional

from .database import Database, DatabaseError

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
                f"   https://github.com/yourusername/flaktor/issues",
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


@app.callback()
def main(
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


if __name__ == "__main__":
    app()