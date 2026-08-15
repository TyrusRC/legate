"""Minimal stdio MCP client — enough to enumerate and call tools on a server
like Praetor. Newline-delimited JSON-RPC 2.0 over the child's stdin/stdout.

Robustness (a server like Praetor is Java/Burp-backed and chatty):
- stdout is drained by ONE background thread into a queue, so a slow reader never
  interleaves and a timeout doesn't orphan a blocked readline.
- stderr is drained by a thread into a bounded buffer, so the child never blocks
  on a full stderr pipe (the classic deadlock).
- start() closes the child if the handshake fails (no orphaned process).
- close() kills, waits (reaps the zombie), and closes the pipes.
"""
from __future__ import annotations

import json
import os
import queue
import subprocess
import threading
import time
from collections import deque
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
        self._q: "queue.Queue[str | None]" = queue.Queue()
        self._stderr: deque[str] = deque(maxlen=200)
        self._readers: list[threading.Thread] = []

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
        self._spawn_readers()
        try:
            self._request("initialize", {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "legate", "version": "0.1.0"},
            })
            self._notify("notifications/initialized", {})
        except Exception:
            self.close()          # don't orphan the child on a failed handshake
            raise

    def _spawn_readers(self) -> None:
        def drain_stdout():
            for line in self._proc.stdout:
                self._q.put(line)
            self._q.put(None)     # EOF sentinel

        def drain_stderr():
            for line in self._proc.stderr:
                self._stderr.append(line)

        for target in (drain_stdout, drain_stderr):
            t = threading.Thread(target=target, daemon=True)
            t.start()
            self._readers.append(t)

    def close(self) -> None:
        if self._proc:
            if self._proc.poll() is None:
                self._proc.kill()
            try:
                self._proc.wait(timeout=5)   # reap the zombie
            except Exception:
                pass
            for stream in (self._proc.stdin, self._proc.stdout, self._proc.stderr):
                try:
                    if stream:
                        stream.close()
                except Exception:
                    pass
        self._proc = None

    # -- transport -------------------------------------------------------
    def _send(self, obj: dict) -> None:
        assert self._proc and self._proc.stdin
        self._proc.stdin.write(json.dumps(obj) + "\n")
        self._proc.stdin.flush()

    def _notify(self, method: str, params: dict) -> None:
        self._send({"jsonrpc": "2.0", "method": method, "params": params})

    def _request(self, method: str, params: dict) -> dict:
        self._id += 1
        rid = self._id
        self._send({"jsonrpc": "2.0", "id": rid, "method": method, "params": params})
        deadline = time.monotonic() + self.timeout   # overall, not per-line
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise MCPError(f"timeout waiting for {method}; stderr: {self._stderr_tail()}")
            try:
                line = self._q.get(timeout=remaining)
            except queue.Empty:
                raise MCPError(f"timeout waiting for {method}; stderr: {self._stderr_tail()}")
            if line is None:  # child closed stdout
                raise MCPError(f"server exited before responding to {method}; "
                               f"stderr: {self._stderr_tail()}")
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
            # else: a notification or a different id — keep waiting

    def _stderr_tail(self) -> str:
        return ("".join(self._stderr))[-500:]

    # -- API -------------------------------------------------------------
    def list_tools(self) -> list[MCPTool]:
        res = self._request("tools/list", {})
        return [MCPTool(t["name"], (t.get("description") or "").strip(),
                        t.get("inputSchema") or {}) for t in res.get("tools", [])]

    def call_tool(self, name: str, arguments: dict | None = None) -> dict:
        return self._request("tools/call", {"name": name, "arguments": arguments or {}})
