"""Parse current (live) notifications from dumpsys notification output."""

import re
from datetime import datetime
from typing import Optional
import pytz


_TICKER_RE  = re.compile(r'tickerText=(.+)')
_WHEN_RE    = re.compile(r'when=(\d+)/')
_PKG_RE     = re.compile(r'appPackage=String \(([^)]+)\)')
_PKG2_RE    = re.compile(r'pkg=(\S+)\s+user=')
_TITLE_RE   = re.compile(r'android\.title(?:\.big)?=String \((.+)\)')
_TEXT_RE    = re.compile(r'android\.text=String \((.+)\)')


def _ts_to_dt(ts_ms: int, tz: pytz.BaseTzInfo) -> datetime:
    return datetime.fromtimestamp(ts_ms / 1000, tz=tz)


def _flush(pkg, when, title, text, ticker, notifications, tz):
    if pkg and when:
        # prefer structured title+text over tickerText
        if title and text:
            display = f"{title}：{text}"
        elif title:
            display = title
        elif text:
            display = text
        elif ticker and ticker != "null":
            display = ticker
        else:
            display = ""
        notifications.append({
            "time": _ts_to_dt(when, tz),
            "time_str": _ts_to_dt(when, tz).strftime("%H:%M:%S"),
            "package": pkg,
            "title": title or "",
            "text": text or ticker or "",
            "display": display,
        })


def parse_current_notifications(raw: str, tz: pytz.BaseTzInfo) -> list[dict]:
    """
    Parse currently active (not yet dismissed) notifications.
    Returns list of {time, package, title, text, display}.
    Prefers android.title / android.text over tickerText for accuracy.
    """
    notifications = []
    lines = raw.splitlines()

    current_pkg: Optional[str]   = None
    current_when: Optional[int]  = None
    current_title: Optional[str] = None
    current_text: Optional[str]  = None
    current_ticker: Optional[str] = None

    for line in lines:
        line_s = line.strip()

        if "NotificationRecord(" in line_s:
            _flush(current_pkg, current_when, current_title,
                   current_text, current_ticker, notifications, tz)
            m = _PKG2_RE.search(line_s)
            current_pkg    = m.group(1) if m else None
            current_when   = None
            current_title  = None
            current_text   = None
            current_ticker = None
            continue

        if current_when is None:
            m = _WHEN_RE.search(line_s)
            if m:
                try:
                    current_when = int(m.group(1))
                except ValueError:
                    pass

        if current_ticker is None:
            m = _TICKER_RE.search(line_s)
            if m:
                t = m.group(1).strip()
                if t != "null":
                    current_ticker = t

        if current_title is None:
            m = _TITLE_RE.search(line_s)
            if m:
                current_title = m.group(1).strip()

        if current_text is None:
            m = _TEXT_RE.search(line_s)
            if m:
                current_text = m.group(1).strip()

        # appPackage override
        if current_pkg is None:
            m = _PKG_RE.search(line_s)
            if m:
                current_pkg = m.group(1)

    _flush(current_pkg, current_when, current_title,
           current_text, current_ticker, notifications, tz)

    notifications.sort(key=lambda x: x["time"], reverse=True)
    return notifications
