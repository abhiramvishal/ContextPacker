"""Git history analysis: recent commits, hotspot files, main branch."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from contextcraft.scanner import FileTree


@dataclass
class GitContext:
    """Git-derived context: recent commits, hotspot files, main branch."""

    main_branch: str = "main"
    recent_commits: list[tuple[str, str]] = field(default_factory=list)  # (sha_short, message)
    hotspot_files: list[tuple[str, int]] = field(default_factory=list)  # (path, change_count)
    is_repo: bool = True


def analyze_git(repo_path: Path, file_tree: FileTree | None = None) -> GitContext | None:
    """
    Use gitpython to get last 30 commits, hotspot files, last 5 messages, main branch.
    Returns None if not a git repo; returns GitContext with is_repo=False on error.
    """
    try:
        import git
    except ImportError:
        return None

    repo_path = Path(repo_path).resolve()
    if not repo_path.is_dir():
        return None

    try:
        repo = git.Repo(repo_path)
    except Exception:
        return None

    ctx = GitContext()

    # Main branch
    try:
        if repo.head.is_valid():
            ctx.main_branch = repo.active_branch.name
        else:
            ctx.main_branch = "main"
    except Exception:
        ctx.main_branch = "main"

    # Last 30 commits, and last 5 messages for "recent work direction"
    try:
        commits = list(repo.iter_commits(max_count=30))
        ctx.recent_commits = [(c.hexsha[:7], c.message.strip().split("\n")[0]) for c in commits]
    except Exception:
        ctx.recent_commits = []

    # Hotspot files: most frequently changed in recent commits
    try:
        change_counts: dict[str, int] = {}
        for c in repo.iter_commits(max_count=100):
            for path in c.stats.files:
                change_counts[path] = change_counts.get(path, 0) + 1
        ctx.hotspot_files = sorted(change_counts.items(), key=lambda x: -x[1])[:20]
    except Exception:
        ctx.hotspot_files = []

    return ctx


def git_context_to_dict(ctx: GitContext | None) -> dict[str, Any] | None:
    """Convert GitContext to JSON-serializable dict; return None if ctx is None."""
    if ctx is None:
        return None
    return {
        "main_branch": ctx.main_branch,
        "recent_commits": ctx.recent_commits[:5],
        "hotspot_files": ctx.hotspot_files[:15],
        "is_repo": ctx.is_repo,
    }
