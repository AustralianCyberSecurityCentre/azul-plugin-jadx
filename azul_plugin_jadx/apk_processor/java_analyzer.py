"""Parses JADX-decompiled Java source files to extract code features."""

import pathlib
import re
from dataclasses import dataclass, field

# Type declarations: captures kind (class|enum|interface) and name.
# e.g. "public class Foo", "enum Bar", "static final class Qux"
_RE_TYPE_DECL = re.compile(
    r"^\s*(?:(?:public|protected|private|abstract|static|final)\s+)*"
    r"(class|enum|interface)\s+(\w+)"
)

# Method declarations (not constructors).
# `*` (not `+`) allows package-private methods with no access modifier.
# e.g. "public void onCreate(Bundle b) {", "void helperMethod() {"
_RE_METHOD_DECL = re.compile(
    r"^\s*(?:(?:public|protected|private|abstract|static|final|synchronized|native|default)\s+)"
    r"*(?:[\w<>\[\],\s]+?\s+)"  # return type (possibly generic)
    r"(\w+)\s*\("  # method name
)

# Package declaration at the top of a .java file.
_RE_PACKAGE = re.compile(r"^\s*package\s+([\w.]+)\s*;")

# Single letter names are common in JADX obfuscation patterns, so ignore method names that are a single letter.
_RE_SINGLE_LETTER_NAME = re.compile(r"^[a-zA-Z]$")

# Java keywords the method regex may accidentally match.
# Includes "synchronized" because `synchronized (lock) {` looks like a method decl.
_JAVA_KEYWORDS = {"if", "for", "while", "switch", "return", "new", "throw", "synchronized"}


@dataclass
class _CodeFeatures:
    """Accumulates code feature sets across .java files."""

    package_class_methods: set[str] = field(default_factory=set)
    class_methods: set[str] = field(default_factory=set)
    package_methods: set[str] = field(default_factory=set)
    classes: set[str] = field(default_factory=set)
    package_classes: set[str] = field(default_factory=set)
    packages: set[str] = field(default_factory=set)
    enums: set[str] = field(default_factory=set)
    interfaces: set[str] = field(default_factory=set)


def analyze_files(java_files: list[pathlib.Path]) -> dict[str, list[str]]:
    """Extract code features from JADX-decompiled .java files.

    Parses each file using regex patterns to extract packages, classes, methods,
    and type declarations. Skips files that cannot be read or parsed.

    Args:
        java_files: List of Path objects pointing to .java source files.

    Returns:
        Dict mapping feature name (str) to deduplicated, sorted list of feature values.
        Example: {"classes": ["MainActivity", "Utils"], "packages": ["com.example"]}
    """
    features = _CodeFeatures()

    for java_file in java_files:
        try:
            _analyze_single_file(java_file, features)
        except (OSError, UnicodeDecodeError):
            pass

    return {k: sorted(list(v)) for k, v in vars(features).items()}


def _extract_package_features(lines: list[str], features: _CodeFeatures) -> str:
    """Extract package declaration and add all package levels to features.

    Scans lines for package statement (e.g., "package com.example.foo;") and
    adds all package hierarchy levels (com, com.example, com.example.foo).

    Args:
        lines: File lines to scan for package declaration.
        features: _CodeFeatures dataclass to accumulate package names.

    Returns:
        The package name (e.g., "com.example.foo"), or empty string if not found.
    """
    package = ""
    for line in lines:
        if m := _RE_PACKAGE.match(line):
            package = m.group(1)  # group(1) captures the package name after "package "
            break

    if package:
        parts = package.split(".")
        for i in range(1, len(parts) + 1):
            features.packages.add(".".join(parts[:i]))

    return package


def _process_type_declaration(
    raw_name: str,
    kind: str,
    package: str,
    features: _CodeFeatures,
) -> None:
    """Process a type declaration (class/enum/interface) and add features.

    Handles inner classes (names with $), filters obfuscated single-letter names,
    and adds to appropriate feature sets based on kind (enum/interface/class).

    Args:
        raw_name: Class name from regex match, may include inner class notation (e.g., "Outer$Inner").
        kind: Type kind: "class", "enum", or "interface".
        package: Fully-qualified package name (e.g., "com.example.foo").
        features: _CodeFeatures dataclass to accumulate class/enum/interface names.
    """
    # Skip single-letter names (obfuscation pattern).
    if _RE_SINGLE_LETTER_NAME.match(raw_name):
        return

    for part in raw_name.split("$"):
        if not part or _RE_SINGLE_LETTER_NAME.match(part):
            continue
        features.classes.add(part)
        if package:
            features.package_classes.add(f"{package}.{part}")

    if kind == "enum":
        features.enums.add(raw_name)
    elif kind == "interface":
        features.interfaces.add(raw_name)


