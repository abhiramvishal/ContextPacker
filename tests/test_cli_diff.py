"""Tests for contextcraft diff command."""

from pathlib import Path

import pytest
from typer.testing import CliRunner

from contextcraft.cli import app

runner = CliRunner()


def test_diff_exits_1_when_context_pack_json_missing(tmp_path: Path) -> None:
    """diff exits with code 1 when context.pack.json is missing."""
    result = runner.invoke(app, ["diff", str(tmp_path)])
    assert result.exit_code == 1
    assert "not found" in result.output.lower() or "context.pack.json" in result.output


def test_diff_detects_new_file_added(tmp_path: Path) -> None:
    """diff detects a new file added (mock old JSON vs new scan)."""
    pack = tmp_path / "context.pack.json"
    pack.write_text("""{
        "file_tree": {"root": "x", "primary_languages": [], "file_count": 1},
        "file_analyses": [{"path": "old.py", "language": "python", "functions": [], "classes": []}],
        "patterns": {},
        "dependency_graph": {},
        "git_context": null,
        "warnings": []
    }""", encoding="utf-8")
    (tmp_path / "old.py").write_text("x = 1", encoding="utf-8")
    (tmp_path / "new.py").write_text("y = 2", encoding="utf-8")
    result = runner.invoke(app, ["diff", str(tmp_path)])
    assert result.exit_code == 0
    assert "new.py" in result.output or "New files" in result.output
