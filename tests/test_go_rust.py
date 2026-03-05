"""Tests for Go and Rust parsing and dependency extraction."""

from pathlib import Path

import pytest

from contextcraft.analyzer.ast_parser import parse_file, _parse_go, _parse_rust
from contextcraft.analyzer.dependency_graph import _go_imports, _rust_imports
from contextcraft.scanner import FileInfo


def test_go_struct_and_function_extraction() -> None:
    """Test Go struct and function extraction on an inline snippet."""
    go_src = """
package main

type FooBar struct {
    Name string
}

func (r *Receiver) MethodName(a int) {
}

func StandaloneFunc() error {
    return nil
}

const ConstName = "x"
"""
    analysis = _parse_go(go_src, "pkg/main.go")
    assert analysis.language == "go"
    assert any(c.name == "FooBar" for c in analysis.classes)
    names = [f.name for f in analysis.functions]
    assert "MethodName" in names
    assert "StandaloneFunc" in names
    assert "ConstName" in analysis.constants
    assert analysis.metrics.get("lines") is not None
    assert analysis.metrics.get("function_count") == 2
    assert analysis.metrics.get("class_count") == 1


def test_rust_struct_enum_and_function_extraction() -> None:
    """Test Rust struct/enum and function extraction on an inline snippet."""
    rust_src = """
pub struct Foo {
    x: i32,
}

enum Bar {
    A, B,
}

pub fn foo_bar(x: i32) -> bool {
    true
}

fn private_fn() {}

pub const FOO: i32 = 42;
"""
    analysis = _parse_rust(rust_src, "src/lib.rs")
    assert analysis.language == "rust"
    names = [c.name for c in analysis.classes]
    assert "Foo" in names
    assert "Bar" in names
    names = [f.name for f in analysis.functions]
    assert "foo_bar" in names
    assert "private_fn" in names
    assert "FOO" in analysis.constants
    assert analysis.metrics.get("function_count") == 2
    assert analysis.metrics.get("class_count") == 2


def test_go_imports_extracts_module_names() -> None:
    """Test _go_imports extracts correct module names."""
    src = '''
import "fmt"
import "myorg/myrepo/pkg/util"
import (
    "encoding/json"
    "internal/helper"
)
'''
    imports = _go_imports(src)
    assert "fmt" not in imports  # stdlib skipped
    assert "util" in imports
    assert "json" not in imports
    assert "helper" in imports


def test_rust_imports_skips_std() -> None:
    """Test _rust_imports extracts crate names and skips std/core/alloc."""
    src = """
use std::collections::HashMap;
use core::ops::Add;
use alloc::vec::Vec;
use my_crate::foo::bar;
use other::Something;
"""
    imports = _rust_imports(src)
    assert "std" not in imports
    assert "core" not in imports
    assert "alloc" not in imports
    assert "my_crate" in imports
    assert "other" in imports
