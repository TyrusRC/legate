import json
import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

from legate import sandbox


@dataclass
class Problem:
    id: str
    language: str
    dir: Path
    test_cmd: list[str]
    protect: list[str] = field(default_factory=list)  # files restored before scoring


@dataclass
class TestResult:
    __test__ = False  # not a pytest test class
    passed: bool
    output: str
    n_passed: int = 0
    n_total: int = 1


_PYTEST_PASS = re.compile(r"(\d+) passed")
_PYTEST_FAIL = re.compile(r"(\d+) (?:failed|error(?:ed)?)")
_PYTEST_SKIP = re.compile(r"(\d+) skipped")
_UNITTEST_RAN = re.compile(r"Ran (\d+) tests?")
_UNITTEST_FAILS = re.compile(r"(?:failures|errors)=(\d+)")
_UNITTEST_SKIP = re.compile(r"skipped=(\d+)")


def _parse_counts(output: str, passed: bool) -> tuple[int, int]:
    """Extract (n_passed, n_total) from pytest/unittest output for partial-credit
    ranking. Skipped tests count toward the total but NOT as passed, so a solution
    that skips its way to green doesn't earn full partial credit. Falls back to
    all-or-nothing when the format isn't recognized."""
    p = sum(int(m) for m in _PYTEST_PASS.findall(output))
    f = sum(int(m) for m in _PYTEST_FAIL.findall(output))
    sk = sum(int(m) for m in _PYTEST_SKIP.findall(output))
    if p or f or sk:
        return p, p + f + sk
    ran = _UNITTEST_RAN.search(output)
    if ran:
        total = int(ran.group(1))
        fails = sum(int(m) for m in _UNITTEST_FAILS.findall(output))
        skipped = sum(int(m) for m in _UNITTEST_SKIP.findall(output))
        return total - fails - skipped, total
    return (1, 1) if passed else (0, 1)


def load_problem(problem_dir: Path) -> Problem:
    """Load a problem from its `.legate-problem.json` manifest."""
    manifest = json.loads((problem_dir / ".legate-problem.json").read_text())
    return Problem(
        id=manifest["id"],
        language=manifest["language"],
        dir=problem_dir,
        test_cmd=manifest["test_cmd"],
        protect=manifest.get("protect", []),
    )


def restore_protected(problem: Problem, worktree_problem_dir: Path) -> None:
    """Restore `problem.protect` files (e.g. the test file) to their committed
    content in the worktree before scoring — so a candidate can't pass by editing
    the tests. Benchmark integrity: the model may touch solution files, not tests.
    """
    for rel in problem.protect:
        subprocess.run(
            ["git", "-C", str(worktree_problem_dir), "checkout", "HEAD", "--", rel],
            capture_output=True,
        )


def run_tests(problem: Problem, cwd: Path, sandboxed: bool = False) -> TestResult:
    """Run the problem's test command in `cwd`. Exit code 0 == all passed.

    When `sandboxed=True` the command is confined by bwrap (no network, writes
    limited to `cwd`) — REQUIRED when the code under test was model-generated
    (best-of-N / solve). Trusted fixtures may skip it.
    """
    if sandboxed:
        proc = sandbox.run(list(problem.test_cmd), cwd, allow_net=False, timeout=600)
    else:
        proc = subprocess.run(problem.test_cmd, cwd=str(cwd), capture_output=True, text=True)
    output = proc.stdout + proc.stderr
    passed = proc.returncode == 0
    n_passed, n_total = _parse_counts(output, passed)
    return TestResult(passed=passed, output=output, n_passed=n_passed, n_total=n_total)
