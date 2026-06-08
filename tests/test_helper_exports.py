import sys
from datetime import date
from pathlib import Path

import pytest
import pytz

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.helper_context import load_helper_context_for_date
from src.helper_exports import (
    helper_export_dates,
    helper_export_is_complete,
    load_helper_usage_for_date,
    pull_helper_exports,
)
from src.writer import build_day_report
FIXTURES = Path(__file__).parent / "fixtures" / "helper_exports"


def _config() -> dict:
    return {
        "filter": {
            "system_prefixes": ["com.example."],
            "force_include": [],
        }
    }


def test_helper_export_is_complete_for_past_full_natural_day():
    export = load_helper_usage_for_date(FIXTURES, date(2026, 3, 16), _config())
    today = date(2026, 5, 19)

    assert helper_export_is_complete(export, date(2026, 3, 16), today) is True
    assert helper_export_is_complete(export, date(2026, 3, 16), date(2026, 3, 16)) is False


def test_load_helper_usage_normalizes_apps_and_metadata():
    export = load_helper_usage_for_date(FIXTURES, date(2026, 3, 16), _config())

    assert export is not None
    assert export["date"] == "2026-03-16"
    assert export["source"] == "helper_usage_stats"
    assert export["query_range"]["start"] == "2026-03-16T00:00:00+08:00"
    assert export["has_data"] is True
    assert export["app_count"] == 1
    assert export["apps"] == [
        {
            "package": "com.tencent.mm",
            "name": "微信",
            "seconds": 3600,
            "time_str": "1h 00m",
            "visible_seconds": 3720,
            "visible_time_str": "1h 02m",
            "sessions": 42,
            "last_used": "2026-03-16T22:30:12+08:00",
            "last_used_str": "22:30:12",
            "source": "helper_usage_stats",
        }
    ]


def test_load_helper_usage_v2_preserves_diagnostics_and_cache_source():
    export = load_helper_usage_for_date(FIXTURES, date(2026, 5, 6), _config())

    assert export is not None
    assert export["schema_version"] == 2
    assert export["source_status"] == "cached_only"
    assert export["recorded_by_helper"] is True
    assert export["raw_system_has_data"] is False
    assert export["cache_has_data"] is True
    assert export["diagnostics"]["exported_app_count"] == 1
    assert export["apps"][0]["source"] == "helper_cache"
    assert export["apps"][0]["recorded_by_helper"] is True


def test_load_helper_usage_filters_cross_day_usage_stats_buckets(tmp_path):
    day_dir = tmp_path / "2026-05-18"
    day_dir.mkdir()
    (day_dir / "usage_stats.json").write_text(
        """{
  "schema_version": 2,
  "date": "2026-05-18",
  "source_status": "ok",
  "apps": [
    {
      "package": "com.dragon.read",
      "name": "番茄免费小说",
      "total_foreground_seconds": 23154,
      "total_visible_seconds": 23217,
      "first_time_stamp": "2026-05-17T11:31:49.54+08:00",
      "last_time_stamp": "2026-05-18T11:31:49.539+08:00",
      "last_used": "2026-05-18T01:21:39.109+08:00",
      "launch_count": 42
    },
    {
      "package": "com.tencent.mm",
      "name": "微信",
      "total_foreground_seconds": 2511,
      "total_visible_seconds": 2539,
      "first_time_stamp": "2026-05-18T11:31:54.654+08:00",
      "last_time_stamp": "2026-05-18T17:40:50.03+08:00",
      "last_used": "2026-05-18T16:53:16.388+08:00",
      "launch_count": 34
    }
  ],
  "diagnostics": {}
}""",
        encoding="utf-8",
    )

    export = load_helper_usage_for_date(tmp_path, date(2026, 5, 18), _config())

    assert export is not None
    assert [app["package"] for app in export["apps"]] == ["com.tencent.mm"]
    assert export["diagnostics"]["skipped_cross_day_bucket_count"] == 1


