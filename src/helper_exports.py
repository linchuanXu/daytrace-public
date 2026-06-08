"""Load and normalize Android helper app UsageStatsManager exports."""

from __future__ import annotations

import json
from datetime import date, datetime, time, timedelta
from pathlib import Path
from typing import Any, Optional

from .filter import is_user_app


HELPER_SOURCE = "helper_usage_stats"


def pull_helper_exports(adb: Any, remote_export_dir: str, local_export_dir: Path) -> None:
    """Pull helper export directory contents into the local cache root."""
    local_export_dir.mkdir(parents=True, exist_ok=True)
    remote_contents = remote_export_dir.rstrip("/") + "/."
    adb.pull(remote_contents, str(local_export_dir), timeout=120)


def helper_export_dates(export_root: Path) -> set[date]:
    """Return dates that have any helper export consumed by desktop sync."""
    if not export_root.exists():
        return set()

    dates: set[date] = set()
    for day_dir in export_root.iterdir():
        if not day_dir.is_dir():
            continue
        has_helper_export = (day_dir / "usage_stats.json").exists() or (
            day_dir / "daily_context.json"
        ).exists()
        if not has_helper_export:
            continue
        try:
            dates.add(date.fromisoformat(day_dir.name))
        except ValueError:
            continue
    return dates


def _fmt_seconds(seconds: int) -> str:
    if seconds >= 3600:
        h = seconds // 3600
        m = (seconds % 3600) // 60
        return f"{h}h {m:02d}m"
    if seconds >= 60:
        m = seconds // 60
        sec = seconds % 60
        return f"{m}m {sec:02d}s"
    return f"{seconds}s"


def _last_used_str(value: str) -> str:
    if not value:
        return ""
    try:
        return datetime.fromisoformat(value).strftime("%H:%M:%S")
    except ValueError:
        return ""


def _safe_int(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _load_json(path: Path) -> Optional[dict[str, Any]]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, UnicodeDecodeError):
        return None
    return data if isinstance(data, dict) else None


def _is_within_target_day(value: str, target_date: date, *, end_allowed: bool = False) -> bool:
    if not value:
        return True
    try:
        dt = datetime.fromisoformat(value)
    except ValueError:
        return True

    start = datetime.combine(target_date, time.min, tzinfo=dt.tzinfo)
    end = datetime.combine(target_date, time.max, tzinfo=dt.tzinfo)
    next_midnight = datetime.combine(
        target_date.fromordinal(target_date.toordinal() + 1),
        time.min,
        tzinfo=dt.tzinfo,
    )
    if end_allowed and dt == next_midnight:
        return True
    if end_allowed and dt.date() == target_date:
        return True
    return start <= dt <= end


def _has_cross_day_bucket(item: dict[str, Any], target_date: date) -> bool:
    first = str(item.get("first_time_stamp") or item.get("firstTimeStamp") or "")
    last = str(item.get("last_time_stamp") or item.get("lastTimeStamp") or "")
    return not (
        _is_within_target_day(first, target_date)
        and _is_within_target_day(last, target_date, end_allowed=True)
    )


_COMPLETE_STATUSES = frozenset({"ok", "empty_from_system"})
_QUERY_END_TOLERANCE = timedelta(seconds=1)


def helper_export_is_complete(
    helper_usage: Optional[dict[str, Any]],
    target_date: date,
    today: date,
) -> bool:
    """True when a past day's helper export queried through end-of-day."""
    if not helper_usage or target_date >= today:
        return False
    if helper_usage.get("source_status") not in _COMPLETE_STATUSES:
        return False

    query_end = str((helper_usage.get("query_range") or {}).get("end") or "")
    if not query_end:
        return False
    try:
        end_dt = datetime.fromisoformat(query_end)
    except ValueError:
        return False

    tzinfo = end_dt.tzinfo
    day_end = datetime.combine(
        target_date + timedelta(days=1),
        time.min,
        tzinfo=tzinfo,
    )
    return end_dt >= day_end - _QUERY_END_TOLERANCE


def load_helper_usage_for_date(
    export_root: Path,
    target_date: date,
    config: dict,
    user_packages: Optional[list[str]] = None,
) -> Optional[dict[str, Any]]:
    """Return normalized helper usage for a date, or None when absent/invalid."""
    path = export_root / target_date.isoformat() / "usage_stats.json"
    raw = _load_json(path)
    if not raw or raw.get("date") != target_date.isoformat():
        return None

    filter_cfg = config.get("filter", {})
    system_prefixes = filter_cfg.get("system_prefixes", [])
    force_include = filter_cfg.get("force_include", [])
    apps: list[dict[str, Any]] = []
    schema_version = _safe_int(raw.get("schema_version")) or 1
    skipped_cross_day_bucket_count = 0

    for item in raw.get("apps", []):
        if not isinstance(item, dict):
            continue
        if _has_cross_day_bucket(item, target_date):
            skipped_cross_day_bucket_count += 1
            continue
        package = str(item.get("package") or item.get("packageName") or "").strip()
        if not package:
            continue
        if not is_user_app(package, system_prefixes, force_include, user_packages):
            continue

        seconds = _safe_int(item.get("total_foreground_seconds", item.get("totalTimeInForeground")))
        visible_seconds = _safe_int(item.get("total_visible_seconds", item.get("totalTimeVisible")))
        if seconds <= 0:
            continue

        last_used = str(item.get("last_used") or item.get("lastTimeUsed") or "")
        sessions = _safe_int(item.get("launch_count", item.get("launchCount")))
        normalized_app = {
            "package": package,
            "name": str(item.get("name") or item.get("appName") or package),
            "seconds": seconds,
            "time_str": _fmt_seconds(seconds),
            "visible_seconds": visible_seconds,
            "visible_time_str": _fmt_seconds(visible_seconds),
            "sessions": sessions,
            "last_used": last_used,
            "last_used_str": _last_used_str(last_used),
            "source": str(item.get("source") or HELPER_SOURCE),
        }
        if schema_version >= 2 or "recorded_by_helper" in item:
            normalized_app["recorded_by_helper"] = bool(
                item.get("recorded_by_helper", raw.get("recorded_by_helper", False))
            )
        apps.append(normalized_app)

    apps.sort(key=lambda app: app["seconds"], reverse=True)
    query_range = raw.get("query_range") if isinstance(raw.get("query_range"), dict) else {}
    diagnostics = raw.get("diagnostics") if isinstance(raw.get("diagnostics"), dict) else {}
    if skipped_cross_day_bucket_count:
        diagnostics = dict(diagnostics)
        diagnostics["skipped_cross_day_bucket_count"] = skipped_cross_day_bucket_count

    return {
        "schema_version": schema_version,
        "date": target_date.isoformat(),
        "timezone": raw.get("timezone"),
        "source": HELPER_SOURCE,
        "raw_source": raw.get("source"),
        "source_status": raw.get("source_status", "ok" if apps else "empty_from_system"),
        "recorded_by_helper": bool(raw.get("recorded_by_helper", False)),
        "raw_system_has_data": bool(raw.get("raw_system_has_data", bool(apps))),
        "cache_has_data": bool(raw.get("cache_has_data", False)),
        "exported_at": raw.get("exported_at"),
        "query_range": query_range,
        "diagnostics": diagnostics,
        "has_data": bool(raw.get("has_data", bool(apps))),
        "app_count": len(apps),
        "apps": apps,
    }
