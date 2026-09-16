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
| `flaktor history <test>` | View detailed history for a test |
| `flaktor report` | Generate a test health report |
| `flaktor export --output <file>` | Export test data to JSON or CSV |
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

See [docs/ci-cd-integration.md](docs/ci-cd-integration.md) for complete examples for:
- GitHub Actions
- GitLab CI/CD
- Jenkins
- CircleCI
- Azure DevOps

## MCP Server (for AI coding agents)

Flaktor can expose its flaky-test data to AI coding agents (Claude Code, Cursor, etc.) over the [Model Context Protocol](https://modelcontextprotocol.io), so an agent can check whether a failing test is a known flake *before* debugging it as a real bug. The server is read-only — `upload`, `init`, and `clean` stay CLI-only.

```bash
pip install "flaktor[mcp]"
```

Add it to your MCP client config, e.g. for Claude Code:

```bash
claude mcp add flaktor -- flaktor mcp
```

Available tools: `list_flaky_tests`, `check_test_flakiness`, `get_test_history`, `get_test_summary`, `get_database_stats`.

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
