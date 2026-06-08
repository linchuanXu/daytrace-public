"""
Generate per-day Markdown + JSON reports from collected data.
"""

import json
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Optional
import pytz

from .app_names import get_app_name
from .parser import (
    ParsedUsageStats, ScreenSession, UsageEvent,
    build_screen_sessions, compute_app_totals,
    extract_notification_events, extract_media_events, extract_foreground_services,
)
from .filter import filter_app_totals, filter_stats
from .collectors.battery import BatteryStats
from .collectors.sms import collect_sms
from .collectors.calls import collect_calls
from .collectors.calendar_col import collect_calendar
from .collectors.wifi import collect_wifi
from .collectors.notifications import parse_current_notifications
from .fs_utils import remove_tree_best_effort
from .helper_exports import helper_export_is_complete


# ── Helpers ──────────────────────────────────────────────────────────────────

def _fmt_seconds(s: int) -> str:
    if s >= 3600:
        h = s // 3600
        m = (s % 3600) // 60
        return f"{h}h {m:02d}m"
    elif s >= 60:
        m = s // 60
        sec = s % 60
        return f"{m}m {sec:02d}s"
    else:
        return f"{s}s"


def _iso(dt: Optional[datetime]) -> Optional[str]:
    return dt.isoformat() if dt else None


def _parse_helper_context_time(value: str, tz: pytz.BaseTzInfo) -> Optional[datetime]:
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(value)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = tz.localize(dt)
    return dt


def _is_recent_report_day(target_date: date, tz: pytz.BaseTzInfo) -> bool:
    today = datetime.now(tz).date()
    return target_date >= today - timedelta(days=1)


def _locations_for_report_day(
    helper_context: Optional[dict],
    target_date: date,
    tz: pytz.BaseTzInfo,
) -> tuple[list[dict], list[dict]]:
    """Split helper locations into (archived on target_date, export-time snapshots)."""
    if not isinstance(helper_context, dict):
        return [], []

    archived_on_day: list[dict] = []
    for item in helper_context.get("archived_location_snapshots") or []:
        if not isinstance(item, dict):
            continue
        dt = _parse_helper_context_time(str(item.get("time") or ""), tz)
        if dt and dt.date() == target_date:
            archived_on_day.append(item)

    export_snapshots: list[dict] = []
    if _is_recent_report_day(target_date, tz):
        for item in helper_context.get("location_snapshots") or []:
            if isinstance(item, dict):
                export_snapshots.append(item)

    return archived_on_day, export_snapshots


def _interval_apps(stats_list, min_seconds: int = 30) -> list:
    return [
        {"package": s.package, "name": s.name,
         "seconds": s.total_used_seconds,
         "time_str": _fmt_seconds(s.total_used_seconds),
         "launches": s.launches,
         "last_used": _iso(s.last_used),
         "last_used_str": s.last_used.strftime("%Y-%m-%d %H:%M:%S") if s.last_used else ""}
        for s in stats_list
        if s.total_used_seconds >= min_seconds
    ]


def _historical_app_evidence(target_date: date, buckets: list[tuple[str, list]]) -> list[dict]:
    """
    Best pure-ADB historical signal: app stats whose lastTimeUsed falls on target_date.
    This confirms the app was used that day, but the duration is bucket-level cumulative,
    not that day's exact duration.
    """
    evidence: dict[str, dict] = {}
    priority = {"daily": 0, "weekly": 1, "monthly": 2, "yearly": 3}
    for bucket_name, stats_list in buckets:
        for s in stats_list:
            if not s.last_used or s.last_used.date() != target_date:
                continue
            old = evidence.get(s.package)
            if old and priority[old["bucket"]] <= priority[bucket_name]:
                continue
            evidence[s.package] = {
                "package": s.package,
                "name": s.name,
                "bucket": bucket_name,
                "last_used": _iso(s.last_used),
                "last_used_str": s.last_used.strftime("%H:%M:%S"),
                "period_seconds": s.total_used_seconds,
                "period_time_str": _fmt_seconds(s.total_used_seconds),
                "period_launches": s.launches,
            }
    return sorted(evidence.values(), key=lambda x: (x["last_used"] or "", -x["period_seconds"]))


def _build_interval_stats(parsed, daily, weekly, monthly, yearly) -> dict:
    def _range(start, end):
        if start and end:
            return {"start": _iso(start), "end": _iso(end)}
        return {}

    return {
        "daily": {
            **_range(parsed.daily_stats[0].time_range_start if daily else None,
                     parsed.daily_stats[0].time_range_end if daily else None),
            "apps": _interval_apps(daily, min_seconds=30),
        },
        "weekly": {
            **_range(parsed.weekly_stats[0].time_range_start if weekly else None,
                     parsed.weekly_stats[0].time_range_end if weekly else None),
            "apps": _interval_apps(weekly, min_seconds=120),
        },
        "monthly": {
            **_range(parsed.monthly_stats[0].time_range_start if monthly else None,
                     parsed.monthly_stats[0].time_range_end if monthly else None),
            "apps": _interval_apps(monthly, min_seconds=300),
        },
        "yearly": {
            **_range(parsed.yearly_stats[0].time_range_start if yearly else None,
                     parsed.yearly_stats[0].time_range_end if yearly else None),
            "apps": _interval_apps(yearly, min_seconds=600),
        },
    }


