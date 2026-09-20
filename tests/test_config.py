"""Tests for .flaktorrc config file support."""

import pytest
from datetime import datetime, timedelta
from pathlib import Path
from typer.testing import CliRunner

from flaktor.cli import app
from flaktor.config import (
    ConfigError,
    find_config_file,
    load_config,
    validate_config,
)
from flaktor.database import Database

runner = CliRunner()


class TestFindConfigFile:
    """Tests for config file discovery."""

    def test_finds_file_in_start_directory(self, tmp_path: Path):
        rc = tmp_path / ".flaktorrc"
        rc.write_text("")

        assert find_config_file(tmp_path) == rc.resolve()

    def test_finds_file_in_parent_directory(self, tmp_path: Path):
        rc = tmp_path / ".flaktorrc"
        rc.write_text("")
        child = tmp_path / "a" / "b"
        child.mkdir(parents=True)

        assert find_config_file(child) == rc.resolve()

    def test_falls_back_to_home(self, tmp_path: Path, monkeypatch):
        home = tmp_path / "home"
        (home / ".flaktorrc").write_text("")
        project = tmp_path / "project"
        project.mkdir()
        monkeypatch.setenv("HOME", str(home))

        assert find_config_file(project) == home / ".flaktorrc"

    def test_returns_none_when_absent(self, tmp_path: Path):
        project = tmp_path / "project"
        project.mkdir()

        assert find_config_file(project) is None


class TestLoadConfig:
    """Tests for parsing config files."""

    def _write(self, tmp_path: Path, content: str) -> Path:
        rc = tmp_path / ".flaktorrc"
        rc.write_text(content)
        return rc

    def test_parses_global_and_command_settings(self, tmp_path: Path):
        rc = self._write(tmp_path, 'webhook = "https://x.test/hook"\n[trend]\ndays = 14\n')

        config = load_config(rc)

        assert config.webhook == "https://x.test/hook"
        assert config.commands == {"trend": {"days": 14}}

    def test_normalizes_option_names(self, tmp_path: Path):
        rc = self._write(tmp_path, "[notify]\nmin-runs = 10\n")

        assert load_config(rc).commands["notify"] == {"min_runs": 10}

    def test_relative_db_is_anchored_to_config_file(self, tmp_path: Path):
        rc = self._write(tmp_path, 'db = "data/flaktor.db"\n')

        assert load_config(rc).db == tmp_path.resolve() / "data" / "flaktor.db"

    def test_command_db_alias_maps_to_db_path(self, tmp_path: Path):
        rc = self._write(tmp_path, '[trend]\ndb = "x.db"\n')

        assert load_config(rc).commands["trend"] == {"db_path": str(tmp_path.resolve() / "x.db")}

    def test_missing_explicit_file_errors(self, tmp_path: Path):
        with pytest.raises(ConfigError, match="not found"):
            load_config(tmp_path / "nope")

    def test_invalid_toml_errors(self, tmp_path: Path):
        rc = self._write(tmp_path, "this is = = not toml")

        with pytest.raises(ConfigError, match="Invalid TOML"):
            load_config(rc)

    def test_unknown_global_setting_errors(self, tmp_path: Path):
        rc = self._write(tmp_path, "days = 5\n")

        with pytest.raises(ConfigError, match="unknown setting 'days'"):
            load_config(rc)

    def test_non_string_global_errors(self, tmp_path: Path):
        rc = self._write(tmp_path, "db = 5\n")

        with pytest.raises(ConfigError, match="must be a string"):
            load_config(rc)


class TestValidateConfig:
    """Tests for typo detection."""

    def test_rejects_unknown_command(self, tmp_path: Path):
        rc = tmp_path / ".flaktorrc"
        rc.write_text("[trned]\ndays = 7\n")

        with pytest.raises(ConfigError, match="unknown command '\\[trned\\]'"):
            validate_config(load_config(rc), {"trend": {"days"}})

    def test_rejects_unknown_option(self, tmp_path: Path):
        rc = tmp_path / ".flaktorrc"
        rc.write_text("[trend]\ndayz = 7\n")

        with pytest.raises(ConfigError, match="unknown option 'dayz'"):
            validate_config(load_config(rc), {"trend": {"days"}})


