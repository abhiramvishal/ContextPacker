# ContextCraft

A Python CLI tool that analyzes a code repository and generates a structured **Context Pack** document optimized for injecting into AI coding tools (Claude, GPT, Cursor, Copilot) so they understand the codebase before writing code.

## Installation

```bash
pip install -e .
```

This registers the `contextcraft` command.

## Usage

```bash
# Generate context.pack.md (requires ANTHROPIC_API_KEY for AI synthesis)
contextcraft init <path_to_repo>

# Offline mode: extraction only, no Claude API call
contextcraft init <path_to_repo> --no-ai

# Output as JSON instead of markdown
contextcraft init <path_to_repo> --format json
```

## Environment

Create a `.env` file (see `.env.example`) or set:

- `ANTHROPIC_API_KEY` — required for AI synthesis (omit or use `--no-ai` for offline)

## Output

- **Default:** `context.pack.md` in the repo root with a Quick Copy section and full Context Pack.
- **JSON:** Raw analysis or pack as JSON when `--format json` is used.

## Requirements

- Python 3.11+
- Git (optional; used for recent commits and hotspot analysis)
