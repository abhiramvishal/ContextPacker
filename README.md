# ContextCraft

[![PyPI version](https://badge.fury.io/py/contextcraft.svg)](https://pypi.org/project/contextcraft/)

A Python CLI tool that analyzes a code repository and generates a structured **Context Pack** document optimized for injecting into AI coding tools (Claude, GPT, Cursor, Copilot) so they understand the codebase before writing code.

## Installation

### CLI

```bash
pip install contextcraft
```

### VS Code Extension

Coming soon on the VS Code Marketplace.

## Usage

```bash
export ANTHROPIC_API_KEY=your_key_here
contextcraft init /path/to/your/repo
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
