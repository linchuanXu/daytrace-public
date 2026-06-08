"""
Parse `dumpsys usagestats` output into structured events and per-app summaries.
"""

import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Optional
import pytz


# ── Event types we care about ───────────────────────────────────────────────
ACTIVITY_RESUMED  = "ACTIVITY_RESUMED"
ACTIVITY_PAUSED   = "ACTIVITY_PAUSED"
ACTIVITY_STOPPED  = "ACTIVITY_STOPPED"
SCREEN_ON         = "SCREEN_INTERACTIVE"   # screen becomes interactive
SCREEN_OFF        = "KEYGUARD_SHOWN"       # keyguard (lock) shown
SCREEN_UNLOCKED   = "KEYGUARD_HIDDEN"      # keyguard hidden = fully unlocked
NOTIF_PUSH        = "NOTIFICATION_INTERRUPTION"
NOTIF_SEEN        = "NOTIFICATION_SEEN"
USER_INTERACT     = "USER_INTERACTION"
FG_SERVICE_START  = "FOREGROUND_SERVICE_START"
FG_SERVICE_STOP   = "FOREGROUND_SERVICE_STOP"
STANDBY_CHANGED   = "STANDBY_BUCKET_CHANGED"

IMPORTANT_TYPES = {
    ACTIVITY_RESUMED, ACTIVITY_PAUSED, ACTIVITY_STOPPED,
    SCREEN_ON, SCREEN_OFF, SCREEN_UNLOCKED,
    NOTIF_PUSH, NOTIF_SEEN,
    USER_INTERACT,
    FG_SERVICE_START, FG_SERVICE_STOP,
}

_EVENT_RE = re.compile(
    r'time="(?P<time>[^"]+)"\s+type=(?P<type>\S+)\s+package=(?P<package>\S+)'
    r'(?:\s+class=(?P<class>\S+))?'
    r'(?:\s+(?P<extras>.+))?'
)
_STATS_RE = re.compile(
    r'package=(?P<package>\S+)\s+'
    r'totalTimeUsed="(?P<total_used>[^"]+)"\s+'
    r'lastTimeUsed="(?P<last_used>[^"]+)"\s+'
    r'totalTimeVisible="(?P<total_visible>[^"]+)"\s+'
    r'lastTimeVisible="(?P<last_visible>[^"]+)"\s+'
    r'lastTimeComponentUsed="(?P<last_component>[^"]+)"\s+'
    r'totalTimeFS="(?P<total_fs>[^"]+)"\s+'
    r'lastTimeFS="(?P<last_fs>[^"]+)"\s+'
    r'appLaunchCount=(?P<launches>\d+)\s+'
    r'errorCount=(?P<errors>\d+)'
)
_TIMERANGE_RE = re.compile(
    r'timeRange="(?P<start>[^–"]+)\s*[–-]\s*(?P<end>[^"]+)"'
)


@dataclass
class UsageEvent:
    time: datetime
    event_type: str
    package: str
    cls: str = ""
    extras: str = ""


@dataclass
class AppStat:
    package: str
    total_used_seconds: int = 0
    total_visible_seconds: int = 0
    launches: int = 0
    last_used: Optional[datetime] = None
    time_range_start: Optional[datetime] = None
    time_range_end: Optional[datetime] = None


@dataclass
class ParsedUsageStats:
    events: list[UsageEvent] = field(default_factory=list)
    # key = (range_label, package) where range_label is "daily/weekly/monthly/yearly"
    daily_stats: list[AppStat] = field(default_factory=list)
    weekly_stats: list[AppStat] = field(default_factory=list)
    monthly_stats: list[AppStat] = field(default_factory=list)
    yearly_stats: list[AppStat] = field(default_factory=list)
    events_range_start: Optional[datetime] = None
    events_range_end: Optional[datetime] = None


def _parse_duration_str(s: str) -> int:
    """Convert '53:45' or '1:10:24' or '147:35:05' to seconds."""
    s = s.strip()
    parts = s.split(":")
    try:
        if len(parts) == 2:
            return int(parts[0]) * 60 + int(parts[1])
        elif len(parts) == 3:
            return int(parts[0]) * 3600 + int(parts[1]) * 60 + int(parts[2])
    except ValueError:
        pass
    return 0


def _parse_dt(s: str, tz: pytz.BaseTzInfo) -> Optional[datetime]:
    s = s.strip()
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y/%m/%d %H:%M"):
        try:
            naive = datetime.strptime(s, fmt)
            return tz.localize(naive)
        except ValueError:
            continue
    return None


