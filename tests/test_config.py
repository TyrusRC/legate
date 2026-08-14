from pathlib import Path

from legate.config import Config, load_dotenv


def test_default_config_has_local_endpoint():
    cfg = Config.default()
    assert cfg.endpoint == "http://127.0.0.1:8080/v1"
    assert cfg.model == "qwen3-coder"
    assert cfg.goose_mode == "auto"
    assert isinstance(cfg.work_root, Path)


def test_from_env_reads_overrides(monkeypatch):
    monkeypatch.setenv("LEGATE_ENDPOINT", "http://host:9000/v1")
    monkeypatch.setenv("LEGATE_MODEL", "custom-model")
    monkeypatch.setenv("LEGATE_MODEL_PATH", "/models/x.gguf")
    cfg = Config.from_env()
    assert cfg.endpoint == "http://host:9000/v1"
    assert cfg.model == "custom-model"
    assert cfg.model_path == Path("/models/x.gguf")


def test_load_dotenv_does_not_override_real_env(tmp_path, monkeypatch):
    env_file = tmp_path / ".env"
    env_file.write_text('LEGATE_MODEL=from-file\nLEGATE_ENDPOINT="http://file:1/v1"\n')
    monkeypatch.setenv("LEGATE_MODEL", "from-real-env")  # already set wins
    load_dotenv(env_file)
    import os
    assert os.environ["LEGATE_MODEL"] == "from-real-env"
    assert os.environ["LEGATE_ENDPOINT"] == "http://file:1/v1"  # unset -> filled
