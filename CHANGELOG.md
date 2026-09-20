# Changelog

All notable changes to Flaktor are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the project uses
[Semantic Versioning](https://semver.org/).

## [0.2.0] - 2026-09-20

### Added

- `flaktor export` - export a summary or a single test's raw history to JSON or CSV.
- `flaktor compare <branch-a> <branch-b>` - diff per-test flakiness between two branches, worst regression first.
- `flaktor trend` - compare each test's flip rate in the last N days against the N days before, labelled worsening, improving, stable or new.
- `flaktor perf` - detect test slowdowns by comparing average duration (passed runs only) across the same two windows. A change must exceed both `--threshold` (percent) and `--min-delta` (seconds) to count, so noise on very fast tests is ignored.
- `flaktor quarantine` / `unquarantine` and `flaktor list --quarantined` - set known-flaky tests aside. Quarantined tests are hidden from flaky results, including the MCP tools, unless explicitly included.
- `flaktor tag` / `untag` / `tags` and `flaktor list --tag` - group tests with tags.
- `flaktor notify` - POST a Slack-compatible webhook alert for newly detected flaky tests. Alert state only advances after a successful send, so nothing is silently missed. Set the URL with `--webhook` or `FLAKTOR_WEBHOOK_URL`.
- `flaktor report --output report.html` - generate a self-contained, shareable HTML report with light and dark themes.
- `flaktor migrate` - apply pending database schema migrations. `flaktor info` now shows the schema version and hints when a migration is needed.
- `.flaktorrc` config file (TOML) for default settings, with `--config` / `FLAKTOR_CONFIG` to select a file and `flaktor config` to inspect the active one. Precedence: command-line flag, environment variable, config file, built-in default. Unknown commands or options in the file are reported as errors.
- MCP server tools: `list_quarantined_tests`, `list_tags`, `list_tests_by_tag`, `list_trending_tests` and `list_duration_trends`. `check_test_flakiness` now includes a test's tags.

### Changed

- The database schema is now version 4 (quarantine, webhook alert state and tags). Fresh databases start at the latest version; existing 0.1.0 databases need a one-time `flaktor migrate`.
- `flaktor list` shows a Tags column.
- `tomli` is now a dependency on Python 3.10 (Python 3.11+ uses the standard library's `tomllib`).
- `flaktor --version` now reads the version from the package instead of a hardcoded string.

## [0.1.0] - 2026-09-14

Initial public release: JUnit XML, Cucumber/BDD and Playwright result parsing,
flaky-test detection, history, reports, `clean`, CI/CD examples and an MCP server
for AI coding agents.
