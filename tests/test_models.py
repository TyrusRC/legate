from legate.hardware import Hardware
from legate.models import (
    CATALOG,
    kv_cache_mib,
    recommend,
    vram_budget_mib,
)


def _spec(key):
    return next(s for s in CATALOG if s.key == key)


def rig(**over):
    """A realistic RTX 3060 12GB / 19GB-RAM WSL2 box, overridable per test."""
    base = dict(
        gpu_name="NVIDIA GeForce RTX 3060", vram_total_mib=12288, vram_free_mib=11000,
        ram_total_mib=19000, ram_avail_mib=15000, cores=10, is_wsl2=True,
    )
    base.update(over)
    return Hardware(**base)


def test_kv_cache_formula_matches_hand_calc():
    # Qwen3-Coder: 2·48·4·128·32768·(q8=1.0)·(factor=1.0) / 2^20 == 1536 MiB
    assert kv_cache_mib(_spec("qwen3-coder"), 32768, "q8_0") == 1536


def test_swa_factor_shrinks_gemma_kv_fourfold():
    # kv_factor 0.25 must quarter the naive cache vs an identical non-SWA model.
    g = _spec("gemma4-coder")
    assert g.kv_factor == 0.25
    naive = kv_cache_mib(g, 32768, "q8_0") / g.kv_factor
    assert kv_cache_mib(g, 32768, "q8_0") == int(naive * 0.25)


def test_vram_budget_reserves_headroom_and_extra_on_wsl2():
    assert vram_budget_mib(rig(is_wsl2=True)) == 12288 - 1228 - 512   # 10548
    assert vram_budget_mib(rig(is_wsl2=False)) == 12288 - 1228        # 11060
    assert vram_budget_mib(rig(vram_total_mib=None)) is None


def test_primary_moe_coder_ranks_first_on_the_rig():
    recs = recommend(rig())
    assert recs[0].spec.key == "qwen3-coder"
    assert recs[0].verdict == "green"
    # every non-red rec carries runnable flags; reds carry none
    for r in recs:
        assert bool(r.flags) == (r.verdict != "red")


def test_moe_goes_red_when_ram_cannot_hold_experts():
    recs = {r.spec.key: r for r in recommend(rig(ram_avail_mib=6000))}
    assert recs["qwen3-coder"].verdict == "red"
    assert "won't fit" in recs["qwen3-coder"].reason


def test_no_gpu_marks_everything_red():
    recs = recommend(rig(vram_total_mib=None, vram_free_mib=None, gpu_name=None))
    assert all(r.verdict == "red" for r in recs)


def test_dense_fallback_fits_on_the_rig():
    recs = {r.spec.key: r for r in recommend(rig())}
    assert recs["gemma4-coder"].verdict == "green"
    assert "-ctk q8_0" in recs["gemma4-coder"].flags[0]
