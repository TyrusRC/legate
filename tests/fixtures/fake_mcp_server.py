#!/usr/bin/env python3
"""A 30-line stdio MCP server for testing MCPClient: initialize + tools/list +
tools/call over newline-delimited JSON-RPC."""
import json
import sys

TOOLS = [
    {"name": "echo", "description": "Echo text back.",
     "inputSchema": {"type": "object", "properties": {"text": {"type": "string"}}}},
    {"name": "add", "description": "Add two numbers.",
     "inputSchema": {"type": "object", "properties": {"a": {"type": "number"}, "b": {"type": "number"}}}},
]


def reply(rid, result):
    sys.stdout.write(json.dumps({"jsonrpc": "2.0", "id": rid, "result": result}) + "\n")
    sys.stdout.flush()


for line in sys.stdin:
    line = line.strip()
    if not line:
        continue
    msg = json.loads(line)
    method, rid = msg.get("method"), msg.get("id")
    if method == "initialize":
        reply(rid, {"protocolVersion": "2024-11-05", "capabilities": {},
                    "serverInfo": {"name": "fake", "version": "1.0"}})
    elif method == "notifications/initialized":
        pass  # notification, no reply
    elif method == "tools/list":
        reply(rid, {"tools": TOOLS})
    elif method == "tools/call":
        p = msg.get("params", {})
        reply(rid, {"content": [{"type": "text", "text": f"called {p.get('name')} with {p.get('arguments')}"}]})
    else:
        reply(rid, {})
