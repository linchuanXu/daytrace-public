"""
Gap detection: figure out which dates need reports generated.

Phone data dates (default sync with helper enabled):
  Helper export folders + today + yesterday

Refresh existing reports when:
  incomplete_dates ∩ phone_data_dates ∩ already_generated

New reports:
  phone_data_dates without an existing .md
"""

import re
from datetime import date, datetime, timedelta
from typing import Optional
import pytz


def find_earliest_data_date(raw_sms: str, raw_calls: str, tz: pytz.BaseTzInfo) -> Optional[date]:
    """
    Scan raw SMS and call log dumps to find the earliest date that has any data.
    Returns None if no data found.
    """
    earliest: Optional[date] = None
    ts_re = re.compile(r'\bdate=(\d{10,13})\b')

    for text in (raw_sms, raw_calls):
        for m in ts_re.finditer(text):
            try:
                ts = int(m.group(1))
                if ts > 1e11:
                    ts = ts / 1000
                d = datetime.fromtimestamp(ts, tz=tz).date()
                if earliest is None or d < earliest:
                    earliest = d
            except (ValueError, OSError):
                continue

    return earliest


def dates_with_any_data(
    raw_sms: str,
    raw_calls: str,
    raw_calendar: str,
    tz: pytz.BaseTzInfo,
) -> set[date]:
    """Dates with at least one SMS, call, or calendar event in ADB dumps."""
    dates: set[date] = set()
    ts_re = re.compile(r'\bdate=(\d{10,13})\b')
    dtstart_re = re.compile(r'\bdtstart=(\d{10,13})\b')

    for text in (raw_sms, raw_calls):
        for m in ts_re.finditer(text):
            try:
                ts = int(m.group(1))
                if ts > 1e11:
                    ts = ts / 1000
                dates.add(datetime.fromtimestamp(ts, tz=tz).date())
            except (ValueError, OSError):
                continue

    for m in dtstart_re.finditer(raw_calendar):
        try:
            ts = int(m.group(1))
            if ts > 1e11:
                ts = ts / 1000
            dates.add(datetime.fromtimestamp(ts, tz=tz).date())
        except (ValueError, OSError):
            continue

    return dates


def phone_data_dates(
    today: date,
    *,
    helper_dates: Optional[set[date]] = None,
    helper_only: bool = False,
    raw_sms: str = "",
    raw_calls: str = "",
    raw_calendar: str = "",
    tz: Optional[pytz.BaseTzInfo] = None,
    start_date: Optional[date] = None,
) -> set[date]:
    """Dates treated as having phone-side material worth syncing."""
    if tz is None:
        tz = pytz.timezone("Asia/Shanghai")

    if helper_only and helper_dates is not None:
        dates = set(helper_dates)
    else:
        dates = dates_with_any_data(raw_sms, raw_calls, raw_calendar, tz)
        if helper_dates:
            dates.update(helper_dates)

    dates.add(today)
    dates.add(today - timedelta(days=1))

    if start_date:
        dates = {d for d in dates if d >= start_date}
    return {d for d in dates if d <= today}


def _new_report_floor(
    today: date,
    already_generated: set[date],
    *,
    lookback_without_reports: int = 14,
    gap_before_earliest_report: int = 7,
) -> date:
    """Don't mass-create reports for ancient helper folders on disk."""
    if already_generated:
        return min(already_generated) - timedelta(days=gap_before_earliest_report)
    return today - timedelta(days=lookback_without_reports)


def dates_needing_reports(
    last_sync_date: Optional[date],
    today: date,
    already_generated: set[date],
    raw_sms: str = "",
    raw_calls: str = "",
    raw_calendar: str = "",
    tz: Optional[pytz.BaseTzInfo] = None,
    start_date: Optional[date] = None,
    helper_dates: Optional[set[date]] = None,
    helper_only: bool = False,
    incomplete_dates: Optional[set[date]] = None,
    refresh_dates: Optional[set[date]] = None,
    extra_dates_with_data: Optional[set[date]] = None,
) -> list[tuple[date, bool]]:
    """
    Return list of (date, is_complete) tuples that need to be generated.

    Default refresh (refresh_dates is None):
      incomplete_dates ∩ phone_data_dates ∩ already_generated
    """
    if tz is None:
        tz = pytz.timezone("Asia/Shanghai")

    # Backward compatibility for tests passing extra_dates_with_data only.
    merged_helper = set(helper_dates or ())
    if extra_dates_with_data:
        merged_helper.update(extra_dates_with_data)

    dates_with_data = phone_data_dates(
        today,
        helper_dates=merged_helper or None,
        helper_only=helper_only,
        raw_sms=raw_sms,
        raw_calls=raw_calls,
        raw_calendar=raw_calendar,
        tz=tz,
        start_date=start_date,
    )

    if refresh_dates is not None:
        always_refresh = set(refresh_dates)
    elif incomplete_dates is not None:
        always_refresh = incomplete_dates & dates_with_data & already_generated
    else:
        always_refresh = {today, today - timedelta(days=1)}
        if last_sync_date:
            always_refresh.add(last_sync_date)

    floor = _new_report_floor(today, already_generated)
    new_days = {d for d in dates_with_data - already_generated if d >= floor}
    candidates = sorted(new_days | always_refresh)

    result: list[tuple[date, bool]] = []
    for current in candidates:
        is_complete = (today - current).days <= 1
        result.append((current, is_complete))

    return result
