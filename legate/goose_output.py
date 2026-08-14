import json
from dataclasses import dataclass, field
from typing import Iterable


@dataclass
class GooseResult:
    """Parsed outcome of a `goose run --output-format stream-json` invocation.

    Note: Goose's JSON `status` is always "completed" on the normal path, so
    failure is inferred from `error` (an emitted error event) or a non-zero
    process exit code (set by the caller), never from a success flag here.
    """

    messages: list[dict] = field(default_factory=list)
    total_tokens: int = 0
    cost_usd: float = 0.0
    error: str | None = None


def parse_stream_json(lines: Iterable[str]) -> GooseResult:
    """Parse Goose stream-json (one JSON object per line) into a GooseResult.

    Blank and malformed lines are skipped so a partial/garbled stream still
    yields whatever structured events were emitted.
    """
    result = GooseResult()
    for line in lines:
        line = line.strip()
        if not line:
            continue
        try:
            evt = json.loads(line)
        except json.JSONDecodeError:
            continue
        etype = evt.get("type")
        if etype == "message":
            result.messages.append(evt["message"])
        elif etype == "error":
            result.error = evt.get("error", "unknown error")
        elif etype == "complete":
            result.total_tokens = evt.get("total_tokens", 0)
            result.cost_usd = evt.get("cost_usd", 0.0)
    return result
