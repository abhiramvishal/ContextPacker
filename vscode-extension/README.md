# ContextCraft (VS Code Extension)

Generate structured **Context Packs** for AI coding tools (Claude, Cursor, Copilot) from your codebase, directly inside VS Code.

This extension runs the [ContextCraft](https://pypi.org/project/llm-codepac/) Python CLI as a subprocess. You must install the CLI first:

```bash
pip install llm-codepac
```

## Commands

- **ContextCraft: Generate Context Pack** — Run `contextcraft init` on the workspace folder. Writes `context.pack.md` to the workspace root.
- **ContextCraft: Update Context Pack** — Run `contextcraft update` to refresh the pack from an existing `context.pack.json`.
- **ContextCraft: Diff Context Pack** — Run `contextcraft diff` to compare the current repo state to the last generated pack.

## Settings

| Setting | Description |
|--------|--------------|
| `contextcraft.apiKey` | Anthropic API key. Leave empty to use the `ANTHROPIC_API_KEY` environment variable. |
| `contextcraft.model` | Claude model ID (default: `claude-sonnet-4-5`). |
| `contextcraft.maxTokens` | Max tokens for Claude output (100–8192, default: 2000). |
| `contextcraft.pythonPath` | Path to the Python executable. Leave empty to use `python3` or `python` from PATH. |

## Requirements

- Python 3.11+ with `contextcraft` installed (`pip install llm-codepac`)
- For AI synthesis: [Anthropic API key](https://console.anthropic.com/)

## License

MIT
