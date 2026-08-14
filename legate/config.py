import os
from dataclasses import dataclass
from pathlib import Path


def load_dotenv(path: str | Path = ".env") -> None:
    """Load KEY=VALUE lines from a .env file into os.environ WITHOUT overriding
    variables already set in the real environment. Minimal, stdlib-only — no
    python-dotenv dependency. Blank lines and `#` comments are ignored.
    """
    p = Path(path)
    if not p.exists():
        return
    for line in p.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, val = line.split("=", 1)
        os.environ.setdefault(key.strip(), val.strip().strip('"').strip("'"))


@dataclass
class Config:
    """Runtime configuration for a Legate session. All values come from the
    environment (see `.env.example`); `from_env()` applies defaults for anything
    unset. Nothing is hardcoded to a machine-specific path.
    """

    endpoint: str
    model: str
    repo_root: Path
    work_root: Path
    model_path: Path | None = None
    goose_mode: str = "auto"

    @classmethod
    def from_env(cls) -> "Config":
        repo_root = Path(os.environ.get("LEGATE_REPO_ROOT", Path.cwd()))
        work_root = Path(os.environ.get("LEGATE_WORK_ROOT", repo_root / ".legate" / "work"))
        model_path = os.environ.get("LEGATE_MODEL_PATH")
        return cls(
            endpoint=os.environ.get("LEGATE_ENDPOINT", "http://127.0.0.1:8080/v1"),
            model=os.environ.get("LEGATE_MODEL", "qwen3-coder"),
            repo_root=repo_root,
            work_root=work_root,
            model_path=Path(model_path) if model_path else None,
            goose_mode=os.environ.get("LEGATE_GOOSE_MODE", "auto"),
        )

    # Back-compat alias: reads env (with defaults) — same result when no LEGATE_* set.
    @classmethod
    def default(cls) -> "Config":
        return cls.from_env()