def _aggregate_fg_services(fg_services: list) -> list:
    """Aggregate foreground service events to per-app counts instead of per-event rows."""
    counts: dict[str, int] = {}
    for e in fg_services:
        pkg = e["package"]
        counts[pkg] = counts.get(pkg, 0) + 1
    return [
        {"package": pkg, "name": get_app_name(pkg), "events": cnt}
        for pkg, cnt in sorted(counts.items(), key=lambda x: -x[1])
    ]


def _helper_context_detail_lines(
    helper_context: Optional[dict],
    target_date: date,
    tz: pytz.BaseTzInfo,
) -> list[str]:
    """Render bounded, human-readable details from Helper daily_context.json."""
    if not isinstance(helper_context, dict):
        return []

    lines: list[str] = ["## Helper 上下文明细", ""]
    wrote = False
    archived_locations, export_snapshots = _locations_for_report_day(
        helper_context, target_date, tz
    )

    def add_items(title: str, items: list, limit: int, render):
        nonlocal wrote
        if not items:
            return
        lines.append(f"### {title}")
        lines.append("")
        for item in items[:limit]:
            if isinstance(item, dict):
                lines.append(f"- {render(item)}")
        if len(items) > limit:
            lines.append(f"- 还有 {len(items) - limit} 条未展开")
        lines.append("")
        wrote = True

    media = helper_context.get("media", {}) if isinstance(helper_context.get("media"), dict) else {}
    add_items(
        "媒体文件",
        media.get("items", []) if isinstance(media.get("items"), list) else [],
        20,
        lambda item: (
            f"`{item.get('time', '')}` {item.get('type', '')} "
            f"{item.get('display_name', '')} [{item.get('relative_path', '')}]"
        ),
    )

    def render_location(item: dict) -> str:
        return (
            f"`{item.get('time', '')}` {item.get('reason') or item.get('provider', '')} "
            f"{item.get('latitude')}, {item.get('longitude')} "
            f"±{item.get('accuracy_m', '')}m"
        )

    add_items("位置记录（当日归档）", archived_locations, 50, render_location)
    if export_snapshots:
        add_items("位置快照（同步时）", export_snapshots, 10, render_location)

    files = helper_context.get("files", {}) if isinstance(helper_context.get("files"), dict) else {}
    add_items(
        "文件活动",
        files.get("items", []) if isinstance(files.get("items"), list) else [],
        20,
        lambda item: (
            f"`{item.get('time', '')}` {item.get('name', '')} "
            f"[{item.get('relative_path', '')}] {item.get('size_bytes', '')} bytes"
        ),
    )

    app_changes = helper_context.get("app_changes", {}) if isinstance(helper_context.get("app_changes"), dict) else {}
    add_items(
        "App 变化",
        app_changes.get("items", []) if isinstance(app_changes.get("items"), list) else [],
        20,
        lambda item: (
            f"{item.get('event', '')} {item.get('name', '')} "
            f"`{item.get('package', '')}` {item.get('version_name', '')}"
        ),
    )

    notifications = helper_context.get("notification_history", {}) if isinstance(helper_context.get("notification_history"), dict) else {}
    add_items(
        "通知历史",
        notifications.get("items", []) if isinstance(notifications.get("items"), list) else [],
        30,
        lambda item: (
            f"`{item.get('time', '')}` {item.get('event', '')} "
            f"`{item.get('package', '')}` {item.get('title', '')} {item.get('text', '')}"
        ),
    )

    accessibility = helper_context.get("accessibility_events", {}) if isinstance(helper_context.get("accessibility_events"), dict) else {}
    add_items(
        "无障碍事件",
        accessibility.get("items", []) if isinstance(accessibility.get("items"), list) else [],
        30,
        lambda item: (
            f"`{item.get('time', '')}` `{item.get('package', '')}` "
            f"{item.get('event_type', '')} {item.get('text', '')} {item.get('view_id', '')}"
        ),
    )

    diagnostics = helper_context.get("diagnostics", {}) if isinstance(helper_context.get("diagnostics"), dict) else {}
    if diagnostics:
        lines.append("### Helper 模块诊断")
        lines.append("")
        for key in sorted(diagnostics):
            value = diagnostics[key]
            if isinstance(value, dict):
                status = value.get("status", "unknown")
                count = value.get("count")
                suffix = f"，count={count}" if count is not None else ""
                lines.append(f"- {key}: {status}{suffix}")
            else:
                lines.append(f"- {key}: {value}")
        lines.append("")
        wrote = True

    return lines if wrote else []


def _coverage_summary(
    day_start: datetime,
    day_end: datetime,
    intervals: list[tuple[datetime, datetime]],
) -> dict:
    """Merge coverage intervals and return honest per-day usagestats coverage."""
    if not intervals:
        return {
            "start": None,
            "end": None,
            "covered_seconds": 0,
            "coverage_ratio": 0.0,
            "coverage_pct": 0.0,
            "is_full_day": False,
            "label": "无 usagestats 事件覆盖",
        }

    clipped = sorted(
        (max(a, day_start), min(b, day_end))
        for a, b in intervals
        if min(b, day_end) > max(a, day_start)
    )
    merged: list[tuple[datetime, datetime]] = []
    for a, b in clipped:
        if not merged or a > merged[-1][1]:
            merged.append((a, b))
        else:
            merged[-1] = (merged[-1][0], max(merged[-1][1], b))

    covered = int(sum((b - a).total_seconds() for a, b in merged))
    total = int((day_end - day_start).total_seconds())
    ratio = covered / total if total else 0.0
    is_full = ratio >= 0.995
    first = merged[0][0] if merged else None
    last = merged[-1][1] if merged else None
    if is_full:
        label = "完整自然日"
    elif first and last:
        label = f"部分覆盖：{first.strftime('%H:%M')}–{last.strftime('%H:%M')}（{ratio * 100:.1f}%）"
    else:
        label = "无 usagestats 事件覆盖"
    return {
        "start": _iso(first),
        "end": _iso(last),
        "covered_seconds": covered,
        "coverage_ratio": round(ratio, 4),
        "coverage_pct": round(ratio * 100, 1),
        "is_full_day": is_full,
        "label": label,
    }


