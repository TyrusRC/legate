import shutil
from pathlib import Path

from legate.eval.polyglot import load_problem, run_tests

FIX = Path(__file__).parent / "fixtures" / "mini_python_problem"


def test_load_problem():
    p = load_problem(FIX)
    assert p.id == "mini/py"
    assert p.language == "python"


def test_run_tests_fail_then_pass(tmp_path):
    work = tmp_path / "w"
    shutil.copytree(FIX, work)
    p = load_problem(work)
    (work / "solution.py").write_text("def add(a, b): return 0\n")
    assert run_tests(p, work).passed is False
    (work / "solution.py").write_text("def add(a, b): return a + b\n")
    assert run_tests(p, work).passed is True
