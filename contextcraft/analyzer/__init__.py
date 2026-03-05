"""Code analysis: AST parsing, patterns, dependencies, git context."""

from contextcraft.analyzer.ast_parser import parse_file
from contextcraft.analyzer.dependency_graph import build_dependency_graph
from contextcraft.analyzer.git_analyzer import analyze_git
from contextcraft.analyzer.pattern_detector import detect_patterns

__all__ = [
    "parse_file",
    "detect_patterns",
    "build_dependency_graph",
    "analyze_git",
]