# ── Main build function ───────────────────────────────────────────────────────

def build_day_report(
    target_date: date,
    is_complete: bool,
    device_info: dict,
    raw: dict,          # {usagestats, sms, calls, calendar, wifi, battery, batterystats, notification}
    config: dict,
    tz: pytz.BaseTzInfo,
    user_packages: list[str],
    usage_events: Optional[list[UsageEvent]] = None,
    usage_coverage: Optional[list[tuple[datetime, datetime]]] = None,
    helper_usage: Optional[dict] = None,
    helper_context: Optional[dict] = None,
) -> tuple[dict, str]:
    """
    Returns (summary_dict, markdown_str).
    raw contains the raw ADB dump strings keyed by source name.
    """
    sys_prefixes = config["filter"]["system_prefixes"]
    force_include = config["filter"]["force_include"]

    # ── Parse usage stats ────────────────────────────────────────────────────
    from .parser import parse_usagestats
    parsed = parse_usagestats(raw.get("usagestats", ""), tz)

    # Filter events to target_date
    day_start = tz.localize(datetime(target_date.year, target_date.month, target_date.day, 0, 0, 0))
    day_end   = day_start + timedelta(days=1)
    source_events = usage_events if usage_events is not None else parsed.events
    day_events = [e for e in source_events if day_start <= e.time < day_end]
    coverage = _coverage_summary(day_start, day_end, usage_coverage or [])
    is_complete = bool(coverage["is_full_day"])
    today = datetime.now(tz).date()
    if not is_complete and helper_usage:
        is_complete = helper_export_is_complete(helper_usage, target_date, today)
    is_today = target_date == today

    screen_sessions = build_screen_sessions(day_events)
    app_totals_raw  = compute_app_totals(screen_sessions)
    app_totals      = filter_app_totals(app_totals_raw, sys_prefixes, force_include, user_packages)
    # Add names
    for a in app_totals:
        a["name"] = get_app_name(a["package"])

    notif_events = extract_notification_events(day_events)
    media_events = extract_media_events(day_events)
    fg_services  = extract_foreground_services(day_events)

    # Notification push counts per app
    notif_counts: dict[str, int] = {}
    for n in notif_events:
        if n["type"] == "push":
            notif_counts[n["package"]] = notif_counts.get(n["package"], 0) + 1

    # ── Parse persistent sources (always available) ───────────────────────────
    sms_messages = collect_sms(raw.get("sms", ""), target_date, tz,
                               raw_mms=raw.get("mms", ""),
                               raw_mms_addr=raw.get("mms_addr", ""))
    call_records  = collect_calls(raw.get("calls", ""), target_date, tz)
    cal_events    = collect_calendar(raw.get("calendar", ""), target_date, tz)
    wifi_conns    = collect_wifi(raw.get("wifi", ""), target_date, tz)
    live_notifs   = parse_current_notifications(raw.get("notification", ""), tz)
    # Only show live notifications that are from today
    live_notifs   = [n for n in live_notifs if n["time"].date() == target_date]

    # ── Battery ───────────────────────────────────────────────────────────────
    from .collectors.battery import parse_battery_stats
    batt = parse_battery_stats(raw.get("batterystats", ""), raw.get("battery", ""))

    # ── Screen summary ────────────────────────────────────────────────────────
    total_screen_seconds = sum(s.duration_seconds for s in screen_sessions)
    unlock_count = len(screen_sessions)
    first_unlock = screen_sessions[0].start if screen_sessions else None
    last_lock    = next((s.end for s in reversed(screen_sessions) if s.end), None)

    # batterystats screen_on is a cumulative total since last reset — only use it
    # as a rough sanity check for today (is_complete), never for historical days.
    if not total_screen_seconds and is_complete and batt.screen_on_seconds:
        total_screen_seconds = batt.screen_on_seconds

    # ── Interval stats (daily/weekly/monthly/yearly totalTimeUsed) ───────────
    def _filter_interval(stats_list):
        filtered = filter_stats(stats_list, sys_prefixes, force_include, user_packages)
        for s in filtered:
            s.name = get_app_name(s.package)  # type: ignore[attr-defined]
        return filtered

    daily_stats_filtered   = _filter_interval(parsed.daily_stats)
    weekly_stats_filtered  = _filter_interval(parsed.weekly_stats)
    monthly_stats_filtered = _filter_interval(parsed.monthly_stats)
    yearly_stats_filtered  = _filter_interval(parsed.yearly_stats)
    historical_app_evidence = _historical_app_evidence(
        target_date,
        [
            ("daily", daily_stats_filtered),
            ("weekly", weekly_stats_filtered),
            ("monthly", monthly_stats_filtered),
            ("yearly", yearly_stats_filtered),
        ],
    )

    # For TODAY only: merge OS daily_stats into app_totals.
    # daily_stats covers only the current partial day (since last stats flush ~11am).
    # Applying it to yesterday would mix today's partial stats into the wrong day.
    if is_today and daily_stats_filtered:
        daily_map = {s.package: s for s in daily_stats_filtered}
        for a in app_totals:
            ds = daily_map.get(a["package"])
            if ds and ds.total_used_seconds > a["seconds"]:
                a["seconds"] = ds.total_used_seconds
        # Also add apps that appear in daily_stats but were missed by event parsing
        event_pkgs = {a["package"] for a in app_totals}
        for ds in daily_stats_filtered:
            if ds.package not in event_pkgs and ds.total_used_seconds >= 30:
                app_totals.append({
                    "package": ds.package,
                    "name": ds.name,
                    "seconds": ds.total_used_seconds,
                    "sessions": ds.launches,
                })
        app_totals.sort(key=lambda a: -a["seconds"])

    # ── Build summary dict ────────────────────────────────────────────────────
    summary = {
        "date": target_date.isoformat(),
        "is_complete": is_complete,
        "device": device_info,
        "sync_time": datetime.now(tz).isoformat(),
        "usagestats_coverage": coverage,
        "screen": {
            "total_seconds": total_screen_seconds,
            "total_str": (
                _fmt_seconds(total_screen_seconds)
                if (is_complete or total_screen_seconds > 0)
                else "—（无数据）"
            ),
            "unlock_count": unlock_count,
            "first_unlock": _iso(first_unlock),
            "last_lock": _iso(last_lock),
            "sessions": [
                {
                    "start": _iso(s.start),
                    "end": _iso(s.end),
                    "duration_seconds": s.duration_seconds,
                    "apps": [
                        {
                            "package": a["package"],
                            "name": get_app_name(a["package"]),
                            "seconds": a["seconds"],
                        }
                        for a in s.app_timeline
                    ],
                }
                for s in screen_sessions
            ],
        },
        # Battery: only include live stats for today's report.
        # For historical days we have no record of that day's battery state —
        # storing today's level/charging against a past date would be misleading.
        "battery": {
            "current_level": batt.current_level if is_today else None,
            "charging": batt.charging if is_today else None,
            "temperature_c": batt.temperature_celsius if is_today else None,
            "screen_on_seconds": batt.screen_on_seconds if is_today else None,
            "discharge_mah": batt.estimated_mah if is_today else None,
            "brightness": batt.brightness if is_today else None,
            "cellular_rx_mb": round(batt.cellular_rx_mb, 2) if is_today else None,
            "cellular_tx_mb": round(batt.cellular_tx_mb, 2) if is_today else None,
            "wifi_rx_mb": round(batt.wifi_rx_mb, 2) if is_today else None,
            "wifi_tx_mb": round(batt.wifi_tx_mb, 2) if is_today else None,
        },
        "apps": [
            {
                "package": a["package"],
                "name": a["name"],
                "seconds": a["seconds"],
                "time_str": _fmt_seconds(a["seconds"]),
                "sessions": a["sessions"],
            }
            for a in app_totals
        ],
        "helper_usage_stats": helper_usage or {
            "date": target_date.isoformat(),
            "source": "helper_usage_stats",
            "has_data": False,
            "app_count": 0,
            "apps": [],
        },
        "helper_daily_context": helper_context or {
            "date": target_date.isoformat(),
            "source": "helper_daily_context",
            "media": {"photos_count": 0, "videos_count": 0, "audio_count": 0, "items": []},
            "location_snapshots": [],
            "archived_location_snapshots": [],
            "device_state": {},
            "files": {"created_or_modified_count": 0, "items": []},
            "app_changes": {"installed_count": 0, "updated_count": 0, "items": []},
            "communication_backup": {
                "sms_count": 0,
                "call_count": 0,
                "calendar_count": 0,
                "contacts_updated_count": 0,
            },
            "notification_history": {"count": 0, "items": []},
            "accessibility_events": {"count": 0, "items": []},
            "diagnostics": {},
        },
        "historical_app_evidence": historical_app_evidence,
        "notifications_push": [
            {"package": pkg, "name": get_app_name(pkg), "count": cnt}
            for pkg, cnt in sorted(notif_counts.items(), key=lambda x: -x[1])
        ],
        "live_notifications": [
            {"time": _iso(n["time"]), "time_str": n["time_str"],
             "package": n["package"], "name": get_app_name(n["package"]),
             "title": n.get("title", ""),
             "text": n.get("text", ""),
             "display": n.get("display", n.get("text", ""))}
            for n in live_notifs
        ],
        "media_events": [
            {"time": _iso(e["time"]), "time_str": e["time"].strftime("%H:%M:%S"),
             "package": e["package"], "name": get_app_name(e["package"]),
             "action": e["action"]}
            for e in media_events
        ],
        "foreground_services": _aggregate_fg_services(fg_services),
        "sms": [
            {"time": _iso(m["time"]), "time_str": m["time_str"],
             "address": m["address"], "body": m["body"],
             "type": m["type"], "kind": m.get("kind", "SMS"), "read": m["read"]}
            for m in sms_messages
        ],
        "calls": [
            {"time": _iso(c["time"]), "time_str": c["time_str"],
             "number": c["number"], "name": c["name"],
             "location": c["location"], "type": c["type"],
             "duration_seconds": c["duration_seconds"],
             "duration_str": c["duration_str"]}
            for c in call_records
        ],
        "calendar": [
            {"start": _iso(e["start"]), "end": _iso(e["end"]),
             "start_str": e["start_str"], "end_str": e["end_str"],
             "title": e["title"], "description": e["description"],
             "location": e["location"], "all_day": e["all_day"]}
            for e in cal_events
        ],
        "wifi": [
            {"time": _iso(w["time"]), "time_str": w["time_str"],
             "ssid": w["ssid"], "event": w["event"]}
            for w in wifi_conns
        ],
        # Interval cumulative stats — useful for historical gap days
        "interval_stats": _build_interval_stats(
            parsed, daily_stats_filtered, weekly_stats_filtered,
            monthly_stats_filtered, yearly_stats_filtered,
        ),
    }

    # ── Build Markdown ─────────────────────────────────────────────────────────
    md = _build_markdown(
        target_date, is_complete, device_info, summary,
        screen_sessions, app_totals, sms_messages, call_records,
        cal_events, wifi_conns, live_notifs, notif_counts,
        media_events, fg_services, batt, tz,
    )

    return summary, md


