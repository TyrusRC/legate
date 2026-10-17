"""Conversational front-end: describe what you want in natural language and
Legate figures out whether it's a coding task or a cybersecurity engagement,
routes the right tools, and drives the local model — no per-task CLI subcommands.

Cybersecurity here is broad — web pentest, red-team tradecraft (post-exploitation,
lateral movement, persistence, C2, exfil), OSINT/recon, and so on — all driven
through the same kill-chain phase model. The small local model can't be handed
Praetor's ~390 tools at once, so intent and phase are inferred *here*
(deterministically, before the model runs) and only the matching tool subset is
mounted (plus the shell tool, so the agent isn't limited to Praetor's surface).
Coding requests get the developer editor.
"""
from __future__ import annotations

import os
import re
import time
from dataclasses import replace
from pathlib import Path

try:
    import readline  # noqa: F401 — gives input() arrow-key cursor movement, line editing, history
except ImportError:
    pass

from legate.toolselect import PHASES, tokenize

# A request is a security engagement if it names a target (URL / IP) or uses an
# explicit security cue. Bare `foo.py` (no scheme, no cue) stays coding. Cues span
# pentest + red-team + broader cyber vocabulary; the phase cues (recon…report) are
# folded in so any tool-mapped term also counts as a security signal.
_URL = re.compile(r"https?://\S+", re.I)
_IP = re.compile(r"\b\d{1,3}(?:\.\d{1,3}){3}\b")
_SEC_CUES = {
    # pentest
    "pentest", "pentesting", "reconnaissance", "vuln", "vulnerability",
    "vulnerabilities", "attack", "owasp", "burp", "target", "bruteforce", "fuzz",
    # red team / adversary emulation
    "redteam", "adversary", "emulation", "lateral", "persistence", "pivot",
    "beacon", "implant", "c2", "exfil", "exfiltration", "privesc", "escalation",
    "credential", "phishing", "phish", "evasion", "opsec", "ttp", "mitre",
    # broader cyber domains
    "osint", "malware", "forensic", "forensics", "threat", "hunt", "cve",
} | {cue for cues in PHASES.values() for cue in cues}


def classify_request(text: str) -> tuple[str, str, str]:
    """Return (kind, phase, query). kind is 'security' or 'dev'. For 'dev', phase
    is '' — it's ignored. `query` is the request itself (drives tool routing)."""
    toks = set(tokenize(text))
    has_target = bool(_URL.search(text) or _IP.search(text))
    has_cue = bool(toks & _SEC_CUES)
    if not (has_target or has_cue):
        return "dev", "", text
    # phase: the bucket whose cues the request hits most; default recon.
    best, best_hits = "recon", 0
    for phase, cues in PHASES.items():
        hits = sum(1 for c in cues if c in toks)
        if hits > best_hits:
            best, best_hits = phase, hits
    return "security", best, text


def route(text: str, mode: str | None = None) -> tuple[str, str]:
    """(kind, phase) for a request, honouring a REPL `/mode` override. mode None =
    auto (classify); 'coding' forces the dev editor; 'security' forces an engagement
    (keeping any phase the text implies, else recon)."""
    if mode == "coding":
        return "dev", ""
    kind, phase, _ = classify_request(text)
    if mode == "security":
        return "security", (phase or "recon")
    return kind, phase


# Pure conversational inputs (whole-message match) get a direct, tool-less reply —
# spawning the agent to run `ls` for "hi" is overkill. Conservative on purpose: a
# real task like "help me fix X" isn't in this set, so it still routes to the agent.
_SMALLTALK = {
    "hi", "hello", "hey", "yo", "sup", "hiya", "howdy", "hola", "hi there",
    "hey there", "hello there", "good morning", "good afternoon", "good evening",
    "thanks", "thank you", "thank u", "ty", "thx", "cheers", "nice", "cool",
    "ok", "okay", "great", "who are you", "what are you", "what can you do",
    "what do you do", "what is this", "help",
}


def _is_smalltalk(text: str) -> bool:
    return text.strip().lower().rstrip("!.?") in _SMALLTALK


