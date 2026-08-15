import json
from pathlib import Path

from legate.eval.runner import (
    OPUS5_POLYGLOT_RESOLVE,
    discover,
    format_report,
    run_suite,
)


def _mk_problem(root: Path, name: str, language: str) -> None:
    d = root / name
    d.mkdir(parents=True)
    (d / ".legate-problem.json").write_text(json.dumps(
        {"id": f"{language}/{name}", "language": language, "test_cmd": ["true"]}))


def test_discover_finds_all_problem_dirs(tmp_path):
    _mk_problem(tmp_path, "wordy", "python")
    _mk_problem(tmp_path, "clock", "go")
    assert len(discover(tmp_path)) == 2


def test_run_suite_aggregates_by_language_and_pct_of_opus(tmp_path):
    _mk_problem(tmp_path, "a", "python")
    _mk_problem(tmp_path, "b", "python")
    _mk_problem(tmp_path, "c", "go")

    def fake_solve(cfg, problem_dir, best_of, max_turns):
        # python problems pass, go fails
        return {"passed": "/a" in str(problem_dir) or "/b" in str(problem_dir),
                "evidence": "x"}

    res = run_suite(cfg=None, problems_root=tmp_path, solve_fn=fake_solve)
    assert res.total == 3 and res.passed == 2
    assert res.by_language["python"] == (2, 2)
    assert res.by_language["go"] == (0, 1)
    assert abs(res.pct_of_opus - (2 / 3) / OPUS5_POLYGLOT_RESOLVE) < 1e-9


def test_format_report_flags_target(tmp_path):
    _mk_problem(tmp_path, "a", "python")
    res = run_suite(cfg=None, problems_root=tmp_path,
                    solve_fn=lambda *a: {"passed": True})
    report = format_report(res)
    assert "% of Opus" in report and "python" in report
