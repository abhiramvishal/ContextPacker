"""AST-based code structure extraction for Python (stdlib ast) and JS/TS/Java (tree-sitter)."""

from __future__ import annotations

import ast
from dataclasses import dataclass, field
from typing import Any

from contextcraft.scanner import FileInfo, read_file_safe


@dataclass
class ClassInfo:
    """Extracted class with methods and docstring."""

    name: str
    methods: list[str]  # method names
    docstring: str | None


@dataclass
class FunctionInfo:
    """Extracted function with signature and docstring."""

    name: str
    signature: str  # e.g. "def foo(a: int, b: str) -> bool"
    docstring: str | None


@dataclass
class FileAnalysis:
    """Structured analysis for one file: path, language, classes, functions, constants, metrics."""

    path: str
    language: str
    classes: list[ClassInfo] = field(default_factory=list)
    functions: list[FunctionInfo] = field(default_factory=list)
    constants: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    metrics: dict[str, Any] = field(default_factory=dict)


def _get_docstring(node: ast.AST) -> str | None:
    """Extract docstring from ast node."""
    doc = ast.get_docstring(node)
    return doc.strip() if doc else None


def _format_arg(arg: ast.arg) -> str:
    if arg.annotation:
        return f"{arg.arg}: {ast.unparse(arg.annotation)}"
    return arg.arg


def _format_signature(f: ast.FunctionDef) -> str:
    parts: list[str] = []
    if isinstance(getattr(f, "decorator_list", None), list) and f.decorator_list:
        for d in f.decorator_list:
            parts.append("@" + ast.unparse(d))
    args = [_format_arg(a) for a in f.args.args if a.arg != "self"]
    if f.args.vararg:
        args.append("*" + f.args.vararg.arg)
    if f.args.kwarg:
        args.append("**" + f.args.kwarg.arg)
    sig = f.name + "(" + ", ".join(args) + ")"
    if f.returns:
        sig += " -> " + ast.unparse(f.returns)
    return sig


def _compute_python_metrics(source: str, out: FileAnalysis, tree: ast.AST) -> None:
    """Populate metrics using ast line numbers."""
    lines = source.splitlines()
    out.metrics["lines"] = len(lines)
    out.metrics["blank_lines"] = sum(1 for L in lines if not L.strip())
    out.metrics["function_count"] = len(out.functions)
    out.metrics["class_count"] = len(out.classes)
    func_linenos: list[int] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef):
            func_linenos.append(node.lineno)
    func_linenos.sort()
    if len(func_linenos) < 2:
        out.metrics["avg_function_length"] = 0
    else:
        gaps = [func_linenos[i + 1] - func_linenos[i] for i in range(len(func_linenos) - 1)]
        out.metrics["avg_function_length"] = round(sum(gaps) / len(gaps), 1)


def _analyze_python(source: str, path: str) -> FileAnalysis:
    """Use stdlib ast to extract classes, functions, constants from Python."""
    out = FileAnalysis(path=path, language="python")
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return out
    for node in tree.body:
        if isinstance(node, ast.ClassDef):
            methods = [n.name for n in node.body if isinstance(n, ast.FunctionDef)]
            doc = _get_docstring(node)
            out.classes.append(ClassInfo(name=node.name, methods=methods, docstring=doc))
        elif isinstance(node, ast.FunctionDef):
            out.functions.append(
                FunctionInfo(
                    name=node.name,
                    signature=_format_signature(node),
                    docstring=_get_docstring(node),
                )
            )
        elif isinstance(node, ast.Assign):
            for t in node.targets:
                if isinstance(t, ast.Name) and isinstance(t.ctx, ast.Store):
                    out.constants.append(t.id)
    _compute_python_metrics(source, out, tree)
    return out


def _js_ts_analyze_tree_sitter(source: bytes, path: str, language: str) -> FileAnalysis:
    """Use tree-sitter for JavaScript/TypeScript."""
    out = FileAnalysis(path=path, language=language)
    try:
        from tree_sitter import Parser, Node
        import tree_sitter_javascript as tsjs
        from tree_sitter import Language
        lang = Language(tsjs.language())
        parser = Parser(lang)
        tree = parser.parse(source)
    except Exception as e:
        out.warnings.append(f"tree-sitter {language} parse failed: {e!s}")
        return out
    root = tree.root_node
    if not root:
        out.warnings.append(f"tree-sitter {language} returned empty tree")
        return out

    def get_text(node: Node) -> str:
        return source[node.start_byte : node.end_byte].decode("utf-8", errors="replace")

    def walk(node: Node) -> None:
        if node.type == "class_declaration":
            name_node = node.child_by_field_name("name")
            if name_node:
                out.classes.append(
                    ClassInfo(name=get_text(name_node).strip(), methods=[], docstring=None)
                )
            for c in node.children:
                if c.type == "class_body":
                    for m in c.children:
                        if m.type == "method_definition":
                            mn = m.child_by_field_name("name")
                            if mn:
                                out.classes[-1].methods.append(get_text(mn).strip().strip("'\""))
        elif node.type == "function_declaration":
            name_node = node.child_by_field_name("name")
            if name_node:
                sig = get_text(node).split("{")[0].strip()
                out.functions.append(
                    FunctionInfo(name=get_text(name_node).strip(), signature=sig, docstring=None)
                )
        elif node.type == "variable_declarator":
            # const/let/var foo = () => {} or async () => {}
            name_node = node.child_by_field_name("name")
            value_node = node.child_by_field_name("value")
            if name_node and value_node and value_node.type == "arrow_function":
                name_str = get_text(name_node).strip()
                if name_str:
                    sig = get_text(value_node).split("{")[0].strip() + " {}"
                    out.functions.append(
                        FunctionInfo(name=name_str, signature=sig, docstring=None)
                    )
        elif node.type == "export_statement":
            # Walk children so export default function foo / export function foo are still captured
            pass
        for c in node.children:
            walk(c)

    walk(root)

    # Metrics: lines, blank_lines, function_count, class_count, avg_function_length
    lines = source.decode("utf-8", errors="replace").splitlines()
    out.metrics["lines"] = len(lines)
    out.metrics["blank_lines"] = sum(1 for L in lines if not L.strip())
    out.metrics["function_count"] = len(out.functions)
    out.metrics["class_count"] = len(out.classes)
    func_linenos: list[int] = []
    _collect_js_ts_function_lines(root, func_linenos)
    if len(func_linenos) < 2:
        out.metrics["avg_function_length"] = 0
    else:
        func_linenos.sort()
        gaps = [func_linenos[i + 1] - func_linenos[i] for i in range(len(func_linenos) - 1)]
        out.metrics["avg_function_length"] = round(sum(gaps) / len(gaps), 1)

    return out