def parse_usagestats(raw: str, tz: pytz.BaseTzInfo) -> ParsedUsageStats:
    result = ParsedUsageStats()

    # Only process user=0 section (primary user). Skip user=999 (work/clone profile).
    # Split on "user=" boundaries and take only the user=0 block.
    user0_raw = raw
    if "\nuser=0 " in raw or raw.startswith("user=0 "):
        # Find start of user=0
        start_idx = raw.find("user=0 ")
        if start_idx < 0:
            start_idx = 0
        # Find next user= that is NOT user=0
        next_user = len(raw)
        for marker in ["\nuser=999 ", "\nuser=10 ", "\nuser=11 "]:
            pos = raw.find(marker, start_idx + 1)
            if pos > 0 and pos < next_user:
                next_user = pos
        user0_raw = raw[start_idx:next_user]

    lines = user0_raw.splitlines()

    # Determine which section we're in
    # Sections:  "Last 24 hour events" → events
    #            "In-memory daily stats" / timeRange narrow  → daily
    #            timeRange wider (weekly/monthly/yearly) parsed by span
    section = None
    current_stats_bucket: list[AppStat] = []
    current_range_start: Optional[datetime] = None
    current_range_end: Optional[datetime] = None

    # We'll assign buckets after parsing by timeRange span (days)
    stat_buckets: list[tuple[int, list[AppStat]]] = []  # (span_days, stats)

    i = 0
    while i < len(lines):
        line = lines[i]
        stripped = line.strip()

        # ── Detect section headers ───────────────────────────────────────
        if "Last 24 hour events" in stripped:
            # Save previous stats bucket
            if current_stats_bucket and current_range_start and current_range_end:
                span = (current_range_end - current_range_start).days + 1
                stat_buckets.append((span, current_stats_bucket))
            current_stats_bucket = []
            current_range_start = None
            current_range_end = None
            section = "events"
            # Parse the timeRange from this line
            m = _TIMERANGE_RE.search(stripped)
            if m:
                result.events_range_start = _parse_dt(m.group("start"), tz)
                result.events_range_end   = _parse_dt(m.group("end"), tz)
            i += 1
            continue

        if "In-memory daily stats" in stripped or "daily stats files" in stripped:
            if current_stats_bucket and current_range_start and current_range_end:
                span = (current_range_end - current_range_start).days + 1
                stat_buckets.append((span, current_stats_bucket))
            current_stats_bucket = []
            current_range_start = None
            current_range_end = None
            section = "stats"
            i += 1
            continue

        if "In-memory weekly stats" in stripped:
            if current_stats_bucket and current_range_start and current_range_end:
                span = (current_range_end - current_range_start).days + 1
                stat_buckets.append((span, current_stats_bucket))
            current_stats_bucket = []
            current_range_start = None
            current_range_end = None
            section = "stats"
            i += 1
            continue

        # ── timeRange line ───────────────────────────────────────────────
        if section == "stats" and "timeRange=" in stripped:
            if current_stats_bucket and current_range_start and current_range_end:
                span = (current_range_end - current_range_start).days + 1
                stat_buckets.append((span, current_stats_bucket))
                current_stats_bucket = []
            m = _TIMERANGE_RE.search(stripped)
            if m:
                current_range_start = _parse_dt(m.group("start"), tz)
                end_str = m.group("end").strip()
                # End may be time-only "HH:MM" when start and end share the same date
                if current_range_start and re.match(r'^\d{1,2}:\d{2}$', end_str):
                    date_prefix = current_range_start.strftime("%Y/%m/%d")
                    current_range_end = _parse_dt(f"{date_prefix} {end_str}", tz)
                else:
                    current_range_end = _parse_dt(end_str, tz)
            i += 1
            continue

        # ── Event lines ──────────────────────────────────────────────────
        if section == "events" and 'time="' in stripped:
            m = _EVENT_RE.search(stripped)
            if m:
                t = _parse_dt(m.group("time"), tz)
                etype = m.group("type")
                if t and etype in IMPORTANT_TYPES:
                    result.events.append(UsageEvent(
                        time=t,
                        event_type=etype,
                        package=m.group("package"),
                        cls=m.group("class") or "",
                        extras=m.group("extras") or "",
                    ))
            i += 1
            continue

        # ── Per-app stats lines ──────────────────────────────────────────
        if section == "stats" and "package=" in stripped and "totalTimeUsed=" in stripped:
            m = _STATS_RE.search(stripped)
            if m:
                stat = AppStat(
                    package=m.group("package"),
                    total_used_seconds=_parse_duration_str(m.group("total_used")),
                    total_visible_seconds=_parse_duration_str(m.group("total_visible")),
                    launches=int(m.group("launches")),
                    last_used=_parse_dt(m.group("last_used"), tz),
                    time_range_start=current_range_start,
                    time_range_end=current_range_end,
                )
                current_stats_bucket.append(stat)
            i += 1
            continue

        i += 1

    # Save last bucket
    if current_stats_bucket and current_range_start and current_range_end:
        span = (current_range_end - current_range_start).days + 1
        stat_buckets.append((span, current_stats_bucket))

    # Assign buckets: shortest span = daily, then weekly, monthly, yearly
    stat_buckets.sort(key=lambda x: x[0])
    bucket_names = ["daily", "weekly", "monthly", "yearly"]
    for idx, (span, stats) in enumerate(stat_buckets):
        if idx == 0:
            result.daily_stats = stats
        elif idx == 1:
            result.weekly_stats = stats
        elif idx == 2:
            result.monthly_stats = stats
        else:
            result.yearly_stats = stats

    result.events.sort(key=lambda e: e.time)
    return result


