"""Format Claude output into final context.pack.md with header and Quick Copy."""

from __future__ import annotations

import re
from datetime import datetime, timezone
from pathlib import Path

from contextcraft import __version__


def extract_ai_briefing_footer(markdown: str) -> str | None:
    """Extract the AI Briefing Footer section from Claude's markdown for Quick Copy."""
    # Look for ## AI Briefing Footer and take the next paragraph(s) until next ## or end
    pattern = r"##\s*AI\s+Briefing\s+Footer\s*\n+(.*?)(?=\n##\s|\n\Z)"
    m = re.search(pattern, markdown, re.DOTALL | re.IGNORECASE)
    if not m:
        return None
    text = m.group(1).strip()
    # Convert to quote lines for Quick Copy
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    return "\n".join("> " + line for line in lines) if lines else None


def format_context_pack(
    claude_output: str,
    repo_name: str,
    output_path: Path,
) -> str:
    """
    Wrap Claude's output in context.pack.md with YAML header and Quick Copy section.
    Returns the full document string; also writes to output_path.
    """
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")
    header = f"""---
generated: {now}
repo: {repo_name}
tool: ContextCraft v{__version__}
---

"""
    quick = extract_ai_briefing_footer(claude_output)
    if quick:
        quick_section = "## Quick Copy (paste this into any AI chat to brief it)\n\n" + quick + "\n\n---\n\n"
    else:
        quick_section = "## Quick Copy (paste this into any AI chat to brief it)\n\n(No AI Briefing Footer found in synthesis output.)\n\n---\n\n"

    full_doc = header + quick_section + claude_output

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(full_doc, encoding="utf-8")

    return full_doc
