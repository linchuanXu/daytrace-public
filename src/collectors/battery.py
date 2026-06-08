"""Parse battery statistics from dumpsys batterystats output."""

import re
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class BatteryStats:
    screen_on_seconds: int = 0
    screen_on_str: str = ""
    screen_off_seconds: int = 0
    estimated_mah: int = 0
    capacity_mah: int = 0
    brightness: dict = field(default_factory=dict)   # dark/dim/medium/light → pct
    current_level: int = -1
    charging: bool = False
    temperature_celsius: float = 0.0
    cellular_rx_mb: float = 0.0
    cellular_tx_mb: float = 0.0
    wifi_rx_mb: float = 0.0
    wifi_tx_mb: float = 0.0
    discharge_steps: list[str] = field(default_factory=list)


_DUR_RE = re.compile(r'(\d+)h\s*(\d+)m\s*(\d+)s')
_DUR_MS_RE = re.compile(r'(\d+)m\s*(\d+)s\s*(\d+)ms')


def _parse_duration(s: str) -> int:
    """Parse '1h 10m 24s 229ms' or '8m 44s 984ms' → seconds."""
    s = s.strip()
    m = _DUR_RE.match(s)
    if m:
        return int(m.group(1)) * 3600 + int(m.group(2)) * 60 + int(m.group(3))
    m = _DUR_MS_RE.match(s)
    if m:
        return int(m.group(1)) * 60 + int(m.group(2))
    # Try simple "Ns" pattern
    m2 = re.match(r'(\d+)s', s)
    if m2:
        return int(m2.group(1))
    return 0


def _parse_mb(s: str) -> float:
    """Parse '5.66MB' or '447.75KB' → float MB."""
    s = s.strip()
    m = re.match(r'([\d.]+)(MB|KB|GB)', s)
    if not m:
        return 0.0
    val = float(m.group(1))
    unit = m.group(2)
    if unit == "KB":
        return val / 1024
    elif unit == "GB":
        return val * 1024
    return val


def parse_battery_stats(raw_batterystats: str, raw_battery: str) -> BatteryStats:
    stats = BatteryStats()

    # ── From dumpsys battery ─────────────────────────────────────────────────
    for line in raw_battery.splitlines():
        line = line.strip()
        if line.startswith("level:"):
            try:
                stats.current_level = int(line.split(":")[1].strip())
            except (ValueError, IndexError):
                pass
        elif "USB powered: true" in line or "AC powered: true" in line:
            stats.charging = True
        elif line.startswith("temperature:"):
            try:
                stats.temperature_celsius = int(line.split(":")[1].strip()) / 10
            except (ValueError, IndexError):
                pass

    # ── From dumpsys batterystats ────────────────────────────────────────────
    for line in raw_batterystats.splitlines():
        line = line.strip()

        if line.startswith("Screen on:"):
            m = re.search(r'Screen on:\s+([\dh\s\dm\ds]+?)\s*\(', line)
            if m:
                stats.screen_on_str = m.group(1).strip()
                stats.screen_on_seconds = _parse_duration(stats.screen_on_str)

        elif line.startswith("Time on battery screen off:"):
            m = re.search(r'Time on battery screen off:\s+([\dh\s\dm\ds]+?)\s*\(', line)
            if m:
                stats.screen_off_seconds = _parse_duration(m.group(1).strip())

        elif line.startswith("Estimated battery capacity:"):
            m = re.search(r'([\d,]+)\s*mAh', line)
            if m:
                try:
                    stats.capacity_mah = int(m.group(1).replace(",", ""))
                except ValueError:
                    pass

        elif line.startswith("Discharge:"):
            m = re.search(r'([\d.]+)\s*mAh', line)
            if m:
                try:
                    stats.estimated_mah = int(float(m.group(1)))
                except ValueError:
                    pass

        elif line.startswith("Estimated screen on time:"):
            # Fallback if Screen on line not found
            m = re.search(r'Estimated screen on time:\s+([\dh\s\dm\ds]+)', line)
            if m and not stats.screen_on_str:
                stats.screen_on_str = m.group(1).strip()
                stats.screen_on_seconds = _parse_duration(stats.screen_on_str)

        # Screen brightness distribution
        elif re.match(r'\s*(dark|dim|medium|light)\s+[\d]+', line.lower()):
            parts = line.split()
            if len(parts) >= 2:
                label = parts[0].lower()
                pct_m = re.search(r'([\d.]+)%', line)
                if pct_m:
                    stats.brightness[label] = float(pct_m.group(1))

        elif line.startswith("Cellular data received:"):
            m = re.search(r'Cellular data received:\s+([\d.]+\w+)', line)
            if m:
                stats.cellular_rx_mb = _parse_mb(m.group(1))
        elif line.startswith("Cellular data sent:"):
            m = re.search(r'Cellular data sent:\s+([\d.]+\w+)', line)
            if m:
                stats.cellular_tx_mb = _parse_mb(m.group(1))
        elif line.startswith("Wifi data received:"):
            m = re.search(r'Wifi data received:\s+([\d.]+\w+)', line)
            if m:
                stats.wifi_rx_mb = _parse_mb(m.group(1))
        elif line.startswith("Wifi data sent:"):
            m = re.search(r'Wifi data sent:\s+([\d.]+\w+)', line)
            if m:
                stats.wifi_tx_mb = _parse_mb(m.group(1))

        elif line.startswith("#") and "screen-on" in line:
            stats.discharge_steps.append(line)

    return stats
