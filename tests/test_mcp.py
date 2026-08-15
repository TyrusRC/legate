import sys
from pathlib import Path

import pytest

from legate.mcp import MCPClient

FAKE = Path(__file__).parent / "fixtures" / "fake_mcp_server.py"
PRAETOR_VENV = Path("/home/kali/project/trc/praetor/mcp-server/.venv/bin/python")


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


@pytest.mark.skipif(not PRAETOR_VENV.exists(), reason="Praetor venv not present")
def test_praetor_mcp_lists_many_tools():
    """Integration: the real Praetor MCP server enumerates its full tool surface."""
    with MCPClient([str(PRAETOR_VENV), "-m", "burpsuite_mcp"],
                   cwd="/home/kali/project/trc/praetor/mcp-server", timeout=60) as c:
        tools = c.list_tools()
    assert len(tools) > 100
    assert any("sqli" in t.name or "scan" in t.name for t in tools)
