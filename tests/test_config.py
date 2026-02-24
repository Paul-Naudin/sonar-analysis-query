"""Tests for sonar_report/config.py"""

import os
import textwrap
from pathlib import Path

import pytest

from sonar_report.config import (
    Config,
    ConfigError,
    ProjectNotFoundError,
    generate_template,
    load,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def write_config(tmp_path: Path, content: str) -> Path:
    p = tmp_path / "sonar-config.yaml"
    p.write_text(textwrap.dedent(content), encoding="utf-8")
    return p


VALID_YAML = """\
    server:
      url: "https://sonar.example.com"
      token: "squ_abc123"
    projects:
      wcs: "ch.corren.wcs"
      wct: "ch.corren.wct"
    """


# ---------------------------------------------------------------------------
# load() — happy path
# ---------------------------------------------------------------------------

def test_load_valid_config(tmp_path):
    p = write_config(tmp_path, VALID_YAML)
    config = load(str(p))
    assert config.url == "https://sonar.example.com"
    assert config.token == "squ_abc123"
    assert config.projects == {"wcs": "ch.corren.wcs", "wct": "ch.corren.wct"}


# ---------------------------------------------------------------------------
# load() — missing file
# ---------------------------------------------------------------------------

def test_load_missing_file(tmp_path):
    with pytest.raises(ConfigError, match="not found"):
        load(str(tmp_path / "no-such-file.yaml"))


# ---------------------------------------------------------------------------
# load() — missing required fields
# ---------------------------------------------------------------------------

def test_load_missing_url(tmp_path):
    p = write_config(tmp_path, """\
        server:
          token: "squ_abc123"
        projects:
          wcs: "ch.corren.wcs"
        """)
    with pytest.raises(ConfigError, match="server.url"):
        load(str(p))


def test_load_missing_token(tmp_path):
    p = write_config(tmp_path, """\
        server:
          url: "https://sonar.example.com"
        projects:
          wcs: "ch.corren.wcs"
        """)
    with pytest.raises(ConfigError, match="server.token"):
        load(str(p))


def test_load_empty_projects(tmp_path):
    p = write_config(tmp_path, """\
        server:
          url: "https://sonar.example.com"
          token: "squ_abc123"
        projects: {}
        """)
    with pytest.raises(ConfigError, match="projects"):
        load(str(p))


# ---------------------------------------------------------------------------
# load() — environment variable overrides
# ---------------------------------------------------------------------------

def test_env_sonar_url_overrides_config(tmp_path, monkeypatch):
    p = write_config(tmp_path, VALID_YAML)
    monkeypatch.setenv("SONAR_URL", "https://override.example.com")
    config = load(str(p))
    assert config.url == "https://override.example.com"


def test_env_sonar_token_overrides_config(tmp_path, monkeypatch):
    p = write_config(tmp_path, VALID_YAML)
    monkeypatch.setenv("SONAR_TOKEN", "squ_override")
    config = load(str(p))
    assert config.token == "squ_override"


def test_env_vars_can_supply_missing_fields(tmp_path, monkeypatch):
    """Config with no server section is valid when env vars are set."""
    p = write_config(tmp_path, """\
        projects:
          wcs: "ch.corren.wcs"
        """)
    monkeypatch.setenv("SONAR_URL", "https://sonar.example.com")
    monkeypatch.setenv("SONAR_TOKEN", "squ_from_env")
    config = load(str(p))
    assert config.url == "https://sonar.example.com"
    assert config.token == "squ_from_env"


# ---------------------------------------------------------------------------
# resolve_project()
# ---------------------------------------------------------------------------

def test_resolve_known_alias():
    config = Config(url="u", token="t", projects={"wcs": "ch.corren.wcs"})
    assert config.resolve_project("wcs") == "ch.corren.wcs"


def test_resolve_raw_key_fallback():
    """Passing the raw SonarQube key directly should also work."""
    config = Config(url="u", token="t", projects={"wcs": "ch.corren.wcs"})
    assert config.resolve_project("ch.corren.wcs") == "ch.corren.wcs"


def test_resolve_unknown_raises():
    config = Config(url="u", token="t", projects={"wcs": "ch.corren.wcs"})
    with pytest.raises(ProjectNotFoundError, match="unknown-project"):
        config.resolve_project("unknown-project")


# ---------------------------------------------------------------------------
# generate_template()
# ---------------------------------------------------------------------------

def test_generate_template_creates_file(tmp_path):
    out = tmp_path / "sonar-config.yaml"
    generate_template(str(out))
    assert out.exists()
    content = out.read_text()
    assert "server:" in content
    assert "projects:" in content


def test_generate_template_refuses_to_overwrite(tmp_path):
    out = tmp_path / "sonar-config.yaml"
    out.write_text("existing content")
    with pytest.raises(ConfigError, match="already exists"):
        generate_template(str(out))

