"""Live smoke eval — the canary the deleted eval harness used to provide.

Drive one real task end-to-end and assert a concrete success SIGNAL — not wiring,
but "did the agent actually change the file / produce findings". This is a manual
canary you run before trusting a change, NOT part of the default suite: it is
opt-in via LEGATE_SMOKE=1 (so a stray server on :8080 can't turn `pytest` red),
and additionally needs a reachable model server.

    LEGATE_SMOKE=1 uv run pytest tests/test_smoke_live.py -v           # coding smoke
    LEGATE_SMOKE=1 LEGATE_SMOKE_NET=1 uv run pytest tests/test_smoke_live.py -v  # + recon
"""
import os

import pytest

from legate import chat
from legate.config import Config

_CFG = Config.from_env()
_OPT_IN = os.environ.get("LEGATE_SMOKE") == "1"
_SERVER_UP = _OPT_IN and chat.server_up(_CFG)
_need_server = pytest.mark.skipif(
    not _SERVER_UP,
    reason="live smoke off (set LEGATE_SMOKE=1 with scripts/serve.sh running)",
)


@_need_server
def test_coding_smoke_actually_edits_the_file(tmp_path):
    """The coding path must change real code, not just narrate."""
    f = tmp_path / "greet.py"
    f.write_text("def greet():\n    return 'TODO'\n")
    out = chat.handle(_CFG, f"edit greet.py so greet() returns the string hello",
                      str(tmp_path), max_turns=8, mode="coding")
    assert "hello" in f.read_text().lower(), f"file unchanged; agent said:\n{out}"


@_need_server
@pytest.mark.skipif(os.environ.get("LEGATE_SMOKE_NET") != "1",
                    reason="network smoke off (set LEGATE_SMOKE_NET=1 to run against the public test target)")
def test_security_recon_smoke_writes_findings(tmp_path):
    """The security path must gather something and record it. Target is the
    Acunetix public, authorized test site; no Praetor required (shell fallback)."""
    out = chat.handle(_CFG, "recon http://testasp.vulnweb.com/ and list the URLs you find",
                      str(tmp_path), max_turns=10, mode="security")
    findings = tmp_path / "findings.md"
    assert findings.exists() or "vulnweb" in out.lower(), f"no recon output; agent said:\n{out}"
