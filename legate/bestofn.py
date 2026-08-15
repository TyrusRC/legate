"""Best-of-N execution-grounded solve: generate N candidate patches, run the
REAL tests on each (the anchor), rank by grounded outcome, and — if the best
still fails — do one bounded Self-Debug repair seeded with the real traceback.

This is the highest-leverage capability multiplier for a small model (spec item
#1): resampling + grounded feedback, NOT verbal self-reflection. Each candidate
runs in its own git worktree so they can't corrupt each other or the repo.

NOTE (ceiling): candidates run sequentially here — one llama.cpp server, one slot.
Shared-prefix batching / parallel slots is the upgrade path; the ranking and
selection logic below is independent of how candidates are generated.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from legate.config import Config
from legate.eval.polyglot import load_problem, restore_protected, run_tests
from legate.goose import run_goose
from legate.worktree import collect_diff, worktree


@dataclass
class Candidate:
    idx: int
    diff: str
    passed: bool
    n_passed: int
    n_total: int
    output: str = ""            # test output (for repair grounding)
    repaired: bool = False
    error: str | None = None

    @property
    def diff_len(self) -> int:
        return len(self.diff)


def rank(candidates: list[Candidate]) -> list[Candidate]:
    """Rank by grounded signal: fully-passing first, then by #tests passed, then
    by a smaller diff (prefer the minimal change), then stable by index.

    Anchoring on REAL tests means a candidate that actually passes always beats
    one that merely looks plausible — no self-test can override a real failure.
    """
    return sorted(
        candidates,
        key=lambda c: (0 if c.passed else 1, -c.n_passed, c.diff_len, c.idx),
    )


def _run_one(cfg: Config, repo_root: Path, rel: Path, idx: int, task_text: str,
             max_turns: int) -> Candidate:
    with worktree(repo_root) as wt:
        wt_pdir = wt / rel
        res = run_goose(cfg, wt_pdir, task_text, max_turns)
        problem = load_problem(wt_pdir)
        restore_protected(problem, wt_pdir)              # no test-tampering
        diff = collect_diff(wt)                           # before tests, so .pyc etc.
        tr = run_tests(problem, wt_pdir, sandboxed=True)  #   don't pollute diff_len
    return Candidate(idx=idx, diff=diff, passed=tr.passed, n_passed=tr.n_passed,
                     n_total=tr.n_total, output=tr.output, error=res.error)


def best_of_n(cfg: Config, problem_dir: Path, n: int = 6, max_turns: int = 30,
              repair_rounds: int = 1) -> dict:
    """Generate N candidates, ground on tests, rank, optionally repair the best."""
    problem_dir = Path(problem_dir).resolve()
    repo_root = cfg.repo_root.resolve()
    rel = Path(".") if problem_dir == repo_root else problem_dir.relative_to(repo_root)
    problem = load_problem(problem_dir)

    base_task = (
        f"Solve the coding problem in this directory. Language: {problem.language}. "
        f"Edit the solution files so the tests pass."
    )

    candidates: list[Candidate] = [
        _run_one(cfg, repo_root, rel, i, base_task, max_turns) for i in range(n)
    ]

    ranked = rank(candidates)
    best = ranked[0]

    # Bounded Self-Debug repair: only if the best still fails and we have a real
    # traceback to feed back. Grounded repair, not blind resampling.
    rounds = 0
    while not best.passed and rounds < repair_rounds and best.output.strip():
        rounds += 1
        repair_task = (
            f"{base_task}\n\nA previous attempt failed its tests with this output:\n"
            f"```\n{best.output[-2000:]}\n```\n"
            f"Fix the root cause so all tests pass."
        )
        rep = _run_one(cfg, repo_root, rel, n + rounds - 1, repair_task, max_turns)
        rep.repaired = True
        candidates.append(rep)
        prev_passed = best.n_passed
        best = rank(candidates)[0]                 # appending can only keep/raise the top
        if not best.passed and best.n_passed <= prev_passed:
            break                                  # repair didn't improve — stop (Self-Debug gate)

    evidence = (f"passes {best.n_passed}/{best.n_total} tests"
                + (" (all)" if best.passed else "")
                + (" [after repair]" if best.repaired else ""))
    return {
        "problem": problem.id,
        "passed": best.passed,
        "winner_idx": best.idx,
        "n_candidates": len(candidates),
        "n_passed": best.n_passed,
        "n_total": best.n_total,
        "diff_len": best.diff_len,
        "evidence": evidence,
        "candidate_summary": [
            {"idx": c.idx, "passed": c.passed, "n_passed": c.n_passed,
             "diff_len": c.diff_len, "repaired": c.repaired}
            for c in candidates
        ],
    }
