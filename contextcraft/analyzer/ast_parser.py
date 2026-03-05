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
    """Structured analysis for one file: path, language, classes, functions, constants."""

    path: str
    language: str
    classes: list[ClassInfo] = field(default_factory=list)
    functions: list[FunctionInfo] = field(default_factory=list)
    constants: list[str] = field(default_factory=list)


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
                    # Constant-like: name only (could check value for literal)
                    out.constants.append(t.id)
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
    except Exception:
        return out
    root = tree.root_node
    if not root:
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
        elif node.type == "arrow_function":
            # Could be in variable declarator: const foo = () => {}
            pass
        elif node.type == "export_statement":
            pass
        for c in node.children:
            walk(c)

    walk(root)
    # Dedupe classes and fill methods by scanning again for method_definition under class
    return out


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
    except Exception:
        return out
    root = tree.root_node
    if not root:
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
    return out


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
    }
