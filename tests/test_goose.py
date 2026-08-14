from pathlib import Path

from legate.config import Config
from legate.goose import build_goose_argv


def test_build_goose_argv_has_required_flags():
    cfg = Config.default()
    argv = build_goose_argv(
        cfg, task_text="fix the bug", recipe=Path("recipes/base.yaml"), max_turns=30
    )
    assert argv[:2] == ["goose", "run"]
    assert "--no-session" in argv
    assert "--output-format" in argv and "stream-json" in argv
    assert "--max-turns" in argv and "30" in argv
    assert "--provider" in argv and "openai" in argv
    assert "--model" in argv and "qwen3-coder" in argv
    assert "--recipe" in argv and "recipes/base.yaml" in argv
    assert argv[-2:] == ["-t", "fix the bug"]
