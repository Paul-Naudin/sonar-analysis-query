"""Configuration loading and validation.

Usage:
    config = load("sonar-config.yaml")       # raises ConfigError on bad config
    key = config.resolve_project("wcs")      # returns "ch.corren.wcs"
    generate_template("sonar-config.yaml")   # writes example file to disk
"""

import os
from dataclasses import dataclass, field
from pathlib import Path

import yaml


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------

class ConfigError(Exception):
    """Raised when the configuration is missing or invalid."""


class ProjectNotFoundError(ConfigError):
    """Raised when a project alias is not found in the config."""


# ---------------------------------------------------------------------------
# Config dataclass
# ---------------------------------------------------------------------------

@dataclass
class Config:
    url: str
    token: str
    projects: dict[str, str] = field(default_factory=dict)

    def resolve_project(self, name: str) -> str:
        """Return the SonarQube project key for a given alias.

        Accepts either a configured alias (e.g. "wcs") or a raw project key
        passed directly (e.g. "ch.corren.wcs") as a convenience fallback.
        """
        if name in self.projects:
            return self.projects[name]
        # Allow passing the raw key directly if it's not in the mapping
        if name in self.projects.values():
            return name
        available = ", ".join(self.projects.keys()) or "(none configured)"
        raise ProjectNotFoundError(
            f"Project '{name}' not found. Available aliases: {available}"
        )


# ---------------------------------------------------------------------------
# Loader
# ---------------------------------------------------------------------------

def load(config_path: str = "sonar-config.yaml") -> Config:
    """Load and validate configuration from a YAML file.

    Environment variables SONAR_URL and SONAR_TOKEN override file values.

    Raises:
        ConfigError: if the file is missing, malformed, or required fields
                     are absent.
    """
    path = Path(config_path)

    if not path.exists():
        raise ConfigError(
            f"Config file not found: '{config_path}'\n"
            "Run `python -m sonar_report init` to generate a template."
        )

    try:
        with path.open(encoding="utf-8") as f:
            raw = yaml.safe_load(f)
    except yaml.YAMLError as exc:
        raise ConfigError(f"Failed to parse '{config_path}': {exc}") from exc

    if not isinstance(raw, dict):
        raise ConfigError(f"'{config_path}' must be a YAML mapping at the top level.")

    server = raw.get("server") or {}
    url   = os.environ.get("SONAR_URL")  or server.get("url",   "")
    token = os.environ.get("SONAR_TOKEN") or server.get("token", "")
    projects: dict[str, str] = raw.get("projects") or {}

    config = Config(url=str(url).strip(), token=str(token).strip(), projects=projects)
    _validate(config)
    return config


def _validate(config: Config) -> None:
    """Raise ConfigError if required fields are missing."""
    errors: list[str] = []

    if not config.url:
        errors.append(
            "  - 'server.url' is missing (or set the SONAR_URL environment variable)"
        )
    if not config.token:
        errors.append(
            "  - 'server.token' is missing (or set the SONAR_TOKEN environment variable)"
        )
    if not config.projects:
        errors.append(
            "  - 'projects' mapping is empty — add at least one project alias"
        )

    if errors:
        raise ConfigError("Invalid configuration:\n" + "\n".join(errors))


# ---------------------------------------------------------------------------
# Template generator (used by `init` command)
# ---------------------------------------------------------------------------

TEMPLATE = """\
server:
  url: "https://sonar.example.com"
  token: "squ_xxxxxxxxxxxx"       # Generate at: <your-sonar-url>/account/security

projects:
  # Human-readable alias: SonarQube project key
  my-project: "com.example.my-project"
  another:    "com.example.another-service"
"""


def generate_template(output_path: str = "sonar-config.yaml") -> None:
    """Write a template sonar-config.yaml to *output_path*.

    Raises:
        ConfigError: if the file already exists (to avoid overwriting secrets).
    """
    path = Path(output_path)
    if path.exists():
        raise ConfigError(
            f"'{output_path}' already exists. Remove it first or choose a different path."
        )
    path.write_text(TEMPLATE, encoding="utf-8")

