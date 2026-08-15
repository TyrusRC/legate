import shutil
import subprocess
from pathlib import Path
from unittest.mock import patch

import legate.cli as cli
from legate.config import Config
from legate.goose_output import GooseResult

FIX = Path(__file__).parent / "fixtures" / "mini_python_problem"


def _init_repo_with_problem(root: Path) -> None:
    shutil.copytree(FIX, root, dirs_exist_ok=True)
    for c in (
        ["git", "init", "-q"],
        ["git", "config", "user.email", "t@t"],
        ["git", "config", "user.name", "t"],
        ["git", "add", "-A"],
        ["git", "commit", "-qm", "init"],
    ):
        subprocess.run(c, cwd=root, check=True)


def test_solve_reports_pass_when_goose_writes_correct_solution(tmp_path):
    src = tmp_path / "src"
    src.mkdir()
    _init_repo_with_problem(src)
    cfg = Config.default()
    cfg.repo_root = src

    def fake_run_goose(cfg, cwd, task_text, max_turns=30):
        (Path(cwd) / "solution.py").write_text("def add(a, b): return a + b\n")
        return GooseResult(messages=[{"role": "assistant", "content": "done"}], total_tokens=10)

    with patch.object(cli, "run_goose", fake_run_goose):
        out = cli.solve(cfg, src, max_turns=5)

    assert out["passed"] is True
    assert out["error"] is None
    assert out["tokens"] == 10
    assert out["diff_len"] > 0


def test_solve_reports_fail_when_solution_wrong(tmp_path):
    src = tmp_path / "src"
    src.mkdir()
    _init_repo_with_problem(src)
    cfg = Config.default()
    cfg.repo_root = src

    def fake_run_goose(cfg, cwd, task_text, max_turns=30):
        (Path(cwd) / "solution.py").write_text("def add(a, b): return 0\n")
        return GooseResult(total_tokens=5)

    with patch.object(cli, "run_goose", fake_run_goose):
        out = cli.solve(cfg, src, max_turns=5)

    assert out["passed"] is False
