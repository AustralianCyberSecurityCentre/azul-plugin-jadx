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

# JADX-generated obfuscated method names (e.g. m9869a, mo9639b, mo858k) -- not useful as features.
_RE_JADX_METHOD = re.compile(r"^mo?\d{3,}[a-z]+$")

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


def analyse_files(java_files: list[str | pathlib.Path]) -> dict[str, list[str]]:
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


def _analyse_single_file(java_file: str | pathlib.Path, features: _CodeFeatures) -> None:
    """Extract features from a single .java file and populate the provided sets."""
    with open(java_file, encoding="utf-8", errors="replace") as f:
        lines = f.readlines()

    # --- Determine package ---
    package = ""
    for line in lines:
        if m := _RE_PACKAGE.match(line):
            package = m.group(1)
            break

    # Add all package levels: "com", "com.example", "com.example.myapp".
    if package:
        parts = package.split(".")
        for i in range(1, len(parts) + 1):
            features.packages.add(".".join(parts[:i]))

    # --- Scan for type and method declarations ---
    brace_depth = 0
    class_stack: list[tuple[str | None, int]] = []  # (class_name, entry_depth); None = renamed
    pending_jadx_rename = False  # whether a JADX rename comment precedes this line

    for line in lines:
        brace_depth += line.count("{") - line.count("}")
        while class_stack and class_stack[-1][1] > brace_depth:
            class_stack.pop()

        stripped = line.strip()

        # JADX rename / informational comments.
        if stripped.startswith("/*") or stripped.startswith("*"):
            if "JADX INFO: renamed from:" in stripped:
                pending_jadx_rename = True
            continue
        if stripped.startswith("//") or stripped.startswith("@") or not stripped:
            continue

        # Type declaration?
        tm = _RE_TYPE_DECL.match(line)
        if tm:
            is_renamed = pending_jadx_rename
            pending_jadx_rename = False

            kind = tm.group(1)
            raw_name = tm.group(2)

            if not is_renamed:
                for part in raw_name.split("$"):
                    if not part:
                        continue
                    features.classes.add(part)
                    if package:
                        features.package_classes.add(f"{package}.{part}")

                if kind == "enum":
                    features.enums.add(raw_name)
                elif kind == "interface":
                    features.interfaces.add(raw_name)

            class_stack.append((raw_name if not is_renamed else None, brace_depth))
            continue

        pending_jadx_rename = False

        # Method declaration?
        if class_stack and (current_class := class_stack[-1][0]):
            mm = _RE_METHOD_DECL.match(line)
            if mm:
                method_name = mm.group(1)
                # Skip Java keywords and JADX obfuscated names.
                if method_name in _JAVA_KEYWORDS or _RE_JADX_METHOD.match(method_name):
                    continue
                # Skip mismatches like `return new Foo(` where the regex captures
                # a class name as a method name.
                pre_method = line[: mm.start(1)]
                if _JAVA_KEYWORDS.intersection(pre_method.split()):
                    continue
                features.class_methods.add(f"{current_class}::{method_name}")
                if package:
                    features.package_class_methods.add(f"{package}.{current_class}::{method_name}")
                    features.package_methods.add(f"{package}::{method_name}")
