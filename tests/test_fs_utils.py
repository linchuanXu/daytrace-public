import shutil

from src.fs_utils import remove_tree_best_effort


def test_remove_tree_best_effort_returns_true_when_path_is_missing(tmp_path):
    assert remove_tree_best_effort(tmp_path / "missing", "missing test dir") is True


def test_remove_tree_best_effort_warns_and_returns_false_on_delete_failure(
    tmp_path,
    monkeypatch,
    capsys,
):
    target = tmp_path / "old-sync"
    target.mkdir()

    def fail_rmtree(path, onerror=None):
        raise PermissionError("locked by cloud sync")

    monkeypatch.setattr(shutil, "rmtree", fail_rmtree)

    assert remove_tree_best_effort(target, "旧 raw 同步快照") is False

    out = capsys.readouterr().out
    assert "跳过清理 旧 raw 同步快照" in out
    assert "locked by cloud sync" in out
