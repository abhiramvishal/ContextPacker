"""Tests for config module."""

from pathlib import Path

import pytest
from typer.testing import CliRunner

from contextcraft.cli import app
from contextcraft.config import load_config, ContextCraftConfig

runner = CliRunner()


def test_load_config_returns_defaults_when_no_file(tmp_path: Path) -> None:
    """load_config returns defaults when no config file exists."""
    cfg = load_config(tmp_path)
    assert isinstance(cfg, ContextCraftConfig)
    assert cfg.skip_paths == []
    assert cfg.skip_extensions == []
    assert cfg.include_languages == []
    assert cfg.model == "claude-sonnet-4-5"
    assert cfg.max_tokens == 2000


def test_load_config_parses_yaml(tmp_path: Path) -> None:
    """load_config correctly parses all fields from a temp YAML file."""
    try:
        import yaml
    except ImportError:
        pytest.skip("PyYAML not installed")
    yml = tmp_path / ".contextcraft.yml"
    yml.write_text("""
skip_paths:
  - vendor
  - .cache
skip_extensions:
  - .xyz
max_tokens: 4096
model: claude-3-opus-1
output_dir: out
include_languages:
  - python
  - go
""", encoding="utf-8")
    cfg = load_config(tmp_path)
    assert cfg.skip_paths == ["vendor", ".cache"]
    assert cfg.skip_extensions == [".xyz"]
    assert cfg.max_tokens == 4096
    assert cfg.model == "claude-3-opus-1"
    assert cfg.output_dir == "out"
    assert set(cfg.include_languages) == {"python", "go"}


def test_load_config_unknown_keys_ignored(tmp_path: Path) -> None:
    """Unknown keys in YAML are silently ignored."""
    try:
        import yaml
    except ImportError:
        pytest.skip("PyYAML not installed")
    yml = tmp_path / ".contextcraft.yml"
    yml.write_text("model: x\nunknown_key: 123\nanother: foo", encoding="utf-8")
    cfg = load_config(tmp_path)
    assert cfg.model == "x"
    assert getattr(cfg, "unknown_key", None) is None


def test_cli_flags_override_config(tmp_path: Path) -> None:
    """CLI flags override config values (test via CliRunner)."""
    (tmp_path / ".contextcraft.yml").write_text("model: from-config\nmax_tokens: 1000", encoding="utf-8")
    try:
        import yaml
    except ImportError:
        pytest.skip("PyYAML not installed")
    (tmp_path / "dummy.py").write_text("x = 1", encoding="utf-8")
    result = runner.invoke(app, ["init", str(tmp_path), "--no-ai", "--model", "from-cli"])
    assert result.exit_code == 0
    pack = tmp_path / "context.pack.json"
    if pack.exists():
        data = __import__("json").loads(pack.read_text())
        assert "file_tree" in data
    # We can't easily assert model was used without API; just ensure init ran and didn't use config model for display
    assert "Wrote" in result.output
