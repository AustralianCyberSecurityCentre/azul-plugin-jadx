"""Finds user-authored Java source files in a JADX output directory."""

import os

_EXCLUDED_FILENAMES = ["R.java", "BuildConfig.java"]


def get_user_source_files(sources_dir: str, packages: list[str]) -> list[str]:
    """Return all .java files from the application package directory recursively.

    Walks the package subtree and collects all .java files except auto-generated ones
    in ``_EXCLUDED_FILENAMES``.
    """
    if not packages:
        return []

    # Use the single package (the manifest package)
    package = packages[0]
    package_dir = os.path.join(sources_dir, package.replace(".", os.sep))
    if not os.path.isdir(package_dir):
        return []

    java_files: list[str] = []
    for dirpath, _, filenames in os.walk(package_dir):
        for filename in filenames:
            if filename.endswith(".java") and filename not in _EXCLUDED_FILENAMES:
                java_files.append(os.path.join(dirpath, filename))

    return sorted(java_files)
