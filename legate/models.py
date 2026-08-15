"""Curated local-model catalog + fit-based recommendation.

Philosophy (from research): don't build a VRAM simulator. Ship a small vetted
catalog with known-good serve profiles, use a closed-form KV-cache estimate only
to RANK/gate off-tier boxes, and leave the exact MoE offload (`-ncmoe`) to a
bounded runtime probe (see `probe.py`) rather than trying to compute it.

VRAM budget rule: total − headroom (never trust WSL2 'free'). MoE models never
"fit" purely in VRAM — they offload routed experts to RAM, so their gate is
"does RAM hold the experts?", and the exact split is probed at serve time.
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class ModelSpec:
    key: str
    filename: str
    role: str                 # "coder" | "uncensored" | "general"
    kind: str                 # "moe" | "dense"
    quality: int              # rough capability rank within role (higher = better)
    file_gib: float           # on-disk quantized footprint
    n_layers: int
    n_kv_heads: int
    head_dim: int
    # KV correction for sliding-window attention (SWA): Gemma runs mostly-local
    # layers with a small window, so its real KV cache is a fraction of the naive
    # full-context size. NOTE: coarse per-family constant, not per-layer accounting
    # — good enough to gate fit; the serve probe is the real check.
    kv_factor: float = 1.0
    # serving hints
    ncmoe_guess: int | None = None   # MoE only: starting -ncmoe for the probe
    notes: str = ""


# The rig's vetted models (see local-llm-rig memory). Numbers are model-card facts.
CATALOG: list[ModelSpec] = [
    ModelSpec(
        key="qwen3-coder", filename="Qwen3-Coder-30B-A3B-Instruct-UD-Q4_K_XL.gguf",
        role="coder", kind="moe", quality=90, file_gib=16.5,
        n_layers=48, n_kv_heads=4, head_dim=128, ncmoe_guess=30,
        notes="3B active MoE; primary driver; needs llama.cpp >= b10435 for tool-calls.",
    ),
    ModelSpec(
        key="gemma4-coder", filename="gemma4-coder-v1-Q4_K_M.gguf",
        role="coder", kind="dense", quality=60, file_gib=6.9,
        n_layers=48, n_kv_heads=8, head_dim=256, kv_factor=0.25,
        notes="Dense 12B coder fallback; fits fully in VRAM.",
    ),
    ModelSpec(
        key="gemma4-agentic", filename="gemma4-agentic-v2-Q4_K_M.gguf",
        role="general", kind="dense", quality=62, file_gib=6.9,
        n_layers=48, n_kv_heads=8, head_dim=256, kv_factor=0.25,
        notes="Dense 12B agentic/general daily driver.",
    ),
    ModelSpec(
        key="gemma4-obliterated", filename="Gemma-4-12B-OBLITERATED-Q4_K_M.gguf",
        role="uncensored", kind="dense", quality=58, file_gib=6.9,
        n_layers=48, n_kv_heads=8, head_dim=256, kv_factor=0.25,
        notes="Uncensored fallback for refusal-prone pentest sessions.",
    ),
]

_BYTES_PER_ELEM = {"f16": 2.0, "q8_0": 1.0, "q4_0": 0.5}


def kv_cache_mib(spec: ModelSpec, ctx: int, kv_quant: str = "q8_0") -> int:
    """Closed-form KV-cache size: 2·layers·kv_heads·head_dim·ctx·bytes / 2^20."""
    be = _BYTES_PER_ELEM.get(kv_quant, 1.0)
    total = 2 * spec.n_layers * spec.n_kv_heads * spec.head_dim * ctx * be * spec.kv_factor
    return int(total / (1024 * 1024))


def vram_budget_mib(hw) -> int | None:
    """Usable VRAM = total − headroom (max(1GiB,10%), +512MiB on WSL2). Never 'free'."""
    if hw.vram_total_mib is None:
        return None
    headroom = max(1024, hw.vram_total_mib // 10)
    if hw.is_wsl2:
        headroom += 512
    return max(0, hw.vram_total_mib - headroom)


@dataclass
class Recommendation:
    spec: ModelSpec
    verdict: str              # "green" | "yellow" | "red"
    reason: str
    flags: list[str] = field(default_factory=list)


def _fits_dense(spec: ModelSpec, budget: int, ctx: int) -> tuple[bool, int]:
    need = int(spec.file_gib * 1024) + kv_cache_mib(spec, ctx) + 800  # +overhead
    return need <= budget, need


def recommend(hw, ctx: int = 32768) -> list[Recommendation]:
    """Rank the catalog for this machine with a fit verdict and serve flags."""
    budget = vram_budget_mib(hw)
    recs: list[Recommendation] = []
    for spec in CATALOG:
        if budget is None:
            recs.append(Recommendation(spec, "red", "no GPU detected — CPU-only serving is out of scope for v1"))
            continue
        kv = kv_cache_mib(spec, ctx)
        if spec.kind == "dense":
            fits, need = _fits_dense(spec, budget, ctx)
            if fits:
                verdict, reason = "green", f"fits VRAM (~{need} MiB need ≤ {budget} MiB budget)"
                flags = [f"-ngl 99 -c {ctx} -fa on -ctk q8_0 -ctv q8_0"]
            else:
                verdict, reason = "red", f"too big for VRAM (~{need} MiB need > {budget} MiB budget)"
                flags = []
        else:  # moe — routed experts spill to RAM (the designed mode on a small GPU)
            experts_mib = int(max(0, spec.file_gib - (budget / 1024) * 0.6) * 1024)
            flags = [f"-ngl 99 -ncmoe {spec.ncmoe_guess} -c {ctx} -fa on -ctk q8_0 -ctv q8_0"]
            if hw.ram_avail_mib >= experts_mib + 4096:
                verdict = "green"
                reason = (f"MoE: attention+KV(~{kv} MiB) on GPU, ~{experts_mib} MiB experts to RAM "
                          f"(comfortable). Exact -ncmoe probed (guess {spec.ncmoe_guess}).")
            elif hw.ram_avail_mib >= experts_mib + 2048:
                verdict = "yellow"
                reason = (f"MoE: ~{experts_mib} MiB experts to RAM — tight RAM margin. "
                          f"Exact -ncmoe probed (guess {spec.ncmoe_guess}).")
            else:
                verdict, flags = "red", []
                reason = f"MoE experts (~{experts_mib} MiB) won't fit in {hw.ram_avail_mib} MiB RAM"
        recs.append(Recommendation(spec, verdict, reason, flags))

    order = {"green": 0, "yellow": 1, "red": 2}
    recs.sort(key=lambda r: (order[r.verdict], -r.spec.quality))
    return recs
