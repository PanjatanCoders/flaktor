"""
Config file support for Flaktor.

A `.flaktorrc` file (TOML) sets defaults so common options don't have to be
repeated on every command. Precedence, highest first: command-line flag,
environment variable, config file, built-in default.

Example:

    db = ".flaktor/flaktor.db"

    [trend]
    days = 14

    [notify]
    min_runs = 10
"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Optional, Set

try:
    import tomllib
except ModuleNotFoundError:  # Python < 3.11
    import tomli as tomllib

CONFIG_FILENAME = ".flaktorrc"

# Settings that apply outside any one command. Everything else at the top
# level must be a [command] table.
GLOBAL_SETTINGS = ("db", "webhook")

# Command tables may spell the database option `db` (as on the command line).
_OPTION_ALIASES = {"db": "db_path"}


class ConfigError(Exception):
    """Raised when a config file is unreadable or invalid."""


@dataclass
class Config:
    """
    Parsed contents of a config file.

    Attributes:
        path: File the config was loaded from (None if no file was found)
        settings: Global settings (`db`, `webhook`)
        commands: Per-command option defaults, keyed by command name, with
            option names normalized to their Python parameter names
    """
    path: Optional[Path] = None
    settings: Dict[str, str] = field(default_factory=dict)
    commands: Dict[str, dict] = field(default_factory=dict)

    @property
    def db(self) -> Optional[Path]:
        value = self.settings.get("db")
        return Path(value) if value else None

    @property
    def webhook(self) -> Optional[str]:
        return self.settings.get("webhook")

    def default_map(self) -> Dict[str, dict]:
        """Per-command defaults in the shape Click's `default_map` expects."""
        return {name: dict(options) for name, options in self.commands.items()}


def find_config_file(start: Optional[Path] = None) -> Optional[Path]:
    """
    Locate a config file.

    Looks for `.flaktorrc` in `start` (default: the current directory) and
    each of its parents, then in the user's home directory.
    """
    directory = (start or Path.cwd()).resolve()
    for candidate_dir in [directory, *directory.parents]:
        candidate = candidate_dir / CONFIG_FILENAME
        if candidate.is_file():
            return candidate

    home_candidate = Path.home() / CONFIG_FILENAME
    if home_candidate.is_file():
        return home_candidate
    return None


def _resolve_path(value: str, base: Path) -> str:
    """Expand `~` and anchor relative paths to the config file's directory."""
    path = Path(value).expanduser()
    if not path.is_absolute():
        path = base / path
    return str(path)


def load_config(path: Optional[Path] = None) -> Config:
    """
    Load a config file.

    Args:
        path: Explicit config file. If None, the file is discovered with
            find_config_file(); finding none is not an error.

    Raises:
        ConfigError: If an explicit file is missing, or a file is not valid
            TOML or has settings of the wrong shape.
    """
    if path is not None:
        if not path.is_file():
            raise ConfigError(f"Config file not found: {path}")
    else:
        path = find_config_file()
        if path is None:
            return Config()

    try:
        with open(path, "rb") as f:
            raw = tomllib.load(f)
    except tomllib.TOMLDecodeError as e:
        raise ConfigError(f"Invalid TOML in {path}: {e}") from e
    except OSError as e:
        raise ConfigError(f"Cannot read {path}: {e}") from e

    base = path.resolve().parent
    config = Config(path=path)

    for key, value in raw.items():
        if isinstance(value, dict):
            options = {}
            for option, option_value in value.items():
                name = option.replace("-", "_")
                name = _OPTION_ALIASES.get(name, name)
                if name == "db_path" and isinstance(option_value, str):
                    option_value = _resolve_path(option_value, base)
                options[name] = option_value
            config.commands[key] = options
        elif key in GLOBAL_SETTINGS:
            if not isinstance(value, str):
                raise ConfigError(f"{path}: '{key}' must be a string")
            config.settings[key] = _resolve_path(value, base) if key == "db" else value
        else:
            raise ConfigError(
                f"{path}: unknown setting '{key}' "
                f"(global settings: {', '.join(GLOBAL_SETTINGS)}; "
                f"anything else belongs under a [command] table)"
            )

    return config


def validate_config(config: Config, known_options: Dict[str, Set[str]]) -> None:
    """
    Check that a config only refers to real commands and options.

    Click silently ignores unknown defaults, so without this a typo like
    `[trned]` or `min-run = 5` would do nothing and never be noticed.

    Args:
        config: The loaded config
        known_options: Command name -> set of that command's parameter names

    Raises:
        ConfigError: On the first unknown command or option
    """
    for command, options in config.commands.items():
        if command not in known_options:
            raise ConfigError(
                f"{config.path}: unknown command '[{command}]' "
                f"(commands: {', '.join(sorted(known_options))})"
            )
        for option in options:
            if option not in known_options[command]:
                raise ConfigError(
                    f"{config.path}: unknown option '{option}' for command '{command}' "
                    f"(options: {', '.join(sorted(known_options[command]))})"
                )
