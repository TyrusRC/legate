import os
import subprocess
from pathlib import Path

from legate.config import Config
from legate.goose_output import GooseResult, parse_stream_json


def build_goose_argv(cfg: Config, task_text: str, recipe: Path, max_turns: int) -> list[str]:
    """Build the `goose run` argv for a headless, non-interactive run.

    Kept pure (no side effects) so it is unit-testable without invoking goose.
    """
    return [
        "goose",
        "run",
        "--no-session",
        "--provider",
        "openai",
        "--model",
        cfg.model,
        "--max-turns",
        str(max_turns),
        "--recipe",
        str(recipe),
        "--output-format",
        "stream-json",
        "-t",
        task_text,
    ]


def run_goose(
    cfg: Config, cwd: Path, task_text: str, recipe: Path, max_turns: int = 30
) -> GooseResult:
    """Run Goose headless in `cwd` and return the parsed result.

    GOOSE_MODE=auto is mandatory — without it a headless run blocks forever on
    tool-approval prompts. The model endpoint is passed via the OpenAI-compatible
    env vars Goose reads. Failure is inferred from a non-zero exit code (or an
    emitted error event), never from the JSON status.
    """
    host = cfg.endpoint.rsplit("/v1", 1)[0]
    env = {
        **os.environ,
        "GOOSE_MODE": cfg.goose_mode,
        "GOOSE_PROVIDER": "openai",
        "GOOSE_MODEL": cfg.model,
        "OPENAI_HOST": host,
        "OPENAI_BASE_PATH": "v1/chat/completions",
    }
    proc = subprocess.run(
        build_goose_argv(cfg, task_text, recipe, max_turns),
        cwd=str(cwd),
        env=env,
        capture_output=True,
        text=True,
    )
    result = parse_stream_json(proc.stdout.splitlines())
    if proc.returncode != 0 and result.error is None:
        result.error = f"goose exited {proc.returncode}: {proc.stderr[-500:]}"
    return result
