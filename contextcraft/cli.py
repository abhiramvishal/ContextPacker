"""Typer CLI entrypoint for contextcraft."""

from __future__ import annotations

import json
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

# Prefer UTF-8 on Windows to avoid UnicodeEncodeError with Rich/console
if sys.platform == "win32" and hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

import typer
from dotenv import load_dotenv
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn

from contextcraft import __version__
from contextcraft.analyzer.ast_parser import analysis_to_dict, parse_file
from contextcraft.analyzer.dependency_graph import build_dependency_graph, dependency_graph_to_dict
from contextcraft.analyzer.git_analyzer import analyze_git, git_context_to_dict
from contextcraft.analyzer.pattern_detector import detect_patterns, patterns_to_dict
from contextcraft.config import load_config
from contextcraft.constants import DEFAULT_MAX_OUTPUT_TOKENS, DEFAULT_MODEL, PARSE_WORKERS
from contextcraft.formatter import format_as_html, format_context_pack
from contextcraft.scanner import FileInfo, FileTree, scan_repo
from contextcraft.synthesizer import build_analysis_payload, synthesize

app = typer.Typer(
    name="contextcraft",
    help="Generate a structured Context Pack for AI coding assistants from a code repository.",
    no_args_is_help=True,
)
console = Console()


_verbose = False


@app.callback()
def _main(
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Print detailed progress and token counts."),
) -> None:
    """ContextCraft CLI."""
    global _verbose
    _verbose = verbose


def _get_api_key() -> str | None:
    """Load ANTHROPIC_API_KEY from .env (repo and cwd) and environment."""
    load_dotenv()
    import os
    return os.environ.get("ANTHROPIC_API_KEY")


def _resolve_output_dir(repo_path: Path, output_dir: Path | None) -> Path:
    """Output directory for pack files; create if needed."""
    out = (output_dir or repo_path).resolve()
    out.mkdir(parents=True, exist_ok=True)
    return out


def _run_analysis(file_tree: FileTree) -> tuple[list[dict], list[str]]:
    """Run AST parsing in parallel (PARSE_WORKERS); preserve file order; collect warnings."""
    warnings: list[str] = []
    files_to_parse = [f for f in file_tree.files if f.language]
    if not files_to_parse:
        return ([], [])

    results: list[tuple[int, dict | None, list[str]]] = []  # (index, analysis_dict or None, file_warnings)
    with ThreadPoolExecutor(max_workers=PARSE_WORKERS) as executor:
        future_to_idx = {executor.submit(_parse_one, f): (i, f) for i, f in enumerate(files_to_parse)}
        for future in as_completed(future_to_idx):
            idx, f = future_to_idx[future]
            try:
                result = future.result()
                results.append((idx, result[0], result[1]))
                if _verbose and result[1]:
                    for w in result[1]:
                        console.print(f"[dim]  {f.relative_path}: {w}[/]")
            except Exception as e:
                results.append((idx, None, [f"Could not parse: {f.relative_path} ({e})"]))
                if _verbose:
                    console.print(f"[dim]Parsing {f.relative_path}... failed[/]")
            else:
                if _verbose:
                    console.print(f"[dim]Parsing {f.relative_path}...[/]")

    results.sort(key=lambda x: x[0])
    file_analyses = [r[1] for r in results if r[1] is not None]
    for r in results:
        if r[1] is None:
            warnings.extend(r[2])
        else:
            warnings.extend(r[2])
    return (file_analyses, warnings)


def _parse_one(f: FileInfo) -> tuple[dict | None, list[str]]:
    """Parse a single file; return (analysis_dict or None, list of warning strings)."""
    analysis = parse_file(f)
    if analysis:
        return (analysis_to_dict(analysis), analysis.warnings)
    return (None, [f"Could not parse: {f.relative_path}"])


