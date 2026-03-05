"""Typer CLI entrypoint for contextcraft."""

from __future__ import annotations

import json
import sys
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
from contextcraft.formatter import format_context_pack
from contextcraft.scanner import FileTree, scan_repo
from contextcraft.synthesizer import build_analysis_payload, synthesize

app = typer.Typer(
    name="contextcraft",
    help="Generate a structured Context Pack for AI coding assistants from a code repository.",
    no_args_is_help=True,
)
console = Console()


@app.callback()
def _main() -> None:
    """ContextCraft CLI."""
    pass


def _get_api_key() -> str | None:
    """Load ANTHROPIC_API_KEY from .env (repo and cwd) and environment."""
    load_dotenv()
    import os
    return os.environ.get("ANTHROPIC_API_KEY")


def _run_analysis(file_tree: FileTree) -> tuple[list[dict], list[str]]:
    """Run AST parsing on all language files; return (file_analyses, warnings)."""
    warnings: list[str] = []
    file_analyses: list[dict] = []
    for f in file_tree.files:
        if f.language:
            analysis = parse_file(f)
            if analysis:
                file_analyses.append(analysis_to_dict(analysis))
                warnings.extend(analysis.warnings)
            else:
                warnings.append(f"Could not parse: {f.relative_path}")
    return (file_analyses, warnings)


def _run_git_and_patterns(file_tree: FileTree, repo_path: Path) -> tuple:
    """Run pattern detection, dependency graph, and git analysis; return (patterns, dependency_graph, git_context)."""
    patterns = detect_patterns(file_tree)
    dependency_graph = build_dependency_graph(file_tree)
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
        help="Output format: markdown or json.",
    ),
) -> None:
    """
    Analyze the repository and generate context.pack.md (or JSON).
    Requires ANTHROPIC_API_KEY for AI synthesis unless --no-ai is used.
    """
    if not repo_path.is_dir():
        console.print("[red]Error:[/] Path is not a directory.")
        raise typer.Exit(1)

    warnings: list[str] = []

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
    ) as progress:
        task_scan = progress.add_task("Scanning...", total=None)
        try:
            file_tree = scan_repo(repo_path)
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
            out_path = repo_path / "context.pack.json"
            out_path.write_text(json.dumps(out, indent=2), encoding="utf-8")
            console.print(f"[green]Wrote[/] {out_path}" + (" (raw analysis; use without --no-ai for markdown)." if format != "json" else ""))
            if warnings:
                console.print("[yellow]Warnings:[/]", *warnings[:10], sep="\n  ")
            return

        api_key = _get_api_key()
        if not api_key:
            console.print("[red]Error:[/] ANTHROPIC_API_KEY is not set.")
            console.print("Set it in .env or environment, or run with [bold]--no-ai[/] for offline extraction.")
            # Save raw analysis so user can retry synthesis later
            out_path = repo_path / "context.pack.json"
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
            payload = build_analysis_payload(
                file_tree_dict, file_analyses, patterns_dict, dep_dict, git_dict
            )
            claude_output = synthesize(payload, api_key)
        except Exception as e:
            progress.update(task_synth, completed=True)
            console.print(f"[red]Claude API failed:[/] {e}")
            out_path = repo_path / "context.pack.json"
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
        out_md = repo_path / "context.pack.md"
        format_context_pack(claude_output, repo_name, out_md)
        progress.update(task_write, completed=True)

    if format == "json":
        out_json = repo_path / "context.pack.json"
        json_out = {"synthesis": claude_output, "file_tree": file_tree_dict, "patterns": patterns_dict}
        out_json.write_text(json.dumps(json_out, indent=2), encoding="utf-8")
        console.print(f"[green]Wrote[/] {out_json}")
    console.print(f"[green]Wrote[/] {out_md}")
    if warnings:
        console.print("[yellow]Warnings:[/]", *warnings[:10], sep="\n  ")


def main() -> None:
    """Entry point for the CLI."""
    app()


if __name__ == "__main__":
    main()
