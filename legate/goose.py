import json
import os
import subprocess
import tempfile
import time
from pathlib import Path

from legate.config import Config
from legate.goose_output import GooseResult, parse_stream_json
from legate.recipe import build_dev_recipe, render_recipe


def build_goose_argv(cfg: Config, recipe_path: Path | str, max_turns: int,
                     session: str | None = None, resume: bool = False) -> list[str]:
    """Build the `goose run` argv for a headless, non-interactive run.

    The task rides inside the recipe's `prompt` (Goose forbids `--recipe` with
    `--text`), so no `-t` here. Kept pure for unit-testing without invoking goose.

    With `session` the run joins a named Goose session so context carries across
    turns (`--resume` continues an existing one); without it, `--no-session` keeps
    the run isolated (one-shot requests / batch use).
    """
    argv = ["goose", "run"]
    if session:
        argv += ["--name", session]
        if resume:
            argv += ["--resume"]
    else:
        argv += ["--no-session"]
    argv += [
        "--provider", "openai",
        "--model", cfg.model,
        "--max-turns", str(max_turns),
        "--recipe", str(recipe_path),
        "--output-format", "stream-json",
    ]
    return argv


def _goose_env(cfg: Config) -> dict:
    """Env for a headless Goose run. GOOSE_MODE=auto is mandatory — without it a
    headless run blocks forever on tool approval."""
    host = cfg.endpoint.rsplit("/v1", 1)[0]
    return {
        **os.environ,
        "GOOSE_MODE": cfg.goose_mode,
        "GOOSE_PROVIDER": "openai",
        "GOOSE_MODEL": cfg.model,
        "OPENAI_HOST": host,
        "OPENAI_BASE_PATH": "v1/chat/completions",
    }


def run_recipe(cfg: Config, cwd: Path, recipe_text: str, max_turns: int = 30,
               on_event=None, session: str | None = None, resume: bool = False,
               timeout: float = 1200) -> GooseResult:
    """Run Goose headless in `cwd` against a prebuilt recipe and return the parsed
    result. This is the execution primitive shared by dev solves and Praetor
    engagements — the recipe (its extensions + prompt) is the only thing that
    differs. Failure is inferred from the exit code (or an error event), never
    from JSON status.

    If `on_event` is given, each parsed stream-json event is passed to it as it
    arrives (line-buffered), so callers can render assistant text and tool calls
    live instead of waiting for the whole run — this is what makes the chat REPL
    stream like Claude Code.

    `timeout` bounds the whole run. A small model can run away — generate without
    end on a hard task, or block forever when the model server dies mid-request —
    and Goose's own `--max-turns` doesn't cap a single runaway turn. On timeout the
    goose process is killed and a GooseResult with an error is returned, so one
    stuck attempt fails cleanly instead of hanging the agent."""
    fd, rpath = tempfile.mkstemp(suffix=".yaml", prefix="legate-recipe-")
    lines: list[str] = []
    stderr_text = ""
    code = 0
    try:
        with os.fdopen(fd, "w") as fh:
            fh.write(recipe_text)
        argv = build_goose_argv(cfg, rpath, max_turns, session, resume)
        if on_event is None:
            try:
                proc = subprocess.run(argv, cwd=str(cwd), env=_goose_env(cfg),
                                      capture_output=True, text=True, timeout=timeout)
                lines = proc.stdout.splitlines()
                stderr_text, code = proc.stderr, proc.returncode
            except subprocess.TimeoutExpired as e:
                lines = (e.stdout or "").splitlines() if isinstance(e.stdout, str) else []
                return _timeout_result(lines, timeout)
        else:
            proc = subprocess.Popen(argv, cwd=str(cwd), env=_goose_env(cfg),
                                    stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                    text=True, bufsize=1)
            deadline = time.monotonic() + timeout
            for line in proc.stdout:                    # stream as Goose emits
                lines.append(line)
                try:
                    on_event(json.loads(line))
                except Exception:
                    pass                                # a bad line / printer error never kills the run
                if time.monotonic() > deadline:             # runaway generation guard
                    proc.kill()
                    return _timeout_result(lines, timeout)
            try:
                proc.wait(timeout=max(1, deadline - time.monotonic()))
            except subprocess.TimeoutExpired:
                proc.kill()
                return _timeout_result(lines, timeout)
            stderr_text = proc.stderr.read()
            code = proc.returncode
    finally:
        os.unlink(rpath)
    result = parse_stream_json(lines)
    if code != 0 and result.error is None:
        result.error = f"goose exited {code}: {stderr_text[-500:]}"
    return result


def _timeout_result(lines: list[str], timeout: float) -> GooseResult:
    """Parse whatever streamed before the kill, and stamp a timeout error."""
    result = parse_stream_json(lines)
    result.error = (f"goose run exceeded {timeout:g}s and was killed (runaway "
                    "generation or dead model server)")
    return result


def run_goose(cfg: Config, cwd: Path, task_text: str, max_turns: int = 30,
              tools: list[str] | None = None, on_event=None,
              session: str | None = None, resume: bool = False) -> GooseResult:
    """Run Goose headless on a developer-editor recipe carrying `task_text` as its
    prompt and the tool allowlist (`tools`, default: edit/write/shell)."""
    return run_recipe(cfg, cwd, render_recipe(build_dev_recipe(task_text, tools)),
                      max_turns, on_event=on_event, session=session, resume=resume)
