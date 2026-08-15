"""Load the project's .env before tests so integration tests can find local,
machine-specific config (e.g. LEGATE_PRAETOR_CMD) without any hardcoded paths.
load_dotenv uses setdefault, so a real environment variable still wins."""
from pathlib import Path

from legate.config import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / ".env")
