"""File tree traversal and scanning with .gitignore-aware filtering."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

import pathspec

from contextcraft.constants import MAX_FILE_READ_BYTES

# Default patterns to skip (in addition to .gitignore)
DEFAULT_SKIP_PATTERNS = """
.git/
.gitignore
node_modules/
__pycache__/
*.py[cod]
*$py.class
.Python
build/
dist/
*.egg-info/
*.egg
*.min.js
*.min.css
package-lock.json
yarn.lock
pnpm-lock.yaml
poetry.lock
Pipfile.lock
*.so
*.dll
*.dylib
.env
.venv/
venv/
*.log
.DS_Store
Thumbs.db
""".strip().splitlines()

# Extensions we consider "binary" or unparseable
BINARY_OR_SKIP_EXTENSIONS = {
    ".pyc", ".pyo", ".pyd", ".so", ".dll", ".dylib",
    ".exe", ".bin", ".zip", ".tar", ".gz", ".pdf",
    ".png", ".jpg", ".jpeg", ".gif", ".ico", ".webp",
    ".woff", ".woff2", ".ttf", ".eot", ".otf",
    ".mp3", ".mp4", ".webm", ".mov", ".avi",
}


@dataclass
class FileInfo:
    """Metadata for a single file in the tree."""

    path: Path
    relative_path: str
    extension: str
    size_bytes: int
    last_modified: float

    @property
    def language(self) -> str | None:
        """Infer language from extension for analysis."""
        ext_map = {
            ".py": "python",
            ".js": "javascript",
            ".jsx": "javascript",
            ".ts": "typescript",
            ".tsx": "typescript",
            ".java": "java",
            ".go": "go",
            ".rs": "rust",
        }
        return ext_map.get(self.extension.lower())


@dataclass
class FileTree:
    """Result of scanning a repository: files and language stats."""

    root: Path
    files: list[FileInfo] = field(default_factory=list)
    primary_languages: list[tuple[str, int]] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def files_by_language(self, lang: str) -> list[FileInfo]:
        """Return files that match the given language."""
        return [f for f in self.files if f.language == lang]

    def get_extension_counts(self) -> dict[str, int]:
        """Count files per extension."""
        counts: dict[str, int] = {}
        for f in self.files:
            ext = f.extension.lower() or "(no ext)"
            counts[ext] = counts.get(ext, 0) + 1
        return counts


def _load_gitignore_spec(root: Path, extra_skip_patterns: list[str] | None = None) -> pathspec.PathSpec:
    """Load .gitignore rules from repo root into a PathSpec; merge with default and extra patterns."""
    gitignore_path = root / ".gitignore"
    patterns: list[str] = []
    if gitignore_path.is_file():
        try:
            text = gitignore_path.read_text(encoding="utf-8", errors="replace")
            patterns.extend(line.strip() for line in text.splitlines() if line.strip() and not line.startswith("#"))
        except OSError:
            pass
    patterns.extend(DEFAULT_SKIP_PATTERNS)
    if extra_skip_patterns:
        patterns.extend(extra_skip_patterns)
    try:
        return pathspec.PathSpec.from_lines("gitignore", patterns)
    except (ValueError, TypeError):
        return pathspec.PathSpec.from_lines("gitwildmatch", patterns)


def _should_skip(
    path: Path,
    relative: str,
    spec: pathspec.PathSpec,
    extra_skip_extensions: set[str] | None = None,
) -> bool:
    """Return True if path should be skipped (gitignore, binary/skip rules, or extra extensions)."""
    norm = relative.replace("\\", "/")
    if spec.match_file(norm):
        return True
    ext = path.suffix.lower()
    if ext in BINARY_OR_SKIP_EXTENSIONS:
        return True
    if extra_skip_extensions and ext in extra_skip_extensions:
        return True
    return False


def _is_likely_binary(path: Path) -> bool:
    """Heuristic: read first 8k and check for null bytes."""
    try:
        with open(path, "rb") as f:
            chunk = f.read(8192)
        return b"\x00" in chunk
    except OSError:
        return True


def scan_repo(
    repo_path: Path,
    extra_skip_patterns: list[str] | None = None,
    extra_skip_extensions: list[str] | None = None,
    include_languages: list[str] | None = None,
) -> FileTree:
    """
    Walk the repository recursively, respecting .gitignore and skip rules.
    extra_skip_patterns: merged with default skip patterns.
    extra_skip_extensions: e.g. [".xyz"] to skip by extension.
    include_languages: if non-empty, only include files with language in this list.
    """
    root = Path(repo_path).resolve()
    if not root.is_dir():
        raise NotADirectoryError(f"Repo path is not a directory: {root}")

    spec = _load_gitignore_spec(root, extra_skip_patterns or [])
    ext_skip_set: set[str] = set()
    if extra_skip_extensions:
        for e in extra_skip_extensions:
            ext_skip_set.add(e.lower() if e.startswith(".") else f".{e.lower()}")
    files: list[FileInfo] = []
    warnings: list[str] = []

    for path in root.rglob("*"):
        if not path.is_file():
            continue
        try:
            relative = path.relative_to(root).as_posix()
        except ValueError:
            continue
        if _should_skip(path, relative, spec, ext_skip_set if ext_skip_set else None):
            continue
        if _is_likely_binary(path):
            continue
        try:
            stat = path.stat()
            ext = path.suffix
            files.append(
                FileInfo(
                    path=path,
                    relative_path=relative,
                    extension=ext,
                    size_bytes=stat.st_size,
                    last_modified=stat.st_mtime,
                )
            )
        except OSError as e:
            warnings.append(f"Skipped {relative}: {e}")

    if include_languages:
        lang_set = {x.lower() for x in include_languages}
        files = [f for f in files if f.language and f.language.lower() in lang_set]

    ext_to_lang: dict[str, str] = {
        ".py": "python", ".js": "javascript", ".jsx": "javascript",
        ".ts": "typescript", ".tsx": "typescript", ".java": "java",
        ".go": "go", ".rs": "rust",
    }
    lang_counts: dict[str, int] = {}
    for f in files:
        lang = ext_to_lang.get(f.extension.lower())
        if lang:
            lang_counts[lang] = lang_counts.get(lang, 0) + 1
    primary_languages = sorted(lang_counts.items(), key=lambda x: -x[1])

    return FileTree(root=root, files=files, primary_languages=primary_languages, warnings=warnings)


def read_file_safe(path: Path, encoding: str = "utf-8", max_size: int = MAX_FILE_READ_BYTES) -> str | None:
    """
    Read file contents safely. Returns None on encoding error or if binary/large.
    """
    try:
        if path.stat().st_size > max_size:
            return None
        return path.read_text(encoding=encoding, errors="strict")
    except (OSError, UnicodeDecodeError):
        return None
