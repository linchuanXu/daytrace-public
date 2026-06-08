"""
Phone Tracker — main entry point.

Usage:
  python main.py                      # sync today + fill any gaps since last run
  python main.py --date 2026-05-14    # force regenerate a specific date
  python main.py --days 7             # regenerate last N days
  python main.py --no-raw             # don't save raw ADB dumps
"""

import argparse
import sys
import time
from datetime import date, datetime, timedelta
from pathlib import Path

import yaml
import pytz

ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT))

from src.adb import ADB, ADBError
from src.db import SyncDB
from src.gap import dates_needing_reports
from src.fs_utils import remove_tree_best_effort
from src.helper_context import load_helper_context_for_date
from src.helper_exports import (
    helper_export_dates,
    load_helper_usage_for_date,
    pull_helper_exports,
)
from src.parser import parse_usagestats
from src.writer import build_day_report, write_day_files, write_sync_raw


def load_config(path: Path = ROOT / "config.yaml") -> dict:
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)


def wait_before_success_exit(seconds: int = 10, sleeper=time.sleep) -> None:
    print(f"\n⏳ 成功完成，{seconds} 秒后关闭…", flush=True)
    sleeper(seconds)


def collect_all_raw(adb: ADB) -> dict[str, str]:
    """Pull all raw data from the device in one go."""
    print("  📡 拉取 usagestats (App使用事件)…", end=" ", flush=True)
    usagestats = adb.dumpsys("usagestats", timeout=90)
    print("✓")

    print("  📡 拉取短信记录…", end=" ", flush=True)
    sms = adb.content_query("content://sms")
    print("✓")

    print("  📡 拉取彩信记录…", end=" ", flush=True)
    try:
        mms = adb.content_query("content://mms")
        mms_addr = adb.content_query("content://mms/addr")
    except Exception:
        mms = ""
        mms_addr = ""
    print("✓")

    print("  📡 拉取通话记录…", end=" ", flush=True)
    calls = adb.content_query("content://call_log/calls")
    print("✓")

    print("  📡 拉取日历事件…", end=" ", flush=True)
    calendar = adb.content_query("content://com.android.calendar/events")
    print("✓")

    print("  📡 拉取 WiFi 历史…", end=" ", flush=True)
    wifi = adb.dumpsys("wifi", timeout=30)
    print("✓")

    print("  📡 拉取电量信息…", end=" ", flush=True)
    battery = adb.dumpsys("battery")
    batterystats = adb.dumpsys("batterystats", "--charged", timeout=60)
    print("✓")

    print("  📡 拉取当前通知…", end=" ", flush=True)
    notification = adb.dumpsys("notification", "--noredact", timeout=30)
    print("✓")

    return {
        "usagestats": usagestats,
        "sms": sms,
        "mms": mms,
        "mms_addr": mms_addr,
        "calls": calls,
        "calendar": calendar,
        "wifi": wifi,
        "battery": battery,
        "batterystats": batterystats,
        "notification": notification,
    }


