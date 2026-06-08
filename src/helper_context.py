"""Load Android helper app daily context exports."""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import Any, Optional


HELPER_CONTEXT_SOURCE = "helper_daily_context"


def _load_json(path: Path) -> Optional[dict[str, Any]]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, UnicodeDecodeError):
        return None
    return data if isinstance(data, dict) else None


def load_helper_context_for_date(export_root: Path, target_date: date) -> Optional[dict[str, Any]]:
    """Return normalized helper context for a date, or None when absent/invalid."""
    path = export_root / target_date.isoformat() / "daily_context.json"
    raw = _load_json(path)
    if not raw or raw.get("date") != target_date.isoformat():
        return None

    media = raw.get("media") if isinstance(raw.get("media"), dict) else {}
    device_state = raw.get("device_state") if isinstance(raw.get("device_state"), dict) else {}
    diagnostics = raw.get("diagnostics") if isinstance(raw.get("diagnostics"), dict) else {}
    snapshots = raw.get("location_snapshots")
    archived_snapshots = raw.get("archived_location_snapshots")
    items = media.get("items") if isinstance(media.get("items"), list) else []

    return {
        "schema_version": int(raw.get("schema_version") or 1),
        "date": target_date.isoformat(),
        "source": HELPER_CONTEXT_SOURCE,
        "raw_source": raw.get("source"),
        "source_status": raw.get("source_status", "ok"),
        "exported_at": raw.get("exported_at"),
        "media": {
            "photos_count": int(media.get("photos_count") or 0),
            "videos_count": int(media.get("videos_count") or 0),
            "audio_count": int(media.get("audio_count") or 0),
            "items": [item for item in items if isinstance(item, dict)],
        },
        "location_snapshots": [
            item for item in (snapshots if isinstance(snapshots, list) else [])
            if isinstance(item, dict)
        ],
        "archived_location_snapshots": [
            item for item in (archived_snapshots if isinstance(archived_snapshots, list) else [])
            if isinstance(item, dict)
        ],
        "device_state": device_state,
        "files": raw.get("files") if isinstance(raw.get("files"), dict) else {
            "created_or_modified_count": 0,
            "items": [],
        },
        "app_changes": raw.get("app_changes") if isinstance(raw.get("app_changes"), dict) else {
            "installed_count": 0,
            "updated_count": 0,
            "items": [],
        },
        "communication_backup": (
            raw.get("communication_backup")
            if isinstance(raw.get("communication_backup"), dict)
            else {
                "sms_count": 0,
                "call_count": 0,
                "calendar_count": 0,
                "contacts_updated_count": 0,
            }
        ),
        "notification_history": (
            raw.get("notification_history")
            if isinstance(raw.get("notification_history"), dict)
            else {"count": 0, "items": []}
        ),
        "accessibility_events": (
            raw.get("accessibility_events")
            if isinstance(raw.get("accessibility_events"), dict)
            else {"count": 0, "items": []}
        ),
        "diagnostics": diagnostics,
    }
