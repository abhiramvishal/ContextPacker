"""Tests for git_analyzer module."""

from pathlib import Path

import pytest

from contextcraft.analyzer.git_analyzer import analyze_git, git_context_to_dict
from contextcraft.scanner import FileTree


def test_contributors_structure_and_commit_frequency(tmp_path: Path) -> None:
    """Mock git repo: contributors list has correct structure; commit_frequency has 8 entries."""
    try:
        import git
    except ImportError:
        pytest.skip("gitpython not installed")

    repo = git.Repo.init(tmp_path)
    (tmp_path / "f.py").write_text("x")
    repo.index.add(["f.py"])
    repo.index.commit("first", author=git.Actor("Alice", "alice@example.com"))
    (tmp_path / "f.py").write_text("y")
    repo.index.add(["f.py"])
    repo.index.commit("second", author=git.Actor("Alice", "alice@example.com"))
    repo.index.add(["f.py"])
    repo.index.commit("third", author=git.Actor("Bob", "bob@example.com"))

    ctx = analyze_git(tmp_path)
    assert ctx is not None
    assert ctx.contributors is not None
    for c in ctx.contributors:
        assert "author" in c
        assert "commits" in c
        assert isinstance(c["author"], str)
        assert isinstance(c["commits"], int)
    assert len(ctx.commit_frequency) == 8
    assert all(isinstance(x, int) for x in ctx.commit_frequency)


def test_git_context_to_dict_includes_new_fields() -> None:
    """git_context_to_dict includes contributors and commit_frequency."""
    from contextcraft.analyzer.git_analyzer import GitContext

    ctx = GitContext(
        contributors=[{"author": "A <a@x.com>", "commits": 5}],
        commit_frequency=[1, 2, 3, 4, 5, 6, 7, 8],
    )
    d = git_context_to_dict(ctx)
    assert d is not None
    assert d["contributors"] == [{"author": "A <a@x.com>", "commits": 5}]
    assert d["commit_frequency"] == [1, 2, 3, 4, 5, 6, 7, 8]
