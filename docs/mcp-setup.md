# MCP Setup for Flaktor

Flaktor exposes its flaky-test data through a standard Python MCP server. There is no separate VS Code extension to install.

## Install

```bash
pip install "flaktor[mcp]"
```

## Start the server

```bash
flaktor mcp
```

This command starts the MCP server in stdio mode, which is the format expected by MCP-compatible clients.

## Claude Code

```bash
claude mcp add flaktor -- flaktor mcp
```

## Cursor

Add this to your MCP client config:

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

## VS Code

Use a stdio server entry such as:

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

## Available tools

- `list_flaky_tests`
- `check_test_flakiness`
- `list_quarantined_tests`
- `list_tags`
- `list_tests_by_tag`
- `list_trending_tests`
- `list_duration_trends`
- `get_test_history`
- `get_test_summary`
- `get_database_stats`

## Notes

- The server is read-only by design.
- Mutating actions such as `upload`, `init`, and `clean` stay on the CLI.
- Flaktor expects a database to exist before the MCP server starts. Initialize it first with `flaktor init`.