def test_load_helper_usage_accepts_exact_next_midnight_boundary(tmp_path):
    day_dir = tmp_path / "2026-05-17"
    day_dir.mkdir()
    (day_dir / "usage_stats.json").write_text(
        """{
  "schema_version": 2,
  "date": "2026-05-17",
  "source_status": "ok",
  "apps": [
    {
      "package": "com.dragon.read",
      "name": "番茄免费小说",
      "total_foreground_seconds": 17426,
      "first_time_stamp": "2026-05-17T01:44:25.323+08:00",
      "last_time_stamp": "2026-05-18T00:00:00+08:00",
      "source": "helper_usage_events"
    },
    {
      "package": "com.example.bad",
      "name": "Bad Cross Day",
      "total_foreground_seconds": 999,
      "first_time_stamp": "2026-05-17T23:50:00+08:00",
      "last_time_stamp": "2026-05-18T00:00:01+08:00",
      "source": "helper_system_query"
    }
  ],
  "diagnostics": {}
}""",
        encoding="utf-8",
    )

    export = load_helper_usage_for_date(
        tmp_path,
        date(2026, 5, 17),
        _config(),
        user_packages=["com.dragon.read", "com.example.bad"],
    )

    assert export is not None
    assert [app["package"] for app in export["apps"]] == ["com.dragon.read"]
    assert export["apps"][0]["seconds"] == 17426
    assert export["diagnostics"]["skipped_cross_day_bucket_count"] == 1


def test_load_helper_usage_returns_none_for_missing_or_malformed_files(tmp_path):
    assert load_helper_usage_for_date(tmp_path, date(2026, 3, 16), _config()) is None

    malformed_dir = tmp_path / "2026-03-16"
    malformed_dir.mkdir()
    (malformed_dir / "usage_stats.json").write_text("{not json", encoding="utf-8")

    assert load_helper_usage_for_date(tmp_path, date(2026, 3, 16), _config()) is None


def test_helper_export_dates_returns_only_valid_usage_export_days(tmp_path):
    (tmp_path / "2026-03-16").mkdir()
    (tmp_path / "2026-03-16" / "usage_stats.json").write_text("{}", encoding="utf-8")
    (tmp_path / "not-a-date").mkdir()
    (tmp_path / "2026-03-17").mkdir()

    assert helper_export_dates(tmp_path) == {date(2026, 3, 16)}


def test_helper_export_dates_includes_daily_context_only_days(tmp_path):
    (tmp_path / "2026-05-16").mkdir()
    (tmp_path / "2026-05-16" / "daily_context.json").write_text("{}", encoding="utf-8")

    assert helper_export_dates(tmp_path) == {date(2026, 5, 16)}


def test_pull_helper_exports_copies_remote_contents_into_local_root(tmp_path):
    class FakeADB:
        def __init__(self):
            self.calls = []

        def pull(self, remote, local, timeout=120):
            self.calls.append((remote, local, timeout))

    adb = FakeADB()

    pull_helper_exports(adb, "/sdcard/PhoneTracker/export", tmp_path)

    assert adb.calls == [("/sdcard/PhoneTracker/export/.", str(tmp_path), 120)]


def test_build_day_report_renders_helper_ranking_without_full_event_coverage():
    tz = pytz.timezone("Asia/Shanghai")
    helper_usage = load_helper_usage_for_date(FIXTURES, date(2026, 3, 16), _config())

    summary, markdown = build_day_report(
        target_date=date(2026, 3, 16),
        is_complete=False,
        device_info={"display": "Test Phone"},
        raw={
            "usagestats": "",
            "sms": "",
            "mms": "",
            "mms_addr": "",
            "calls": "",
            "calendar": "",
            "wifi": "",
            "battery": "",
            "batterystats": "",
            "notification": "",
        },
        config=_config(),
        tz=tz,
        user_packages=["com.tencent.mm"],
        usage_events=[],
        usage_coverage=[],
        helper_usage=helper_usage,
    )

    assert summary["usagestats_coverage"]["is_full_day"] is False
    assert summary["apps"] == []
    assert summary["helper_usage_stats"]["source"] == "helper_usage_stats"
    assert summary["helper_usage_stats"]["apps"][0]["package"] == "com.tencent.mm"
    assert "## 📱 App 使用排行（来自手机端 UsageStatsManager）" in markdown
    assert "| 1 | 微信 | 1h 00m | 42 次 | 22:30:12 |" in markdown
    assert "helper daily aggregates" not in summary["usagestats_coverage"].get("label", "")