def _run_git_and_patterns(file_tree: FileTree, repo_path: Path) -> tuple:
    """Run pattern detection, dependency graph, and git analysis; return (patterns, dependency_graph, git_context)."""
    patterns = detect_patterns(file_tree)
    if _verbose:
        console.print("[dim]Building dependency graph...[/]")
    dependency_graph = build_dependency_graph(file_tree)
    if _verbose:
        console.print("[dim]Analyzing git history...[/]")
    git_context = analyze_git(repo_path, file_tree)
    return (patterns, dependency_graph, git_context)


@app.command()
def init(
    repo_path: Path = typer.Argument(
        ".",
        help="Path to the repository to analyze.",
        exists=True,
        file_okay=False,
        dir_okay=True,
        resolve_path=True,
    ),
    no_ai: bool = typer.Option(
        False,
        "--no-ai",
        help="Run extraction only; skip Claude synthesis (offline mode).",
    ),
    format: str = typer.Option(
        "markdown",
        "--format",
        "-f",
        help="Output format: markdown, json, or html.",
    ),
    max_tokens: int = typer.Option(
        None,
        "--max-tokens",
        help="Max tokens for Claude output (default from config or 2000, max 8192).",
        min=1,
        max=8192,
    ),
    model: str = typer.Option(
        None,
        "--model",
        help="Claude model ID (default from config or claude-sonnet-4-5).",
    ),
    output_dir: Path | None = typer.Option(
        None,
        "--output-dir",
        "-o",
        path_type=Path,
        help="Directory for output files (default from config or repo path).",
        exists=False,
    ),
) -> None:
    """
    Analyze the repository and generate context.pack.md (or JSON/HTML).
    Requires ANTHROPIC_API_KEY for AI synthesis unless --no-ai is used.
    """
    if not repo_path.is_dir():
        console.print("[red]Error:[/] Path is not a directory.")
        raise typer.Exit(1)

    cfg = load_config(repo_path)
    out_dir = _resolve_output_dir(
        repo_path,
        Path(cfg.output_dir) if cfg.output_dir else output_dir,
    )
    max_tokens_val = max_tokens if max_tokens is not None else cfg.max_tokens
    model_val = model if model is not None else cfg.model
    warnings: list[str] = []

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
    ) as progress:
        task_scan = progress.add_task("Scanning...", total=None)
        try:
            file_tree = scan_repo(
                repo_path,
                extra_skip_patterns=cfg.skip_paths or None,
                extra_skip_extensions=cfg.skip_extensions or None,
                include_languages=cfg.include_languages or None,
            )
        except NotADirectoryError as e:
            console.print(f"[red]Error:[/] {e}")
            raise typer.Exit(1)
        warnings.extend(file_tree.warnings)
        progress.update(task_scan, completed=True)

        task_analyze = progress.add_task("Analyzing...", total=None)
        file_analyses, analysis_warnings = _run_analysis(file_tree)
        warnings.extend(analysis_warnings)
        patterns, dependency_graph, git_context = _run_git_and_patterns(file_tree, repo_path)
        progress.update(task_analyze, completed=True)

        file_tree_dict = {
            "root": str(file_tree.root),
            "primary_languages": file_tree.primary_languages,
            "file_count": len(file_tree.files),
        }
        patterns_dict = patterns_to_dict(patterns)
        dep_dict = dependency_graph_to_dict(dependency_graph)
        git_dict = git_context_to_dict(git_context)

        if no_ai:
            progress.add_task("Skipping synthesis (--no-ai)...", completed=True)
            out = {
                "file_tree": file_tree_dict,
                "file_analyses": file_analyses,
                "patterns": patterns_dict,
                "dependency_graph": dep_dict,
                "git_context": git_dict,
                "warnings": warnings,
            }
            out_path = out_dir / "context.pack.json"
            out_path.write_text(json.dumps(out, indent=2), encoding="utf-8")
            console.print(f"[green]Wrote[/] {out_path}" + (" (raw analysis; use without --no-ai for markdown)." if format != "json" else ""))
            if warnings:
                console.print("[yellow]Warnings:[/]", *warnings[:10], sep="\n  ")
            return

        api_key = _get_api_key()
        if not api_key:
            console.print("[red]Error:[/] ANTHROPIC_API_KEY is not set.")
            console.print("Set it in .env or environment, or run with [bold]--no-ai[/] for offline extraction.")
            out_path = out_dir / "context.pack.json"
            out = {
                "file_tree": file_tree_dict,
                "file_analyses": file_analyses,
                "patterns": patterns_dict,
                "dependency_graph": dep_dict,
                "git_context": git_dict,
                "warnings": warnings,
            }
            out_path.write_text(json.dumps(out, indent=2), encoding="utf-8")
            console.print(f"[dim]Saved raw analysis to {out_path}; run again with API key to synthesize.[/]")
            raise typer.Exit(1)

        task_synth = progress.add_task("Synthesizing...", total=None)
        try:
            payload_json, metrics_summary = build_analysis_payload(
                file_tree_dict, file_analyses, patterns_dict, dep_dict, git_dict
            )
            usage: dict = {}
            claude_output = synthesize(
                payload_json, api_key,
                model=model_val, max_tokens=max_tokens_val, metrics_summary=metrics_summary,
                usage_out=usage if _verbose else None,
            )
            if _verbose and usage:
                console.print(f"[dim]Synthesis: {usage.get('input_tokens', 0)} in / {usage.get('output_tokens', 0)} out[/]")
        except Exception as e:
            progress.update(task_synth, completed=True)
            console.print(f"[red]Claude API failed:[/] {e}")
            out_path = out_dir / "context.pack.json"
            out = {
                "file_tree": file_tree_dict,
                "file_analyses": file_analyses,
                "patterns": patterns_dict,
                "dependency_graph": dep_dict,
                "git_context": git_dict,
                "warnings": warnings,
            }
            out_path.write_text(json.dumps(out, indent=2), encoding="utf-8")
            console.print(f"[yellow]Saved raw analysis to {out_path}. Fix API/key and re-run to retry synthesis.[/]")
            raise typer.Exit(1)
        progress.update(task_synth, completed=True)

        task_write = progress.add_task("Writing...", total=None)
        repo_name = repo_path.name or "repo"
        out_md = out_dir / "context.pack.md"
        full_doc = format_context_pack(claude_output, repo_name, out_md)
        progress.update(task_write, completed=True)

    if format == "json":
        out_json = out_dir / "context.pack.json"
        json_out = {"synthesis": claude_output, "file_tree": file_tree_dict, "patterns": patterns_dict}
        out_json.write_text(json.dumps(json_out, indent=2), encoding="utf-8")
        console.print(f"[green]Wrote[/] {out_json}")
    elif format == "html":
        out_html = out_dir / "context.pack.html"
        html_content = format_as_html(full_doc, repo_name)
        out_html.write_text(html_content, encoding="utf-8")
        console.print(f"[green]Wrote[/] {out_html}")
    console.print(f"[green]Wrote[/] {out_md}")
    if warnings:
        console.print("[yellow]Warnings:[/]", *warnings[:10], sep="\n  ")


