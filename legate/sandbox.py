"""Confine untrusted execution (model-generated code, its tests) with bubblewrap.

Model output is untrusted — during best-of-N and eval we run it, so it runs
locked down: read-only root, a single writable work dir, no network by default,
private pid/tmp namespaces. Fail CLOSED — if no sandbox is available and the
caller requires one, we raise rather than run untrusted code bare.

bwrap only (firejail path omitted — bwrap is the better primitive and is what's
installed). Network is denied unless explicitly allowed (a live pentest tool that
must reach a target opts in).
"""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path


class SandboxUnavailable(RuntimeError):
    pass


def available() -> str | None:
    """Return the sandbox backend name if usable, else None."""
    return "bwrap" if shutil.which("bwrap") else None


def wrap(argv: list[str], workdir: str | Path, allow_net: bool = False,
         require: bool = True) -> list[str]:
    """Return `argv` wrapped to run confined to `workdir`. If no sandbox is
    available: raise when require=True (fail closed), else return argv unchanged."""
    workdir = str(Path(workdir).resolve())
    if available() is None:
        if require:
            raise SandboxUnavailable(
                "no sandbox (bwrap) available; refusing to run untrusted code unwrapped")
        return argv

    bwrap = [
        "bwrap",
        "--ro-bind", "/", "/",            # read-only root...
        "--dev", "/dev",
        "--proc", "/proc",
        "--tmpfs", "/tmp",                # private /tmp...
        "--bind", workdir, workdir,       # ...but the writable work dir wins, even
        "--chdir", workdir,               #    when it lives under /tmp (bind after tmpfs)
        "--unshare-pid",
        "--die-with-parent",
        "--new-session",
    ]
    if not allow_net:
        bwrap.append("--unshare-net")     # no network by default
    bwrap.append("--")
    return bwrap + argv


def run(argv: list[str], workdir: str | Path, allow_net: bool = False,
        require: bool = True, timeout: float | None = None,
        capture: bool = True) -> subprocess.CompletedProcess:
    """Convenience: wrap `argv` and run it. Same signature intent as subprocess.run."""
    wrapped = wrap(argv, workdir, allow_net=allow_net, require=require)
    return subprocess.run(wrapped, capture_output=capture, text=True, timeout=timeout)