def test_build_day_report_keeps_period_totals_out_of_daily_markdown():
    tz = pytz.timezone("Asia/Shanghai")
    raw_usagestats = """
user=0
In-memory daily stats
timeRange="2026-03-16 00:00 – 2026-03-17 00:00"
package=com.tencent.mm totalTimeUsed="00:30" lastTimeUsed="2026-03-16 12:00:00" totalTimeVisible="00:30" lastTimeVisible="2026-03-16 12:00:00" lastTimeComponentUsed="2026-03-16 12:00:00" totalTimeFS="00:00" lastTimeFS="2026-03-16 12:00:00" appLaunchCount=1 errorCount=0
timeRange="2026-03-11 00:00 – 2026-03-18 00:00"
package=com.tencent.mm totalTimeUsed="3:00:00" lastTimeUsed="2026-03-16 12:00:00" totalTimeVisible="3:00:00" lastTimeVisible="2026-03-16 12:00:00" lastTimeComponentUsed="2026-03-16 12:00:00" totalTimeFS="00:00" lastTimeFS="2026-03-16 12:00:00" appLaunchCount=8 errorCount=0
timeRange="2026-03-01 00:00 – 2026-03-31 00:00"
package=com.tencent.mm totalTimeUsed="12:00:00" lastTimeUsed="2026-03-16 12:00:00" totalTimeVisible="12:00:00" lastTimeVisible="2026-03-16 12:00:00" lastTimeComponentUsed="2026-03-16 12:00:00" totalTimeFS="00:00" lastTimeFS="2026-03-16 12:00:00" appLaunchCount=30 errorCount=0
timeRange="2026-01-01 00:00 – 2026-12-31 00:00"
package=com.tencent.mm totalTimeUsed="100:00:00" lastTimeUsed="2026-03-16 12:00:00" totalTimeVisible="100:00:00" lastTimeVisible="2026-03-16 12:00:00" lastTimeComponentUsed="2026-03-16 12:00:00" totalTimeFS="00:00" lastTimeFS="2026-03-16 12:00:00" appLaunchCount=100 errorCount=0
"""

    summary, markdown = build_day_report(
        target_date=date(2026, 3, 16),
        is_complete=False,
        device_info={"display": "Test Phone"},
        raw={
            "usagestats": raw_usagestats,
            "sms": "",
            "mms": "",
            "mms_addr": "",
            "calls": "",
            "calendar": "",
            "wifi": "",
            "battery": "",
            "batterystats": "",
            "notification": "",
        },
        config=_config(),
        tz=tz,
        user_packages=["com.tencent.mm"],
        usage_events=[],
        usage_coverage=[],
        helper_usage=None,
    )

    assert summary["interval_stats"]["weekly"]["apps"]
    assert summary["interval_stats"]["monthly"]["apps"]
    assert summary["interval_stats"]["yearly"]["apps"]
    assert "本周累计 App 用时" not in markdown
    assert "本月累计 App 用时" not in markdown
    assert "年度累计 App 用时" not in markdown


def test_build_day_report_explains_empty_helper_export():
    tz = pytz.timezone("Asia/Shanghai")
    helper_usage = load_helper_usage_for_date(FIXTURES, date(2026, 3, 17), _config())

    summary, markdown = build_day_report(
        target_date=date(2026, 3, 17),
        is_complete=False,
        device_info={"display": "Test Phone"},
        raw={
            "usagestats": "",
            "sms": "",
            "mms": "",
            "mms_addr": "",
            "calls": "",
            "calendar": "",
            "wifi": "",
            "battery": "",
            "batterystats": "",
            "notification": "",
        },
        config=_config(),
        tz=tz,
        user_packages=["com.tencent.mm"],
        usage_events=[],
        usage_coverage=[],
        helper_usage=helper_usage,
    )

    assert summary["helper_usage_stats"]["source_status"] == "empty_from_system"
    assert "## Helper App 导出诊断" in markdown
    assert "Android returned no daily app records" in markdown