@app.command()
def update(
    repo_path: Path = typer.Argument(
        ".",
        help="Path to the repository (must contain context.pack.json).",
        exists=True,
        file_okay=False,
        dir_okay=True,
        resolve_path=True,
    ),
    format: str = typer.Option(
        "markdown",
        "--format",
        "-f",
        help="Output format: markdown, json, or html.",
    ),
    max_tokens: int = typer.Option(
        None,
        "--max-tokens",
        help="Max tokens for Claude output.",
        min=1,
        max=8192,
    ),
    model: str = typer.Option(
        None,
        "--model",
        help="Claude model ID.",
    ),
    output_dir: Path | None = typer.Option(
        None,
        "--output-dir",
        "-o",
        path_type=Path,
        help="Directory for output files (default from config or repo path).",
        exists=False,
    ),
) -> None:
    """
    Re-run synthesis from cached context.pack.json (no rescan).
    Writes fresh context.pack.md. Fails if context.pack.json is missing or invalid.
    """
    cfg = load_config(repo_path)
    out_dir = _resolve_output_dir(
        repo_path,
        Path(cfg.output_dir) if cfg.output_dir else output_dir,
    )
    max_tokens_val = max_tokens if max_tokens is not None else cfg.max_tokens
    model_val = model if model is not None else cfg.model
    pack_json_path = repo_path / "context.pack.json"
    if not pack_json_path.is_file():
        console.print("[red]Error:[/] context.pack.json not found. Run [bold]contextcraft init[/] first.")
        raise typer.Exit(1)

    try:
        data = json.loads(pack_json_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as e:
        console.print(f"[red]Error:[/] Could not read context.pack.json: {e}")
        raise typer.Exit(1)

    required = ("file_tree", "file_analyses", "patterns", "dependency_graph", "git_context")
    if not all(k in data for k in required):
        console.print("[red]Error:[/] context.pack.json missing raw analysis keys. Run [bold]contextcraft init[/] to regenerate.")
        raise typer.Exit(1)

    file_tree_dict = data["file_tree"]
    file_analyses = data["file_analyses"]
    patterns_dict = data["patterns"]
    dep_dict = data["dependency_graph"]
    git_dict = data.get("git_context")

    api_key = _get_api_key()
    if not api_key:
        console.print("[red]Error:[/] ANTHROPIC_API_KEY is not set.")
        raise typer.Exit(1)

    payload_json, metrics_summary = build_analysis_payload(
        file_tree_dict, file_analyses, patterns_dict, dep_dict, git_dict
    )
    usage: dict = {}
    try:
        claude_output = synthesize(
            payload_json, api_key,
            model=model_val, max_tokens=max_tokens_val, metrics_summary=metrics_summary,
            usage_out=usage if _verbose else None,
        )
        if _verbose and usage:
            console.print(f"[dim]Synthesis: {usage.get('input_tokens', 0)} in / {usage.get('output_tokens', 0)} out[/]")
    except Exception as e:
        console.print(f"[red]Claude API failed:[/] {e}")
        raise typer.Exit(1)

    repo_name = repo_path.name or "repo"
    out_md = out_dir / "context.pack.md"
    old_generated: str | None = None
    if out_md.exists():
        try:
            head = out_md.read_text(encoding="utf-8").split("---")[1]
            for line in head.splitlines():
                if line.strip().startswith("generated:"):
                    old_generated = line.split(":", 1)[1].strip()
                    break
        except Exception:
            pass

    full_doc = format_context_pack(claude_output, repo_name, out_md)
    new_doc = out_md.read_text(encoding="utf-8")
    new_generated = ""
    for line in new_doc.split("---")[1].splitlines():
        if line.strip().startswith("generated:"):
            new_generated = line.split(":", 1)[1].strip()
            break

    if old_generated:
        console.print(f"[dim]Previous:[/] {old_generated} [dim]-> New:[/] {new_generated}")
    console.print(f"[green]Wrote[/] {out_md}")

    if format == "json":
        out_json = out_dir / "context.pack.json"
        existing = json.loads(pack_json_path.read_text(encoding="utf-8"))
        existing["synthesis"] = claude_output
        out_json.write_text(json.dumps(existing, indent=2), encoding="utf-8")
        console.print(f"[green]Wrote[/] {out_json}")
    elif format == "html":
        out_html = out_dir / "context.pack.html"
        html_content = format_as_html(full_doc, repo_name)
        out_html.write_text(html_content, encoding="utf-8")
        console.print(f"[green]Wrote[/] {out_html}")


@app.command()
def diff(
    repo_path: Path = typer.Argument(
        ".",
        help="Path to the repository.",
        exists=True,
        file_okay=False,
        dir_okay=True,
        resolve_path=True,
    ),
    output_dir: Path | None = typer.Option(
        None,
        "--output-dir",
        "-o",
        path_type=Path,
        help="Directory where context.pack.json is located (default: repo path).",
        exists=False,
    ),
) -> None:
    """
    Compare current repo state to last context.pack.json. Re-runs scan and analysis (no API).
    Prints new/removed files, changed function/class counts, new warnings, hotspot changes.
    """
    cfg = load_config(repo_path)
    out_dir = (Path(cfg.output_dir) if cfg.output_dir else output_dir or repo_path).resolve()
    pack_path = out_dir / "context.pack.json"
    if not pack_path.is_file():
        console.print("[red]Error:[/] context.pack.json not found. Run [bold]contextcraft init[/] first.")
        raise typer.Exit(1)

    try:
        data = json.loads(pack_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as e:
        console.print(f"[red]Error:[/] Could not read context.pack.json: {e}")
        raise typer.Exit(1)

    required = ("file_tree", "file_analyses")
    if not all(k in data for k in required):
        console.print("[red]Error:[/] context.pack.json missing file_tree or file_analyses.")
        raise typer.Exit(1)

    file_tree = scan_repo(
        repo_path,
        extra_skip_patterns=cfg.skip_paths or None,
        extra_skip_extensions=cfg.skip_extensions or None,
        include_languages=cfg.include_languages or None,
    )
    file_analyses_new, analysis_warnings = _run_analysis(file_tree)
    dep_graph = build_dependency_graph(file_tree)
    git_ctx = analyze_git(repo_path, file_tree)

    old_paths = {a["path"] for a in data["file_analyses"]}
    new_paths = {a["path"] for a in file_analyses_new}
    old_by_path = {a["path"]: a for a in data["file_analyses"]}
    new_by_path = {a["path"]: a for a in file_analyses_new}

    added = sorted(new_paths - old_paths)
    removed = sorted(old_paths - new_paths)
    changed: list[tuple[str, str]] = []
    for path in sorted(new_paths & old_paths):
        o, n = old_by_path[path], new_by_path[path]
        fc_old = (len(o.get("functions", [])), len(o.get("classes", [])))
        fc_new = (len(n.get("functions", [])), len(n.get("classes", [])))
        if fc_old != fc_new:
            changed.append((path, f"functions {fc_old[0]} -> {fc_new[0]}, classes {fc_old[1]} -> {fc_new[1]}"))

    old_warnings = set(data.get("warnings", []))
    new_warnings = set(analysis_warnings)
    new_warn_only = sorted(new_warnings - old_warnings)

    hotspot_changed = False
    if git_ctx and data.get("git_context") and "hotspot_files" in data["git_context"]:
        old_top = [p for p, _ in (data["git_context"].get("hotspot_files") or [])[:3]]
        new_top = [p for p, _ in (git_ctx.hotspot_files or [])[:3]]
        if old_top != new_top:
            hotspot_changed = True

    if added:
        console.print("[green]New files:[/]")
        for p in added:
            console.print(f"  + {p}")
    if removed:
        console.print("[red]Removed files:[/]")
        for p in removed:
            console.print(f"  - {p}")
    if changed:
        console.print("[yellow]Changed (function/class count):[/]")
        for path, msg in changed:
            console.print(f"  {path}: {msg}")
    if new_warn_only:
        console.print("[yellow]New warnings:[/]")
        for w in new_warn_only[:15]:
            console.print(f"  {w}")
    if hotspot_changed:
        console.print("[dim]Git hotspot files (top 3) changed.[/]")
    if not (added or removed or changed or new_warn_only or hotspot_changed):
        console.print("[dim]No changes from last run.[/]")


def main() -> None:
    """Entry point for the CLI."""
    app()


if __name__ == "__main__":
    main()
