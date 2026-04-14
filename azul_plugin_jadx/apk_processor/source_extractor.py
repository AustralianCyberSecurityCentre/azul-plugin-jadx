"""Finds user-authored Java source files in a JADX output directory."""

import os
from xml.etree.ElementTree import ElementTree

_ANDROID_NS = "http://schemas.android.com/apk/res/android"
_COMPONENT_TAGS = frozenset({"activity", "service", "receiver", "provider"})
_EXCLUDED_FILENAMES = frozenset({"R.java", "BuildConfig.java"})


def get_user_packages(manifest_tree: ElementTree, manifest_package: str) -> list[str]:
    """Return deduplicated, subpackage-collapsed package prefixes for user-authored code.

    Reads component class names from the manifest and keeps packages that share
    at least two leading segments with ``manifest_package``, excluding third-party
    libraries without a deny-list. Falls back to ``[manifest_package]`` if none match.
    """
    if not manifest_package:
        return []

    manifest_segments = manifest_package.split(".")
    # Require at least 2 matching segments (e.g. "com.example") to exclude third-party libs.
    min_common = min(2, len(manifest_segments))
    name_attr = f"{{{_ANDROID_NS}}}name"

    application = manifest_tree.getroot().find("application")
    if application is None:
        return [manifest_package]

    packages: set[str] = set()
    for child in application:
        # Strip namespace prefix (e.g. "{http://...}activity" -> "activity").
        tag = child.tag.split("}")[-1] if "}" in child.tag else child.tag
        if tag not in _COMPONENT_TAGS:
            continue
        raw_name = child.get(name_attr, "")
        if not raw_name:
            continue

        # Resolve shorthand names to fully-qualified class names.
        if raw_name.startswith("."):
            fq_name = manifest_package + raw_name  # ".MyActivity" -> "com.example.MyActivity"
        elif "." not in raw_name:
            fq_name = f"{manifest_package}.{raw_name}"  # "MyActivity" -> "com.example.MyActivity"
        else:
            fq_name = raw_name  # already fully qualified

        if "." not in fq_name:
            continue

        # Derive the package from the class name and count shared leading segments.
        pkg = fq_name.rsplit(".", 1)[0]
        pkg_segments = pkg.split(".")
        common = sum(1 for a, b in zip(manifest_segments, pkg_segments) if a == b)  # noqa: B905
        if common >= min_common:
            packages.add(pkg)

    if not packages:
        # No matching components found; fall back to the manifest package itself.
        return [manifest_package]

    return _remove_subpackages(sorted(packages))


def _remove_subpackages(packages: list[str]) -> list[str]:
    """Remove any package that is already covered by a shorter package in the list."""
    result: list[str] = []
    for pkg in packages:
        if not any(pkg.startswith(kept + ".") for kept in result):
            result.append(pkg)
    return result


def get_user_source_files(sources_dir: str, packages: list[str]) -> list[str]:
    """Return deduplicated paths to user-authored .java files under the given packages.

    Walks each package subtree in ``sources_dir``, skipping auto-generated files
    (``R.java``, ``BuildConfig.java``) and deduplicating when package prefixes overlap.
    """
    seen: set[str] = set()
    java_files: list[str] = []

    for package in packages:
        # Convert dot-separated package name to a filesystem path.
        package_dir = os.path.join(sources_dir, package.replace(".", os.sep))
        if not os.path.isdir(package_dir):
            continue
        for dirpath, _, filenames in os.walk(package_dir):
            for filename in filenames:
                if not filename.endswith(".java") or filename in _EXCLUDED_FILENAMES:
                    continue
                abs_path = os.path.join(dirpath, filename)
                # Guard against duplicates when package prefixes overlap.
                if abs_path not in seen:
                    seen.add(abs_path)
                    java_files.append(abs_path)

    return java_files