def test_build_day_report_marks_complete_from_helper_full_day_query_range():
    helper_usage = {
        "date": "2026-05-15",
        "source_status": "ok",
        "query_range": {
            "start": "2026-05-15T00:00:00+08:00",
            "end": "2026-05-16T00:00:00+08:00",
        },
    }
    summary, markdown = build_day_report(
        target_date=date(2026, 5, 15),
        is_complete=False,
        device_info={"display": "Test Phone"},
        raw={"usagestats": "", "sms": "", "mms": "", "mms_addr": "", "calls": "", "calendar": "", "wifi": "", "battery": "", "batterystats": "", "notification": ""},
        config=_config(),
        tz=pytz.timezone("Asia/Shanghai"),
        user_packages=[],
        usage_events=[],
        usage_coverage=[],
        helper_usage=helper_usage,
        helper_context=None,
    )

    assert summary["is_complete"] is True
    assert "is_complete: true" in markdown
    assert "完整日标记来自 Helper 导出" in markdown


def test_build_day_report_hides_export_time_location_on_old_days(tmp_path):
    day_dir = tmp_path / "2020-01-01"
    day_dir.mkdir()
    (day_dir / "daily_context.json").write_text(
        """{
  "date": "2020-01-01",
  "media": {"photos_count": 0, "videos_count": 0, "audio_count": 0, "items": []},
  "location_snapshots": [
    {"time": "2026-05-19T09:00:00+08:00", "provider": "network", "latitude": 22.7, "longitude": 114.0, "accuracy_m": 20}
  ],
  "archived_location_snapshots": [],
  "device_state": {"battery_level": 50, "charging": false},
  "files": {"created_or_modified_count": 0, "items": []},
  "app_changes": {"installed_count": 0, "updated_count": 0, "items": []},
  "communication_backup": {"sms_count": 0, "call_count": 0, "calendar_count": 0, "contacts_updated_count": 0},
  "notification_history": {"count": 0, "items": []},
  "accessibility_events": {"count": 0, "items": []},
  "diagnostics": {}
}""",
        encoding="utf-8",
    )
    helper_context = load_helper_context_for_date(tmp_path, date(2020, 1, 1))

    _, markdown = build_day_report(
        target_date=date(2020, 1, 1),
        is_complete=False,
        device_info={"display": "Test Phone"},
        raw={"usagestats": "", "sms": "", "mms": "", "mms_addr": "", "calls": "", "calendar": "", "wifi": "", "battery": "", "batterystats": "", "notification": ""},
        config=_config(),
        tz=pytz.timezone("Asia/Shanghai"),
        user_packages=[],
        usage_events=[],
        usage_coverage=[],
        helper_usage=None,
        helper_context=helper_context,
    )

    assert "22.7" not in markdown
    assert "位置快照" not in markdown
    assert "设备状态" not in markdown


