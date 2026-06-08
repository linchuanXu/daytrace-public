"""Filter system packages, keeping only user-relevant ones."""

from typing import Optional


def is_user_app(
    package: str,
    system_prefixes: list[str],
    force_include: list[str],
    user_packages: Optional[list[str]] = None,
) -> bool:
    """Return True if this package should appear in the report."""
    if package in force_include:
        return True
    # If we have the third-party list from pm, use it as the primary filter
    if user_packages is not None:
        return package in user_packages
    # Fall back to prefix-based heuristic
    for prefix in system_prefixes:
        normalized = prefix.rstrip(".")
        if package == normalized or package.startswith(normalized + "."):
            return False
    return True


def filter_app_totals(
    totals: dict,
    system_prefixes: list[str],
    force_include: list[str],
    user_packages: Optional[list[str]] = None,
    min_seconds: int = 5,
) -> list[dict]:
    """Return sorted list of user apps with meaningful usage time."""
    result = []
    for pkg, data in totals.items():
        if not is_user_app(pkg, system_prefixes, force_include, user_packages):
            continue
        if data["seconds"] < min_seconds:
            continue
        result.append(data)
    result.sort(key=lambda x: x["seconds"], reverse=True)
    return result


def filter_stats(
    stats: list,
    system_prefixes: list[str],
    force_include: list[str],
    user_packages: Optional[list[str]] = None,
) -> list:
    return [
        s for s in stats
        if is_user_app(s.package, system_prefixes, force_include, user_packages)
        and s.total_used_seconds > 0
    ]