def _collect_js_ts_function_lines(node: Any, out_list: list[int]) -> None:
    """Recursively collect line numbers of function_declaration and arrow_function (in variable_declarator)."""
    if getattr(node, "type", None) == "function_declaration":
        out_list.append(node.start_point[0] + 1)
    elif getattr(node, "type", None) == "variable_declarator":
        val = node.child_by_field_name("value")
        if val and getattr(val, "type", None) == "arrow_function":
            out_list.append(val.start_point[0] + 1)
    for c in getattr(node, "children", []):
        _collect_js_ts_function_lines(c, out_list)


def _java_analyze_tree_sitter(source: bytes, path: str) -> FileAnalysis:
    """Use tree-sitter for Java (optional; fallback to empty analysis if not installed)."""
    out = FileAnalysis(path=path, language="java")
    try:
        from tree_sitter import Parser, Node
        import tree_sitter_java as tsjava
        from tree_sitter import Language
        lang = Language(tsjava.language())
        parser = Parser(lang)
        tree = parser.parse(source)
    except Exception as e:
        out.warnings.append(f"tree-sitter java parse failed: {e!s}")
        return out
    root = tree.root_node
    if not root:
        out.warnings.append("tree-sitter java returned empty tree")
        return out

    def get_text(node: Node) -> str:
        return source[node.start_byte : node.end_byte].decode("utf-8", errors="replace")

    def walk(node: Node) -> None:
        if node.type in ("class_declaration", "interface_declaration"):
            name_node = node.child_by_field_name("name")
            if name_node:
                out.classes.append(
                    ClassInfo(name=get_text(name_node).strip(), methods=[], docstring=None)
                )
            for c in node.children:
                if c.type == "class_body":
                    for m in c.children:
                        if m.type == "method_declaration":
                            name_node = m.child_by_field_name("name")
                            if name_node:
                                out.classes[-1].methods.append(get_text(name_node).strip())
                walk(c)
            return
        for c in node.children:
            walk(c)

    walk(root)

    lines = source.decode("utf-8", errors="replace").splitlines()
    out.metrics["lines"] = len(lines)
    out.metrics["blank_lines"] = sum(1 for L in lines if not L.strip())
    out.metrics["function_count"] = len(out.functions)
    out.metrics["class_count"] = len(out.classes)
    method_linenos: list[int] = []
    for c in root.children:
        _collect_java_method_lines(c, method_linenos)
    if len(method_linenos) < 2:
        out.metrics["avg_function_length"] = 0
    else:
        method_linenos.sort()
        gaps = [method_linenos[i + 1] - method_linenos[i] for i in range(len(method_linenos) - 1)]
        out.metrics["avg_function_length"] = round(sum(gaps) / len(gaps), 1)

    return out


def _collect_java_method_lines(node: Any, out_list: list[int]) -> None:
    """Recursively collect line numbers of method_declaration in Java."""
    if getattr(node, "type", None) == "method_declaration":
        out_list.append(node.start_point[0] + 1)
    for c in getattr(node, "children", []):
        _collect_java_method_lines(c, out_list)


def parse_file(file_info: FileInfo, source: str | None = None) -> FileAnalysis | None:
    """
    Parse a single file and return structured analysis (classes, functions, constants).
    Returns None if file could not be read or parsed; caller may skip or warn.
    """
    path_str = file_info.relative_path
    if source is None:
        source = read_file_safe(file_info.path)
    if source is None:
        return None
    lang = file_info.language
    if lang == "python":
        return _analyze_python(source, path_str)
    if lang == "javascript":
        return _js_ts_analyze_tree_sitter(source.encode("utf-8"), path_str, "javascript")
    if lang == "typescript":
        return _js_ts_analyze_tree_sitter(source.encode("utf-8"), path_str, "typescript")
    if lang == "java":
        return _java_analyze_tree_sitter(source.encode("utf-8"), path_str)
    return None


def analysis_to_dict(analysis: FileAnalysis) -> dict[str, Any]:
    """Convert FileAnalysis to a JSON-serializable dict."""
    return {
        "path": analysis.path,
        "language": analysis.language,
        "classes": [
            {"name": c.name, "methods": c.methods, "docstring": c.docstring}
            for c in analysis.classes
        ],
        "functions": [
            {"name": f.name, "signature": f.signature, "docstring": f.docstring}
            for f in analysis.functions
        ],
        "constants": analysis.constants,
        "warnings": analysis.warnings,
        "metrics": analysis.metrics,
    }
