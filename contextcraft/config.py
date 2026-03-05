"""Project-level config from .contextcraft.yml or .contextcraft.toml."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from contextcraft.constants import DEFAULT_MAX_OUTPUT_TOKENS, DEFAULT_MODEL


@dataclass
class ContextCraftConfig:
    """Project config: skip paths/extensions, defaults for model/tokens/output, language filter."""

    skip_paths: list[str] = field(default_factory=list)
    skip_extensions: list[str] = field(default_factory=list)
    max_tokens: int = DEFAULT_MAX_OUTPUT_TOKENS
    model: str = DEFAULT_MODEL
    output_dir: str = ""
    include_languages: list[str] = field(default_factory=list)


def _from_dict(data: dict) -> ContextCraftConfig:
    """Build config from a dict; only known keys are read, unknown keys ignored."""
    cfg = ContextCraftConfig()
    if isinstance(data.get("skip_paths"), list):
        cfg.skip_paths = [str(x) for x in data["skip_paths"]]
    if isinstance(data.get("skip_extensions"), list):
        cfg.skip_extensions = [str(x) for x in data["skip_extensions"]]
    if isinstance(data.get("max_tokens"), int) and data["max_tokens"] > 0:
        cfg.max_tokens = data["max_tokens"]
    if isinstance(data.get("model"), str) and data["model"]:
        cfg.model = data["model"]
    if isinstance(data.get("output_dir"), str):
        cfg.output_dir = data["output_dir"]
    if isinstance(data.get("include_languages"), list):
        cfg.include_languages = [str(x) for x in data["include_languages"]]
    return cfg


def load_config(repo_path: Path) -> ContextCraftConfig:
    """
    Load config from <repo_path>/.contextcraft.yml (PyYAML) or .contextcraft.toml (stdlib).
    Returns defaults if no file exists. Unknown keys are silently ignored.
    """
    root = Path(repo_path).resolve()
    if not root.is_dir():
        return ContextCraftConfig()

    # Try .contextcraft.yml with PyYAML
    yml_path = root / ".contextcraft.yml"
    if yml_path.is_file():
        try:
            import yaml
            raw = yaml.safe_load(yml_path.read_text(encoding="utf-8"))
            if isinstance(raw, dict):
                return _from_dict(raw)
        except Exception:
            pass

    # Fallback: .contextcraft.toml with stdlib tomllib
    toml_path = root / ".contextcraft.toml"
    if toml_path.is_file():
        try:
            import tomllib
            with open(toml_path, "rb") as f:
                raw = tomllib.load(f)
            # Flatten [tool.contextcraft] or top-level
            data = raw.get("tool", {}).get("contextcraft", raw) if isinstance(raw.get("tool"), dict) else raw
            if isinstance(data, dict):
                return _from_dict(data)
        except Exception:
            pass

    return ContextCraftConfig()
