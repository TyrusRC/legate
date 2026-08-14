import subprocess
from pathlib import Path

from legate.worktree import collect_diff, worktree


def _init_repo(tmp_path: Path) -> Path:
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.email", "t@t"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.name", "t"], cwd=tmp_path, check=True)
    (tmp_path / "a.txt").write_text("one\n")
    subprocess.run(["git", "add", "-A"], cwd=tmp_path, check=True)
    subprocess.run(["git", "commit", "-qm", "init"], cwd=tmp_path, check=True)
    return tmp_path


def test_worktree_isolates_and_collects_diff(tmp_path):
    repo = _init_repo(tmp_path)
    with worktree(repo) as wt:
        (wt / "a.txt").write_text("one\ntwo\n")
        diff = collect_diff(wt)
    assert "two" in diff
    # original repo untouched
    assert (repo / "a.txt").read_text() == "one\n"


def test_collect_diff_includes_new_untracked_files(tmp_path):
    repo = _init_repo(tmp_path)
    with worktree(repo) as wt:
        (wt / "solution.py").write_text("def add(a, b): return a + b\n")
        diff = collect_diff(wt)
    assert "solution.py" in diff
    assert "def add" in diff
