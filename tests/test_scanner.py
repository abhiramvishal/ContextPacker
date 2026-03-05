"""Tests for the scanner module."""

from pathlib import Path

import pytest

from contextcraft.scanner import (
    FileInfo,
    FileTree,
    scan_repo,
    read_file_safe,
)


def test_scan_repo_not_a_directory(tmp_path: Path) -> None:
    """Scanning a file raises NotADirectoryError."""
    f = tmp_path / "file.txt"
    f.write_text("x")
    with pytest.raises(NotADirectoryError):
        scan_repo(f)


def test_scan_repo_empty_dir(tmp_path: Path) -> None:
    """Scanning an empty directory returns empty file list."""
    tree = scan_repo(tmp_path)
    assert tree.root == tmp_path.resolve()
    assert tree.files == []
    assert tree.primary_languages == []


def test_scan_repo_respects_gitignore(tmp_path: Path) -> None:
    """Files and dirs in .gitignore are skipped."""
    (tmp_path / ".gitignore").write_text("skipme.txt\nignore_dir/")
    (tmp_path / "keep.txt").write_text("keep")
    (tmp_path / "skipme.txt").write_text("skip")
    (tmp_path / "ignore_dir").mkdir()
    (tmp_path / "ignore_dir" / "x.txt").write_text("x")
    tree = scan_repo(tmp_path)
    paths = {f.relative_path for f in tree.files}
    assert "keep.txt" in paths
    assert "skipme.txt" not in paths
    assert not any(p.startswith("ignore_dir") for p in paths)


def test_scan_repo_primary_languages(tmp_path: Path) -> None:
    """Primary languages are detected by file count."""
    (tmp_path / "a.py").write_text("# py")
    (tmp_path / "b.py").write_text("# py")
    (tmp_path / "c.js").write_text("// js")
    tree = scan_repo(tmp_path)
    assert len(tree.files) == 3
    assert tree.primary_languages[0][0] == "python"
    assert tree.primary_languages[0][1] == 2
    assert tree.primary_languages[1][0] == "javascript"
    assert tree.primary_languages[1][1] == 1


def test_file_info_language() -> None:
    """FileInfo.language returns correct language for extension."""
    info = FileInfo(
        path=Path("/x/foo.py"),
        relative_path="foo.py",
        extension=".py",
        size_bytes=0,
        last_modified=0.0,
    )
    assert info.language == "python"


def test_read_file_safe_success(tmp_path: Path) -> None:
    """read_file_safe returns content for valid UTF-8 file."""
    f = tmp_path / "t.txt"
    f.write_text("hello", encoding="utf-8")
    assert read_file_safe(f) == "hello"


def test_read_file_safe_invalid_encoding(tmp_path: Path) -> None:
    """read_file_safe returns None for invalid UTF-8."""
    f = tmp_path / "t.bin"
    f.write_bytes(b"\xff\xfe")
    assert read_file_safe(f) is None


def test_read_file_safe_missing() -> None:
    """read_file_safe returns None for missing file."""
    assert read_file_safe(Path("/nonexistent/path/file.txt")) is None
