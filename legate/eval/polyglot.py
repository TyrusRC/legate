import json
import subprocess
from dataclasses import dataclass
from pathlib import Path


@dataclass
class Problem:
    id: str
    language: str
    dir: Path
    test_cmd: list[str]


@dataclass
class TestResult:
    passed: bool
    output: str


def load_problem(problem_dir: Path) -> Problem:
    """Load a problem from its `.legate-problem.json` manifest."""
    manifest = json.loads((problem_dir / ".legate-problem.json").read_text())
    return Problem(
        id=manifest["id"],
        language=manifest["language"],
        dir=problem_dir,
        test_cmd=manifest["test_cmd"],
    )


def run_tests(problem: Problem, cwd: Path) -> TestResult:
    """Run the problem's test command in `cwd`. Exit code 0 == all passed.

    NOTE: runs the test command directly on the host. Fine for trusted polyglot
    fixtures; untrusted model-generated code must be wrapped (bwrap/firejail) —
    added in Plan 02 before best-of-N sampling executes model output.
    """
    proc = subprocess.run(problem.test_cmd, cwd=str(cwd), capture_output=True, text=True)
    return TestResult(passed=proc.returncode == 0, output=proc.stdout + proc.stderr)
