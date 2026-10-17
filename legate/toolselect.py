"""Two-stage tool selection so a small local model can drive a huge MCP surface.

Praetor exposes ~390 tools; a 3B-active model cliffs above ~15 in context. For a
given phase/query we surface a capped working set: the phase's tool group, topped
up by lexical **BM25** hits over tool name+description for the current query
(cross-phase relevance). BM25, not embeddings: security jargon is exact-match
("sqli", "jwt", "ssrf"), and it costs zero VRAM. The selection is baked into the
Goose recipe at mount time — it is not a live tool the model calls.

Pure stdlib — no numpy, no model. The router output is capped so the surfaced
schema stays within the small model's reliable working set.
"""
from __future__ import annotations

import math
import re
from collections import Counter
from dataclasses import dataclass, field

# Ordered kill-chain phases + the lexical cues that map a tool into one. These span
# both web pentest AND red-team engagements (the offensive chain is the same shape);
# `post` covers post-exploitation / red-team tradecraft. A tool can match several;
# assign_phase picks the earliest strong match, else "general".
PHASES: dict[str, list[str]] = {
    "recon": ["recon", "sitemap", "crawl", "spider", "endpoint", "subfinder", "amass",
              "discover", "wayback", "gau", "katana", "tech", "fingerprint", "enumerate",
              "osint", "footprint", "asset", "dns", "whois"],
    "scan": ["scan", "nuclei", "audit", "matcher", "probe", "detect", "nikto", "wafw00f",
             "passive", "wpscan", "secrets", "gitleaks", "trufflehog", "opengrep", "sast",
             "portscan", "nmap", "service", "version"],
    "exploit": ["exploit", "sqli", "sqlmap", "xss", "dalfox", "ssrf", "ssti", "xxe", "rce",
                "csrf", "commix", "injection", "payload", "intruder", "jwt", "forge",
                "bypass", "poison", "prototype", "websocket", "collaborator", "oob",
                "shellcode", "metasploit", "cve", "deserialization"],
    # post-exploitation / red-team tradecraft
    "post": ["session", "cookie", "auth", "privilege", "idor", "access", "token",
             "lifecycle", "mfa", "reset", "escalat", "privesc", "lateral", "movement",
             "pivot", "persistence", "beacon", "implant", "c2", "command", "control",
             "exfil", "exfiltrate", "credential", "dump", "kerberos", "mimikatz",
             "evasion", "evade", "opsec", "backdoor", "adversary", "ttp", "mitre"],
    "report": ["report", "finding", "save", "assess", "sarif", "junit", "export",
               "poc", "repro", "compliance", "severity"],
}

_CAMEL = re.compile(r"(?<=[a-z0-9])(?=[A-Z])")

# Security acronyms ↔ their expansions. Applied both to tool docs and queries so
# a query for "server side request forgery" matches a tool named `test_ssrf`, and
# vice-versa. BM25 is exact-match; this bridges the acronym/phrase gap cheaply.
_SYNONYMS: dict[str, tuple[str, ...]] = {
    "ssrf": ("server", "side", "request", "forgery"),
    "xss": ("cross", "site", "scripting"),
    "sqli": ("sql", "injection"),
    "csrf": ("cross", "site", "request", "forgery"),
    "ssti": ("server", "side", "template", "injection"),
    "xxe": ("xml", "external", "entity"),
    "idor": ("insecure", "direct", "object", "reference"),
    "rce": ("remote", "code", "execution"),
    "mfa": ("multi", "factor", "authentication"),
    "lfi": ("local", "file", "inclusion"),
    "rfi": ("remote", "file", "inclusion"),
}


def tokenize(text: str) -> list[str]:
    """Lowercase word tokens; split snake_case and camelCase so `test_sqli` and
    `forgeJwt` both yield their parts, then bridge acronyms ↔ expansions."""
    text = _CAMEL.sub(" ", text)
    tokens = [t for t in re.split(r"[^a-z0-9]+", text.lower()) if t]
    tset = set(tokens)
    for acro, phrase in _SYNONYMS.items():
        if acro in tset:                                  # doc/query has acronym → add words
            tokens.extend(phrase)
        elif all(w in tset for w in phrase):              # has full phrase → add acronym
            tokens.append(acro)
    return tokens


