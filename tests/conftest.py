"""Shared test fixtures."""

import pytest


@pytest.fixture(autouse=True)
def isolated_home(tmp_path, monkeypatch):
    """Point HOME at an empty dir so a real ~/.flaktorrc or ~/.flaktor can't leak into tests."""
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.delenv("FLAKTOR_CONFIG", raising=False)
    monkeypatch.delenv("FLAKTOR_DB", raising=False)
    monkeypatch.delenv("FLAKTOR_WEBHOOK_URL", raising=False)
