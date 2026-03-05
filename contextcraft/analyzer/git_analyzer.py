"""Git history analysis: recent commits, hotspot files, main branch."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from contextcraft.scanner import FileTree


@dataclass
class GitContext:
    """Git-derived context: recent commits, hotspot files, main branch, contributors, commit frequency."""

    main_branch: str = "main"
    recent_commits: list[tuple[str, str]] = field(default_factory=list)  # (sha_short, message)
    hotspot_files: list[tuple[str, int]] = field(default_factory=list)  # (path, change_count)
    is_repo: bool = True
    contributors: list[dict[str, Any]] = field(default_factory=list)  # [{"author": str, "commits": int}]
    commit_frequency: list[int] = field(default_factory=list)  # 8 weeks, index 0 = oldest


def analyze_git(
    repo_path: Path,
    file_tree: FileTree | None = None,
    max_commits: int = 50,
) -> GitContext | None:
    """
    Use gitpython to get last max_commits commits, hotspot files, contributors, commit frequency.
    Returns None if not a git repo.
    """
    try:
        import git
        from datetime import datetime, timezone, timedelta
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

    # Recent commits (default 50)
    try:
        commits = list(repo.iter_commits(max_count=max_commits))
        ctx.recent_commits = [(c.hexsha[:7], c.message.strip().split("\n")[0]) for c in commits]
    except Exception:
        ctx.recent_commits = []

    # Contributors: count commits per author (name + email), top 5
    try:
        author_counts: dict[str, int] = {}
        for c in repo.iter_commits(max_count=max_commits):
            key = f"{c.author.name} <{c.author.email}>"
            author_counts[key] = author_counts.get(key, 0) + 1
        ctx.contributors = [
            {"author": author, "commits": count}
            for author, count in sorted(author_counts.items(), key=lambda x: -x[1])[:5]
        ]
    except Exception:
        ctx.contributors = []

    # Commit frequency: commits per week for last 8 weeks (index 0 = oldest, 7 = most recent)
    try:
        now = datetime.now(timezone.utc)
        week_buckets = [0] * 8
        for c in repo.iter_commits(max_count=500):
            try:
                ts = c.committed_datetime
                if ts.tzinfo is None:
                    ts = ts.replace(tzinfo=timezone.utc)
                age_days = (now - ts).days
                if age_days < 0:
                    continue
                weeks_ago = age_days // 7
                if weeks_ago >= 8:
                    continue
                week_buckets[7 - weeks_ago] += 1
            except Exception:
                continue
        ctx.commit_frequency = week_buckets
    except Exception:
        ctx.commit_frequency = [0] * 8

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
        "contributors": ctx.contributors,
        "commit_frequency": ctx.commit_frequency,
    }
