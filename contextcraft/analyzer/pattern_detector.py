"""Detect naming conventions, test framework, error handling, API style, and config patterns."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from contextcraft.scanner import FileInfo, FileTree, read_file_safe


@dataclass
class Patterns:
    """Detected conventions: naming, testing, error handling, API, config."""

    naming: str = "mixed"  # snake_case | camelCase | PascalCase | mixed
    test_framework: str | None = None  # pytest | unittest | jest | mocha | None
    error_handling: list[str] = field(default_factory=list)  # e.g. try/except, custom exceptions
    api_style: str = "unknown"  # REST | GraphQL | internal | unknown
    config_style: list[str] = field(default_factory=list)  # env | config_file | hardcoded
    custom_exceptions: list[str] = field(default_factory=list)


# Naming regexes
SNAKE_RE = re.compile(r"\b[a-z][a-z0-9]*(_[a-z0-9]+)+\b")
CAMEL_RE = re.compile(r"\b[a-z][a-zA-Z0-9]*[A-Z][a-zA-Z0-9]*\b")
PASCAL_RE = re.compile(r"\b[A-Z][a-zA-Z0-9]*\b")

# Test framework indicators
PYTEST_IMPORTS = ("pytest", "pytest.")
UNITTEST_IMPORTS = ("unittest", "unittest.")
JEST_PATTERNS = ("jest", "describe(", "it(", "test(", "expect(")
MOCHA_PATTERNS = ("mocha", "describe(", "it(", "require(", "chai")

# API style indicators
REST_PATTERNS = ("@app.route", "router.", "FastAPI", "flask", "express.", "get(", "post(", "/api/", "Router")
GRAPHQL_PATTERNS = ("graphql", "gql", "resolver", "GraphQL", "Apollo")

# Config indicators
ENV_PATTERNS = ("os.environ", "getenv", "process.env", "dotenv", "load_dotenv", "pydantic_settings", "BaseSettings")
CONFIG_FILE_PATTERNS = ("config.", "yaml.load", "json.load", "ConfigParser", "configparser", "settings.", "config[")


def _detect_naming(sources: list[str]) -> str:
    """Determine primary naming convention from source samples."""
    snake, camel, pascal = 0, 0, 0
    for s in sources:
        snake += len(SNAKE_RE.findall(s))
        camel += len(CAMEL_RE.findall(s))
        pascal += len(PASCAL_RE.findall(s))
    if snake > camel and snake > pascal:
        return "snake_case"
    if camel > snake and camel > pascal:
        return "camelCase"
    if pascal > snake and pascal > camel:
        return "PascalCase"
    return "mixed"


def _detect_test_framework(file_tree: FileTree, sources: list[tuple[str, str]]) -> str | None:
    """Detect test framework from file names and imports."""
    # By file name
    for f in file_tree.files:
        r = f.relative_path.lower()
        if "test" in r or "spec" in r or "_test" in r or ".test." in r:
            if f.extension in (".py",):
                # Prefer pytest if both appear
                for path, src in sources:
                    if path == f.relative_path and ("pytest" in src or "import pytest" in src):
                        return "pytest"
                    if path == f.relative_path and ("unittest" in src):
                        return "unittest"
            if f.extension in (".js", ".ts", ".jsx", ".tsx"):
                for path, src in sources:
                    if path == f.relative_path:
                        if "jest" in src or "expect(" in src:
                            return "jest"
                        if "mocha" in src or "chai" in src:
                            return "mocha"
    # By import across repo
    all_src = " ".join(s for _, s in sources)
    if "pytest" in all_src or "from pytest" in all_src:
        return "pytest"
    if "import unittest" in all_src or "from unittest" in all_src:
        return "unittest"
    if "jest" in all_src or "describe(" in all_src and "expect(" in all_src:
        return "jest"
    if "mocha" in all_src or "chai" in all_src:
        return "mocha"
    return None


def _detect_error_handling(sources: list[str]) -> list[str]:
    """Detect error handling style: try/except, custom exceptions."""
    out: list[str] = []
    full = " ".join(sources)
    if "try:" in full or "try {" in full or "except " in full or "catch (" in full:
        out.append("try/except or try/catch")
    if "raise " in full or "throw new " in full:
        out.append("raise/throw exceptions")
    # Custom exception classes (Python: class XError, Java: extends Exception)
    if re.search(r"class\s+\w+Error\s*[:(]", full) or re.search(r"extends\s+\w*Exception", full):
        out.append("custom exception classes")
    return out


def _detect_custom_exceptions(sources: list[str]) -> list[str]:
    """Find custom exception class names."""
    names: list[str] = []
    for s in sources:
        for m in re.finditer(r"class\s+(\w+Error|\w+Exception)\s*[:(]", s):
            names.append(m.group(1))
    return list(dict.fromkeys(names))


def _detect_api_style(sources: list[str]) -> str:
    """Detect API style: REST, GraphQL, or internal."""
    full = " ".join(sources)
    gql = sum(1 for p in GRAPHQL_PATTERNS if p in full)
    rest = sum(1 for p in REST_PATTERNS if p in full)
    if gql > rest:
        return "GraphQL"
    if rest > 0:
        return "REST"
    return "internal"


def _detect_config_style(sources: list[str]) -> list[str]:
    """Detect how config is loaded: env vars, config files, hardcoded."""
    out: list[str] = []
    full = " ".join(sources)
    if any(p in full for p in ENV_PATTERNS):
        out.append("env vars (.env, os.environ, BaseSettings)")
    if any(p in full for p in CONFIG_FILE_PATTERNS):
        out.append("config files (yaml/json/ini)")
    if not out:
        out.append("unknown or hardcoded")
    return out


def detect_patterns(file_tree: FileTree, max_files: int = 200) -> Patterns:
    """
    Analyze naming conventions, test framework, error handling, API style, config.
    Samples up to max_files of readable source files.
    """
    patterns = Patterns()
    sources: list[str] = []
    path_sources: list[tuple[str, str]] = []  # (relative_path, source)

    for f in file_tree.files[: max_files * 2]:  # oversample in case some fail to read
        if not f.language:
            continue
        src = read_file_safe(f.path)
        if src:
            sources.append(src)
            path_sources.append((f.relative_path, src))
        if len(sources) >= max_files:
            break

    if not sources:
        return patterns

    patterns.naming = _detect_naming(sources)
    patterns.test_framework = _detect_test_framework(file_tree, path_sources)
    patterns.error_handling = _detect_error_handling(sources)
    patterns.custom_exceptions = _detect_custom_exceptions(sources)
    patterns.api_style = _detect_api_style(sources)
    patterns.config_style = _detect_config_style(sources)

    return patterns


def patterns_to_dict(patterns: Patterns) -> dict[str, Any]:
    """Convert Patterns to JSON-serializable dict."""
    return {
        "naming": patterns.naming,
        "test_framework": patterns.test_framework,
        "error_handling": patterns.error_handling,
        "api_style": patterns.api_style,
        "config_style": patterns.config_style,
        "custom_exceptions": patterns.custom_exceptions,
    }
