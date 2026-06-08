"""Collect calendar events for a target date."""

import re
from datetime import datetime, date, timedelta
from typing import Optional
import pytz


def _parse_row(line: str) -> dict:
    fields: dict = {}
    parts = re.split(r',\s+(?=\w+=)', line)
    for part in parts:
        eq = part.find("=")
        if eq == -1:
            continue
        key = part[:eq].strip()
        val = part[eq+1:].strip()
        if val == "NULL":
            val = None
        fields[key] = val
    return fields


def _ts_to_dt(ts_str: Optional[str], tz: pytz.BaseTzInfo) -> Optional[datetime]:
    if not ts_str:
        return None
    try:
        ms = int(ts_str)
        return datetime.fromtimestamp(ms / 1000, tz=tz)
    except (ValueError, TypeError):
        return None


def collect_calendar(raw: str, target_date: date, tz: pytz.BaseTzInfo) -> list[dict]:
    """Return calendar events that overlap with target_date."""
    events = []
    day_start = tz.localize(datetime(target_date.year, target_date.month, target_date.day, 0, 0, 0))
    day_end   = day_start + timedelta(days=1)

    for line in raw.splitlines():
        line = line.strip()
        if not line.startswith("Row:"):
            continue
        m = re.match(r'Row:\s*\d+\s+(.*)', line)
        if not m:
            continue
        fields = _parse_row(m.group(1))

        dtstart = _ts_to_dt(fields.get("dtstart"), tz)
        dtend   = _ts_to_dt(fields.get("dtend"), tz)
        if dtstart is None:
            continue

        # All-day events: dtstart in UTC midnight, need to check if it falls on target_date
        all_day = fields.get("allDay") == "1"
        if all_day:
            # dtstart for all-day is UTC midnight; convert to local
            local_start_date = dtstart.astimezone(tz).date()
            if local_start_date != target_date:
                continue
        else:
            # Regular event: check if it overlaps with the day
            if dtstart >= day_end:
                continue
            if dtend and dtend <= day_start:
                continue

        title = fields.get("title") or ""
        description = fields.get("description") or ""
        location = fields.get("eventLocation") or ""

        events.append({
            "start": dtstart,
            "end": dtend,
            "start_str": dtstart.astimezone(tz).strftime("%H:%M") if not all_day else "全天",
            "end_str": dtend.astimezone(tz).strftime("%H:%M") if (dtend and not all_day) else "",
            "title": title,
            "description": description,
            "location": location,
            "all_day": all_day,
        })

    events.sort(key=lambda x: x["start"])
    return events
