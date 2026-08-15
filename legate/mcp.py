"""Minimal stdio MCP client — enough to enumerate and call tools on a server
like Praetor. Newline-delimited JSON-RPC 2.0 over the child's stdin/stdout.

We don't need a full framework: Legate uses this to (1) list a server's tools so
the BM25 router can pick a working subset, and (2) optionally smoke-call a tool.
Goose itself speaks MCP natively to the server at run time (via .mcp.json); this
client is Legate's own introspection path.
"""
from __future__ import annotations

import json
import os
import subprocess
import threading
from dataclasses import dataclass


@dataclass
class MCPTool:
    name: str
    description: str
    input_schema: dict


class MCPError(RuntimeError):
    pass


class MCPClient:
    def __init__(self, command: list[str], cwd: str | None = None,
                 env: dict | None = None, timeout: float = 30.0):
        self.command = command
        self.cwd = cwd
        self.env = {**os.environ, **(env or {})}
        self.timeout = timeout
        self._proc: subprocess.Popen | None = None
        self._id = 0

    # -- lifecycle -------------------------------------------------------
    def __enter__(self) -> "MCPClient":
        self.start()
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    def start(self) -> None:
        self._proc = subprocess.Popen(
            self.command, cwd=self.cwd, env=self.env,
            stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=subprocess.PIPE, text=True, bufsize=1,
        )
        self._request("initialize", {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {"name": "legate", "version": "0.1.0"},
        })
        self._notify("notifications/initialized", {})

    def close(self) -> None:
        if self._proc and self._proc.poll() is None:
            self._proc.kill()
        self._proc = None

    # -- transport -------------------------------------------------------
    def _send(self, obj: dict) -> None:
        assert self._proc and self._proc.stdin
        self._proc.stdin.write(json.dumps(obj) + "\n")
        self._proc.stdin.flush()

    def _readline(self) -> str | None:
        assert self._proc and self._proc.stdout
        box: dict = {}

        def _r():
            box["line"] = self._proc.stdout.readline()

        t = threading.Thread(target=_r, daemon=True)
        t.start()
        t.join(self.timeout)
        return box.get("line")

    def _notify(self, method: str, params: dict) -> None:
        self._send({"jsonrpc": "2.0", "method": method, "params": params})

    def _request(self, method: str, params: dict) -> dict:
        self._id += 1
        rid = self._id
        self._send({"jsonrpc": "2.0", "id": rid, "method": method, "params": params})
        # read until we see the matching id (skip notifications/other ids)
        for _ in range(200):
            line = self._readline()
            if line is None:
                err = self._stderr_tail()
                raise MCPError(f"timeout waiting for {method}; stderr: {err}")
            line = line.strip()
            if not line:
                continue
            try:
                msg = json.loads(line)
            except json.JSONDecodeError:
                continue
            if msg.get("id") == rid:
                if "error" in msg:
                    raise MCPError(f"{method} failed: {msg['error']}")
                return msg.get("result", {})
        raise MCPError(f"no response id={rid} for {method}")

    def _stderr_tail(self) -> str:
        try:
            if self._proc and self._proc.stderr:
                return (self._proc.stderr.read() or "")[:500]
        except Exception:
            pass
        return ""

    # -- API -------------------------------------------------------------
    def list_tools(self) -> list[MCPTool]:
        res = self._request("tools/list", {})
        return [MCPTool(t["name"], (t.get("description") or "").strip(),
                        t.get("inputSchema") or {}) for t in res.get("tools", [])]

    def call_tool(self, name: str, arguments: dict | None = None) -> dict:
        return self._request("tools/call", {"name": name, "arguments": arguments or {}})
