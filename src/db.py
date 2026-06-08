"""SQLite database for tracking sync history."""

import sqlite3
from datetime import date, datetime
from pathlib import Path
from typing import Optional

from .parser import UsageEvent


class SyncDB:
    def __init__(self, db_path: Path):
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(str(db_path))
        self._init()

    def _init(self):
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS syncs (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                sync_time   TEXT NOT NULL,
                device      TEXT,
                dates_generated TEXT
            )
        """)
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS day_reports (
                report_date TEXT PRIMARY KEY,
                generated_at TEXT NOT NULL,
                is_complete  INTEGER NOT NULL DEFAULT 0,
                sync_id      INTEGER
            )
        """)
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS usage_events (
                time       TEXT NOT NULL,
                event_type TEXT NOT NULL,
                package    TEXT NOT NULL,
                cls        TEXT NOT NULL DEFAULT '',
                extras     TEXT NOT NULL DEFAULT '',
                PRIMARY KEY (time, event_type, package, cls, extras)
            )
        """)
        self.conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_usage_events_time
            ON usage_events(time)
        """)
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS usage_coverage (
                start TEXT NOT NULL,
                end   TEXT NOT NULL,
                PRIMARY KEY (start, end)
            )
        """)
        self.conn.commit()

    def get_last_sync_date(self) -> Optional[date]:
        """Return the date of the most recently generated complete report."""
        row = self.conn.execute(
            "SELECT report_date FROM day_reports WHERE is_complete=1 ORDER BY report_date DESC LIMIT 1"
        ).fetchone()
        if row:
            return date.fromisoformat(row[0])
        return None

    def get_last_sync_generated_date(self) -> Optional[date]:
        """Return the last date listed by the latest sync run."""
        rows = self.conn.execute(
            "SELECT dates_generated FROM syncs ORDER BY id DESC"
        ).fetchall()
        for (dates_generated,) in rows:
            dates = [
                value.strip()
                for value in (dates_generated or "").split(",")
                if value.strip()
            ]
            if not dates:
                continue
            try:
                return date.fromisoformat(dates[-1])
            except ValueError:
                continue
        return None

    def get_generated_dates(self) -> set[date]:
        rows = self.conn.execute("SELECT report_date FROM day_reports").fetchall()
        return {date.fromisoformat(r[0]) for r in rows}

    def get_incomplete_dates(self, since: Optional[date] = None) -> set[date]:
        if since is None:
            rows = self.conn.execute(
                "SELECT report_date FROM day_reports WHERE is_complete=0",
            ).fetchall()
        else:
            rows = self.conn.execute(
                "SELECT report_date FROM day_reports WHERE is_complete=0 AND report_date >= ?",
                (since.isoformat(),),
            ).fetchall()
        return {date.fromisoformat(row[0]) for row in rows}

    def record_sync(self, device: str, dates: list[date]) -> int:
        cur = self.conn.execute(
            "INSERT INTO syncs (sync_time, device, dates_generated) VALUES (?, ?, ?)",
            (datetime.now().isoformat(), device, ",".join(d.isoformat() for d in dates)),
        )
        self.conn.commit()
        return cur.lastrowid

    def record_day(self, d: date, is_complete: bool, sync_id: Optional[int] = None):
        self.conn.execute(
            """INSERT OR REPLACE INTO day_reports (report_date, generated_at, is_complete, sync_id)
               VALUES (?, ?, ?, ?)""",
            (d.isoformat(), datetime.now().isoformat(), int(is_complete), sync_id),
        )
        self.conn.commit()

    def cache_usage_events(self, events: list[UsageEvent]) -> int:
        """Deduplicate and persist parsed usagestats events for future full-day reports."""
        before = self.conn.total_changes
        self.conn.executemany(
            """INSERT OR IGNORE INTO usage_events (time, event_type, package, cls, extras)
               VALUES (?, ?, ?, ?, ?)""",
            [
                (
                    ev.time.isoformat(),
                    ev.event_type,
                    ev.package,
                    ev.cls or "",
                    ev.extras or "",
                )
                for ev in events
            ],
        )
        self.conn.commit()
        return self.conn.total_changes - before

    def get_usage_events(self, start: datetime, end: datetime) -> list[UsageEvent]:
        rows = self.conn.execute(
            """SELECT time, event_type, package, cls, extras
               FROM usage_events
               WHERE time >= ? AND time < ?
               ORDER BY time""",
            (start.isoformat(), end.isoformat()),
        ).fetchall()
        events: list[UsageEvent] = []
        for time_str, event_type, package, cls, extras in rows:
            events.append(UsageEvent(
                time=datetime.fromisoformat(time_str),
                event_type=event_type,
                package=package,
                cls=cls or "",
                extras=extras or "",
            ))
        return events

    def cache_usage_coverage(self, start: Optional[datetime], end: Optional[datetime]):
        if not start or not end or end <= start:
            return
        self.conn.execute(
            "INSERT OR IGNORE INTO usage_coverage (start, end) VALUES (?, ?)",
            (start.isoformat(), end.isoformat()),
        )
        self.conn.commit()

    def get_usage_coverage(self, start: datetime, end: datetime) -> list[tuple[datetime, datetime]]:
        rows = self.conn.execute(
            """SELECT start, end
               FROM usage_coverage
               WHERE end > ? AND start < ?
               ORDER BY start""",
            (start.isoformat(), end.isoformat()),
        ).fetchall()
        intervals: list[tuple[datetime, datetime]] = []
        for s, e in rows:
            a = max(datetime.fromisoformat(s), start)
            b = min(datetime.fromisoformat(e), end)
            if b > a:
                intervals.append((a, b))
        return intervals

    def remove_day(self, d: date):
        """Remove a day_report record (used when cleaning up old data directories)."""
        self.conn.execute("DELETE FROM day_reports WHERE report_date=?", (d.isoformat(),))
        self.conn.commit()

    def close(self):
        self.conn.close()
