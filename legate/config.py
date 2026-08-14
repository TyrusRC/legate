from dataclasses import dataclass
from pathlib import Path


@dataclass
class Config:
    """Runtime configuration for a Legate session."""

    endpoint: str
    model: str
    repo_root: Path
    work_root: Path
    goose_mode: str = "auto"

    @classmethod
    def default(cls) -> "Config":
        return cls(
            endpoint="http://127.0.0.1:8080/v1",
            model="qwen3-coder",
            repo_root=Path.cwd(),
            work_root=Path.cwd() / ".legate" / "work",
            goose_mode="auto",
        )
