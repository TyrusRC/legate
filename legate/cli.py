import argparse
import os
import sys
from pathlib import Path

from legate.config import Config, load_dotenv
from legate.hardware import detect
from legate.models import recommend

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


def build_parser() -> argparse.ArgumentParser:
    """The CLI's argument parser. Factored out so tests exercise the real parser
    (not a hand-rebuilt copy that can silently drift from this one)."""
    ap = argparse.ArgumentParser(
        prog="legate",
        description="Local agent for coding and cybersecurity work. Bare `legate` opens "
                    "the conversational agent; describe a task and it runs.",
    )
    # `cmd` is optional: bare `legate` opens the agent (like `claude` / `codex`).
    sub = ap.add_subparsers(dest="cmd", required=False)

    cp = sub.add_parser("chat", help="Conversational agent — describe a task, it runs (default)")
    cp.add_argument("request", nargs="*", help="One-shot request; omit for an interactive session")
    cp.add_argument("--cwd", default=None, help="Working directory (default: current)")
    cp.add_argument("--max-turns", type=int, default=20)

    sub.add_parser("doctor", help="Detect and report this machine's hardware (serving setup)")

    mp = sub.add_parser("models", help="Curated local-model catalog")
    msub = mp.add_subparsers(dest="models_cmd", required=True)
    msub.add_parser("recommend", help="Rank models by fit for this machine")
    return ap


def main() -> int:
    load_dotenv(Path.cwd() / ".env")
    args = build_parser().parse_args()

    if args.cmd == "doctor":
        return cmd_doctor()
    if args.cmd == "models":
        return cmd_models_recommend()

    # Default (bare `legate`) and explicit `chat` both open the agent.
    from legate.chat import chat_loop, handle
    cfg = Config.from_env()
    cwd = getattr(args, "cwd", None) or os.getcwd()
    mt = getattr(args, "max_turns", 20)
    request = getattr(args, "request", None)
    if request:  # one-shot: `legate chat "recon http://target/ for sqli"`
        print(handle(cfg, " ".join(request), cwd, max_turns=mt, stream=True))
        return 0
    return chat_loop(cfg, workdir=cwd, max_turns=mt)


if __name__ == "__main__":
    sys.exit(main())