class TestConfigInCli:
    """End-to-end tests: config values reaching real commands."""

    def _upload_at(self, db_path: Path, tmp_path: Path, name: str, days_ago: int, seq: int):
        timestamp = (datetime.now() - timedelta(days=days_ago)).isoformat(timespec="seconds")
        xml = tmp_path / f"{name}-{seq}.xml"
        xml.write_text(f"""<?xml version="1.0" encoding="UTF-8"?>
        <testsuite name="s" tests="1" failures="0" timestamp="{timestamp}">
            <testcase name="{name}" classname="T" time="0.1"/>
        </testsuite>
        """)
        runner.invoke(app, ["upload", str(xml), "--db", str(db_path)])

    def test_db_setting_is_used_when_no_flag(self, tmp_path: Path, monkeypatch):
        db_path = tmp_path / "custom" / "my.db"
        db_path.parent.mkdir()
        with Database(db_path) as db:
            db.initialize_schema()
        (tmp_path / ".flaktorrc").write_text(f'db = "{db_path}"\n')
        monkeypatch.chdir(tmp_path)

        result = runner.invoke(app, ["info"])

        # The default locations don't exist, so success means the config's db was used.
        assert result.exit_code == 0
        assert "Flaktor Database Info" in result.stdout

    def test_env_var_beats_config_db(self, tmp_path: Path, monkeypatch):
        db_path = tmp_path / "from_config.db"
        with Database(db_path) as db:
            db.initialize_schema()
        (tmp_path / ".flaktorrc").write_text(f'db = "{db_path}"\n')
        monkeypatch.setenv("FLAKTOR_DB", str(tmp_path / "from_env.db"))  # doesn't exist
        monkeypatch.chdir(tmp_path)

        result = runner.invoke(app, ["info"])

        assert result.exit_code == 1

    def test_command_defaults_apply(self, tmp_path: Path, monkeypatch):
        """Config sets `min_runs`, so a test with too few runs is excluded without a flag."""
        db_path = tmp_path / "flaktor.db"
        with Database(db_path) as db:
            db.initialize_schema()
        for i in range(3):
            self._upload_at(db_path, tmp_path, "test_x", i, i)
        (tmp_path / ".flaktorrc").write_text("[trend]\nmin_runs = 10\n")
        monkeypatch.chdir(tmp_path)

        result = runner.invoke(app, ["trend", "--db", str(db_path)])

        assert "at least 10 run(s)" in result.stdout

    def test_missing_explicit_config_file_errors(self, tmp_path: Path):
        result = runner.invoke(app, ["--config", str(tmp_path / "nope"), "info"])

        assert result.exit_code == 1
        assert "Config file not found" in result.stdout

    def test_cli_flag_beats_config(self, tmp_path: Path, monkeypatch):
        db_path = tmp_path / "flaktor.db"
        with Database(db_path) as db:
            db.initialize_schema()
        (tmp_path / ".flaktorrc").write_text("[trend]\nmin_runs = 10\n")
        monkeypatch.chdir(tmp_path)

        result = runner.invoke(app, ["trend", "--db", str(db_path), "--min-runs", "2"])

        assert "at least 2 run(s)" in result.stdout

    def test_explicit_config_option(self, tmp_path: Path, monkeypatch):
        db_path = tmp_path / "flaktor.db"
        with Database(db_path) as db:
            db.initialize_schema()
        rc = tmp_path / "elsewhere.toml"
        rc.write_text("[trend]\nmin_runs = 7\n")

        result = runner.invoke(app, ["--config", str(rc), "trend", "--db", str(db_path)])

        assert "at least 7 run(s)" in result.stdout

    def test_config_env_var(self, tmp_path: Path, monkeypatch):
        db_path = tmp_path / "flaktor.db"
        with Database(db_path) as db:
            db.initialize_schema()
        rc = tmp_path / "elsewhere.toml"
        rc.write_text("[trend]\nmin_runs = 8\n")
        monkeypatch.setenv("FLAKTOR_CONFIG", str(rc))

        result = runner.invoke(app, ["trend", "--db", str(db_path)])

        assert "at least 8 run(s)" in result.stdout

    def test_invalid_config_exits_with_error(self, tmp_path: Path, monkeypatch):
        (tmp_path / ".flaktorrc").write_text("[trned]\ndays = 7\n")
        monkeypatch.chdir(tmp_path)

        result = runner.invoke(app, ["info"])

        assert result.exit_code == 1
        assert "Invalid config" in result.stdout
        assert "trned" in result.stdout

    def test_webhook_setting_is_used_by_notify(self, tmp_path: Path, monkeypatch):
        """With a webhook in config, notify gets past the 'no webhook configured' branch."""
        db_path = tmp_path / "flaktor.db"
        with Database(db_path) as db:
            db.initialize_schema()
        (tmp_path / ".flaktorrc").write_text('webhook = "https://hooks.test/abc"\n')
        monkeypatch.chdir(tmp_path)

        result = runner.invoke(app, ["notify", "--db", str(db_path)])

        assert result.exit_code == 0
        assert "No webhook configured" not in result.stdout

    def test_config_command_without_file(self, tmp_path: Path, monkeypatch):
        monkeypatch.chdir(tmp_path)

        result = runner.invoke(app, ["config"])

        assert result.exit_code == 0
        assert "No config file found" in result.stdout

    def test_config_command_shows_settings_and_masks_webhook(self, tmp_path: Path, monkeypatch):
        (tmp_path / ".flaktorrc").write_text(
            'webhook = "https://hooks.slack.com/services/T000/B000/SECRET"\n[trend]\ndays = 14\n'
        )
        monkeypatch.chdir(tmp_path)

        result = runner.invoke(app, ["config"])

        assert result.exit_code == 0
        assert "days" in result.stdout
        assert "14" in result.stdout
        assert "hooks.slack.com" in result.stdout
        assert "SECRET" not in result.stdout
