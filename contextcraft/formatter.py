"""Format Claude output into final context.pack.md with header and Quick Copy."""

from __future__ import annotations

import re
from datetime import datetime, timezone
from pathlib import Path
from html import escape

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


def format_as_html(markdown_content: str, repo_name: str) -> str:
    """
    Convert markdown to basic HTML (stdlib only). Wrap in full document with inline CSS.
    YAML front matter (---\\n...\\n---) becomes <div class="meta">. Handles malformed input.
    """
    content = markdown_content or ""
    # Extract YAML front matter if present
    meta_html = ""
    body = content
    if content.strip().startswith("---"):
        parts = content.split("---", 2)
        if len(parts) >= 2 and parts[0].strip() == "":
            meta_lines = parts[1].strip().splitlines()
            meta_html = "<div class=\"meta\"><pre>" + escape("\n".join(meta_lines)) + "</pre></div>"
            body = parts[2] if len(parts) > 2 else ""
        else:
            body = content

    lines = body.splitlines()
    out: list[str] = []
    i = 0
    in_code = False
    code_lang = ""
    code_buf: list[str] = []
    in_ul = False

    def flush_code() -> None:
        nonlocal code_buf, code_lang
        if code_buf:
            cls = f" language-{code_lang}" if code_lang else ""
            joined = "\n".join(code_buf)
            out.append(f'<pre><code class="{cls.strip()}">{escape(joined)}</code></pre>')
            code_buf = []
            code_lang = ""

    def flush_ul() -> None:
        nonlocal in_ul
        if in_ul:
            out.append("</ul>")
            in_ul = False

    while i < len(lines):
        line = lines[i]
        rest = line.strip()
        if rest.startswith("```"):
            flush_ul()
            if in_code:
                flush_code()
                in_code = False
            else:
                in_code = True
                code_lang = rest[3:].strip() or ""
            i += 1
            continue
        if in_code:
            code_buf.append(line)
            i += 1
            continue
        if rest.startswith("## "):
            flush_ul()
            out.append(f"<h2>{_inline_md(rest[3:].strip())}</h2>")
        elif rest.startswith("### "):
            flush_ul()
            out.append(f"<h3>{_inline_md(rest[4:].strip())}</h3>")
        elif rest.startswith("- ") or rest.startswith("* "):
            if not in_ul:
                out.append("<ul>")
                in_ul = True
            out.append(f"<li>{_inline_md(rest[2:].strip())}</li>")
        elif not rest:
            flush_ul()
            out.append("<p></p>")
        else:
            flush_ul()
            out.append(f"<p>{_inline_md(rest)}</p>")
        i += 1
    flush_code()
    flush_ul()

    body_html = "\n".join(out)
    title = escape(f"{repo_name} — ContextCraft")
    css = """
    * { box-sizing: border-box; }
    body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; max-width: 860px; margin: 0 auto; padding: 1rem 1.5rem; line-height: 1.5; color: #1a1a1a; }
    .header-bar { background: #f0f0f0; margin: -1rem -1.5rem 1.5rem; padding: 0.75rem 1.5rem; border-bottom: 1px solid #ddd; }
    .meta { background: #f8f8f8; padding: 0.75rem 1rem; border-radius: 4px; margin-bottom: 1rem; font-size: 0.9em; overflow-x: auto; }
    .meta pre { margin: 0; }
    h2 { font-size: 1.25rem; margin-top: 1.5rem; border-bottom: 1px solid #eee; padding-bottom: 0.25rem; }
    h3 { font-size: 1.1rem; margin-top: 1rem; }
    pre { background: #f5f5f5; padding: 1rem; border-radius: 4px; overflow-x: auto; }
    code { background: #f0f0f0; padding: 0.15em 0.4em; border-radius: 3px; font-size: 0.9em; }
    pre code { background: none; padding: 0; }
    ul { margin: 0.5rem 0; padding-left: 1.5rem; }
    """
    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>{title}</title>
<style>{css}</style>
</head>
<body>
<div class="header-bar"><strong>{title}</strong></div>
{meta_html}
{body_html}
</body>
</html>"""
    return html


def _inline_md(text: str) -> str:
    """Convert inline markdown: **bold**, `code`; escape HTML in plain parts."""
    if not text:
        return ""
    placeholders: list[str] = []
    def repl_bold(m: re.Match) -> str:
        placeholders.append("<strong>" + escape(m.group(1)) + "</strong>")
        return f"\x00P{len(placeholders) - 1}\x00"
    def repl_code(m: re.Match) -> str:
        placeholders.append("<code>" + escape(m.group(1)) + "</code>")
        return f"\x00P{len(placeholders) - 1}\x00"
    text = re.sub(r"\*\*(.+?)\*\*", repl_bold, text)
    text = re.sub(r"__(.+?)__", repl_bold, text)
    text = re.sub(r"`([^`]+)`", repl_code, text)
    text = escape(text)
    for i, p in enumerate(placeholders):
        text = text.replace(f"\x00P{i}\x00", p)
    return text
