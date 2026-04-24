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

# Maximum number of values emitted per feature key to prevent unbounded feature lists.
_MAX_FEATURES_PER_KEY = 5000

# Java keywords the method regex may accidentally match.
# Includes "synchronized" because `synchronized (lock) {` looks like a method decl.
_JAVA_KEYWORDS = frozenset({"if", "for", "while", "switch", "return", "new", "throw", "synchronized"})


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


def analyse_files(java_files: list[pathlib.Path]) -> dict[str, list[str]]:
    """Extract code features from JADX-decompiled .java files.

    Returns a dict mapping feature name to a deduplicated list of values,
    capped at _MAX_FEATURES_PER_KEY per key.
    """
    features = _CodeFeatures()

    for java_file in java_files:
        try:
            _analyse_single_file(java_file, features)
        except Exception:  # noqa: BLE001,S110
            # Tolerate malformed or unreadable files -- continue with others.
            pass  # noqa: S110

    return {k: list(v)[:_MAX_FEATURES_PER_KEY] for k, v in vars(features).items()}


def _extract_package_features(lines: list[str], features: _CodeFeatures) -> str:
    """Extract package declaration and add all package levels to features.

    Returns the package name, or empty string if not found.
    """
    package = ""
    for line in lines:
        if m := _RE_PACKAGE.match(line):
            package = m.group(1)
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
    """Process a type declaration (class/enum/interface) and add features."""
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
    """Process a method declaration and add features."""
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
    """Check if a line should be skipped (comments, decorators, empty)."""
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
    """Process a line for type or method declarations."""
    # Handle type declarations.
    tm = _RE_TYPE_DECL.match(line)
    if tm:
        kind = tm.group(1)
        raw_name = tm.group(2)
        _process_type_declaration(raw_name, kind, package, features)
        class_stack.append((raw_name, brace_depth))
        return

    # Handle method declarations.
    if class_stack and (current_class := class_stack[-1][0]):
        mm = _RE_METHOD_DECL.match(line)
        if mm:
            method_name = mm.group(1)
            _process_method_declaration(current_class, method_name, line, mm.start(1), package, features)


def _scan_file_for_features(
    lines: list[str],
    package: str,
    features: _CodeFeatures,
) -> None:
    """Scan file lines for type and method declarations and extract features."""
    brace_depth = 0
    class_stack: list[tuple[str, int]] = []

    for line in lines:
        brace_depth += line.count("{") - line.count("}")
        while class_stack and class_stack[-1][1] > brace_depth:
            class_stack.pop()

        stripped = line.strip()

        if _should_skip_line(stripped):
            continue

        _process_line_for_declarations(line, package, class_stack, features, brace_depth)


def _analyse_single_file(java_file: pathlib.Path, features: _CodeFeatures) -> None:
    """Extract features from a single .java file and populate the provided sets."""
    with open(java_file, encoding="utf-8", errors="replace") as f:
        lines = f.readlines()

    # Extract package and add package levels.
    package = _extract_package_features(lines, features)

    # Scan for type and method declarations.
    _scan_file_for_features(lines, package, features)
