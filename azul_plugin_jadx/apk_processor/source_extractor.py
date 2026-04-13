"""Finds user-authored Java source files in a JADX output directory."""

import os

_ANDROID_NS = "http://schemas.android.com/apk/res/android"
_COMPONENT_TAGS = frozenset({"activity", "service", "receiver", "provider"})
_EXCLUDED_FILENAMES = frozenset({"R.java", "BuildConfig.java"})


def get_user_packages(manifest_tree, manifest_package: str) -> list[str]:
    """Return the source package prefixes that contain user-authored code.

    Parses component class names (activity, service, receiver, provider) from
    the manifest and keeps those whose package shares at least two leading
    segments with the manifest ``package`` attribute (e.g. both start with
    ``com.example``).  This excludes third-party libraries regardless of
    origin without requiring a maintained deny-list.

    Falls back to ``[manifest_package]`` when no matching components are found.

    Args:
        manifest_tree: A parsed ``ElementTree`` from the AndroidManifest.xml.
        manifest_package: The app's package name from the manifest ``package``
            attribute (e.g. ``com.sosauce.cutecalc``).

    Returns:
        A deduplicated, subpackage-collapsed list of source package prefixes.
    """
    if not manifest_package:
        return []

    manifest_segments = manifest_package.split(".")
    min_common = min(2, len(manifest_segments))
    name_attr = f"{{{_ANDROID_NS}}}name"

    application = manifest_tree.getroot().find("application")
    if application is None:
        return [manifest_package]

    packages: set[str] = set()
    for child in application:
        # Strip namespace from tag if present.
        tag = child.tag.split("}")[-1] if "}" in child.tag else child.tag
        if tag not in _COMPONENT_TAGS:
            continue
        raw_name = child.get(name_attr, "")
        if not raw_name:
            continue

        # Resolve relative names: ".Foo" or "Foo" (no dot) → fully qualified.
        if raw_name.startswith("."):
            fq_name = manifest_package + raw_name
        elif "." not in raw_name:
            fq_name = f"{manifest_package}.{raw_name}"
        else:
            fq_name = raw_name

        if "." not in fq_name:
            continue

        pkg = fq_name.rsplit(".", 1)[0]
        pkg_segments = pkg.split(".")
        common = sum(1 for a, b in zip(manifest_segments, pkg_segments) if a == b)
        if common >= min_common:
            packages.add(pkg)

    if not packages:
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
    """Return paths to all user-authored .java files under the given packages.

    Walks each package subtree under ``sources_dir`` and collects ``.java``
    files, excluding auto-generated files (``R.java``, ``BuildConfig.java``)
    and deduplicating paths when package prefixes overlap.

    Args:
        sources_dir: Absolute path to the ``sources/`` directory produced by JADX.
        packages: List of dot-separated package prefixes to walk (e.g.
            ``["com.sosauce.vanilla"]``).

    Returns:
        A deduplicated list of absolute paths to ``.java`` files.
    """
    seen: set[str] = set()
    java_files: list[str] = []

    for package in packages:
        package_dir = os.path.join(sources_dir, package.replace(".", os.sep))
        if not os.path.isdir(package_dir):
            continue
        for dirpath, _, filenames in os.walk(package_dir):
            for filename in filenames:
                if not filename.endswith(".java") or filename in _EXCLUDED_FILENAMES:
                    continue
                abs_path = os.path.join(dirpath, filename)
                if abs_path not in seen:
                    seen.add(abs_path)
                    java_files.append(abs_path)

    return java_files
