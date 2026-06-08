from datetime import date, timedelta

import pytz

from src.gap import dates_needing_reports, phone_data_dates


def test_dates_needing_reports_refreshes_only_requested_existing_day():
    today = date(2026, 5, 16)
    already_generated = {date(2026, 5, 15), date(2026, 5, 16)}

    targets = dates_needing_reports(
        last_sync_date=date(2026, 5, 15),
        today=today,
        already_generated=already_generated,
        tz=pytz.timezone("Asia/Shanghai"),
        refresh_dates={date(2026, 5, 15)},
    )

    assert targets == [(date(2026, 5, 15), True)]


def test_dates_needing_reports_still_generates_missing_recent_day():
    today = date(2026, 5, 16)
    already_generated = {date(2026, 5, 15)}

    targets = dates_needing_reports(
        last_sync_date=date(2026, 5, 15),
        today=today,
        already_generated=already_generated,
        tz=pytz.timezone("Asia/Shanghai"),
        refresh_dates={date(2026, 5, 15)},
    )

    assert targets == [
        (date(2026, 5, 15), True),
        (date(2026, 5, 16), True),
    ]


def test_incomplete_intersection_with_phone_data_refreshes_matching_days():
    today = date(2026, 5, 19)
    yesterday = today - timedelta(days=1)
    older = date(2026, 5, 17)
    already_generated = {older, yesterday, today}
    helper_dates = {yesterday, today}
    incomplete = {yesterday, today}

    targets = dates_needing_reports(
        last_sync_date=older,
        today=today,
        already_generated=already_generated,
        tz=pytz.timezone("Asia/Shanghai"),
        start_date=older,
        extra_dates_with_data=helper_dates,
        incomplete_dates=incomplete,
    )

    target_set = {d for d, _ in targets}
    assert yesterday in target_set
    assert today in target_set
    assert older not in target_set


def test_incomplete_without_existing_report_still_creates_new_day():
    """Intersection only refreshes existing MDs; missing days are created separately."""
    today = date(2026, 5, 19)
    missing = date(2026, 5, 14)
    already_generated = {today}

    targets = dates_needing_reports(
        last_sync_date=today,
        today=today,
        already_generated=already_generated,
        tz=pytz.timezone("Asia/Shanghai"),
        start_date=missing,
        extra_dates_with_data={missing, today},
        incomplete_dates={missing, today},
    )

    target_set = {d for d, _ in targets}
    assert today in target_set
    assert missing in target_set


def test_new_reports_skip_ancient_helper_folders():
    today = date(2026, 5, 19)
    already_generated = {date(2026, 5, 15), date(2026, 5, 16)}
    helper_dates = {
        date(2025, 1, 1),
        date(2026, 5, 14),
        date(2026, 5, 15),
        date(2026, 5, 16),
        date(2026, 5, 17),
    }

    targets = dates_needing_reports(
        last_sync_date=None,
        today=today,
        already_generated=already_generated,
        tz=pytz.timezone("Asia/Shanghai"),
        start_date=date(2025, 12, 1),
        helper_dates=helper_dates,
        helper_only=True,
        incomplete_dates={date(2026, 5, 15), date(2026, 5, 16)},
    )

    target_set = {d for d, _ in targets}
    assert date(2025, 1, 1) not in target_set
    assert date(2026, 5, 14) in target_set
    assert date(2026, 5, 15) in target_set
    assert date(2026, 5, 16) in target_set


def test_helper_only_uses_helper_dates_not_sms_history():
    today = date(2026, 5, 19)
    sms = "Row: 0 date=1577836800000"  # 2020-01-01 in ms

    dates = phone_data_dates(
        today,
        helper_dates={date(2026, 5, 18)},
        helper_only=True,
        raw_sms=sms,
        tz=pytz.timezone("Asia/Shanghai"),
        start_date=date(2025, 12, 1),
    )

    assert date(2026, 5, 18) in dates
    assert date(2026, 5, 19) in dates
    assert date(2020, 1, 1) not in dates


def test_incomplete_without_phone_data_is_not_refreshed():
    today = date(2026, 5, 19)
    stale = date(2026, 5, 10)
    already_generated = {stale, today}

    targets = dates_needing_reports(
        last_sync_date=stale,
        today=today,
        already_generated=already_generated,
        tz=pytz.timezone("Asia/Shanghai"),
        start_date=stale,
        extra_dates_with_data={today},
        incomplete_dates={stale, today},
    )

    target_set = {d for d, _ in targets}
    assert today in target_set
    assert stale not in target_set
