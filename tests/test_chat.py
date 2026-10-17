from legate.chat import classify_request


def test_coding_requests_route_to_dev():
    for q in ("fix the failing test in ./wordy",
              "refactor parse_config to be O(n)",
              "add a docstring to utils.py"):
        kind, phase, _ = classify_request(q)
        assert kind == "dev", (q, kind)
        assert phase == ""


def test_security_requests_route_to_pentest_with_phase():
    cases = {
        "recon http://testasp.vulnweb.com/": "recon",
        "crawl the site and enumerate urls": "recon",
        "scan 10.0.0.5 for vulnerabilities": "scan",
        "test the login for sql injection": "exploit",
        "escalate privileges via the session cookie": "post",
    }
    for q, expected_phase in cases.items():
        kind, phase, _ = classify_request(q)
        assert kind == "security", (q, kind)
        assert phase == expected_phase, (q, phase, expected_phase)


def test_bare_url_alone_is_a_target():
    kind, _, _ = classify_request("look at https://example.com/app")
    assert kind == "security"


def test_filename_with_dot_is_not_mistaken_for_a_target():
    # a coding request naming a file must not trip target detection
    kind, _, _ = classify_request("update the parser in main.py")
    assert kind == "dev"


def test_red_team_and_broader_cyber_route_to_security():
    from legate.chat import classify_request
    cases = {
        "establish persistence and move laterally on 10.0.0.5": "post",
        "set up a c2 beacon and exfiltrate credentials": "post",
        "run osint footprinting on example.com": "recon",
        "emulate the adversary ttp for privilege escalation": "post",
    }
    for q, expected_phase in cases.items():
        kind, phase, _ = classify_request(q)
        assert kind == "security", (q, kind)
        assert phase == expected_phase, (q, phase, expected_phase)


def test_handle_fails_fast_when_server_down(monkeypatch, tmp_path):
    # A dead model endpoint must return a clear message, not hang on goose.
    import legate.chat as c
    from legate.config import Config
    monkeypatch.setattr(c, "server_up", lambda cfg, timeout=3.0: False)
    out = c.handle(Config.default(), "hi", str(tmp_path))
    assert "not reachable" in out and "serve.sh" in out


def test_smalltalk_takes_the_tool_less_fast_path(monkeypatch):
    # Greetings/trivial questions must NOT spawn the agent; they get a direct reply.
    import legate.chat as c
    from legate.config import Config
    monkeypatch.setattr(c, "server_up", lambda cfg, timeout=3.0: True)
    monkeypatch.setattr(c, "_direct_reply", lambda cfg, text, timeout=60.0: "hi, I'm Legate")
    # if the agent path were taken this would raise (run_goose not reachable in test)
    monkeypatch.setattr(c, "make_renderer", lambda: (_ for _ in ()).throw(AssertionError("agent spawned")))
    out = c.handle(Config.default(), "hello", "/tmp", stream=True)
    assert out == "hi, I'm Legate"


def test_real_task_is_not_smalltalk():
    from legate.chat import _is_smalltalk
    assert not _is_smalltalk("help me fix the parser")
    assert not _is_smalltalk("scan 10.0.0.5 for sqli")
    assert _is_smalltalk("Hello!") and _is_smalltalk("who are you?")


def test_security_routes_to_security_model(monkeypatch, tmp_path):
    # Security work must use cfg.security_model (e.g. an uncensored gemma), not the
    # coding model. Verify handle() passes the security model to the runner.
    import legate.chat as c
    from legate.config import Config
    from dataclasses import replace
    cfg = replace(Config.default(), model="qwen3-coder", security_model="gemma4-obliterated")
    monkeypatch.setattr(c, "server_up", lambda cfg, timeout=3.0: True)
    monkeypatch.setattr(c, "_praetor_env", lambda: (None, [], None))  # no Praetor → shell path
    seen = {}
    def fake_run_goose(scfg, cwd, task, max_turns=30, on_event=None, session=None,
                       resume=False, instructions=None):
        seen["model"] = scfg.model
        seen["instructions"] = instructions
        seen["task"] = task
        from legate.goose_output import GooseResult
        return GooseResult(total_tokens=1)
    monkeypatch.setattr(c, "run_goose", fake_run_goose, raising=False)
    import legate.goose as g
    monkeypatch.setattr(g, "run_goose", fake_run_goose)
    out = c.handle(cfg, "exploit sqli on 10.0.0.5", str(tmp_path), stream=True)
    assert seen["model"] == "gemma4-obliterated", seen
    assert "security · gemma4-obliterated" in out
    # security steering rides in the recipe instructions, and the task stays clean
    assert "authorized security work" in (seen["instructions"] or "").lower()
    assert seen["task"] == "exploit sqli on 10.0.0.5"


def test_mode_override_forces_route():
    from legate.chat import route
    assert route("hello there", "security") == ("security", "recon")   # forced, default phase
    assert route("scan 10.0.0.5 for vulnerabilities", "coding") == ("dev", "")
    assert route("fix the parser", None)[0] == "dev"                   # auto = classifier
    assert route("sql injection on http://t/", None)[0] == "security"


def test_session_logger_writes_jsonl_and_still_forwards(tmp_path):
    import json
    from legate.chat import _session_logger
    forwarded = []
    wrapped, fh = _session_logger(str(tmp_path), "sess1", forwarded.append)
    wrapped({"type": "message", "x": 1})
    wrapped({"type": "complete", "total_tokens": 7})
    fh.close()
    log = tmp_path / ".legate" / "sessions" / "sess1.jsonl"
    rows = [json.loads(l) for l in log.read_text().splitlines() if l]
    assert [r.get("total_tokens") for r in rows][-1] == 7
    assert forwarded == [{"type": "message", "x": 1}, {"type": "complete", "total_tokens": 7}]
