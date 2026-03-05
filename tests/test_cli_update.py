"""Tests for contextcraft update command."""

from pathlib import Path
from unittest.mock import patch

import pytest
from typer.testing import CliRunner

from contextcraft.cli import app

runner = CliRunner()


def test_update_fails_when_context_pack_json_missing(tmp_path: Path) -> None:
    """update command fails gracefully when context.pack.json is missing."""
    result = runner.invoke(app, ["update", str(tmp_path)])
    assert result.exit_code != 0
    assert "context.pack.json not found" in result.output or "not found" in result.output.lower()


def test_update_fails_when_no_raw_analysis_keys(tmp_path: Path) -> None:
    """update command fails when context.pack.json has no raw analysis keys (e.g. only 'synthesis')."""
    pack = tmp_path / "context.pack.json"
    pack.write_text('{"synthesis": "some text"}', encoding="utf-8")
    with patch("contextcraft.cli.synthesize") as mock_synth:
        result = runner.invoke(app, ["update", str(tmp_path)])
    assert result.exit_code != 0
    assert "missing raw analysis" in result.output.lower() or "missing" in result.output.lower()
    mock_synth.assert_not_called()
