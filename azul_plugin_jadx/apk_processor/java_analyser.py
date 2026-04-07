"""Parses JADX-decompiled Java source files to extract code features."""

import re
from dataclasses import dataclass, field

# Matches type declarations. Captures the kind (class|enum|interface) and name.
# Examples:
#   public class Foo
#   public enum Bar
#   public interface Baz
#   class Qux extends ...
_RE_TYPE_DECL = re.compile(
    r"^\s*(?:(?:public|protected|private|abstract|static|final)\s+)*"
    r"(class|enum|interface)\s+(\w+)"
)

# Matches method declarations (not constructors).
# `*` (not `+`) allows package-private methods that have no access modifier keyword.
# Examples:
#   public void onCreate(Bundle bundle) {
#   private static String m9517a() {
#   void helperMethod() {    <-- package-private, no modifier
_RE_METHOD_DECL = re.compile(
    r"^\s*(?:(?:public|protected|private|abstract|static|final|synchronized|native|default)\s+)"
    r"*(?:[\w<>\[\],\s]+?\s+)"  # return type (possibly generic)
    r"(\w+)\s*\("  # method name
)

# Matches the package declaration at the top of a .java file.
_RE_PACKAGE = re.compile(r"^\s*package\s+([\w.]+)\s*;")

# Matches JADX-generated obfuscated method names (not useful as features).
# JADX renames obfuscated methods as: optional 'o' + 4+ digits + lowercase suffix.
# Examples: m9869a, mo9639b, m9871a, mo9590c
_RE_JADX_METHOD = re.compile(r"^mo?\d{4,}[a-z]+$")

# Maximum number of values emitted per feature key to prevent unbounded feature lists.
_MAX_FEATURES_PER_KEY = 5000

# Java control-flow keywords the method regex may accidentally match.
_JAVA_KEYWORDS = frozenset({"if", "for", "while", "switch", "return", "new", "throw"})


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


def analyse_files(java_files: list[str]) -> dict[str, list[str]]:
    """Analyse a list of JADX-decompiled .java files and extract code features.

    The returned dict mirrors the namespace decomposition from the dotnet plugin,
    with ``package`` substituted for ``namespace``:

    - ``package_class_methods``: ``com.example.MyClass::methodName``
    - ``class_methods``: ``MyClass::methodName``
    - ``package_methods``: ``com.example::methodName``
    - ``classes``: unique outer/inner class names (split on ``$``)
    - ``package_classes``: ``com.example.MyClass``
    - ``packages``: ``com.example``
    - ``enums``: enum type names
    - ``interfaces``: interface type names

    Results are capped at ``_MAX_FEATURES_PER_KEY`` values per key.

    Args:
        java_files: List of absolute paths to .java files.

    Returns:
        A dict mapping feature name to a deduplicated, capped list of string values.
    """
    features = _CodeFeatures()

    for java_file in java_files:
        try:
            _analyse_single_file(java_file, features)
        except Exception:  # noqa: BLE001,S110
            # Tolerate malformed or unreadable files — continue with others.
            pass  # noqa: S110

    return {k: list(v)[:_MAX_FEATURES_PER_KEY] for k, v in vars(features).items()}


def _analyse_single_file(java_file: str, features: _CodeFeatures) -> None:
    """Extract features from a single .java file and populate the provided sets."""
    with open(java_file, encoding="utf-8", errors="replace") as f:
        lines = f.readlines()

    # --- Determine package ---
    package = ""
    for line in lines:
        m = _RE_PACKAGE.match(line)
        if m:
            package = m.group(1)
            break

    # Add all package levels (e.g. "com", "com.example", "com.example.myapp").
    if package:
        parts = package.split(".")
        for i in range(1, len(parts) + 1):
            features.packages.add(".".join(parts[:i]))

    # --- Scan for type and method declarations ---
    # Track the current class context (outermost declared type in this file).
    current_class = ""
    # Track whether a JADX rename comment directly precedes the current line.
    pending_jadx_rename = False

    for line in lines:
        stripped = line.strip()

        # JADX rename / informational comments — update pending state, don't reset it.
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

            kind = tm.group(1)  # "class", "enum", or "interface"
            raw_name = tm.group(2)

            if not is_renamed:
                # Split on $ to handle both outer and inner class names.
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

            # Use the first (outermost) declared type as the class context for methods,
            # even if it is renamed — we use is_renamed below to gate method emission.
            if not current_class:
                current_class = raw_name if not is_renamed else ""
            continue

        pending_jadx_rename = False

        # Method declaration?
        if current_class:
            mm = _RE_METHOD_DECL.match(line)
            if mm:
                method_name = mm.group(1)
                # Skip synthetic Java constructs and JADX-generated obfuscated names.
                if method_name in _JAVA_KEYWORDS or _RE_JADX_METHOD.match(method_name):
                    continue
                features.class_methods.add(f"{current_class}::{method_name}")
                if package:
                    features.package_class_methods.add(f"{package}.{current_class}::{method_name}")
                    features.package_methods.add(f"{package}::{method_name}")
