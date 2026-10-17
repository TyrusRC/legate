"""Smoke tests for the chat-first CLI: bare `legate` and `legate chat` open the
agent; only doctor/models remain as utility subcommands."""
import legate.cli as cli


def _parser():
    # The REAL parser main() uses — so these assertions can't drift from it.
    return cli.build_parser()


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