@dataclass
class Tool:
    name: str
    description: str = ""
    phase: str = "general"
    tokens: list[str] = field(default_factory=list)


def assign_phase(name: str, description: str) -> str:
    text = f"{name} {description}".lower()
    for phase, cues in PHASES.items():
        if any(cue in text for cue in cues):
            return phase
    return "general"


class Router:
    """Holds the tool catalog, a BM25 index, and phase groups."""

    def __init__(self, tools: list[dict], k1: float = 1.5, b: float = 0.75):
        self.k1, self.b = k1, b
        self.tools: list[Tool] = []
        for t in tools:
            name, desc = t["name"], t.get("description", "") or ""
            self.tools.append(Tool(name, desc, assign_phase(name, desc),
                                   tokenize(f"{name} {name} {desc}")))  # name weighted 2x
        self._by_name = {t.name: t for t in self.tools}
        self._build_bm25()

    def _build_bm25(self) -> None:
        self.df: Counter = Counter()
        for t in self.tools:
            for term in set(t.tokens):
                self.df[term] += 1
        n = len(self.tools) or 1
        self.idf = {term: math.log(1 + (n - dfi + 0.5) / (dfi + 0.5))
                    for term, dfi in self.df.items()}
        self.avgdl = (sum(len(t.tokens) for t in self.tools) / n) or 1.0

    def _score(self, query_tokens: list[str], t: Tool) -> float:
        if not t.tokens:
            return 0.0
        tf = Counter(t.tokens)
        dl = len(t.tokens)
        s = 0.0
        for term in query_tokens:
            if term not in tf:
                continue
            idf = self.idf.get(term, 0.0)
            num = tf[term] * (self.k1 + 1)
            den = tf[term] + self.k1 * (1 - self.b + self.b * dl / self.avgdl)
            s += idf * num / den
        return s

    def search(self, query: str, k: int = 5) -> list[Tool]:
        """Top-k tools by BM25 over name+description (cross-phase)."""
        qt = list(dict.fromkeys(tokenize(query)))  # dedupe (acronym bridging can repeat terms)
        scored = [(self._score(qt, t), t) for t in self.tools]
        scored = [(s, t) for s, t in scored if s > 0]
        scored.sort(key=lambda x: (-x[0], x[1].name))
        return [t for _, t in scored[:k]]

    def phase_group(self, phase: str) -> list[Tool]:
        return [t for t in self.tools if t.phase == phase]

    def select(self, phase: str | None = None, query: str | None = None,
               cap: int = 15) -> list[Tool]:
        """The surfaced working set, deduped and capped. When both a phase and a
        query are given, roughly half the cap is reserved for cross-phase BM25 hits
        and half for the phase group, so neither crowds the other out: the model
        keeps solid coverage of the current phase AND can reach the query-relevant
        tool even if it lives in another phase. With only one of them, that one
        fills the cap. (This is as far as cross-phase reach goes without a live
        search tool; mid-engagement pivots to an entirely new need still fall back
        to the shell — see chat._SECURITY_STEER.)"""
        chosen: list[Tool] = []
        seen: set[str] = set()

        def add(t: Tool) -> None:
            if t.name not in seen and len(chosen) < cap:
                seen.add(t.name)
                chosen.append(t)

        q_hits = self.search(query, k=cap) if query else []
        p_hits = self.phase_group(phase) if phase else []
        if q_hits and p_hits:
            for t in q_hits[:max(1, cap // 2)]:  # reserve ~half for cross-phase hits
                add(t)
            for t in p_hits:                     # current-phase coverage
                add(t)
            for t in q_hits:                     # backfill leftover slots
                add(t)
        else:
            for t in (q_hits or p_hits):
                add(t)
        return chosen
