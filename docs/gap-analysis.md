# Legate vs. Claude Code + Opus 5 — Gap Analysis

*What Legate can realistically match, what it can't, and what it adds to close
the distance. Grounded in on-rig validation (RTX 3060 12GB, WSL2), not aspiration.*

## The honest thesis

Legate's goal is **50–60% of Claude Code + Opus 5 on the *winnable envelope*** —
localized, ≤2-file coding tasks and straightforward Praetor-driven pentest probes —
running a local model with no subscription. It is **~0% on the tasks where Opus 5
actually shines**: multi-file refactors, long-horizon planning, and anything
needing a large-context read of an unfamiliar codebase. We report per-task-type
and never average the winnable and unwinnable together into a flattering number.

## Dimension-by-dimension

| Dimension | Claude Code + Opus 5 | Legate (local) | Gap |
|---|---|---|---|
| Base model | Opus 5 (frontier) | Qwen3-Coder-30B-A3B Q4 (3B active) | Large on hard tasks |
| Polyglot pass@2 | ~83% (published) | ~61% *model-alone* (target ≥50% of Opus) | Closable on localized tasks |
| SWE-bench (localized) | ~70–80%+ | ~51% model-alone | Best-of-N lifts this |
| Gen speed | fast, hosted | **~27 tok/s** on-rig (validated) | Usable; turn-budgeted |
| Context window | 200K+ | 32K served (KV-quant) | **Hard gap** — big repos |
| Multi-file / long-horizon | strong | ~0 on 12GB | **Hard gap** — out of envelope |
| Tool calling | native, reliable | **5/5 native** (llama.cpp ≥b10435) | Closed |
| MCP ecosystem | full | full (Goose native client) | Parity |
| Cost | subscription / metered | **$0 after hardware** | Legate wins |
| Privacy / offline | cloud | **fully local** | Legate wins |
| Uncensored / pentest | guardrailed | uncensored slot (OBLITERATED) | Legate wins for authorized security work |

## Where Legate closes the gap (the net-new engine)

These are the pieces Claude Code doesn't need (it has Opus) but a small model does:

1. **Best-of-N execution-grounded solve** (`legate solve --best-of N`). Generate N
   candidates in isolated git worktrees, run the *real* tests on each, rank
   test-anchored, and repair the best with the actual traceback. Resampling +
   grounded feedback is the single biggest capability multiplier at this model size.
2. **MCP tool-selection router.** Praetor exposes **390 tools** (validated, not the
   70 the spec assumed). A 3B-active model drowns above ~15. Phase-grouping + BM25
   (zero VRAM, exact-match on security jargon, acronym↔expansion bridging) surfaces
   a ≤15-tool working set per step. Without this, driving Praetor is impossible.
3. **Model-fit flow** (`legate doctor`, `legate models recommend`). Detects the
   machine and prints ranked model slots with exact serve flags — so a user on
   different hardware gets a working config, not a guess.
4. **Low-level serving wins.** KV-cache q8_0 + `-ncmoe` expert offload took the
   3060 from 5–7 tok/s to **~27 tok/s** at healthy VRAM (9.3/12 GB). The tool-call
   fix (llama.cpp ≥b10435) was a hard prerequisite the whole harness depended on.
5. **bwrap sandbox** around every execution of model-generated code (no network,
   confined FS, fail-closed) — Claude Code trusts its own sandbox; we build ours.

## What is still missing (do not oversell)

- **Large-context codebase comprehension.** 32K vs 200K+ is architectural. A
  repo-map / retrieval layer is roadmap, not built. Today: point Legate at the
  ≤2-file locus, not "the repo."
- **Long-horizon autonomy.** Published scores assume ~100-turn runs; at 27 tok/s
  we budget turns and measure `resolve@turn-limit`. Deep multi-step plans degrade.
- **Multi-model mid-session routing / llama-swap.** One model at a time in v1.
- **Dual-protocol (Codex CLI / Claude Code front-ends).** v1 drives Goose only.
- **Eval breadth.** The suite runs but the committed problem set is tiny; wiring the
  full 225-exercise Aider polyglot set is the next data task before the %-of-Opus
  number is load-bearing.
- **Praetor live backend.** The MCP seam enumerates 390 tools now, but the tools
  need Burp Suite + Java 21 (box has Java 17) to actually act against a target.

## Bottom line

On a localized bug-fix or a scoped Praetor probe, Legate + best-of-N is a
plausible 50–60% of Opus at $0/token, fully local, uncensored for authorized
security work. Ask it to reason across an unfamiliar large codebase and it is not
in the same class — and the eval reports that honestly rather than hiding it.