def _process_method_declaration(
    current_class: str,
    method_name: str,
    line: str,
    match_start: int,
    package: str,
    features: _CodeFeatures,
) -> None:
    """Process a method declaration and add features.

    Filters out Java keywords (if, for, while, synchronized) and obfuscated names.
    Adds method to three feature types: class_methods, package_class_methods, package_methods.

    Args:
        current_class: Class name containing this method (e.g., "MainActivity").
        method_name: Method name from regex match (e.g., "onCreate").
        line: Full source line for context checking.
        match_start: Start position of method name in line (for keyword filtering).
        package: Fully-qualified package name.
        features: _CodeFeatures dataclass to accumulate method names.
    """
    # Skip Java keywords and JADX obfuscated names.
    if method_name in _JAVA_KEYWORDS or _RE_SINGLE_LETTER_NAME.match(method_name):
        return

    # Skip mismatches like `return new Foo(` where the regex captures a class name as method name.
    pre_method = line[:match_start]
    if _JAVA_KEYWORDS.intersection(pre_method.split()):
        return

    features.class_methods.add(f"{current_class}::{method_name}")
    if package:
        features.package_class_methods.add(f"{package}.{current_class}::{method_name}")
        features.package_methods.add(f"{package}::{method_name}")


def _should_skip_line(stripped: str) -> bool:
    """Check if a line should be skipped (comments, decorators, empty).

    Args:
        stripped: Stripped (whitespace-trimmed) line content.

    Returns:
        True if line is comment, decorator, or empty; False otherwise.
    """
    if stripped.startswith("/*") or stripped.startswith("*") or stripped.startswith("//"):
        return True
    if stripped.startswith("@") or not stripped:
        return True
    return False


def _process_line_for_declarations(
    line: str,
    package: str,
    class_stack: list[tuple[str, int]],
    features: _CodeFeatures,
    brace_depth: int,
) -> None:
    """Process a line for type or method declarations.

    Matches type declarations (class/enum/interface) and method declarations,
    updates class_stack to track scope. Called from _scan_file_for_features().

    Args:
        line: Raw source line to parse.
        package: Current package name.
        class_stack: Stack of (class_name, brace_depth_at_declaration) tuples.
        features: _CodeFeatures dataclass to accumulate declarations.
        brace_depth: Current brace nesting depth in file.
    """
    # Handle type declarations: match (class|enum|interface) keyword and name.
    tm = _RE_TYPE_DECL.match(line)
    if tm:
        kind = tm.group(1)  # group(1) = "class", "enum", or "interface"
        raw_name = tm.group(2)  # group(2) = class name
        _process_type_declaration(raw_name, kind, package, features)
        class_stack.append((raw_name, brace_depth))
        return

    # Handle method declarations: only if we're inside a class (class_stack not empty).
    if class_stack and (current_class := class_stack[-1][0]):
        mm = _RE_METHOD_DECL.match(line)
        if mm:
            method_name = mm.group(1)  # group(1) = method name from regex
            _process_method_declaration(current_class, method_name, line, mm.start(1), package, features)


def _scan_file_for_features(
    lines: list[str],
    package: str,
    features: _CodeFeatures,
) -> None:
    """Scan file lines for type and method declarations and extract features.

    Maintains brace_depth counter to track scope (nesting level). Maintains class_stack
    to associate methods with their containing class. Filters comments and decorators.

    Args:
        lines: All lines from .java file.
        package: Package name extracted from file.
        features: _CodeFeatures dataclass to accumulate declarations.
    """
    brace_depth = 0
    class_stack: list[tuple[str, int]] = []

    for line in lines:
        # Track brace depth to know when we exit class scopes.
        brace_depth += line.count("{") - line.count("}")
        # Pop classes from stack if we've exited their scope (brace_depth decreased).
        while class_stack and class_stack[-1][1] > brace_depth:
            class_stack.pop()

        stripped = line.strip()

        # Skip comments, decorators, and empty lines.
        if _should_skip_line(stripped):
            continue

        _process_line_for_declarations(line, package, class_stack, features, brace_depth)


def _analyze_single_file(java_file: pathlib.Path, features: _CodeFeatures) -> None:
    """Extract features from a single .java file and populate the provided sets.

    Orchestrates parsing: extract package -> scan for declarations -> update features.
    Raises OSError/UnicodeDecodeError if file cannot be read/decoded.

    Args:
        java_file: Path to .java file.
        features: _CodeFeatures dataclass to accumulate declarations across the file.

    Raises:
        OSError: If file cannot be opened/read.
        UnicodeDecodeError: If file encoding is not valid UTF-8 (fallback to 'replace' mode).
    """
    with open(java_file, encoding="utf-8", errors="replace") as f:
        lines = f.readlines()

    # Extract package and add package levels.
    package = _extract_package_features(lines, features)

    # Scan for type and method declarations.
    _scan_file_for_features(lines, package, features)
