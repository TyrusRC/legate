"""Dependency-light hardware detection for model-fit recommendations.

Everything here is stdlib + one `nvidia-smi` subprocess. On WSL2 the GPU's
*free* VRAM figure is unreliable (paravirtualized), so callers budget from
`vram_total_mib` and treat `vram_free_mib` only as a "is the card already busy?"
sanity check. Detection never raises — a machine with no GPU yields gpu=None.
"""
from __future__ import annotations

import os
import re
import shutil
import subprocess
from dataclasses import dataclass


@dataclass
class Hardware:
    gpu_name: str | None
    vram_total_mib: int | None
    vram_free_mib: int | None
    ram_total_mib: int
    ram_avail_mib: int
    cores: int
    is_wsl2: bool


def _detect_wsl2() -> bool:
    try:
        with open("/proc/version", "r") as fh:
            return "microsoft" in fh.read().lower()
    except OSError:
        return False


def _detect_gpu() -> tuple[str | None, int | None, int | None]:
    """Return (name, total_mib, free_mib) from nvidia-smi, or (None, None, None)."""
    if not shutil.which("nvidia-smi"):
        return None, None, None
    try:
        out = subprocess.run(
            ["nvidia-smi", "--query-gpu=memory.total,memory.free,name",
             "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=15,
        ).stdout.strip()
    except (subprocess.SubprocessError, OSError):
        return None, None, None
    if not out:
        return None, None, None
    # first GPU only (v1 is single-GPU); fields: total, free, name
    first = out.splitlines()[0]
    parts = [p.strip() for p in first.split(",")]
    if len(parts) < 3:
        return None, None, None
    try:
        total = int(parts[0])
        free = int(parts[1])
    except ValueError:
        return None, None, None
    name = parts[2] or None
    return name, total, free


def _meminfo_mib() -> tuple[int, int]:
    """(MemTotal, MemAvailable) in MiB from /proc/meminfo; kB→MiB."""
    total_kb = avail_kb = 0
    try:
        with open("/proc/meminfo", "r") as fh:
            for line in fh:
                m = re.match(r"(\w+):\s+(\d+)\s+kB", line)
                if not m:
                    continue
                if m.group(1) == "MemTotal":
                    total_kb = int(m.group(2))
                elif m.group(1) == "MemAvailable":
                    avail_kb = int(m.group(2))
    except OSError:
        pass
    return total_kb // 1024, avail_kb // 1024


def _usable_cores() -> int:
    try:
        return len(os.sched_getaffinity(0))
    except (AttributeError, OSError):
        return os.cpu_count() or 1


def detect() -> Hardware:
    name, vram_total, vram_free = _detect_gpu()
    ram_total, ram_avail = _meminfo_mib()
    return Hardware(
        gpu_name=name,
        vram_total_mib=vram_total,
        vram_free_mib=vram_free,
        ram_total_mib=ram_total,
        ram_avail_mib=ram_avail,
        cores=_usable_cores(),
        is_wsl2=_detect_wsl2(),
    )