def main():
    parser = argparse.ArgumentParser(description="Phone usage tracker via ADB")
    parser.add_argument("--date", help="Force regenerate a specific date (YYYY-MM-DD)")
    parser.add_argument("--days", type=int, help="Regenerate last N days")
    parser.add_argument("--no-raw", action="store_true", help="Don't save raw ADB dumps")
    parser.add_argument("--config", default=str(ROOT / "config.yaml"), help="Config file path")
    args = parser.parse_args()

    cfg = load_config(Path(args.config))
    tz  = pytz.timezone(cfg.get("timezone", "Asia/Shanghai"))
    today = datetime.now(tz).date()

    output_dir = ROOT / cfg["data"]["output_dir"]
    output_dir.mkdir(parents=True, exist_ok=True)
    db = SyncDB(ROOT / "db" / "tracker.db")

    # ── Enforce start_date: remove reports older than configured start ────────
    start_date_str = cfg["data"].get("start_date")
    if start_date_str:
        cfg_start_date = date.fromisoformat(start_date_str)
        removed = 0
        skipped = 0
        for day_dir in sorted(output_dir.iterdir()):
            if not day_dir.is_dir() or not day_dir.name[0].isdigit():
                continue
            try:
                d = date.fromisoformat(day_dir.name)
            except ValueError:
                continue
            if d < cfg_start_date:
                if remove_tree_best_effort(day_dir, "旧报告目录"):
                    db.remove_day(d)
                    removed += 1
                else:
                    skipped += 1
        if removed:
            print(f"🧹 已清理 {removed} 个早于 {start_date_str} 的旧报告目录")
        if skipped:
            print(f"⚠️  有 {skipped} 个旧报告目录暂时无法清理，已继续同步")

    # ── Connect ───────────────────────────────────────────────────────────────
    print("\n🔌 检查 ADB 连接…")
    adb = ADB(
        adb_path=cfg["adb"].get("path"),
        serial=cfg["adb"].get("serial"),
    )
    try:
        device_info = adb.check_connection()
    except ADBError as e:
        print(f"❌ {e}")
        sys.exit(1)
    print(f"✓ 已连接：{device_info['display']} (序列号: {device_info['serial']})")

    # ── Get user app list ─────────────────────────────────────────────────────
    print("  📋 获取用户App列表…", end=" ", flush=True)
    user_packages = adb.get_user_packages()
    print(f"✓ ({len(user_packages)} 个)")

    helper_cfg = cfg.get("helper", {})
    helper_enabled = bool(helper_cfg.get("enabled", False))
    helper_local_dir = ROOT / helper_cfg.get("local_export_dir", "data/_helper_exports")
    if helper_enabled and helper_cfg.get("pull_on_sync", True):
        remote_dir = helper_cfg.get("remote_export_dir", "/sdcard/PhoneTracker/export")
        print("  📥 拉取 Helper App 导出…", end=" ", flush=True)
        try:
            pull_helper_exports(adb, remote_dir, helper_local_dir)
            print("✓")
        except Exception as e:
            print(f"跳过（{e}）")

    helper_dates = helper_export_dates(helper_local_dir) if helper_enabled else set()
    if helper_dates:
        print(f"  📦 Helper 导出日期: {len(helper_dates)} 天")

    # ── Pull raw data first (needed for gap detection) ───────────────────────
    print("\n📲 开始拉取数据…")
    raw = collect_all_raw(adb)
    sync_time = datetime.now(tz)

    parsed_usage = parse_usagestats(raw.get("usagestats", ""), tz)
    new_events = db.cache_usage_events(parsed_usage.events)
    db.cache_usage_coverage(parsed_usage.events_range_start, parsed_usage.events_range_end)
    if parsed_usage.events_range_start and parsed_usage.events_range_end:
        print(
            f"  🧩 usagestats 覆盖: "
            f"{parsed_usage.events_range_start.strftime('%Y-%m-%d %H:%M')} ~ "
            f"{parsed_usage.events_range_end.strftime('%Y-%m-%d %H:%M')} "
            f"(新增事件 {new_events} 条)"
        )

    # Store raw once per sync (not per day)
    if cfg["data"].get("keep_raw", True):
        retain = cfg["data"].get("raw_retain_days", 7)
        write_sync_raw(raw, output_dir, sync_time, retain_days=retain)
    print()

    # ── Determine which dates to generate ────────────────────────────────────
    if args.date:
        target_dates = [(date.fromisoformat(args.date), True)]
    elif args.days:
        target_dates = [
            (today - timedelta(days=i), i <= 1)
            for i in range(args.days - 1, -1, -1)
        ]
    else:
        last_sync = db.get_last_sync_date()

        # "已生成" = 磁盘上确实存在 MD 文件，而不是仅看 DB 记录。
        # 这样删掉 MD 文件就能触发重新生成，符合直觉。
        already: set[date] = set()
        for day_dir in output_dir.iterdir():
            if not day_dir.is_dir() or not day_dir.name[0].isdigit():
                continue
            md_file = day_dir / f"{day_dir.name}.md"
            if md_file.exists():
                try:
                    already.add(date.fromisoformat(day_dir.name))
                except ValueError:
                    pass

        # Parse start_date from config (floor for report generation)
        start_date_str = cfg["data"].get("start_date")
        cfg_start_date = date.fromisoformat(start_date_str) if start_date_str else None
        incomplete_dates = db.get_incomplete_dates(cfg_start_date) & already

        target_dates = dates_needing_reports(
            last_sync, today, already,
            raw_sms=raw.get("sms", ""),
            raw_calls=raw.get("calls", ""),
            raw_calendar=raw.get("calendar", ""),
            tz=tz,
            start_date=cfg_start_date,
            helper_dates=helper_dates,
            helper_only=helper_enabled,
            incomplete_dates=incomplete_dates,
        )

    if not target_dates:
        print("✅ 所有日期已是最新，无需更新。")
        db.close()
        wait_before_success_exit()
        return

    print(f"📅 需要生成 {len(target_dates)} 天报告")
    print("   └─ 刷新：不完整 ∩ 手机有数据；新建：Helper 有导出但尚无报告")
    print()

    # ── Generate each day ─────────────────────────────────────────────────────
    sync_id = db.record_sync(device_info["display"], [d for d, _ in target_dates])
    generated: list[date] = []

    for target_date, is_complete in target_dates:
        day_start = tz.localize(datetime(target_date.year, target_date.month, target_date.day, 0, 0, 0))
        day_end = day_start + timedelta(days=1)
        usage_events = db.get_usage_events(day_start, day_end)
        usage_coverage = db.get_usage_coverage(day_start, day_end)
        helper_usage = (
            load_helper_usage_for_date(helper_local_dir, target_date, cfg, user_packages)
            if helper_enabled
            else None
        )
        helper_context = (
            load_helper_context_for_date(helper_local_dir, target_date)
            if helper_enabled
            else None
        )

        label = "📊 生成"
        print(f"  [{label}] {target_date.isoformat()}…", end=" ", flush=True)
        try:
            summary, markdown = build_day_report(
                target_date=target_date,
                is_complete=is_complete,
                device_info=device_info,
                raw=raw,
                config=cfg,
                tz=tz,
                user_packages=user_packages,
                usage_events=usage_events,
                usage_coverage=usage_coverage,
                helper_usage=helper_usage,
                helper_context=helper_context,
            )
            write_day_files(
                target_date=target_date,
                summary=summary,
                markdown=markdown,
                output_dir=output_dir,
            )
            db.record_day(target_date, bool(summary.get("is_complete")), sync_id)
            generated.append(target_date)
            apps_count = len(summary.get("apps", []))
            screen_str = summary["screen"]["total_str"]
            sms_count  = len(summary.get("sms", []))
            cov_label = summary.get("usagestats_coverage", {}).get("label", "未知")
            print(f"✓  覆盖:{cov_label}  屏幕:{screen_str}  App:{apps_count}个  短信:{sms_count}条")
        except Exception as e:
            print(f"❌ 生成失败: {e}")
            import traceback
            traceback.print_exc()

    db.close()

    # ── Summary ───────────────────────────────────────────────────────────────
    print(f"\n🎉 完成！生成了 {len(generated)} 天报告")
    print(f"📁 输出目录：{output_dir.resolve()}")
    if generated:
        newest = max(generated)
        print(f"📄 最新报告：{output_dir / newest.isoformat() / f'{newest.isoformat()}.md'}")
    wait_before_success_exit()


if __name__ == "__main__":
    main()
