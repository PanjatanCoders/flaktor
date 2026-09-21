# Release Checklist

This checklist covers the Flaktor release flow for the package and the optional MCP server support.

## 1. Verify the project state

```bash
cd /data/Projects/products/flaktor
python3 -m venv .venv
. .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e '.[dev,mcp]'
pytest -q
```

Expected result: tests pass before release.

## 2. Build the package

```bash
python -m build
```

## 3. Validate package metadata

```bash
python -m twine check dist/*
```

## 4. Version and changelog

- Confirm the version in [pyproject.toml](pyproject.toml)
- Confirm the version in [flaktor/__init__.py](flaktor/__init__.py)
- Confirm the release notes in [CHANGELOG.md](CHANGELOG.md)

## 5. Tag the release

```bash
git tag v0.2.0
git push origin v0.2.0
```

## 6. Publish to PyPI

```bash
python -m twine upload dist/*
```

## 7. Verify installation path for users

```bash
pip install "flaktor[mcp]"
flaktor --help
flaktor mcp --help
```

Expected result: the package installs successfully and the MCP command appears in the CLI help output.

## 8. MCP usage after release

Users do not install a VS Code extension. They install the Python package with the `mcp` extra:

```bash
pip install "flaktor[mcp]"
```

Then they connect their MCP client to the standard CLI server:

```bash
flaktor mcp
```

or configure the client to run:

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

## 9. Final release notes

The MCP server is released as part of the `flaktor` package, not as a separate VS Code extension or a separate package. It is made available through the optional `mcp` dependency extra.
