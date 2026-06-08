"""Collect call log entries filtered to a target date."""

import re
import json
from datetime import datetime, date
from typing import Optional
import pytz


_ROW_RE = re.compile(r'Row:\s*\d+\s+(.+)')
_FIELD_RE = re.compile(r'(\w+)=(?:([^,\s]+(?:\{[^}]*\})?)|NULL)')


def _parse_row(row_content: str) -> dict:
    fields: dict = {}
    # Use a simple split-by-field approach for the complex OPLUS format
    # Fields are separated by ", fieldname=" pattern
    parts = re.split(r',\s+(?=\w+=)', row_content)
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


CALL_TYPES = {
    "1": "拨出",
    "2": "接入",
    "3": "未接",
    "4": "语音信箱",
    "5": "拒接",
    "6": "已拦截",
}


def _parse_identify_name(raw: Optional[str]) -> str:
    """Parse OPLUS identify_name JSON field for caller ID."""
    if not raw:
        return ""
    try:
        # raw might be like: {"name":"快递外卖","markType":6,...}
        data = json.loads(raw)
        if data.get("name"):
            return str(data["name"])
        if data.get("phoneFlag"):
            return str(data["phoneFlag"])
    except Exception:
        pass
    return ""


def collect_calls(raw: str, target_date: date, tz: pytz.BaseTzInfo) -> list[dict]:
    """Parse raw call_log content query output and return calls for target_date."""
    calls = []
    for line in raw.splitlines():
        line = line.strip()
        if not line.startswith("Row:"):
            continue
        # Extract row content after "Row: N "
        m = re.match(r'Row:\s*\d+\s+(.*)', line)
        if not m:
            continue
        fields = _parse_row(m.group(1))

        dt = _ts_to_dt(fields.get("date"), tz)
        if dt is None or dt.date() != target_date:
            continue

        call_type = CALL_TYPES.get(fields.get("type", ""), fields.get("type", "未知"))
        duration = int(fields.get("duration") or 0)
        number = fields.get("number") or fields.get("formatted_number") or ""
        name = fields.get("name") or _parse_identify_name(fields.get("identify_name")) or ""
        location = fields.get("geocoded_location") or ""

        calls.append({
            "time": dt,
            "time_str": dt.strftime("%H:%M:%S"),
            "number": number,
            "name": name,
            "location": location,
            "type": call_type,
            "duration_seconds": duration,
            "duration_str": (
                "—" if duration == 0 else
                f"{duration // 60}m {duration % 60}s" if duration >= 60 else
                f"{duration}s"
            ),
        })

    calls.sort(key=lambda x: x["time"])
    return calls
