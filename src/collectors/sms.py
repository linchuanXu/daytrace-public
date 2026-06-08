"""Collect SMS and MMS messages, filtered to a date range."""

import re
from datetime import datetime, date
from typing import Optional
import pytz


_ROW_RE = re.compile(r'Row:\s*\d+\s+(.+)')
_FIELD_RE = re.compile(r'(\w+)=(?:"([^"]*)"|(NULL)|([^\s,]+))')


def _parse_row(row_content: str) -> dict:
    fields = {}
    for m in _FIELD_RE.finditer(row_content):
        key = m.group(1)
        val = m.group(2) if m.group(2) is not None else (
            None if m.group(3) else m.group(4)
        )
        fields[key] = val
    return fields


def _ts_ms_to_dt(ts_str: Optional[str], tz: pytz.BaseTzInfo) -> Optional[datetime]:
    """SMS timestamps are in milliseconds."""
    if not ts_str:
        return None
    try:
        ms = int(ts_str)
        return datetime.fromtimestamp(ms / 1000, tz=tz)
    except (ValueError, TypeError, OSError):
        return None


def _ts_sec_to_dt(ts_str: Optional[str], tz: pytz.BaseTzInfo) -> Optional[datetime]:
    """MMS timestamps are in seconds."""
    if not ts_str:
        return None
    try:
        s = int(ts_str)
        return datetime.fromtimestamp(s, tz=tz)
    except (ValueError, TypeError, OSError):
        return None


SMS_TYPES = {
    "1": "收到",
    "2": "发出",
    "3": "草稿",
    "4": "发件箱",
    "5": "失败",
    "6": "排队中",
}

MMS_BOX = {
    "1": "收到",
    "2": "发出",
    "3": "草稿",
    "4": "发件箱",
}


def _parse_mms_addr(raw_addr: str) -> dict[str, str]:
    """
    Parse content://mms/N/addr output to get sender/recipient addresses.
    Returns {mms_id: address} for type=137 (FROM) entries.
    """
    addr_map: dict[str, str] = {}
    for line in raw_addr.splitlines():
        line = line.strip()
        if not line.startswith("Row:"):
            continue
        m = _ROW_RE.match(line)
        if not m:
            continue
        f = _parse_row(m.group(1))
        # type=137 = FROM address
        if f.get("type") == "137":
            msg_id = f.get("msg_id", "")
            addr = f.get("address") or ""
            if msg_id and addr and addr != "insert-address-token":
                addr_map[msg_id] = addr
    return addr_map


def collect_sms(raw_sms: str, target_date: date, tz: pytz.BaseTzInfo,
                raw_mms: str = "", raw_mms_addr: str = "") -> list[dict]:
    """Parse SMS + MMS and return all messages for target_date."""
    messages = []

    # ── SMS ──────────────────────────────────────────────────────────────────
    for line in raw_sms.splitlines():
        line = line.strip()
        if not line.startswith("Row:"):
            continue
        m = _ROW_RE.match(line)
        if not m:
            continue
        fields = _parse_row(m.group(1))

        dt = _ts_ms_to_dt(fields.get("date"), tz)
        if dt is None or dt.date() != target_date:
            continue

        msg_type = SMS_TYPES.get(fields.get("type", ""), fields.get("type", ""))
        messages.append({
            "time": dt,
            "time_str": dt.strftime("%H:%M:%S"),
            "address": fields.get("address") or "",
            "body": fields.get("body") or "",
            "type": msg_type,
            "kind": "SMS",
            "read": fields.get("read") == "1",
        })

    # ── MMS ──────────────────────────────────────────────────────────────────
    if raw_mms:
        mms_addr_map = _parse_mms_addr(raw_mms_addr) if raw_mms_addr else {}
        for line in raw_mms.splitlines():
            line = line.strip()
            if not line.startswith("Row:"):
                continue
            m = _ROW_RE.match(line)
            if not m:
                continue
            fields = _parse_row(m.group(1))

            dt = _ts_sec_to_dt(fields.get("date"), tz)
            if dt is None or dt.date() != target_date:
                continue

            mms_id = fields.get("_id", "")
            address = mms_addr_map.get(mms_id, "")
            subject = fields.get("sub") or ""
            msg_box = MMS_BOX.get(fields.get("msg_box", ""), "收到")

            messages.append({
                "time": dt,
                "time_str": dt.strftime("%H:%M:%S"),
                "address": address,
                "body": subject,   # MMS body in subject field; parts need separate query
                "type": msg_box,
                "kind": "MMS",
                "read": fields.get("read") == "1",
            })

    messages.sort(key=lambda x: x["time"])
    return messages
