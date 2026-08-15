import shutil
import subprocess
from pathlib import Path

import legate.bestofn as bofn
from legate.bestofn import Candidate, best_of_n, rank
from legate.config import Config
from legate.eval.polyglot import TestResult
from legate.goose_output import GooseResult

FIX = Path(__file__).parent / "fixtures" / "mini_python_problem"


def _c(idx, passed, n_passed, n_total=3, diff="x"):
    return Candidate(idx=idx, diff=diff, passed=passed, n_passed=n_passed, n_total=n_total)


def test_rank_prefers_passing_then_more_passed_then_smaller_diff():
    cands = [
        _c(0, False, 1),
        _c(1, False, 3, diff="xxxxx"),   # more passed, bigger diff
        _c(2, True, 3, diff="xx"),       # fully passing
        _c(3, False, 3, diff="xx"),      # same passed as #1 but smaller diff
    ]
    order = [c.idx for c in rank(cands)]
    assert order[0] == 2                 # passing wins
    assert order.index(3) < order.index(1)  # smaller diff breaks the tie


def _init_repo_with_problem(root: Path) -> None:
    shutil.copytree(FIX, root, dirs_exist_ok=True)
    for c in (["git", "init", "-q"], ["git", "config", "user.email", "t@t"],
              ["git", "config", "user.name", "t"], ["git", "add", "-A"],
              ["git", "commit", "-qm", "init"]):
        subprocess.run(c, cwd=root, check=True)


def test_best_of_n_selects_the_passing_candidate(tmp_path, monkeypatch):
    src = tmp_path / "src"
    src.mkdir()
    _init_repo_with_problem(src)
    cfg = Config.default()
    cfg.repo_root = src

    state = {"i": -1}

    def fake_run_goose(cfg, cwd, task_text, max_turns=30, tools=None):
        state["i"] += 1
        good = state["i"] == 2                     # only candidate #2 solves it
        (Path(cwd) / "solution.py").write_text(
            "def add(a, b): return a + b\n" if good else "def add(a, b): return 0\n")
        return GooseResult(total_tokens=1)

    def fake_run_tests(problem, cwd, sandboxed=False):
        ok = "a + b" in (Path(cwd) / "solution.py").read_text()
        return TestResult(passed=ok, output="" if ok else "AssertionError",
                          n_passed=3 if ok else 0, n_total=3)

    monkeypatch.setattr(bofn, "run_goose", fake_run_goose)
    monkeypatch.setattr(bofn, "run_tests", fake_run_tests)

    out = best_of_n(cfg, src, n=4, max_turns=5, repair_rounds=0)
    assert out["passed"] is True
    assert out["winner_idx"] == 2
    assert out["n_candidates"] == 4
    assert "3/3" in out["evidence"]


def test_best_of_n_repairs_when_all_fail(tmp_path, monkeypatch):
    src = tmp_path / "src"
    src.mkdir()
    _init_repo_with_problem(src)
    cfg = Config.default()
    cfg.repo_root = src

    state = {"i": -1}

    def fake_run_goose(cfg, cwd, task_text, max_turns=30, tools=None):
        state["i"] += 1
        # all initial candidates fail; the repair attempt (sees traceback) fixes it
        good = "previous attempt failed" in task_text
        (Path(cwd) / "solution.py").write_text(
            "def add(a, b): return a + b\n" if good else "def add(a, b): return 0\n")
        return GooseResult(total_tokens=1)

    def fake_run_tests(problem, cwd, sandboxed=False):
        ok = "a + b" in (Path(cwd) / "solution.py").read_text()
        return TestResult(passed=ok, output="" if ok else "AssertionError: expected 3",
                          n_passed=3 if ok else 0, n_total=3)

    monkeypatch.setattr(bofn, "run_goose", fake_run_goose)
    monkeypatch.setattr(bofn, "run_tests", fake_run_tests)

    out = best_of_n(cfg, src, n=2, max_turns=5, repair_rounds=1)
    assert out["passed"] is True
    assert "after repair" in out["evidence"]
