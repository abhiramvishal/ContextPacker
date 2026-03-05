"""Build import/dependency graph and identify entry points and central modules."""

from __future__ import annotations

import ast
import re
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any

from contextcraft.constants import MAX_FILES_FOR_DEP_GRAPH
from contextcraft.scanner import FileInfo, FileTree, read_file_safe


@dataclass
class DependencyGraph:
    """Import graph: who imports whom; top internal modules by import count."""

    imports: dict[str, list[str]] = field(default_factory=dict)  # path -> list of imported modules
    imported_by: dict[str, list[str]] = field(default_factory=dict)  # module -> list of paths that import it
    top_internal: list[tuple[str, int]] = field(default_factory=list)  # (module, count) top 10


# Go stdlib single-word packages to skip
_GO_STDLIB = frozenset({"fmt", "os", "io", "bufio", "bytes", "strings", "strconv", "sort", "encoding", "log", "math", "net", "http", "json", "time", "context", "errors", "flag", "path", "regexp", "sync", "testing", "unicode", "crypto", "database", "html", "image", "mime", "reflect", "runtime", "text", "url", "archive", "compress", "container", "debug", "embed", "expvar", "hash", "index", "plugin", "builtin", "syscall", "unsafe", "internal"})

# Rust stdlib crates to skip
_RUST_STDLIB = frozenset({"std", "core", "alloc"})


def _normalize_module_path(relative_path: str, language: str) -> str:
    """Normalize file path to module name."""
    if language == "python":
        return relative_path.replace("\\", "/").replace("/", ".").replace(".py", "").rstrip(".")
    if language in ("javascript", "typescript"):
        return relative_path.replace("\\", "/").replace(".js", "").replace(".ts", "").replace(".jsx", "").replace(".tsx", "")
    if language == "java":
        return relative_path.replace("\\", "/").replace(".java", "")
    if language == "go":
        return relative_path.replace("\\", "/").replace(".go", "")
    if language == "rust":
        return relative_path.replace("\\", "/").replace(".rs", "")
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


def _normalize_relative_import(imp: str, current_file_path: str) -> str:
    """Resolve relative import to a clean module path (no leading ./, ../)."""
    imp = imp.replace("\\", "/").strip()
    while imp.startswith("./"):
        imp = imp[2:]
    if not imp:
        return ""
    # Resolve ../ and current dir from current_file_path's directory
    current_dir = current_file_path.replace("\\", "/").rsplit("/", 1)[0]
    if not current_dir:
        current_dir = "."
    parts = current_dir.split("/") if current_dir != "." else []
    for seg in imp.split("/"):
        if seg == "..":
            if parts:
                parts.pop()
        elif seg != ".":
            parts.append(seg)
    path = "/".join(parts).strip("/")
    # Drop extension for consistency
    for ext in (".js", ".ts", ".jsx", ".tsx", ".mjs", ".cjs"):
        if path.endswith(ext):
            path = path[: -len(ext)]
            break
    return path


def _js_ts_imports(source: str, current_file_path: str) -> list[str]:
    """Extract import targets from JS/TS source. Includes relative imports (internal); excludes bare package names (node_modules)."""
    imports: list[str] = []
    # require('x'), require("x")
    for m in re.finditer(r"(?:require\s*\(\s*['\"])([^'\"]+)(?:['\"])", source):
        imp = m.group(1).strip()
        if imp.startswith("."):
            norm = _normalize_relative_import(imp, current_file_path)
            if norm:
                imports.append(norm)
    for m in re.finditer(r"import\s+.*?\s+from\s+['\"]([^'\"]+)['\"]", source):
        imp = m.group(1).strip()
        if imp.startswith("."):
            norm = _normalize_relative_import(imp, current_file_path)
            if norm:
                imports.append(norm)
    for m in re.finditer(r"import\s+['\"]([^'\"]+)['\"]", source):
        imp = m.group(1).strip()
        if imp.startswith("."):
            norm = _normalize_relative_import(imp, current_file_path)
            if norm:
                imports.append(norm)
    return imports


def _java_imports(source: str) -> list[str]:
    """Extract import targets from Java source (package or top-level type)."""
    imports: list[str] = []
    for m in re.finditer(r"import\s+(?:static\s+)?([\w.]+)(?:\.\*)?\s*;", source):
        full = m.group(1)
        imports.append(full.split(".")[0])
    return imports


def _go_imports(source: str) -> list[str]:
    """Extract import targets from Go: import \"...\" and import ( \"...\" ); last segment as module; skip stdlib."""
    imports: list[str] = []
    # import "path/to/pkg"
    for m in re.finditer(r'import\s+"([^"]+)"', source):
        path = m.group(1).strip()
        if "/" in path:
            name = path.split("/")[-1]
        else:
            name = path
        if name not in _GO_STDLIB:
            imports.append(name)
    # import ( "pkg1" \n "pkg2" )
    for block in re.finditer(r'import\s*\(\s*(.*?)\s*\)', source, re.DOTALL):
        for m in re.finditer(r'"([^"]+)"', block.group(1)):
            path = m.group(1).strip()
            if "/" in path:
                name = path.split("/")[-1]
            else:
                name = path
            if name not in _GO_STDLIB:
                imports.append(name)
    return imports


def _rust_imports(source: str) -> list[str]:
    """Extract import targets from Rust: use foo::bar::baz; top-level crate (first segment); skip std/core/alloc."""
    imports: list[str] = []
    for m in re.finditer(r"use\s+([\w:]+)(?:::\*)?\s*;", source):
        path = m.group(1).strip()
        first = path.split("::")[0]
        if first not in _RUST_STDLIB:
            imports.append(first)
    return imports


def build_dependency_graph(file_tree: FileTree, max_files: int = MAX_FILES_FOR_DEP_GRAPH) -> DependencyGraph:
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
            raw = _js_ts_imports(src, path)
            for imp in raw:
                graph.imports[path].append(imp)
                graph.imported_by.setdefault(imp, []).append(path)
        elif f.language == "java":
            raw = _java_imports(src)
            for imp in raw:
                graph.imports[path].append(imp)
                first = imp.split(".")[0]
                if first in internal_prefixes:
                    graph.imported_by.setdefault(first, []).append(path)
        elif f.language == "go":
            raw = _go_imports(src)
            for imp in raw:
                graph.imports[path].append(imp)
                if imp in internal_prefixes:
                    graph.imported_by.setdefault(imp, []).append(path)
        elif f.language == "rust":
            raw = _rust_imports(src)
            for imp in raw:
                graph.imports[path].append(imp)
                if imp in internal_prefixes:
                    graph.imported_by.setdefault(imp, []).append(path)

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
