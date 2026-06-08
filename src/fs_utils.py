"""
Filesystem helpers for Windows/OneDrive-friendly cleanup.
"""

import os
import shutil
import stat
from pathlib import Path


def _make_writable(path: Path) -> None:
    """Best-effort chmod for read-only files/directories before deletion."""
    try:
        path.chmod(stat.S_IWRITE | stat.S_IREAD | stat.S_IEXEC)
    except OSError:
        pass


def remove_tree_best_effort(path: Path, description: str) -> bool:
    """
    Remove a directory tree without letting cleanup failures stop sync.

    OneDrive can leave old report/raw folders as read-only reparse points on
    Windows. These folders are cache/report cleanup targets, so a delete failure
    should be visible but non-fatal.
    """
    path = Path(path)
    if not path.exists():
        return True

    _make_writable(path)

    def onerror(func, failed_path, exc_info):
        failed = Path(failed_path)
        _make_writable(failed)
        try:
            func(failed_path)
        except OSError:
            raise

    try:
        shutil.rmtree(path, onerror=onerror)
        return True
    except OSError as exc:
        print(f"⚠️  跳过清理 {description}：{path}（{exc}）")
        return False
