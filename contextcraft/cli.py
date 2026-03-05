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
from contextcraft.constants import DEFAULT_MAX_OUTPUT_TOKENS, DEFAULT_MODEL
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


def _resolve_output_dir(repo_path: Path, output_dir: Path | None) -> Path:
    """Output directory for pack files; create if needed."""
    out = (output_dir or repo_path).resolve()
    out.mkdir(parents=True, exist_ok=True)
    return out


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
    max_tokens: int = typer.Option(
        DEFAULT_MAX_OUTPUT_TOKENS,
        "--max-tokens",
        help="Max tokens for Claude output (default 2000, max 8192).",
        min=1,
        max=8192,
    ),
    model: str = typer.Option(
        DEFAULT_MODEL,
        "--model",
        help="Claude model ID.",
    ),
    output_dir: Path | None = typer.Option(
        None,
        "--output-dir",
        "-o",
        path_type=Path,
        help="Directory for output files (default: repo path).",
        exists=False,
    ),
) -> None:
    """
    Analyze the repository and generate context.pack.md (or JSON).
    Requires ANTHROPIC_API_KEY for AI synthesis unless --no-ai is used.
    """
    if not repo_path.is_dir():
        console.print("[red]Error:[/] Path is not a directory.")
        raise typer.Exit(1)

    out_dir = _resolve_output_dir(repo_path, output_dir)
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
            claude_output = synthesize(
                payload_json, api_key,
                model=model, max_tokens=max_tokens, metrics_summary=metrics_summary,
            )
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
        format_context_pack(claude_output, repo_name, out_md)
        progress.update(task_write, completed=True)

    if format == "json":
        out_json = out_dir / "context.pack.json"
        json_out = {"synthesis": claude_output, "file_tree": file_tree_dict, "patterns": patterns_dict}
        out_json.write_text(json.dumps(json_out, indent=2), encoding="utf-8")
        console.print(f"[green]Wrote[/] {out_json}")
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
        help="Output format: also write synthesis as json.",
    ),
    max_tokens: int = typer.Option(
        DEFAULT_MAX_OUTPUT_TOKENS,
        "--max-tokens",
        help="Max tokens for Claude output.",
        min=1,
        max=8192,
    ),
    model: str = typer.Option(
        DEFAULT_MODEL,
        "--model",
        help="Claude model ID.",
    ),
    output_dir: Path | None = typer.Option(
        None,
        "--output-dir",
        "-o",
        path_type=Path,
        help="Directory for output files (default: repo path).",
        exists=False,
    ),
) -> None:
    """
    Re-run synthesis from cached context.pack.json (no rescan).
    Writes fresh context.pack.md. Fails if context.pack.json is missing or invalid.
    """
    out_dir = _resolve_output_dir(repo_path, output_dir)
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
    try:
        claude_output = synthesize(
            payload_json, api_key,
            model=model, max_tokens=max_tokens, metrics_summary=metrics_summary,
        )
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

    format_context_pack(claude_output, repo_name, out_md)
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


def main() -> None:
    """Entry point for the CLI."""
    app()


if __name__ == "__main__":
    main()