# ── Derive screen sessions from events ──────────────────────────────────────

@dataclass
class ScreenSession:
    start: datetime          # when screen became interactive / keyguard hidden
    end: Optional[datetime]  # when keyguard shown
    duration_seconds: int = 0
    app_timeline: list[dict] = field(default_factory=list)  # list of {package, start, end, seconds}


def build_screen_sessions(events: list[UsageEvent]) -> list[ScreenSession]:
    sessions: list[ScreenSession] = []
    current_session: Optional[ScreenSession] = None
    current_app_pkg: Optional[str] = None
    current_app_start: Optional[datetime] = None

    def close_app(end_time: datetime):
        nonlocal current_app_pkg, current_app_start
        if current_session and current_app_pkg and current_app_start:
            dur = int((end_time - current_app_start).total_seconds())
            if dur > 0:
                current_session.app_timeline.append({
                    "package": current_app_pkg,
                    "start": current_app_start,
                    "end": end_time,
                    "seconds": dur,
                })
        current_app_pkg = None
        current_app_start = None

    for ev in events:
        if ev.event_type in (SCREEN_ON, SCREEN_UNLOCKED):
            if current_session is None:
                current_session = ScreenSession(start=ev.time, end=None)
                current_app_pkg = None
                current_app_start = None

        elif ev.event_type == SCREEN_OFF:
            if current_session is not None:
                close_app(ev.time)
                current_session.end = ev.time
                current_session.duration_seconds = int(
                    (ev.time - current_session.start).total_seconds()
                )
                sessions.append(current_session)
                current_session = None
                current_app_pkg = None
                current_app_start = None

        elif ev.event_type == ACTIVITY_RESUMED:
            if current_session is not None:
                if current_app_pkg and current_app_pkg != ev.package:
                    close_app(ev.time)
                if current_app_pkg != ev.package:
                    current_app_pkg = ev.package
                    current_app_start = ev.time

        elif ev.event_type in (ACTIVITY_PAUSED, ACTIVITY_STOPPED):
            if current_session is not None and current_app_pkg == ev.package:
                close_app(ev.time)

    # Close any open session (screen still on at end of dump)
    if current_session is not None:
        close_app(events[-1].time if events else current_session.start)
        current_session.end = None  # still open
        if events:
            current_session.duration_seconds = int(
                (events[-1].time - current_session.start).total_seconds()
            )
        sessions.append(current_session)

    return sessions


def compute_app_totals(screen_sessions: list[ScreenSession]) -> dict[str, dict]:
    """Aggregate per-app usage from screen sessions."""
    totals: dict[str, dict] = {}
    for sess in screen_sessions:
        for entry in sess.app_timeline:
            pkg = entry["package"]
            if pkg not in totals:
                totals[pkg] = {"package": pkg, "seconds": 0, "sessions": 0}
            totals[pkg]["seconds"] += entry["seconds"]
            totals[pkg]["sessions"] += 1
    return totals


def extract_notification_events(events: list[UsageEvent]) -> list[dict]:
    result = []
    for ev in events:
        if ev.event_type == NOTIF_PUSH:
            result.append({"time": ev.time, "package": ev.package, "type": "push"})
        elif ev.event_type == NOTIF_SEEN:
            result.append({"time": ev.time, "package": ev.package, "type": "seen"})
    return result


def extract_media_events(events: list[UsageEvent]) -> list[dict]:
    result = []
    for ev in events:
        if ev.event_type == USER_INTERACT and "android.media" in ev.extras:
            action = "start" if "EVENT_ACTION=start" in ev.extras else "stop"
            result.append({"time": ev.time, "package": ev.package, "action": action})
    return result


def extract_foreground_services(events: list[UsageEvent]) -> list[dict]:
    result = []
    for ev in events:
        if ev.event_type in (FG_SERVICE_START, FG_SERVICE_STOP):
            result.append({
                "time": ev.time,
                "package": ev.package,
                "cls": ev.cls,
                "action": "start" if ev.event_type == FG_SERVICE_START else "stop",
            })
    return result