# ── Markdown renderer ─────────────────────────────────────────────────────────

def _build_markdown(
    target_date, is_complete, device_info, summary,
    screen_sessions, app_totals, sms_messages, call_records,
    cal_events, wifi_conns, live_notifs, notif_counts,
    media_events, fg_services, batt, tz,
) -> str:
    lines: list[str] = []

    # Frontmatter
    lines += [
        "---",
        f"date: {target_date.isoformat()}",
        f"device: {device_info.get('display', 'Unknown')}",
        f"sync_time: {datetime.now(tz).strftime('%Y-%m-%d %H:%M:%S')}",
        f"is_complete: {'true' if is_complete else 'false'}",
        f"usagestats_coverage: {summary['usagestats_coverage']['label']}",
        f"screen_total: {summary['screen']['total_str'] if (is_complete or summary['screen']['total_seconds'] > 0) else '—（无数据）'}",
        f"unlocks: {summary['screen']['unlock_count']}",
        f"sms_count: {len(sms_messages)}",
        f"call_count: {len(call_records)}",
        "---",
        "",
    ]

    # Title
    lines.append(f"# {target_date.strftime('%Y年%m月%d日')}  手机使用报告")
    lines.append("")

    cov = summary["usagestats_coverage"]
    if is_complete and not cov.get("is_full_day"):
        lines.append(
            "> ℹ️ **完整日标记来自 Helper 导出**（已覆盖自然日）；"
            "ADB usagestats 时间轴仍可能不完整，App 排行以各自数据源为准。"
        )
        lines.append("")
    elif not is_complete:
        if cov["covered_seconds"] > 0:
            lines.append(f"> ⚠️ **usagestats 部分覆盖** — {cov['label']}。屏幕时间、解锁次数、App 时间轴只代表已覆盖时段，不能当全天。")
        else:
            lines.append("> ⚠️ **usagestats 无精确事件覆盖** — 此日没有本地缓存到的 App/屏幕时间轴；下方会尽量展示 ADB 能拿到的周期聚合 App 数据、短信、通话、日历等。")
        lines.append("")

    # ── 概览 ─────────────────────────────────────────────────────────────────
    lines.append("## 📊 概览")
    lines.append("")
    lines.append("| 项目 | 数值 |")
    lines.append("|------|------|")
    scr = summary["screen"]
    lines.append(f"| usagestats 覆盖 | {summary['usagestats_coverage']['label']} |")
    if scr["total_seconds"] > 0:
        lines.append(f"| 屏幕总时长 | {scr['total_str']} |")
        lines.append(f"| 解锁次数 | {scr['unlock_count']} 次 |")
        if scr["first_unlock"]:
            first_dt = datetime.fromisoformat(scr["first_unlock"])
            lines.append(f"| 第一次解锁 | {first_dt.strftime('%H:%M')} |")
        if scr["last_lock"]:
            last_dt = datetime.fromisoformat(scr["last_lock"])
            lines.append(f"| 最后锁屏 | {last_dt.strftime('%H:%M')} |")
    is_today = target_date == datetime.now(tz).date()
    if is_today:
        if batt.current_level >= 0:
            charging_mark = " 🔌充电中" if batt.charging else ""
            lines.append(f"| 当前电量 | {batt.current_level}%{charging_mark} |")
        if batt.estimated_mah:
            lines.append(f"| 本次放电 | {batt.estimated_mah} mAh |")
        if batt.temperature_celsius:
            lines.append(f"| 机身温度 | {batt.temperature_celsius:.1f}°C |")
    lines.append(f"| 短信 | {len(sms_messages)} 条 |")
    lines.append(f"| 通话 | {len(call_records)} 次 |")
    lines.append(f"| 日历事件 | {len(cal_events)} 个 |")
    if is_today:
        if batt.cellular_rx_mb or batt.cellular_tx_mb:
            lines.append(f"| 蜂窝流量 | ↓{batt.cellular_rx_mb:.1f}MB / ↑{batt.cellular_tx_mb:.1f}MB |")
        if batt.wifi_rx_mb or batt.wifi_tx_mb:
            lines.append(f"| WiFi 流量 | ↓{batt.wifi_rx_mb:.1f}MB / ↑{batt.wifi_tx_mb:.1f}MB |")
    lines.append("")

    # ── App 使用排行 ─────────────────────────────────────────────────────────
    if app_totals:
        lines.append("## 📱 App 使用排行")
        if not is_complete:
            lines.append("")
            lines.append("> 此排行仅统计 usagestats 已覆盖时段，不代表全天。")
        lines.append("")
        lines.append("| # | App | 时长 | 打开次数 |")
        lines.append("|---|-----|------|---------|")
        for i, a in enumerate(app_totals[:20], 1):
            lines.append(f"| {i} | {a['name']} | {_fmt_seconds(a['seconds'])} | {a['sessions']} 次 |")
        lines.append("")

    helper_usage = summary.get("helper_usage_stats", {})
    helper_apps = helper_usage.get("apps", [])
    if helper_apps and not app_totals:
        lines.append("## 📱 App 使用排行（来自手机端 UsageStatsManager）")
        lines.append("")
        lines.append("> 这些数据来自手机端 Helper App 导出的每日聚合，只表示系统保存的当天 App 汇总，不是精确时间轴。")
        lines.append("")
        lines.append("| # | App | 时长 | 打开次数 | 最后使用 |")
        lines.append("|---|-----|------|---------|----------|")
        for i, app in enumerate(helper_apps[:20], 1):
            sessions = app.get("sessions")
            sessions_str = f"{sessions} 次" if sessions else "未知"
            lines.append(
                f"| {i} | {app['name']} | {app['time_str']} | "
                f"{sessions_str} | {app.get('last_used_str', '')} |"
            )
        lines.append("")

    helper_status = helper_usage.get("source_status")
    helper_diag = helper_usage.get("diagnostics", {})
    helper_notes = helper_diag.get("export_notes", []) if isinstance(helper_diag, dict) else []
    if helper_usage and not helper_apps and helper_status:
        lines.append("## Helper App 导出诊断")
        lines.append("")
        status_labels = {
            "ok": "有每日 App 聚合数据",
            "cached_only": "系统查询为空，使用 Helper 本地缓存",
            "empty_from_system": "Helper 已检查，但 Android 没有返回当天 App 记录",
            "permission_missing": "导出时缺少使用情况访问权限",
            "query_failed": "导出时系统查询失败",
        }
        lines.append(f"- 状态：{status_labels.get(helper_status, helper_status)}")
        if isinstance(helper_diag, dict):
            if "queried_at" in helper_diag:
                lines.append(f"- 查询时间：{helper_diag['queried_at']}")
            if "raw_app_count" in helper_diag:
                lines.append(f"- 系统返回 App 数：{helper_diag['raw_app_count']}")
            if "exported_app_count" in helper_diag:
                lines.append(f"- 导出 App 数：{helper_diag['exported_app_count']}")
        for note in helper_notes:
            lines.append(f"- 说明：{note}")
        lines.append("")

    evidence = summary.get("historical_app_evidence", [])
    if evidence and not is_complete:
        lines.append("## 🧭 当天 App 使用线索（ADB 聚合）")
        lines.append("")
        lines.append("> 这些来自系统 usagestats 聚合的 `lastTimeUsed`。可确认这些 App 的最后一次使用落在当天；时长是所在统计周期累计值，不等于当天精确用时。")
        lines.append("")
        lines.append("| 时间 | App | 统计周期 | 周期累计用时 | 周期打开次数 |")
        lines.append("|------|-----|----------|--------------|--------------|")
        bucket_names = {
            "daily": "日",
            "weekly": "周",
            "monthly": "月",
            "yearly": "年",
        }
        for item in evidence[:25]:
            lines.append(
                f"| {item['last_used_str']} | {item['name']} | "
                f"{bucket_names.get(item['bucket'], item['bucket'])} | "
                f"{item['period_time_str']} | {item['period_launches']} 次 |"
            )
        lines.append("")

    helper_context = summary.get("helper_daily_context", {})
    context_media = helper_context.get("media", {}) if isinstance(helper_context, dict) else {}
    archived_locations, export_snapshots = _locations_for_report_day(
        helper_context if isinstance(helper_context, dict) else None,
        target_date,
        tz,
    )
    context_device = helper_context.get("device_state", {}) if isinstance(helper_context, dict) else {}
    show_live_device_state = _is_recent_report_day(target_date, tz)
    context_files = helper_context.get("files", {}) if isinstance(helper_context, dict) else {}
    context_apps = helper_context.get("app_changes", {}) if isinstance(helper_context, dict) else {}
    context_comm = helper_context.get("communication_backup", {}) if isinstance(helper_context, dict) else {}
    context_notifications = helper_context.get("notification_history", {}) if isinstance(helper_context, dict) else {}
    context_accessibility = helper_context.get("accessibility_events", {}) if isinstance(helper_context, dict) else {}
    photos_count = int(context_media.get("photos_count") or 0)
    videos_count = int(context_media.get("videos_count") or 0)
    audio_count = int(context_media.get("audio_count") or 0)
    files_count = int(context_files.get("created_or_modified_count") or 0)
    installed_count = int(context_apps.get("installed_count") or 0)
    updated_count = int(context_apps.get("updated_count") or 0)
    notification_count = int(context_notifications.get("count") or 0)
    accessibility_count = int(context_accessibility.get("count") or 0)
    backup_counts = [
        int(context_comm.get("sms_count") or 0),
        int(context_comm.get("call_count") or 0),
        int(context_comm.get("calendar_count") or 0),
        int(context_comm.get("contacts_updated_count") or 0),
    ]
    archived_location_count = len(archived_locations)
    if photos_count or videos_count or audio_count or archived_location_count or export_snapshots or (show_live_device_state and context_device) or files_count or installed_count or updated_count or any(backup_counts) or notification_count or accessibility_count:
        lines.append("## 🧩 Helper 上下文补强")
        lines.append("")
        if photos_count or videos_count:
            lines.append(f"- 媒体：照片 {photos_count} 张，视频 {videos_count} 段")
        if audio_count:
            lines.append(f"- 音频：音频/录音 {audio_count} 个")
        if files_count:
            lines.append(f"- 文件：文件新增/修改 {files_count} 个")
        if installed_count or updated_count:
            lines.append(f"- App 变化：App 安装 {installed_count} 个，更新 {updated_count} 个")
        if any(backup_counts):
            lines.append(
                f"- APK 备份源：短信 {backup_counts[0]} 条，通话 {backup_counts[1]} 次，"
                f"日历 {backup_counts[2]} 个，联系人更新 {backup_counts[3]} 个"
            )
        if notification_count:
            lines.append(f"- 通知监听：通知历史 {notification_count} 条")
        if accessibility_count:
            lines.append(f"- 无障碍归档：无障碍事件 {accessibility_count} 条")
        if archived_location_count:
            lines.append(f"- 位置归档：当日归档位置 {archived_location_count} 条")
        if export_snapshots:
            loc = export_snapshots[0]
            lat = loc.get("latitude")
            lon = loc.get("longitude")
            provider = loc.get("provider", "")
            accuracy = loc.get("accuracy_m")
            if lat is not None and lon is not None:
                acc = f"，精度 {accuracy}m" if accuracy is not None else ""
                lines.append(f"- 位置快照（同步时）：{provider} {float(lat):.6f}, {float(lon):.6f}{acc}")
        if show_live_device_state:
            wifi_ssid = context_device.get("wifi_ssid")
            battery_level = context_device.get("battery_level")
            available_storage = context_device.get("available_storage_mb")
            device_bits = []
            if battery_level is not None:
                charging = "充电中" if context_device.get("charging") else "未充电"
                device_bits.append(f"电量 {battery_level}%（{charging}）")
            if wifi_ssid:
                device_bits.append(f"WiFi {wifi_ssid}")
            if available_storage is not None:
                device_bits.append(f"可用存储 {available_storage}MB")
            if device_bits:
                lines.append(f"- 设备状态（同步时）：{'；'.join(device_bits)}")
        lines.append("")

        detail_lines = _helper_context_detail_lines(helper_context, target_date, tz)
        if detail_lines:
            lines.extend(detail_lines)

    # ── 屏幕使用时间轴 ────────────────────────────────────────────────────────
    if screen_sessions:
        lines.append("## 🕐 屏幕使用时间轴")
        if not is_complete:
            lines.append("")
            lines.append("> 这不是全天时间轴，只是已缓存到的 usagestats 事件片段。")
        lines.append("")
        for sess in screen_sessions:
            start_str = sess.start.strftime("%H:%M:%S")
            if sess.end:
                end_str = sess.end.strftime("%H:%M:%S")
                header = f"### {start_str} – {end_str}（{_fmt_seconds(sess.duration_seconds)}）"
            else:
                header = f"### {start_str} – （进行中）"
            lines.append(header)
            lines.append("")
            lines.append(f"- 🔓 `{start_str}` 解锁")
            for app in sess.app_timeline:
                pkg = app["package"]
                name = get_app_name(pkg)
                app_start = app["start"].strftime("%H:%M:%S")
                lines.append(f"- 📱 `{app_start}` **{name}** → {_fmt_seconds(app['seconds'])}")
            if sess.end:
                lines.append(f"- 🔒 `{end_str}` 锁屏")
            lines.append("")

    # ── 媒体播放 ─────────────────────────────────────────────────────────────
    if media_events:
        lines.append("## 🎵 媒体播放记录")
        lines.append("")
        # Group consecutive start-stop pairs
        i = 0
        while i < len(media_events):
            ev = media_events[i]
            name = get_app_name(ev["package"])
            t = ev["time"].strftime("%H:%M:%S")
            if ev["action"] == "start":
                # Look for the next stop from same app
                duration_str = ""
                if i + 1 < len(media_events) and media_events[i+1]["action"] == "stop":
                    dur = int((media_events[i+1]["time"] - ev["time"]).total_seconds())
                    duration_str = f" ({_fmt_seconds(dur)})"
                    i += 1
                lines.append(f"- `{t}` **{name}** 播放{duration_str}")
            i += 1
        lines.append("")

    # ── 前台服务 ─────────────────────────────────────────────────────────────
    if fg_services:
        # Group by package, find start-stop pairs
        interesting = [
            s for s in fg_services
            if not any(skip in s["package"] for skip in ["oplus", "coloros", "heytap", "mediatek"])
        ]
        if interesting:
            lines.append("## ⚙️ 后台服务记录")
            lines.append("")
            i = 0
            while i < len(interesting):
                ev = interesting[i]
                name = get_app_name(ev["package"])
                t = ev["time"].strftime("%H:%M:%S")
                if ev["action"] == "start":
                    duration_str = ""
                    if i + 1 < len(interesting) and interesting[i+1]["action"] == "stop" \
                            and interesting[i+1]["package"] == ev["package"]:
                        dur = int((interesting[i+1]["time"] - ev["time"]).total_seconds())
                        duration_str = f" → {_fmt_seconds(dur)}"
                        i += 1
                    cls_short = ev.get("class", "").split(".")[-1]
                    lines.append(f"- `{t}` **{name}** `{cls_short}`{duration_str}")
                i += 1
            lines.append("")

    # ── 通知推送统计 ─────────────────────────────────────────────────────────
    if notif_counts:
        lines.append("## 🔔 通知推送统计（今日）")
        lines.append("")
        lines.append("| App | 推送次数 |")
        lines.append("|-----|---------|")
        for pkg, cnt in sorted(notif_counts.items(), key=lambda x: -x[1]):
            lines.append(f"| {get_app_name(pkg)} | {cnt} 次 |")
        lines.append("")

    # ── 当前未消除通知（快照） ────────────────────────────────────────────────
    if live_notifs:
        lines.append("## 📬 未消除通知（同步时快照）")
        lines.append("")
        for n in live_notifs:
            name = get_app_name(n["package"])
            display = n.get("display") or n.get("text", "")
            display = display[:100] + "…" if len(display) > 100 else display
            lines.append(f"- `{n['time_str']}` **{name}**：{display}")
        lines.append("")

    # ── 短信 ─────────────────────────────────────────────────────────────────
    lines.append("## 💬 短信记录")
    lines.append("")
    if sms_messages:
        for m in sms_messages:
            direction = "📨" if m["type"] == "收到" else "📤"
            body_preview = m["body"][:100] + "…" if len(m["body"]) > 100 else m["body"]
            read_mark = "" if m["read"] else " 🔴"
            lines.append(f"- `{m['time_str']}` {direction} **{m['address']}**{read_mark}")
            lines.append(f"  {body_preview}")
    else:
        lines.append("*无短信记录*")
    lines.append("")

    # ── 通话 ─────────────────────────────────────────────────────────────────
    lines.append("## 📞 通话记录")
    lines.append("")
    if call_records:
        for c in call_records:
            icon = {"拨出": "📲", "接入": "📳", "未接": "📵"}.get(c["type"], "📞")
            name_part = f" ({c['name']})" if c["name"] else ""
            loc_part = f" [{c['location']}]" if c["location"] else ""
            dur_part = f" ⏱{c['duration_str']}" if c["duration_seconds"] > 0 else " ⏱—"
            lines.append(f"- `{c['time_str']}` {icon} {c['type']} **{c['number']}**{name_part}{loc_part}{dur_part}")
    else:
        lines.append("*无通话记录*")
    lines.append("")

    # ── 日历 ─────────────────────────────────────────────────────────────────
    lines.append("## 📅 日历事件")
    lines.append("")
    if cal_events:
        for e in cal_events:
            time_part = "全天" if e["all_day"] else f"{e['start_str']}–{e['end_str']}"
            loc_part = f" 📍{e['location']}" if e["location"] else ""
            desc_part = f"\n  > {e['description'][:80]}" if e["description"] else ""
            lines.append(f"- `{time_part}` **{e['title']}**{loc_part}{desc_part}")
    else:
        lines.append("*无日历事件*")
    lines.append("")

    # ── WiFi 轨迹 ─────────────────────────────────────────────────────────────
    if wifi_conns:
        lines.append("## 📶 WiFi 连接轨迹")
        lines.append("")
        for w in wifi_conns:
            lines.append(f"- `{w['time_str']}` **{w['ssid']}**")
        lines.append("")

    # ── 屏幕亮度分布 ─────────────────────────────────────────────────────────
    if batt.brightness and target_date == datetime.now(tz).date():
        lines.append("## 💡 屏幕亮度分布")
        lines.append("")
        labels = {"dark": "暗", "dim": "低", "medium": "中", "light": "亮", "bright": "高"}
        for k, pct in batt.brightness.items():
            label = labels.get(k, k)
            bar_len = int(pct / 5)
            bar = "█" * bar_len + "░" * (20 - bar_len)
            lines.append(f"- {label}：{bar} {pct:.1f}%")
        lines.append("")

    return "\n".join(lines)


