from pathlib import Path

from legate.config import Config


def test_default_config_has_local_endpoint():
    cfg = Config.default()
    assert cfg.endpoint == "http://127.0.0.1:8080/v1"
    assert cfg.model == "qwen3-coder"
    assert cfg.goose_mode == "auto"
    assert isinstance(cfg.work_root, Path)
