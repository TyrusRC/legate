from legate.toolselect import Router, assign_phase, tokenize

TOOLS = [
    {"name": "get_sitemap", "description": "Get Burp's site map of discovered URLs/endpoints."},
    {"name": "extract_api_endpoints", "description": "Extract API endpoints from proxy history."},
    {"name": "run_nuclei", "description": "Run nuclei templates to scan for known vulnerabilities."},
    {"name": "test_sqli", "description": "Test a parameter for SQL injection using sqlmap over Burp."},
    {"name": "test_xss", "description": "Test for reflected and stored cross-site scripting via dalfox."},
    {"name": "forge_jwt", "description": "Forge a JWT with 8 attack modes (alg none, key confusion)."},
    {"name": "test_login_bypass", "description": "Attempt authentication bypass on a login form."},
    {"name": "save_finding", "description": "Save a validated finding to the report pipeline."},
    {"name": "generate_repro_script", "description": "Render a runnable curl repro from a finding."},
    {"name": "curl_request", "description": "Send a curl-style HTTP request through Burp's proxy."},
]


def test_tokenize_splits_snake_and_camel():
    assert tokenize("test_sqli")[:2] == ["test", "sqli"]
    assert tokenize("forgeJwt") == ["forge", "jwt"]


def test_tokenize_bridges_acronym_and_expansion():
    # acronym present -> expansion added, and vice-versa (so BM25 matches either)
    assert set(tokenize("test_ssrf")) >= {"ssrf", "server", "request", "forgery"}
    assert "ssrf" in tokenize("server side request forgery attack")


def test_assign_phase_by_jargon():
    assert assign_phase("test_sqli", "SQL injection via sqlmap") == "exploit"
    assert assign_phase("get_sitemap", "site map of endpoints") == "recon"
    assert assign_phase("run_nuclei", "scan for known vulns") == "scan"
    assert assign_phase("save_finding", "save to report") == "report"
    assert assign_phase("test_login_bypass", "authentication bypass") in ("exploit", "post")


def test_bm25_ranks_the_obvious_tool_first():
    r = Router(TOOLS)
    assert r.search("sql injection", k=1)[0].name == "test_sqli"
    assert r.search("jwt token forgery", k=1)[0].name == "forge_jwt"
    assert r.search("cross site scripting", k=1)[0].name == "test_xss"


def test_search_returns_nothing_for_unmatched_query():
    r = Router(TOOLS)
    assert r.search("kubernetes helm chart", k=5) == []


def test_select_caps_and_prioritizes_query_hits():
    r = Router(TOOLS)
    sel = r.select(phase="recon", query="sql injection", cap=3)
    assert len(sel) <= 3
    # the query hit must be surfaced even though phase is recon (cross-phase pivot)
    assert "test_sqli" in [t.name for t in sel]


def test_select_dedups_across_phase_and_query():
    r = Router(TOOLS)
    sel = r.select(phase="exploit", query="sqli", cap=15)
    names = [t.name for t in sel]
    assert len(names) == len(set(names))
