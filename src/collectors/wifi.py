"""Parse WiFi connection history from dumpsys wifi output."""

import re
from datetime import datetime, date
from typing import Optional
import pytz


# Matches lines like: "rec[N]: time=MM-DD HH:MM:SS.mmm ..."
_REC_RE = re.compile(r'rec\[\d+\]:\s+time=(?P<month>\d+)-(?P<day>\d+)\s+(?P<hms>\d+:\d+:\d+)\.\d+\s+(?P<rest>.+)')
_SSID_RE = re.compile(r'ssid:\s+"(?P<ssid>[^"]*)"')
_CONNECT_RE = re.compile(r'CMD_START_CONNECT.*targetConfigKey="(?P<ssid>[^"]+)"')


def collect_wifi(raw: str, target_date: date, tz: pytz.BaseTzInfo) -> list[dict]:
    """Extract WiFi SSID connection attempts for target_date."""
    connections = []
    current_year = target_date.year

    for line in raw.splitlines():
        line = line.strip()
        m = _REC_RE.match(line)
        if not m:
            continue

        try:
            dt = tz.localize(datetime(
                current_year,
                int(m.group("month")),
                int(m.group("day")),
                *[int(x) for x in m.group("hms").split(":")],
            ))
        except ValueError:
            continue

        if dt.date() != target_date:
            continue

        rest = m.group("rest")

        # CMD_START_CONNECT = actively initiating connection
        cm = _CONNECT_RE.search(rest)
        if cm:
            raw_ssid = cm.group("ssid")
            # Strip security suffix like "WPA_PSK"
            ssid = re.sub(r'"(WPA_PSK|WPA2_PSK|NONE|WEP)$', '', raw_ssid).strip('"')
            connections.append({
                "time": dt,
                "time_str": dt.strftime("%H:%M:%S"),
                "ssid": ssid,
                "event": "connecting",
            })
            continue

        # ASSOCIATED_BSSID_EVENT + L3Connected = fully connected
        if "ASSOCIATED_BSSID_EVENT" in rest and "L3Connected" in rest:
            sm = _SSID_RE.search(rest)
            if sm and sm.group("ssid"):
                connections.append({
                    "time": dt,
                    "time_str": dt.strftime("%H:%M:%S"),
                    "ssid": sm.group("ssid"),
                    "event": "connected",
                })

    # De-duplicate: keep one entry per SSID per hour
    seen: set = set()
    deduped = []
    for c in sorted(connections, key=lambda x: x["time"]):
        key = (c["ssid"], c["time"].strftime("%H"))
        if key not in seen:
            seen.add(key)
            deduped.append(c)

    return deduped
