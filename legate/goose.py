import os
import subprocess
import tempfile
from pathlib import Path

from legate.config import Config
from legate.goose_output import GooseResult, parse_stream_json
from legate.recipe import build_dev_recipe, render_recipe


def build_goose_argv(cfg: Config, recipe_path: Path | str, max_turns: int) -> list[str]:
    """Build the `goose run` argv for a headless, non-interactive run.

    The task rides inside the recipe's `prompt` (Goose forbids `--recipe` with
    `--text`), so no `-t` here. Kept pure for unit-testing without invoking goose.
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
        str(recipe_path),
        "--output-format",
        "stream-json",
    ]


def run_goose(cfg: Config, cwd: Path, task_text: str, max_turns: int = 30,
              tools: list[str] | None = None) -> GooseResult:
    """Run Goose headless in `cwd` and return the parsed result.

    Generates a temporary developer recipe carrying `task_text` as its prompt and
    the tool allowlist (`tools`, default: edit/write/shell). GOOSE_MODE=auto is
    mandatory — without it a headless run blocks forever on tool approval. Failure
    is inferred from the exit code (or an error event), never from JSON status.
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
    recipe_text = render_recipe(build_dev_recipe(task_text, tools))
    fd, rpath = tempfile.mkstemp(suffix=".yaml", prefix="legate-recipe-")
    try:
        with os.fdopen(fd, "w") as fh:
            fh.write(recipe_text)
        proc = subprocess.run(
            build_goose_argv(cfg, rpath, max_turns),
            cwd=str(cwd),
            env=env,
            capture_output=True,
            text=True,
        )
    finally:
        os.unlink(rpath)
    result = parse_stream_json(proc.stdout.splitlines())
    if proc.returncode != 0 and result.error is None:
        result.error = f"goose exited {proc.returncode}: {proc.stderr[-500:]}"
    return result
