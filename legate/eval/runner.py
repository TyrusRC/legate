"""Eval suite runner: solve a set of polyglot problems and report an honest,
per-language resolve rate and a "% of Opus" figure — never a flattering average
over task types Legate can't do.

The comparison target is Claude Code + Opus 5 on the SAME Aider polyglot problem
set. We store the published Opus-class polyglot pass rate as a baseline constant;
`% of Opus = legate_resolve / opus_resolve`. Multi-file / long-horizon tasks are
outside the local model's envelope and are reported as such, not hidden.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

# Published Aider polyglot pass@2 for an Opus-class model on the 225-exercise set.
# NOTE: reference point for "% of Opus"; update from the live Aider leaderboard.
OPUS5_POLYGLOT_RESOLVE = 0.83


@dataclass
class SuiteResult:
    total: int
    passed: int
    by_language: dict[str, tuple[int, int]] = field(default_factory=dict)  # lang -> (passed, total)
    problems: list[dict] = field(default_factory=list)

    @property
    def resolve(self) -> float:
        return self.passed / self.total if self.total else 0.0

    @property
    def pct_of_opus(self) -> float:
        return self.resolve / OPUS5_POLYGLOT_RESOLVE if OPUS5_POLYGLOT_RESOLVE else 0.0


def discover(problems_root: Path) -> list[Path]:
    """Every directory under `problems_root` holding a `.legate-problem.json`."""
    root = Path(problems_root)
    return sorted(p.parent for p in root.rglob(".legate-problem.json"))


def run_suite(cfg, problems_root: Path, best_of: int = 1, max_turns: int = 40,
              solve_fn=None) -> SuiteResult:
    """Run each discovered problem and aggregate resolve rate by language.

    `solve_fn(cfg, problem_dir, best_of, max_turns) -> dict` is injectable so the
    aggregation is testable without a live model. Default wires the real solver.
    """
    if solve_fn is None:
        solve_fn = _default_solve
    from legate.eval.polyglot import load_problem

    dirs = discover(problems_root)
    res = SuiteResult(total=len(dirs), passed=0)
    for d in dirs:
        lang = load_problem(d).language
        out = solve_fn(cfg, d, best_of, max_turns)
        ok = bool(out.get("passed"))
        res.passed += int(ok)
        p, t = res.by_language.get(lang, (0, 0))
        res.by_language[lang] = (p + int(ok), t + 1)
        res.problems.append({"dir": str(d), "language": lang, "passed": ok,
                             "evidence": out.get("evidence", "")})
    return res


def _default_solve(cfg, problem_dir: Path, best_of: int, max_turns: int) -> dict:
    from legate.bestofn import best_of_n
    from legate.cli import solve
    if best_of > 1:
        return best_of_n(cfg, problem_dir, n=best_of, max_turns=max_turns)
    return solve(cfg, problem_dir, max_turns)


def format_report(res: SuiteResult) -> str:
    lines = [
        "Legate eval — polyglot resolve vs Claude Code + Opus 5",
        f"  problems       : {res.total}",
        f"  resolved       : {res.passed}  ({res.resolve:.0%})",
        f"  Opus-5 baseline: {OPUS5_POLYGLOT_RESOLVE:.0%} (published polyglot pass@2)",
        f"  % of Opus      : {res.pct_of_opus:.0%}   "
        f"[{'MEETS' if res.pct_of_opus >= 0.5 else 'below'} 50-60% target]",
        "  by language:",
    ]
    for lang, (p, t) in sorted(res.by_language.items()):
        lines.append(f"    {lang:10} {p}/{t}")
    lines.append("  NOTE: winnable envelope only (localized/≤2-file). Multi-file &")
    lines.append("        long-horizon tasks are out of envelope and not sampled here.")
    return "\n".join(lines)
