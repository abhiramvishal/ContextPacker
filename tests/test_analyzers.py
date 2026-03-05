"""Tests for analyzer modules: ast_parser, dependency_graph, pattern_detector."""

from pathlib import Path

import pytest

from contextcraft.analyzer.ast_parser import (
    FileAnalysis,
    parse_file,
    analysis_to_dict,
)
from contextcraft.analyzer.dependency_graph import (
    build_dependency_graph,
    _js_ts_imports,
    _normalize_relative_import,
)
from contextcraft.analyzer.pattern_detector import detect_patterns
from contextcraft.scanner import FileInfo, FileTree


# ---- ast_parser ----
def test_parse_file_python_extracts_class_and_functions(tmp_path: Path) -> None:
    """Parse a small Python snippet; assert class and function names are extracted."""
    py_path = tmp_path / "mymod.py"
    py_path.write_text(
        """
class MyClass:
    '''A class.'''
    def method_one(self):
        pass
    def method_two(self):
        pass

def top_level_func(a: int, b: str) -> bool:
    '''A function.'''
    return True

OTHER_CONST = 42
""",
        encoding="utf-8",
    )
    info = FileInfo(
        path=py_path,
        relative_path="mymod.py",
        extension=".py",
        size_bytes=py_path.stat().st_size,
        last_modified=0.0,
    )
    analysis = parse_file(info)
    assert analysis is not None
    assert analysis.path == "mymod.py"
    assert analysis.language == "python"
    assert len(analysis.classes) == 1
    assert analysis.classes[0].name == "MyClass"
    assert set(analysis.classes[0].methods) == {"method_one", "method_two"}
    assert len(analysis.functions) == 1
    assert analysis.functions[0].name == "top_level_func"
    assert "a: int" in analysis.functions[0].signature
    assert "OTHER_CONST" in analysis.constants


def test_analysis_to_dict_includes_warnings() -> None:
    """analysis_to_dict includes warnings field."""
    a = FileAnalysis(path="x", language="python", warnings=["w1"])
    d = analysis_to_dict(a)
    assert d["warnings"] == ["w1"]


# ---- dependency_graph ----
def test_build_dependency_graph_internal_modules(tmp_path: Path) -> None:
    """Build graph from mock FileTree with 2–3 Python files; assert top internal modules."""
    (tmp_path / "app").mkdir()
    (tmp_path / "app" / "main.py").write_text("from app.utils import foo\nfrom app import config")
    (tmp_path / "app" / "utils.py").write_text("from app import config")
    (tmp_path / "app" / "config.py").write_text("# no imports")
    files = [
        FileInfo(
            path=tmp_path / "app" / "main.py",
            relative_path="app/main.py",
            extension=".py",
            size_bytes=0,
            last_modified=0.0,
        ),
        FileInfo(
            path=tmp_path / "app" / "utils.py",
            relative_path="app/utils.py",
            extension=".py",
            size_bytes=0,
            last_modified=0.0,
        ),
        FileInfo(
            path=tmp_path / "app" / "config.py",
            relative_path="app/config.py",
            extension=".py",
            size_bytes=0,
            last_modified=0.0,
        ),
    ]
    tree = FileTree(root=tmp_path, files=files, primary_languages=[("python", 3)])
    graph = build_dependency_graph(tree)
    assert "app/main.py" in graph.imports
    assert "app" in graph.imported_by
    assert any(m[0] == "app" for m in graph.top_internal)


def test_js_ts_imports_relative_included() -> None:
    """Relative imports are included and normalized."""
    source = "import x from './utils'; import { y } from '../lib/helper'; require('lodash');"
    imports = _js_ts_imports(source, "src/foo/bar.js")
    assert "./utils" not in imports
    assert "../lib/helper" not in imports
    # Normalized: ./utils from src/foo/bar.js -> src/foo/utils; ../lib/helper -> src/lib/helper
    assert "src/foo/utils" in imports
    assert "src/lib/helper" in imports
    # Bare package lodash excluded (node_modules)
    assert "lodash" not in imports


def test_normalize_relative_import() -> None:
    """_normalize_relative_import strips ./ and ../ and normalizes."""
    assert _normalize_relative_import("./foo", "a/b/c.js") == "a/b/foo"
    assert _normalize_relative_import("../lib", "a/b/c.js") == "a/lib"


# ---- pattern_detector ----
def test_detect_patterns_naming_snake_case(tmp_path: Path) -> None:
    """Run detect_patterns on minimal FileTree with snake_case source; assert naming detected."""
    (tmp_path / "code.py").write_text(
        "def my_snake_function():\n    my_variable_name = 1\n    return my_variable_name"
    )
    info = FileInfo(
        path=tmp_path / "code.py",
        relative_path="code.py",
        extension=".py",
        size_bytes=0,
        last_modified=0.0,
    )
    tree = FileTree(root=tmp_path, files=[info], primary_languages=[("python", 1)])
    patterns = detect_patterns(tree)
    assert patterns.naming == "snake_case"
