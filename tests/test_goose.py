from pathlib import Path

from legate.config import Config
from legate.goose import build_goose_argv


def test_build_goose_argv_has_required_flags():
    cfg = Config.default()
    argv = build_goose_argv(cfg, recipe_path=Path("/tmp/r.yaml"), max_turns=30)
    assert argv[:2] == ["goose", "run"]
    assert "--no-session" in argv
    assert "--output-format" in argv and "stream-json" in argv
    assert "--max-turns" in argv and "30" in argv
    assert "--provider" in argv and "openai" in argv
    assert "--model" in argv and "qwen3-coder" in argv
    assert "--recipe" in argv and "/tmp/r.yaml" in argv
    # task rides in the recipe prompt now, not via -t (Goose forbids both)
    assert "-t" not in argv and "--text" not in argv


def test_run_goose_generates_prompt_recipe(tmp_path, monkeypatch):
    """run_goose writes a recipe carrying the task prompt + tool allowlist, and
    passes it via --recipe (no -t)."""
    import legate.goose as g
    captured = {}

    class FakeProc:
        returncode = 0
        stdout = ""
        stderr = ""

    def fake_run(argv, cwd, env, capture_output, text, timeout=None):
        # the recipe file must exist and contain the task at call time
        rpath = argv[argv.index("--recipe") + 1]
        captured["recipe"] = Path(rpath).read_text()
        captured["argv"] = argv
        return FakeProc()

    monkeypatch.setattr(g.subprocess, "run", fake_run)
    cfg = Config.default()
    g.run_goose(cfg, tmp_path, "solve the wordy problem", max_turns=5)
    assert "solve the wordy problem" in captured["recipe"]
    assert "developer" in captured["recipe"]
    assert "-t" not in captured["argv"]


def test_build_goose_argv_isolated_by_default():
    from legate.goose import build_goose_argv
    from legate.config import Config
    argv = build_goose_argv(Config.default(), "/r.yaml", 10)
    assert "--no-session" in argv and "--name" not in argv


def test_build_goose_argv_named_session_and_resume():
    from legate.goose import build_goose_argv
    from legate.config import Config
    c = Config.default()
    fresh = build_goose_argv(c, "/r.yaml", 10, session="s1")
    assert "--name" in fresh and "s1" in fresh
    assert "--resume" not in fresh and "--no-session" not in fresh
    resumed = build_goose_argv(c, "/r.yaml", 10, session="s1", resume=True)
    assert "--resume" in resumed


def test_run_recipe_times_out_cleanly(monkeypatch, tmp_path):
    # A runaway/hung goose run must be killed and returned as an error, not hang.
    import legate.goose as g
    from legate.config import Config
    monkeypatch.setattr(g, "build_goose_argv", lambda *a, **k: ["sleep", "30"])
    monkeypatch.setattr(g, "_goose_env", lambda cfg: {"PATH": __import__("os").environ["PATH"]})
    res = g.run_recipe(Config.default(), tmp_path, "recipe: x", max_turns=1, timeout=1)
    assert res.error is not None and "exceeded" in res.error