def _direct_reply(cfg, text: str, timeout: float = 60.0) -> str:
    """A single tool-less chat completion — for greetings / trivial questions, so
    the agent (and its tools) never spins up. Fast and cheap."""
    import json
    import urllib.request
    from legate.recipe import LEGATE_INSTRUCTIONS
    body = json.dumps({
        "model": cfg.model, "max_tokens": 150, "temperature": 0.7,
        "messages": [{"role": "system", "content": LEGATE_INSTRUCTIONS},
                     {"role": "user", "content": text}],
    }).encode()
    req = urllib.request.Request(
        cfg.endpoint.rstrip("/") + "/chat/completions", data=body,
        headers={"Content-Type": "application/json", "Authorization": "Bearer x"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        data = json.loads(r.read())
    return data["choices"][0]["message"]["content"].strip()


def server_up(cfg, timeout: float = 3.0) -> bool:
    """Quick reachability check for the local model server, so a request fails fast
    with a clear message instead of the agent hanging on a dead endpoint."""
    import urllib.request
    host = cfg.endpoint.rsplit("/v1", 1)[0]
    for url in (f"{host}/health", f"{cfg.endpoint}/models"):
        try:
            with urllib.request.urlopen(url, timeout=timeout) as r:
                if r.status < 500:
                    return True
        except Exception:
            continue
    return False


def _praetor_env() -> tuple[str | None, list[str], str | None]:
    cmd = os.environ.get("LEGATE_PRAETOR_CMD")
    args = os.environ.get("LEGATE_PRAETOR_ARGS", "-m burpsuite_mcp").split()
    cwd = os.environ.get("LEGATE_PRAETOR_CWD")
    return cmd, args, cwd


def _clip(s: str, n: int = 200) -> str:
    s = " ".join(str(s).split())
    return s if len(s) <= n else s[:n] + "…"


def _ctx_limit() -> int:
    """The served context window, used to warn before a session overflows it."""
    try:
        return int(os.environ.get("LEGATE_CTX", "32768"))
    except ValueError:
        return 32768


def make_renderer():
    """A stateful printer for Goose stream-json events. Assistant text tokens
    (Goose emits one event per token) print inline; tool calls, results, errors
    and the final token tally each start on their own line. Returns a callable
    suitable for goose.run_recipe(on_event=...)."""
    import sys
    ctx = _ctx_limit()
    mid_line = False  # currently in the middle of an inline assistant sentence

    def nl():
        nonlocal mid_line
        if mid_line:
            sys.stdout.write("\n")
            mid_line = False

    def emit(evt: dict) -> None:
        nonlocal mid_line
        etype = evt.get("type")
        if etype == "error":
            nl(); print(f"  ✗ {_clip(evt.get('error', 'error'), 300)}")
            return
        if etype == "complete":
            total = evt.get("total_tokens", 0)
            nl(); print(f"  · {total} tokens")
            if total >= int(ctx * 0.85):  # near the window → context will start to truncate
                print(f"  ⚠ nearing the {ctx}-token context window; start a fresh "
                      f"session (/exit, rerun — or /mode toggles a new segment) to avoid truncation")
            return
        if etype != "message":
            return
        content = evt.get("message", {}).get("content", [])
        if isinstance(content, str):
            if content.strip():
                nl(); print(content.strip())
            return
        for p in content if isinstance(content, list) else []:
            if not isinstance(p, dict):
                continue
            pt = p.get("type")
            if pt == "text":
                txt = p.get("text", "")
                if txt:
                    sys.stdout.write(txt); sys.stdout.flush(); mid_line = True
            elif pt == "toolRequest":
                call = (p.get("toolCall") or {}).get("value") or {}
                nl(); print(f"  ⚙ {call.get('name', 'tool')}({_clip(call.get('arguments', ''), 120)})")
            elif pt == "toolResponse":
                res = (p.get("toolResult") or {}).get("value") or {}
                texts = [c.get("text", "") for c in res.get("content", [])
                         if isinstance(c, dict) and c.get("type") == "text"]
                mark = "✗" if res.get("isError") else "↳"
                nl(); print(f"  {mark} {_clip(' '.join(texts), 200)}")

    return emit


def _session_logger(workdir: str, session: str | None, on_event):
    """Wrap `on_event` so every stream-json event is also appended, verbatim, to a
    per-session JSONL under <workdir>/.legate/sessions/ — an audit trail of the run
    (what the model said, every tool call and result), which matters for authorized
    security work and for debugging runaway turns. Returns (wrapped_on_event, fh);
    logging never fails the run — a log error is swallowed and the run continues."""
    import json
    name = session or time.strftime("legate-%Y%m%d-%H%M%S")
    logdir = os.path.join(workdir or ".", ".legate", "sessions")
    try:
        os.makedirs(logdir, exist_ok=True)
        fh = open(os.path.join(logdir, f"{name}.jsonl"), "a", encoding="utf-8")
    except OSError:
        return on_event, None  # can't open the log → run without it

    def wrapped(evt: dict) -> None:
        try:
            fh.write(json.dumps(evt, ensure_ascii=False) + "\n"); fh.flush()
        except Exception:
            pass
        if on_event is not None:
            on_event(evt)

    return wrapped, fh


# Steers a small model on a live engagement: use the routed tools, but fall back
# to the shell when a tool errors or needs a backend that isn't up — and stop
# looping. Without this the model hammers a broken tool for dozens of turns. This
# is a SYSTEM-instructions block (appended to LEGATE_INSTRUCTIONS in the recipe),
# not glued onto the task — the user's request stays clean in the recipe prompt.
_SECURITY_STEER = (
    "This is authorized security work (pentest, red team, or another cybersecurity "
    "task on a sanctioned target/scope). Use the mounted Praetor tools for the task. "
    "If a tool errors or reports that a backend (e.g. Burp) or binary is unavailable, "
    "DO NOT retry it — fall back to the shell tool with standard CLI tooling (curl, "
    "httpx, gobuster, ffuf, nmap, and the like); this is how you reach a capability "
    "outside the mounted tool set. After you have gathered results, write them to "
    "findings.md and give a short summary, then stop. Do not repeat a tool call that "
    "already failed."
)


def _security_instructions() -> str:
    from legate.recipe import LEGATE_INSTRUCTIONS
    return LEGATE_INSTRUCTIONS + "\n\n" + _SECURITY_STEER


def _coding_instructions(workdir: str) -> str:
    """Base identity/steering plus a compact repo map of `workdir`, when it has
    Python to map — so the coding path starts with the codebase skeleton."""
    from legate.recipe import LEGATE_INSTRUCTIONS
    from legate.repomap import build_repo_map
    rmap = build_repo_map(workdir)
    if not rmap:
        return LEGATE_INSTRUCTIONS
    return (LEGATE_INSTRUCTIONS + "\n\nRepo map (symbols only — open a file for its "
            "full contents):\n" + rmap)


def handle(cfg, text: str, workdir: str, max_turns: int = 20, stream: bool = False,
           session: str | None = None, resume: bool = False, renderer=None,
           mode: str | None = None) -> str:
    """Route one request and drive it. With `stream`, events render live via a
    renderer and the return value is a compact status line (the body already
    printed). Pass `renderer` (an event callback) to override the default plain-text
    one — the TUI passes a rich renderer. `session`/`resume` carry context. `mode`
    ('coding'/'security'/None) forces the route past the auto-classifier."""
    from legate.goose import run_goose

    if not server_up(cfg):
        return (f"[model server not reachable at {cfg.endpoint} — start it first:\n"
                f"    bash scripts/serve.sh &\n"
                f"then try again. (nothing was run)]")

    # Fast-path: a greeting or trivial question gets a direct tool-less reply.
    if _is_smalltalk(text) and mode is None:
        try:
            return _direct_reply(cfg, text)
        except Exception:
            pass  # fall through to the full agent if the direct call fails

    on_event = (renderer or make_renderer()) if stream else None
    # Tee every event to a per-session audit log (best-effort); close it after.
    log_fh = None
    if on_event is not None:
        on_event, log_fh = _session_logger(workdir, session, on_event)
    kind, phase = route(text, mode)
    query = text
    try:
        if kind == "security":
            # Security work runs on the (typically uncensored) security model, with the
            # security steering carried in the recipe's system instructions (not the task).
            scfg = replace(cfg, model=cfg.security_model, endpoint=cfg.security_endpoint)
            sec_instr = _security_instructions()
            cmd, args, cwd = _praetor_env()
            if cmd:  # Praetor configured → mount its phase tools + engage
                from legate.pentest import run_engagement
                plan, result = run_engagement(scfg, cmd, args, phase=phase,
                                              task=text, query=query,
                                              praetor_cwd=cwd, workdir=workdir,
                                              max_turns=max_turns, on_event=on_event,
                                              session=session, resume=resume,
                                              instructions=sec_instr)
                head = (f"[security · {scfg.model} · phase={phase} · "
                        f"{len(plan.selected_tools)}/{plan.total_tools} Praetor tools]")
            else:  # no Praetor → still run on the uncensored model with the shell/editor
                result = run_goose(scfg, Path(workdir), text,
                                   max_turns=max_turns, on_event=on_event,
                                   session=session, resume=resume, instructions=sec_instr)
                head = f"[security · {scfg.model} · shell (Praetor not configured)]"
            if stream:
                return head + (f"  [error: {result.error}]" if result.error else "")
            body = result.final_text or "(no text output)"
            return f"{head}\n{body}" + (f"\n[error: {result.error}]" if result.error else "")
        # coding — prepend a compact repo map so a short-context model knows the
        # codebase shape without reading every file first.
        result = run_goose(cfg, Path(workdir), text, max_turns=max_turns, on_event=on_event,
                           session=session, resume=resume,
                           instructions=_coding_instructions(workdir))
        if stream:
            return "[coding done]" + (f"  [error: {result.error}]" if result.error else "")
        body = result.final_text or "(no text output)"
        return f"[coding]\n{body}" + (f"\n[error: {result.error}]" if result.error else "")
    finally:
        if log_fh is not None:
            try:
                log_fh.close()
            except Exception:
                pass


_HELP = (
    "  just type a request — coding or a security task; it auto-routes\n"
    "  /cwd <dir>              set the working directory\n"
    "  /mode auto|coding|security   force the route (default: auto)\n"
    "  /help                   this help\n"
    "  /exit                   quit  (or ctrl-d)\n"
    "  copy/paste works normally — this is your terminal's own scrollback"
)


def chat_loop(cfg, workdir: str | None = None, max_turns: int = 20) -> int:
    """Interactive line-mode REPL: type a request, Legate routes and streams the
    result to normal terminal scrollback — so your terminal's native selection and
    copy/paste work as usual. One Goose session, so context carries across turns."""
    cwd = workdir or os.getcwd()
    base = f"legate-{os.getpid()}"
    prev_tag: str | None = None
    seg = 0
    mode: str | None = None  # None = auto; else forced 'coding'/'security' via /mode
    print(f"legate · {cfg.model} · local")
    print(f"{cwd}   (/help, /exit)")
    while True:
        try:
            line = input("\n❯ ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return 0
        if not line:
            continue
        if line in ("/exit", "/quit"):
            return 0
        if line == "/help":
            print(_HELP)
            continue
        if line.startswith("/cwd "):
            cand = os.path.expanduser(line[5:].strip())
            if os.path.isdir(cand):
                cwd = cand
                print(cwd)
            else:
                print(f"not a directory: {cand}")
            continue
        if line == "/mode" or line.startswith("/mode "):
            arg = line[5:].strip().lower()
            if arg in ("", "auto"):
                mode = None; print("mode: auto")
            elif arg in ("coding", "security"):
                mode = arg; print(f"mode: {arg}")
            else:
                print("usage: /mode auto|coding|security")
            continue
        kind, phase = route(line, mode)
        tag = f"security/{phase}" if kind == "security" else "coding"
        print(f"→ {tag}")
        # A Goose session binds its mounted tool set at init, so --resume keeps the
        # PREVIOUS turn's tools. Resume only when the route (hence the tool set) is
        # unchanged — carrying context forward; on a route/phase change, start a
        # fresh session segment so the new phase's tools actually mount.
        resume = tag == prev_tag
        if prev_tag is not None and not resume:
            seg += 1
        session = f"{base}-{seg}"
        try:
            print(handle(cfg, line, cwd, max_turns=max_turns, stream=True,
                         session=session, resume=resume, mode=mode))
        except Exception as e:  # keep the REPL alive on a single failed turn
            print(f"[turn failed: {type(e).__name__}: {e}]")
        prev_tag = tag
