from datetime import date

from src.db import SyncDB


def test_get_last_sync_generated_date_uses_last_date_from_latest_sync(tmp_path):
    db = SyncDB(tmp_path / "tracker.db")

    db.record_sync("phone", [date(2026, 5, 12), date(2026, 5, 13)])
    db.record_sync("phone", [date(2026, 5, 14), date(2026, 5, 15)])

    assert db.get_last_sync_generated_date() == date(2026, 5, 15)

    db.close()
