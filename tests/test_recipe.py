import json

from legate.recipe import (
    CONTROL_TOOLS,
    build_recipe,
    render_recipe,
    select_praetor_tools,
)
from legate.toolselect import Router

TOOLS = [
    {"name": "run_sqlmap", "description": "SQL injection via sqlmap over Burp."},
    {"name": "confirm_sqli", "description": "Confirm a SQL injection finding."},
    {"name": "test_xss", "description": "Reflected/stored cross-site scripting via dalfox."},
    {"name": "forge_jwt", "description": "Forge a JWT (alg none, key confusion)."},
    {"name": "run_nuclei", "description": "Scan for known vulns with nuclei."},
    {"name": "save_finding", "description": "Save a finding to the report pipeline."},
]


def test_select_always_includes_control_tools_and_respects_cap():
    r = Router(TOOLS)
    sel = select_praetor_tools(r, phase="exploit", query="sql injection", cap=5)
    assert sel[:2] == CONTROL_TOOLS
    assert len(sel) <= 5
    assert "run_sqlmap" in sel                      # query-relevant hit surfaced
    assert len(sel) == len(set(sel))                # no dupes


def test_build_recipe_mounts_praetor_with_allowlist():
    rec = build_recipe("/venv/python", ["-m", "burpsuite_mcp"], "exploit",
                       ["search_tools", "advance_phase", "run_sqlmap"])
    exts = {e["name"]: e for e in rec["extensions"]}
    assert exts["developer"]["type"] == "builtin"
    assert exts["praetor"]["type"] == "stdio"
    assert exts["praetor"]["available_tools"] == ["search_tools", "advance_phase", "run_sqlmap"]
    assert rec["title"] == "legate-praetor-exploit"


def test_render_recipe_is_parseable_yaml_shape():
    rec = build_recipe("/venv/python", ["-m", "burpsuite_mcp"], "scan",
                       ["search_tools", "run_nuclei"])
    text = render_recipe(rec)
    assert '"stdio"' in text
    assert 'cmd: "/venv/python"' in text
    # inline lists must be valid JSON (a valid YAML flow sequence)
    for line in text.splitlines():
        if "available_tools:" in line or line.strip().startswith("args:"):
            payload = line.split(":", 1)[1].strip()
            json.loads(payload)  # raises if malformed


def test_render_recipe_escapes_nasty_scalars():
    # regression: backslashes (Windows path), quotes, and a prompt whose first
    # line is indented + multiline must all produce valid YAML. Every scalar
    # value is JSON — validate each renders as parseable JSON (JSON ⊂ YAML).
    from legate.recipe import build_dev_recipe
    rec = build_dev_recipe('  indented first line\nsecond "quoted" line\npath C:\\tmp\\x',
                           tools=['edit'])
    text = render_recipe(rec)
    for line in text.splitlines():
        stripped = line.strip()
        # scalar lines are `key: <json>`; skip structural/list lines
        if stripped.startswith(("version:", "title:", "description:", "cmd:",
                                "cwd:", "name:", "type:", "prompt:")):
            json.loads(stripped.split(":", 1)[1].strip())  # raises if malformed
