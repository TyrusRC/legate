from legate.repomap import build_repo_map


def test_maps_python_symbols_and_signatures(tmp_path):
    (tmp_path / "mod.py").write_text(
        "def top(a, b, *rest, **kw):\n    pass\n\n"
        "class Thing:\n    def method(self, x):\n        return x\n    def other(self):\n        pass\n"
    )
    m = build_repo_map(tmp_path)
    assert "mod.py:" in m
    assert "def top(a, b, *rest, **kw)" in m
    assert "class Thing: method, other" in m


def test_skips_noise_dirs_and_non_python(tmp_path):
    (tmp_path / "keep.py").write_text("def keep():\n    pass\n")
    (tmp_path / "readme.md").write_text("# not python\n")
    noise = tmp_path / ".venv" / "pkg"
    noise.mkdir(parents=True)
    (noise / "buried.py").write_text("def buried():\n    pass\n")
    m = build_repo_map(tmp_path)
    assert "keep.py:" in m
    assert "readme.md" not in m          # non-python skipped
    assert "buried" not in m             # .venv pruned


def test_unparseable_file_is_skipped_not_fatal(tmp_path):
    (tmp_path / "bad.py").write_text("def oops(:\n")   # syntax error
    (tmp_path / "ok.py").write_text("def ok():\n    pass\n")
    m = build_repo_map(tmp_path)
    assert "ok.py:" in m and "bad.py" not in m


def test_respects_char_budget(tmp_path):
    for i in range(50):
        (tmp_path / f"m{i}.py").write_text(f"def f{i}(aaaaaaaaaaaaaaaaaaaa):\n    pass\n")
    m = build_repo_map(tmp_path, max_chars=200)
    assert len(m) <= 200 + len("\n… (repo map truncated)")
    assert "truncated" in m


def test_empty_or_non_dir_returns_blank(tmp_path):
    assert build_repo_map(tmp_path) == ""              # no python
    assert build_repo_map(tmp_path / "nope") == ""     # missing dir
