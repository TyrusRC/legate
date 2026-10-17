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

    @property
    def final_text(self) -> str:
        """The last assistant text emitted. Goose message content is a list of
        parts; we join the text parts of the last message that has any."""
        for msg in reversed(self.messages):
            content = msg.get("content") if isinstance(msg, dict) else None
            if isinstance(content, str) and content.strip():
                return content.strip()
            if isinstance(content, list):
                texts = [p.get("text", "") for p in content
                         if isinstance(p, dict) and p.get("type") == "text"]
                joined = "\n".join(t for t in texts if t).strip()
                if joined:
                    return joined
        return ""


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
            if "message" in evt:  # tolerate a message event missing the field
                result.messages.append(evt["message"])
        elif etype == "error":
            result.error = evt.get("error", "unknown error")
        elif etype == "complete":
            result.total_tokens = evt.get("total_tokens", 0)
            result.cost_usd = evt.get("cost_usd", 0.0)
    return result
