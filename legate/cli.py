import argparse
import os
import sys
from pathlib import Path

from legate.bestofn import best_of_n
from legate.config import Config, load_dotenv
from legate.eval.polyglot import load_problem, restore_protected, run_tests
from legate.eval.runner import format_report, run_suite
from legate.goose import run_goose
from legate.hardware import detect
from legate.models import recommend
from legate.worktree import collect_diff, worktree

_BADGE = {"green": "🟢", "yellow": "🟡", "red": "🔴"}


def cmd_doctor() -> int:
    """Print detected hardware + the serving-relevant facts."""
    hw = detect()
    print("legate doctor — detected hardware")
    print(f"  GPU        : {hw.gpu_name or 'none detected'}")
    if hw.vram_total_mib is not None:
        print(f"  VRAM       : {hw.vram_total_mib} MiB total, {hw.vram_free_mib} MiB free"
              + ("  (WSL2: 'free' is unreliable — budget from total)" if hw.is_wsl2 else ""))
    print(f"  RAM        : {hw.ram_total_mib} MiB total, {hw.ram_avail_mib} MiB available")
    print(f"  CPU cores  : {hw.cores} usable")
    print(f"  WSL2       : {'yes' if hw.is_wsl2 else 'no'}")
    if hw.vram_total_mib is None:
        print("\n  No NVIDIA GPU found — v1 targets single-GPU serving; CPU-only is out of scope.")
    return 0


def cmd_pentest_plan(phase: str, query: str | None, task: str | None) -> int:
    """Plan a Praetor engagement: route its 390 tools down to a phase working set
    and emit the mounting recipe. Praetor location comes from LEGATE_PRAETOR_* env."""
    from legate.pentest import plan_engagement
    cmd = os.environ.get("LEGATE_PRAETOR_CMD")
    if not cmd:
        print("set LEGATE_PRAETOR_CMD (path to Praetor's MCP python) and optionally "
              "LEGATE_PRAETOR_ARGS / LEGATE_PRAETOR_CWD in .env", file=sys.stderr)
        return 2
    args = os.environ.get("LEGATE_PRAETOR_ARGS", "-m burpsuite_mcp").split()
    cwd = os.environ.get("LEGATE_PRAETOR_CWD")
    plan = plan_engagement(cmd, args, phase=phase, query=query, task=task, praetor_cwd=cwd)
    print(f"# engagement plan: phase={phase} query={query!r}")
    print(f"# routed {len(plan.selected_tools)} of {plan.total_tools} Praetor tools")
    print("selected: " + ", ".join(plan.selected_tools))
    print("\n--- recipe ---")
    print(plan.recipe_yaml(), end="")
    return 0


def cmd_models_recommend() -> int:
    """Rank the curated catalog for this machine with fit verdicts + serve flags."""
    hw = detect()
    print("legate models recommend — ranked for your machine\n")
    for r in recommend(hw):
        print(f"{_BADGE[r.verdict]} {r.spec.key}  [{r.spec.role}/{r.spec.kind}]")
        print(f"     {r.reason}")
        if r.flags:
            print(f"     serve: {r.flags[0]}")
        print()
    print("Pick a slot by setting LEGATE_MODEL_PATH in .env; MoE -ncmoe is auto-probed at serve time.")
    return 0


def solve(cfg: Config, problem_dir: Path, max_turns: int = 30) -> dict:
    """Solve one problem end-to-end in an isolated worktree and report the outcome.

    The problem must live inside `cfg.repo_root` and be committed, so the worktree
    already contains it — we operate on it in place (no copying, no git-metadata
    collisions). Goose runs in the problem's directory; the outcome is derived from
    the problem's tests plus the collected diff, never from Goose's JSON status.
    """
    problem_dir = Path(problem_dir).resolve()
    repo_root = cfg.repo_root.resolve()
    rel = Path(".") if problem_dir == repo_root else problem_dir.relative_to(repo_root)

    problem = load_problem(problem_dir)
    task_text = (
        f"Solve the coding problem in this directory. Language: {problem.language}. "
        f"Edit the solution files so the tests pass."
    )

    with worktree(repo_root) as wt:
        wt_problem_dir = wt / rel
        result = run_goose(cfg, wt_problem_dir, task_text, max_turns)
        wt_problem = load_problem(wt_problem_dir)
        restore_protected(wt_problem, wt_problem_dir)  # no test-tampering
        diff = collect_diff(wt)                          # before tests (avoid .pyc noise)
        test_res = run_tests(wt_problem, wt_problem_dir, sandboxed=True)

    return {
        "problem": problem.id,
        "passed": test_res.passed,
        "error": result.error,
        "tokens": result.total_tokens,
        "diff_len": len(diff),
    }


def main() -> int:
    load_dotenv(Path.cwd() / ".env")
    ap = argparse.ArgumentParser(prog="legate")
    sub = ap.add_subparsers(dest="cmd", required=True)

    sp = sub.add_parser("solve", help="Solve one problem end-to-end")
    sp.add_argument("problem_dir")
    sp.add_argument("--max-turns", type=int, default=30)
    sp.add_argument("--best-of", type=int, default=1, metavar="N",
                    help="Generate N candidates, ground on tests, pick the best (default 1)")
    sp.add_argument("--repair-rounds", type=int, default=1,
                    help="Bounded Self-Debug repair rounds when best-of-N still fails")

    sub.add_parser("doctor", help="Detect and report this machine's hardware")

    mp = sub.add_parser("models", help="Curated local-model catalog")
    msub = mp.add_subparsers(dest="models_cmd", required=True)
    msub.add_parser("recommend", help="Rank models by fit for this machine")

    ep = sub.add_parser("eval", help="Run the polyglot suite; report % of Opus 5")
    ep.add_argument("problems_root", nargs="?", default="problems")
    ep.add_argument("--best-of", type=int, default=1, metavar="N")
    ep.add_argument("--max-turns", type=int, default=40)

    pp = sub.add_parser("pentest", help="Drive Praetor (MCP)")
    ppsub = pp.add_subparsers(dest="pentest_cmd", required=True)
    plan = ppsub.add_parser("plan", help="Route Praetor tools + emit the mounting recipe")
    plan.add_argument("--phase", default="recon",
                      choices=["recon", "scan", "exploit", "post", "report"])
    plan.add_argument("--query", default=None, help="Cross-phase tool search (e.g. 'sql injection')")
    plan.add_argument("--task", default=None, help="Task prompt to embed in the recipe")

    args = ap.parse_args()

    if args.cmd == "doctor":
        return cmd_doctor()
    if args.cmd == "models":
        return cmd_models_recommend()
    if args.cmd == "pentest":
        return cmd_pentest_plan(args.phase, args.query, args.task)
    if args.cmd == "eval":
        res = run_suite(Config.from_env(), Path(args.problems_root),
                        best_of=args.best_of, max_turns=args.max_turns)
        print(format_report(res))
        return 0 if res.passed == res.total else 1

    cfg = Config.from_env()
    if args.best_of > 1:
        out = best_of_n(cfg, Path(args.problem_dir), n=args.best_of,
                        max_turns=args.max_turns, repair_rounds=args.repair_rounds)
    else:
        out = solve(cfg, Path(args.problem_dir), args.max_turns)
    print(out)
    return 0 if out["passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
