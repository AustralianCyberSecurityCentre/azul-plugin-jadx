"""Finds user-authored Java source files in a JADX output directory."""

import os


def get_user_source_files(sources_dir: str, package_name: str) -> list[str]:
    """Return paths to all .java files belonging to the app's own package.

    JADX writes decompiled sources to a directory tree mirroring the Java
    package structure (e.g. ``sources/com/example/myapp/``).  This function
    locates that subtree and returns the absolute paths to every .java file
    within it, excluding third-party library code.

    Args:
        sources_dir: Absolute path to the ``sources/`` directory produced by JADX.
        package_name: The app's package name (e.g. ``com.example.myapp``).

    Returns:
        A list of absolute paths to .java files under the package subtree.
        Returns an empty list if the package directory does not exist.
    """
    package_rel_path = package_name.replace(".", "/")
    package_dir = os.path.join(sources_dir, package_rel_path)

    if not os.path.isdir(package_dir):
        return []

    java_files = []
    for dirpath, _, filenames in os.walk(package_dir):
        for filename in filenames:
            if filename.endswith(".java"):
                java_files.append(os.path.join(dirpath, filename))

    return java_files
