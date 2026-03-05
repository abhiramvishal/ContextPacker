"""Tests for formatter module."""

from pathlib import Path

import pytest

from contextcraft.formatter import (
    format_context_pack,
    extract_ai_briefing_footer,
)


def test_format_context_pack_produces_yaml_header(tmp_path: Path) -> None:
    """format_context_pack() produces output with the YAML header."""
    out_path = tmp_path / "context.pack.md"
    result = format_context_pack(
        claude_output="## Project Overview\n\nNothing.\n\n## AI Briefing Footer\n\nUse this repo.",
        repo_name="my-project",
        output_path=out_path,
    )
    assert "---" in result
    assert "generated:" in result
    assert "repo: my-project" in result
    assert "tool: ContextCraft" in result
    assert out_path.read_text(encoding="utf-8") == result


def test_extract_ai_briefing_footer_when_present() -> None:
    """extract_ai_briefing_footer() correctly extracts the footer section when present."""
    markdown = """
## Other Section
Content here.

## AI Briefing Footer

This codebase is a FastAPI app. Key conventions: snake_case. When writing code, always test.

## Next Section
More content.
"""
    result = extract_ai_briefing_footer(markdown)
    assert result is not None
    assert "This codebase is a FastAPI app" in result
    assert "> " in result


def test_extract_ai_briefing_footer_when_absent() -> None:
    """extract_ai_briefing_footer() returns None (falsy) when section absent."""
    markdown = "## Project Overview\n\nNo footer here."
    result = extract_ai_briefing_footer(markdown)
    assert result is None


def test_format_as_html_contains_structure() -> None:
    """format_as_html produces a string containing <html>, <h2>, <pre>."""
    from contextcraft.formatter import format_as_html
    md = "## Overview\n\nText.\n\n```py\nx = 1\n```"
    html = format_as_html(md, "my-repo")
    assert "<html" in html
    assert "<h2>" in html
    assert "<pre>" in html
    assert "my-repo" in html


def test_format_as_html_yaml_meta_div() -> None:
    """YAML front matter is wrapped in <div class=\"meta\">."""
    from contextcraft.formatter import format_as_html
    md = "---\ngenerated: 2025-01-01\nrepo: r\n---\n\n## Section"
    html = format_as_html(md, "r")
    assert 'class="meta"' in html
    assert "generated" in html


def test_format_as_html_bold_and_inline_code() -> None:
    """Bold and inline code are converted correctly."""
    from contextcraft.formatter import format_as_html
    md = "**bold** and `code`"
    html = format_as_html(md, "r")
    assert "<strong>" in html
    assert "<code>" in html
