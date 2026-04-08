"""Parses AndroidManifest.xml to extract APK metadata features."""

from xml.etree.ElementTree import Element

import defusedxml.ElementTree as ET

ANDROID_NS = "http://schemas.android.com/apk/res/android"


def _attr(element: Element, name: str) -> str | None:
    """Return an Android-namespaced attribute value, or None if absent."""
    return element.get(f"{{{ANDROID_NS}}}{name}")


def _is_user_component(name: str, package_name: str) -> bool:
    """Return True if a component name belongs to the app (not a third-party library)."""
    return name.startswith(".") or name.startswith(package_name)


def parse_manifest(manifest_path: str) -> dict:
    """Parse AndroidManifest.xml and return a dict of extracted metadata."""
    tree = ET.parse(manifest_path)
    root = tree.getroot()

    package_name = root.get("package", "")
    version_code = _attr(root, "versionCode") or ""
    version_name = _attr(root, "versionName") or ""
    compile_sdk_version = _attr(root, "compileSdkVersion") or ""

    uses_sdk = root.find("uses-sdk")
    min_sdk_version = _attr(uses_sdk, "minSdkVersion") if uses_sdk is not None else ""
    target_sdk_version = _attr(uses_sdk, "targetSdkVersion") if uses_sdk is not None else ""

    permissions = [_attr(el, "name") for el in root.findall("uses-permission") if _attr(el, "name")]

    features_used = [_attr(el, "name") for el in root.findall("uses-feature") if _attr(el, "name")]

    application = root.find("application")
    activities: list[str] = []
    services: list[str] = []
    receivers: list[str] = []
    providers: list[str] = []

    if application is not None:
        for tag, target_list in [
            ("activity", activities),
            ("service", services),
            ("receiver", receivers),
            ("provider", providers),
        ]:
            for el in application.findall(tag):
                name = _attr(el, "name") or ""
                if name and _is_user_component(name, package_name):
                    # Resolve relative names (starting with ".") to fully qualified names.
                    if name.startswith("."):
                        name = package_name + name
                    target_list.append(name)

    return {
        "package_name": package_name,
        "version_code": version_code,
        "version_name": version_name,
        "min_sdk_version": min_sdk_version,
        "target_sdk_version": target_sdk_version,
        "compile_sdk_version": compile_sdk_version,
        "permissions": permissions,
        "features_used": features_used,
        "activities": activities,
        "services": services,
        "receivers": receivers,
        "providers": providers,
    }