def test_build_day_report_renders_helper_daily_context(tmp_path):
    day_dir = tmp_path / "2026-05-16"
    day_dir.mkdir()
    (day_dir / "daily_context.json").write_text(
        """{
  "schema_version": 1,
  "date": "2026-05-16",
  "source": "PhoneTrackerHelper",
  "source_status": "partial",
  "exported_at": "2026-05-16T12:00:00+08:00",
  "media": {
    "photos_count": 2,
    "videos_count": 1,
    "audio_count": 1,
    "items": [
      {"type": "photo", "time": "2026-05-16T09:10:00+08:00", "display_name": "IMG_1.jpg", "relative_path": "DCIM/Camera/", "latitude": 31.1, "longitude": 121.2},
      {"type": "video", "time": "2026-05-16T10:20:00+08:00", "display_name": "VID_1.mp4", "relative_path": "DCIM/Camera/", "duration_seconds": 12},
      {"type": "audio", "time": "2026-05-16T10:25:00+08:00", "display_name": "REC_1.m4a", "relative_path": "Recordings/", "duration_seconds": 60}
    ]
  },
  "location_snapshots": [
    {"time": "2026-05-16T12:00:00+08:00", "provider": "gps", "latitude": 31.2, "longitude": 121.3, "accuracy_m": 15.0}
  ],
  "archived_location_snapshots": [
    {"time": "2026-05-16T08:00:00+08:00", "provider": "network", "latitude": 31.0, "longitude": 121.0, "reason": "periodic_location_worker"}
  ],
  "device_state": {
    "battery_level": 88,
    "charging": true,
    "wifi_ssid": "HomeWiFi",
    "available_storage_mb": 1024
  },
  "files": {
    "created_or_modified_count": 2,
    "items": [
      {"time": "2026-05-16T11:00:00+08:00", "name": "receipt.pdf", "relative_path": "Download/", "size_bytes": 1234}
    ]
  },
  "app_changes": {
    "installed_count": 1,
    "updated_count": 2,
    "items": [
      {"package": "com.example.newapp", "name": "New App", "event": "installed"}
    ]
  },
  "communication_backup": {
    "sms_count": 3,
    "call_count": 1,
    "calendar_count": 2,
    "contacts_updated_count": 4
  },
  "notification_history": {
    "count": 5,
    "items": [
      {"time": "2026-05-16T12:10:00+08:00", "package": "com.tencent.mm", "event": "posted", "title": "微信"}
    ]
  },
  "accessibility_events": {
    "count": 7,
    "items": [
      {"time": "2026-05-16T12:11:00+08:00", "package": "com.tencent.mm", "event_type": "TYPE_WINDOW_STATE_CHANGED", "text": "微信"}
    ]
  },
  "diagnostics": {
    "media": {"status": "ok"},
    "location": {"status": "ok"},
    "device_state": {"status": "ok"},
    "files": {"status": "ok"},
    "apps": {"status": "ok"},
    "sms_backup": {"status": "ok"},
    "calls_backup": {"status": "ok"},
    "calendar_backup": {"status": "ok"},
    "contacts_backup": {"status": "ok"}
  }
}""",
        encoding="utf-8",
    )
    helper_context = load_helper_context_for_date(tmp_path, date(2026, 5, 16))

    summary, markdown = build_day_report(
        target_date=date(2026, 5, 16),
        is_complete=False,
        device_info={"display": "Test Phone"},
        raw={
            "usagestats": "",
            "sms": "",
            "mms": "",
            "mms_addr": "",
            "calls": "",
            "calendar": "",
            "wifi": "",
            "battery": "",
            "batterystats": "",
            "notification": "",
        },
        config=_config(),
        tz=pytz.timezone("Asia/Shanghai"),
        user_packages=[],
        usage_events=[],
        usage_coverage=[],
        helper_usage=None,
        helper_context=helper_context,
    )

    assert summary["helper_daily_context"]["media"]["photos_count"] == 2
    assert summary["helper_daily_context"]["media"]["audio_count"] == 1
    assert summary["helper_daily_context"]["location_snapshots"][0]["provider"] == "gps"
    assert summary["helper_daily_context"]["archived_location_snapshots"][0]["reason"] == "periodic_location_worker"
    assert summary["helper_daily_context"]["files"]["created_or_modified_count"] == 2
    assert summary["helper_daily_context"]["app_changes"]["installed_count"] == 1
    assert summary["helper_daily_context"]["communication_backup"]["sms_count"] == 3
    assert summary["helper_daily_context"]["notification_history"]["count"] == 5
    assert summary["helper_daily_context"]["accessibility_events"]["count"] == 7
    assert "## 🧩 Helper 上下文补强" in markdown
    assert "照片 2 张，视频 1 段" in markdown
    assert "音频/录音 1 个" in markdown
    assert "文件新增/修改 2 个" in markdown
    assert "App 安装 1 个，更新 2 个" in markdown
    assert "APK 备份源：短信 3 条，通话 1 次，日历 2 个，联系人更新 4 个" in markdown
    assert "通知历史 5 条" in markdown
    assert "无障碍事件 7 条" in markdown
    assert "HomeWiFi" not in markdown
    assert "31.200000, 121.300000" not in markdown
    assert "当日归档位置 1 条" in markdown
    assert "## Helper 上下文明细" in markdown
    assert "### 媒体文件" in markdown
    assert "IMG_1.jpg" in markdown
    assert "### 位置记录（当日归档）" in markdown
    assert "periodic_location_worker" in markdown
    assert "### 文件活动" in markdown
    assert "receipt.pdf" in markdown
    assert "### App 变化" in markdown
    assert "New App" in markdown
    assert "### 通知历史" in markdown
    assert "### 无障碍事件" in markdown
    assert "TYPE_WINDOW_STATE_CHANGED" in markdown
    assert "### Helper 模块诊断" in markdown

