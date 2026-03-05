"""Call Claude API to generate the final Context Pack from structured analysis."""

from __future__ import annotations

import json
from typing import Any

ANTHROPIC_MODEL = "claude-sonnet-4-20250514"
MAX_OUTPUT_TOKENS = 2000

SYSTEM_PROMPT = """You are a senior software architect. Your job is to write a concise, structured Context Pack for an AI coding assistant. The pack should tell the AI everything it needs to know to write idiomatic code for this codebase. Be precise and dense — every word should add information."""

USER_PROMPT_TEMPLATE = """Based on the following structured analysis of a codebase, produce a Context Pack in this exact structure. Use markdown. Max output ~2000 tokens. Dense, not verbose.

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
# Trailing newline and placeholder for payload
USER_PROMPT_END = "\n"


def build_analysis_payload(
    file_tree: dict[str, Any],
    file_analyses: list[dict[str, Any]],
    patterns: dict[str, Any],
    dependency_graph: dict[str, Any],
    git_context: dict[str, Any] | None,
) -> str:
    """Build a single JSON payload for the user prompt."""
    payload = {
        "file_tree": {
            "root": str(file_tree.get("root", "")),
            "primary_languages": file_tree.get("primary_languages", []),
            "file_count": file_tree.get("file_count", 0),
        },
        "file_analyses": file_analyses[:150],
        "patterns": patterns,
        "dependency_graph": dependency_graph,
        "git_context": git_context,
    }
    return json.dumps(payload, indent=0)


def synthesize(
    analysis_payload: str,
    api_key: str,
    model: str = ANTHROPIC_MODEL,
    max_tokens: int = MAX_OUTPUT_TOKENS,
) -> str:
    """
    Call Claude API to generate the Context Pack text.
    Raises on API or key errors; caller should handle and e.g. save raw JSON.
    """
    from anthropic import Anthropic

    client = Anthropic(api_key=api_key)
    user_content = USER_PROMPT_TEMPLATE + analysis_payload + USER_PROMPT_END

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
