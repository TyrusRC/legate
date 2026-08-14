import shutil
import subprocess
import tempfile
from contextlib import contextmanager
from pathlib import Path


@contextmanager
def worktree(base_repo: Path, base_ref: str = "HEAD"):
    """Create an isolated detached git worktree off `base_ref`, yield its path,
    and remove it on exit. Worktrees share the object store, so N of them are
    cheap — this is the isolation boundary for best-of-N candidate runs.
    """
    tmp = Path(tempfile.mkdtemp(prefix="legate-wt-"))
    subprocess.run(
        ["git", "-C", str(base_repo), "worktree", "add", "--detach", str(tmp), base_ref],
        check=True,
        capture_output=True,
    )
    try:
        yield tmp
    finally:
        subprocess.run(
            ["git", "-C", str(base_repo), "worktree", "remove", "--force", str(tmp)],
            capture_output=True,
        )
        shutil.rmtree(tmp, ignore_errors=True)


def collect_diff(worktree_path: Path) -> str:
    """Return `git diff` of uncommitted changes in a worktree."""
    return subprocess.run(
        ["git", "-C", str(worktree_path), "diff"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout
