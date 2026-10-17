import os
import sys
from pathlib import Path

import pytest

from legate.mcp import MCPClient, MCPError

FAKE = Path(__file__).parent / "fixtures" / "fake_mcp_server.py"
# Praetor location comes from the environment (.env via conftest) — never hardcoded.
PRAETOR_CMD = os.environ.get("LEGATE_PRAETOR_CMD")
PRAETOR_ARGS = os.environ.get("LEGATE_PRAETOR_ARGS", "-m burpsuite_mcp").split()
PRAETOR_CWD = os.environ.get("LEGATE_PRAETOR_CWD")
_praetor_missing = not PRAETOR_CMD or not Path(PRAETOR_CMD).exists()


def test_client_handshakes_and_lists_tools():
    with MCPClient([sys.executable, str(FAKE)]) as c:
        tools = c.list_tools()
    names = [t.name for t in tools]
    assert names == ["echo", "add"]
    assert tools[0].input_schema["type"] == "object"


def test_client_calls_a_tool():
    with MCPClient([sys.executable, str(FAKE)]) as c:
        res = c.call_tool("echo", {"text": "hi"})
    assert "called echo" in res["content"][0]["text"]


@pytest.mark.skipif(_praetor_missing, reason="LEGATE_PRAETOR_CMD not set/found")
def test_praetor_mcp_lists_many_tools():
    """Integration: the real Praetor MCP server enumerates its full tool surface."""
    try:
        with MCPClient([PRAETOR_CMD, *PRAETOR_ARGS], cwd=PRAETOR_CWD, timeout=60) as c:
            tools = c.list_tools()
    except MCPError as e:  # path is set but the server can't start (backend/module missing)
        pytest.skip(f"Praetor not runnable: {e}")
    assert len(tools) > 100
    assert any("sqli" in t.name or "scan" in t.name for t in tools)