# ── File I/O ──────────────────────────────────────────────────────────────────

def write_day_files(
    target_date: date,
    summary: dict,
    markdown: str,
    output_dir: Path,
):
    """Write per-day .md and summary.json. Raw data is stored separately via write_sync_raw."""
    day_dir = output_dir / target_date.isoformat()
    day_dir.mkdir(parents=True, exist_ok=True)

    (day_dir / f"{target_date.isoformat()}.md").write_text(markdown, encoding="utf-8")
    (day_dir / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2, default=str),
        encoding="utf-8",
    )


def write_sync_raw(
    raw: dict,
    output_dir: Path,
    sync_time: datetime,
    retain_days: int = 7,
):
    """
    Store the raw ADB dump ONCE per sync run in data/_syncs/YYYY-MM-DD_HH-MM/.
    Old sync folders beyond retain_days are cleaned up automatically.
    """
    syncs_dir = output_dir / "_syncs"
    syncs_dir.mkdir(exist_ok=True)

    folder_name = sync_time.strftime("%Y-%m-%d_%H-%M")
    sync_dir = syncs_dir / folder_name
    sync_dir.mkdir(exist_ok=True)

    for name, content in raw.items():
        if content:
            (sync_dir / f"{name}.txt").write_text(content, encoding="utf-8", errors="replace")

    # Clean up old syncs
    if retain_days > 0:
        cutoff = sync_time.date() - timedelta(days=retain_days)
        for old_dir in syncs_dir.iterdir():
            if not old_dir.is_dir():
                continue
            try:
                dir_date = date.fromisoformat(old_dir.name[:10])
                if dir_date < cutoff:
                    remove_tree_best_effort(old_dir, "旧 raw 同步快照")
            except (ValueError, IndexError):
                pass
