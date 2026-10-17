"""Smoke tests for the chat-first CLI: bare `legate` and `legate chat` open the
agent; only doctor/models remain as utility subcommands."""
import argparse
import legate.cli as cli


def _parser():
    # Rebuild just the parser the way main() does, to assert its shape.
    ap = argparse.ArgumentParser(prog="legate")
    sub = ap.add_subparsers(dest="cmd", required=False)
    cp = sub.add_parser("chat")
    cp.add_argument("request", nargs="*")
    cp.add_argument("--cwd", default=None)
    cp.add_argument("--max-turns", type=int, default=20)
    sub.add_parser("doctor")
    mp = sub.add_parser("models")
    msub = mp.add_subparsers(dest="models_cmd", required=True)
    msub.add_parser("recommend")
    return ap


def test_bare_invocation_has_no_required_subcommand():
    # Bare `legate` must parse (opens the agent), not error for a missing command.
    ns = _parser().parse_args([])
    assert ns.cmd is None


def test_chat_oneshot_request_parses():
    ns = _parser().parse_args(["chat", "recon", "http://x/"])
    assert ns.cmd == "chat" and ns.request == ["recon", "http://x/"]


def test_legacy_task_subcommands_are_gone():
    # solve / eval / pentest were removed in favor of the chat agent.
    for gone in ("solve", "eval", "pentest"):
        import pytest
        with pytest.raises(SystemExit):
            _parser().parse_args([gone])


def test_utility_subcommands_remain():
    assert _parser().parse_args(["doctor"]).cmd == "doctor"
    assert _parser().parse_args(["models", "recommend"]).models_cmd == "recommend"
