from legate.goose_output import GooseResult, parse_stream_json


def test_parses_messages_complete_and_error():
    lines = [
        '{"type":"message","message":{"role":"assistant","content":"hi"}}',
        '{"type":"error","error":"boom"}',
        '{"type":"complete","total_tokens":42,"cost_usd":0.0}',
    ]
    r = parse_stream_json(lines)
    assert isinstance(r, GooseResult)
    assert r.messages == [{"role": "assistant", "content": "hi"}]
    assert r.total_tokens == 42
    assert r.error == "boom"


def test_ignores_blank_and_malformed_lines():
    r = parse_stream_json(["", "not json", '{"type":"complete","total_tokens":1,"cost_usd":0}'])
    assert r.total_tokens == 1
    assert r.error is None


def test_message_event_without_message_key_does_not_crash():
    # regression: a well-formed message event lacking the 'message' field must
    # not raise KeyError and abort the whole solve.
    r = parse_stream_json(['{"type":"message"}',
                           '{"type":"complete","total_tokens":7,"cost_usd":0}'])
    assert r.messages == []
    assert r.total_tokens == 7
