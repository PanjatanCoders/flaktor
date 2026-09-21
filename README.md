# Flaktor

**Flaky test detection made simple.**

Flaktor is a framework-agnostic CLI tool that tracks your test results over time and identifies flaky tests - tests that sometimes pass and sometimes fail without code changes.

## Features

- **Framework Agnostic**: Works with any test framework that outputs JUnit/xUnit XML
- **Simple CLI**: Easy-to-use commands for uploading results and viewing reports
- **Flaky Detection**: Automatically detects tests with inconsistent results
- **CI/CD Ready**: Built-in support for GitHub Actions, GitLab CI, and more
- **Beautiful Output**: Rich terminal output with tables and colored status
- **Lightweight**: SQLite database with no external dependencies

## Installation

```bash
pip install flaktor
```

## Quick Start

```bash
# Initialize the database
flaktor init

# Run your tests with JUnit XML output
pytest --junitxml=results.xml tests/

# Upload results
flaktor upload results.xml

# View flaky tests
flaktor list --flaky

# Generate a report
flaktor report
```

## Commands

| Command | Description |
|---------|-------------|
| `flaktor init` | Initialize the database |
| `flaktor upload <files>` | Upload test results from XML files |
| `flaktor list` | List tests with statistics |
| `flaktor list --flaky` | Show only flaky tests |
| `flaktor quarantine <test>` | Quarantine a test, excluding it from flaky detection |
| `flaktor unquarantine <test>` | Remove a test from quarantine |
| `flaktor tag <test> <tags...>` | Tag a test for grouping and filtering |
| `flaktor untag <test> <tag>` | Remove a tag from a test |
| `flaktor tags` | List all tags and how many tests carry each |
| `flaktor list --tag <tag>` | Show only tests with a given tag |
| `flaktor history <test>` | View detailed history for a test |
| `flaktor report` | Generate a test health report |
| `flaktor report --output report.html` | Generate a shareable HTML report |
| `flaktor export --output <file>` | Export test data to JSON or CSV |
| `flaktor compare <branch-a> <branch-b>` | Compare flakiness between two branches |
| `flaktor trend` | Show flakiness trends over time (improving/worsening) |
| `flaktor config` | Show the active `.flaktorrc` and the defaults it sets |
| `flaktor perf` | Show test duration trends and detect slowdowns |
| `flaktor notify` | Send a webhook alert for newly detected flaky tests |
| `flaktor clean` | Remove old data from the database |
| `flaktor info` | Show database information |
| `flaktor migrate` | Apply pending database schema migrations |
| `flaktor mcp` | Start the MCP server for AI coding agents |

## CI/CD Integration

Flaktor is designed for CI/CD pipelines. Track test results across runs to detect flaky tests.

### GitHub Actions

```yaml
- name: Upload to Flaktor
  run: |
    flaktor upload results.xml \
      --branch "${{ github.ref_name }}" \
      --commit "${{ github.sha }}"
```

### GitLab CI

```yaml
script:
  - flaktor upload results.xml --branch "$CI_COMMIT_REF_NAME" --commit "$CI_COMMIT_SHA"
```

### Webhook Alerts

Get notified when a new flaky test shows up, right after uploading results:

```bash
export FLAKTOR_WEBHOOK_URL=https://hooks.slack.com/services/...
flaktor upload results.xml
flaktor notify
```

`flaktor notify` only alerts on tests that weren't already flagged flaky, so re-running it in CI won't spam the same alert every build. The payload's `text` field works as-is with Slack Incoming Webhooks.

See [docs/ci-cd-integration.md](docs/ci-cd-integration.md) for complete examples for:
- GitHub Actions
- GitLab CI/CD
- Jenkins
- CircleCI
- Azure DevOps

## Configuration

Put defaults in a `.flaktorrc` file (TOML) so you don't repeat flags on every command. Flaktor looks in the current directory, then each parent directory, then your home directory. Use `flaktor --config path/to/file` or the `FLAKTOR_CONFIG` environment variable to point at a specific file.

```toml
# Global settings
db = ".flaktor/flaktor.db"        # relative paths are relative to this file
webhook = "https://hooks.slack.com/services/..."

# Per-command defaults: use the command's option names (`--min-runs` -> min_runs)
[trend]
days = 14

[notify]
min_runs = 10
```

Precedence, highest first: command-line flag, environment variable (`FLAKTOR_DB`, `FLAKTOR_WEBHOOK_URL`), `.flaktorrc`, built-in default. Unknown commands or options in the file are reported as errors rather than silently ignored. Webhook URLs are secrets, so prefer the environment variable over committing one to a shared `.flaktorrc`. Run `flaktor config` to see which file is active.

## MCP Server (for AI coding agents)

Flaktor can expose its flaky-test data to AI coding agents (Claude Code, Cursor, etc.) over the [Model Context Protocol](https://modelcontextprotocol.io), so an agent can check whether a failing test is a known flake *before* debugging it as a real bug. The server is read-only — `upload`, `init`, and `clean` stay CLI-only.

No VS Code extension is required. Flaktor ships as a standard Python MCP server that connects through your MCP client.

```bash
pip install "flaktor[mcp]"
```

Then either run it directly:

```bash
flaktor mcp
```

Or add it to your MCP client config:

### Claude Code

```bash
claude mcp add flaktor -- flaktor mcp
```

### Cursor

```json
{
  "mcpServers": {
    "flaktor": {
      "command": "flaktor",
      "args": ["mcp"]
    }
  }
}
```

### VS Code

```json
{
  "servers": {
    "flaktor": {
      "type": "stdio",
      "command": "flaktor",
      "args": ["mcp"]
    }
  }
}
```

If your client expects a config file instead of a JSON snippet, the important part is the same: run `flaktor mcp` as a stdio MCP server.

Available tools: `list_flaky_tests`, `check_test_flakiness`, `list_quarantined_tests`, `list_tags`, `list_tests_by_tag`, `list_trending_tests`, `list_duration_trends`, `get_test_history`, `get_test_summary`, `get_database_stats`.

## Understanding Flakiness

Flaktor calculates a "flip rate" for each test:

```
flip_rate = 2 * min(pass_rate, fail_rate)
```

- A test that always passes: flip_rate = 0%
- A test that always fails: flip_rate = 0%
- A test that passes 50% of the time: flip_rate = 100% (most flaky)
- A test that passes 80% of the time: flip_rate = 40%

Tests with a flip rate above 20% (default threshold) are considered flaky.

## Example Output

```
$ flaktor list --flaky

                    Flaky Tests (last 30 days)
+----------------------------------------+------+------+------+-----+--------+
| Test Name                              | Flip | Pass | Runs | P/F | Avg    |
+----------------------------------------+------+------+------+-----+--------+
| test_api.TestAuth.test_token_refresh   | 80%  | 60%  | 25   | 15/10 | 0.45s |
| test_db.TestConn.test_reconnect        | 60%  | 70%  | 20   | 14/6  | 1.23s |
| test_ui.TestLogin.test_remember_me     | 40%  | 80%  | 15   | 12/3  | 2.10s |
+----------------------------------------+------+------+------+-----+--------+
```

## Development

```bash
# Clone the repository
git clone https://github.com/PanjatanCoders/flaktor.git
cd flaktor

# Install in development mode
pip install -e .

# Run tests
pytest tests/ -v
```

## License

MIT License - see LICENSE file for details.

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.
