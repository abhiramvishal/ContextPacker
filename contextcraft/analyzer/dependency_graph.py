"""Build import/dependency graph and identify entry points and central modules."""

from __future__ import annotations

import ast
import re
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any

from contextcraft.scanner import FileInfo, FileTree, read_file_safe


@dataclass
class DependencyGraph:
    """Import graph: who imports whom; top internal modules by import count."""

    imports: dict[str, list[str]] = field(default_factory=dict)  # path -> list of imported modules
    imported_by: dict[str, list[str]] = field(default_factory=dict)  # module -> list of paths that import it
    top_internal: list[tuple[str, int]] = field(default_factory=list)  # (module, count) top 10


def _normalize_module_path(relative_path: str, language: str) -> str:
    """Normalize file path to module name (e.g. for Python: path/to/module.py -> path.to.module)."""
    if language == "python":
        return relative_path.replace("\\", "/").replace("/", ".").replace(".py", "").rstrip(".")
    if language in ("javascript", "typescript"):
        return relative_path.replace("\\", "/").replace(".js", "").replace(".ts", "").replace(".jsx", "").replace(".tsx", "")
    if language == "java":
        return relative_path.replace("\\", "/").replace(".java", "")
    return relative_path


def _python_imports(source: str, file_path: str) -> list[str]:
    """Extract import targets from Python source."""
    imports: list[str] = []
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return imports
    base = file_path.replace("\\", "/").rsplit("/", 1)[0]
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                name = alias.name.split(".")[0]
                imports.append(name)
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                name = node.module.split(".")[0]
                imports.append(name)
    return imports


def _js_ts_imports(source: str) -> list[str]:
    """Extract import targets from JS/TS source (first segment of path or package name)."""
    imports: list[str] = []
    # require('x'), require("x"), import x from 'y', import { z } from 'y'
    for m in re.finditer(r"(?:require\s*\(\s*['\"])([^'\"]+)(?:['\"])", source):
        imp = m.group(1).split("/")[0]
        if not imp.startswith("."):
            imports.append(imp)
    for m in re.finditer(r"import\s+.*?\s+from\s+['\"]([^'\"]+)['\"]", source):
        imp = m.group(1).split("/")[0]
        if not imp.startswith("."):
            imports.append(imp)
    for m in re.finditer(r"import\s+['\"]([^'\"]+)['\"]", source):
        imp = m.group(1).split("/")[0]
        if not imp.startswith("."):
            imports.append(imp)
    return imports


def _java_imports(source: str) -> list[str]:
    """Extract import targets from Java source (package or top-level type)."""
    imports: list[str] = []
    for m in re.finditer(r"import\s+(?:static\s+)?([\w.]+)(?:\.\*)?\s*;", source):
        full = m.group(1)
        imports.append(full.split(".")[0])
    return imports


def build_dependency_graph(file_tree: FileTree, max_files: int = 2000) -> DependencyGraph:
    """
    Parse imports across the repo; build graph; return top 10 most-imported internal modules.
    """
    graph = DependencyGraph()
    path_to_module: dict[str, str] = {}
    internal_modules: set[str] = set()

    # Collect all internal module names (by path)
    for f in file_tree.files:
        if not f.language:
            continue
        mod = _normalize_module_path(f.relative_path, f.language)
        path_to_module[f.relative_path] = mod
        if f.language == "python":
            internal_modules.add(mod.split(".")[0])
        internal_modules.add(mod)

    # Build set of "internal" top-level names (e.g. package or first path segment)
    internal_prefixes: set[str] = set()
    for f in file_tree.files:
        if not f.language:
            continue
        parts = f.relative_path.replace("\\", "/").split("/")
        if parts:
            internal_prefixes.add(parts[0])

    count = 0
    for f in file_tree.files:
        if count >= max_files:
            break
        if not f.language:
            continue
        src = read_file_safe(f.path)
        if not src:
            continue
        count += 1
        path = f.relative_path
        mod = path_to_module[path]
        graph.imports[path] = []

        if f.language == "python":
            raw = _python_imports(src, path)
            for imp in raw:
                graph.imports[path].append(imp)
                # Consider internal if it matches a top-level dir or known internal
                if imp in internal_prefixes or any(mod.startswith(imp + ".") for mod in path_to_module.values()):
                    graph.imported_by.setdefault(imp, []).append(path)
        elif f.language in ("javascript", "typescript"):
            raw = _js_ts_imports(src)
            for imp in raw:
                if imp.startswith("."):
                    continue
                graph.imports[path].append(imp)
                if imp in internal_prefixes:
                    graph.imported_by.setdefault(imp, []).append(path)
        elif f.language == "java":
            raw = _java_imports(src)
            for imp in raw:
                graph.imports[path].append(imp)
                first = imp.split(".")[0]
                if first in internal_prefixes:
                    graph.imported_by.setdefault(first, []).append(path)

    # Top 10 most-imported internal modules (by path or first segment)
    internal_import_counts: dict[str, int] = defaultdict(int)
    for path, mod_list in graph.imports.items():
        for m in mod_list:
            if m in internal_prefixes or any(m in p for p in path_to_module.values()):
                internal_import_counts[m] += 1
    graph.top_internal = sorted(internal_import_counts.items(), key=lambda x: -x[1])[:10]

    return graph


def dependency_graph_to_dict(graph: DependencyGraph) -> dict[str, Any]:
    """Convert DependencyGraph to JSON-serializable dict."""
    return {
        "imports": graph.imports,
        "imported_by": graph.imported_by,
        "top_internal_modules": graph.top_internal,
    }
