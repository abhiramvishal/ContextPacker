"""Call Claude API to generate the final Context Pack from structured analysis."""

from __future__ import annotations

import json
import time
from typing import Any

from contextcraft.constants import DEFAULT_MAX_OUTPUT_TOKENS, DEFAULT_MODEL, MAX_FILES_FOR_SYNTHESIS

SYSTEM_PROMPT = """You are a senior software architect. Your job is to write a concise, structured Context Pack for an AI coding assistant. The pack should tell the AI everything it needs to know to write idiomatic code for this codebase. Be precise and dense — every word should add information."""

USER_PROMPT_TEMPLATE = """Based on the following structured analysis of a codebase, produce a Context Pack in this exact structure. Use markdown. Dense, not verbose.

1. ## Project Overview (2-3 sentences: what it does, stack, scale)
2. ## Architecture (how the codebase is organized, key modules and their roles)
3. ## Conventions (naming, error handling, testing, config patterns)
4. ## Key APIs & Interfaces (the most important classes/functions an AI needs to know)
5. ## Dependency Map (which modules are central, what imports what)
6. ## Recent Activity (what's been worked on lately, from git)
7. ## Anti-Patterns to Avoid (things that look wrong in this codebase)
8. ## AI Briefing Footer (a short paragraph the developer can paste at the top of any AI chat: "This codebase is a [X] built with [Y]. Key conventions: [Z]. When writing code for this repo, always...")

Structured analysis (JSON):
"""
USER_PROMPT_END = "\n"


def _build_metrics_summary(file_analyses: list[dict[str, Any]]) -> str:
    """Build Metrics Summary section for the user prompt if file_analyses have metrics."""
    if not file_analyses:
        return ""
    with_metrics = [a for a in file_analyses if a.get("metrics")]
    if not with_metrics:
        return ""
    total_lines = sum(a["metrics"].get("lines", 0) for a in with_metrics)
    by_lines = sorted(with_metrics, key=lambda a: a["metrics"].get("lines", 0), reverse=True)[:5]
    by_functions = sorted(with_metrics, key=lambda a: a["metrics"].get("function_count", 0), reverse=True)[:5]
    lines = [
        "Metrics Summary",
        f"- Total files analyzed: {len(file_analyses)}",
        f"- Total lines of code: {total_lines}",
        "- Top 5 largest files by line count:",
    ]
    for a in by_lines:
        path = a.get("path", "?")
        lines.append(f"  - {path} ({a['metrics'].get('lines', 0)} lines)")
    lines.append("- Top 5 files by function count:")
    for a in by_functions:
        path = a.get("path", "?")
        lines.append(f"  - {path} ({a['metrics'].get('function_count', 0)} functions)")
    return "\n".join(lines) + "\n\n"


def build_analysis_payload(
    file_tree: dict[str, Any],
    file_analyses: list[dict[str, Any]],
    patterns: dict[str, Any],
    dependency_graph: dict[str, Any],
    git_context: dict[str, Any] | None,
) -> tuple[str, str]:
    """Build JSON payload string and optional metrics summary. Returns (payload_json, metrics_summary)."""
    payload = {
        "file_tree": {
            "root": str(file_tree.get("root", "")),
            "primary_languages": file_tree.get("primary_languages", []),
            "file_count": file_tree.get("file_count", 0),
        },
        "file_analyses": file_analyses[:MAX_FILES_FOR_SYNTHESIS],
        "patterns": patterns,
        "dependency_graph": dependency_graph,
        "git_context": git_context,
    }
    payload_json = json.dumps(payload, indent=0)
    metrics_summary = _build_metrics_summary(file_analyses)
    return (payload_json, metrics_summary)


def synthesize(
    analysis_payload: str,
    api_key: str,
    model: str = DEFAULT_MODEL,
    max_tokens: int = DEFAULT_MAX_OUTPUT_TOKENS,
    metrics_summary: str = "",
) -> str:
    """
    Call Claude API to generate the Context Pack text.
    Retries up to 3 times on 429 or 529 with exponential backoff (2s, 4s, 8s).
    Raises on other API or key errors; caller should handle and e.g. save raw JSON.
    """
    from anthropic import Anthropic
    from anthropic import APIStatusError

    client = Anthropic(api_key=api_key)
    user_content = (
        USER_PROMPT_TEMPLATE
        + (metrics_summary if metrics_summary else "")
        + analysis_payload
        + USER_PROMPT_END
    )
    delays = [2, 4, 8]
    last_error: Exception | None = None

    for attempt in range(1 + len(delays)):
        try:
            response = client.messages.create(
                model=model,
                max_tokens=max_tokens,
                system=SYSTEM_PROMPT,
                messages=[{"role": "user", "content": user_content}],
            )
            text = ""
            for block in response.content:
                if hasattr(block, "text"):
                    text += block.text
            return text.strip()
        except APIStatusError as e:
            last_error = e
            if e.status_code in (429, 529) and attempt < len(delays):
                time.sleep(delays[attempt])
                continue
            raise
        except Exception:
            raise

    if last_error is not None:
        raise last_error
    raise RuntimeError("synthesize failed after retries")
