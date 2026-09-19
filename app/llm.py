from __future__ import annotations

import anthropic

from .config import MAX_OUTPUT_TOKENS, MODEL
from .store import add_step

_client: anthropic.Anthropic | None = None


def client() -> anthropic.Anthropic:
    global _client
    if _client is None:
        _client = anthropic.Anthropic()
    return _client


def complete(run: dict, system: str, messages: list[dict], tools: list[dict]):
    last_error = None
    for _ in range(3):
        try:
            filtered_msgs = []
            for msg in messages:
                if isinstance(msg.get("content"), list):
                    clean = [b for b in msg["content"] if not (hasattr(b, "type") and b.type == "thinking") and not (isinstance(b, dict) and b.get("type") == "thinking")]
                    if clean:
                        filtered_msgs.append({**msg, "content": clean})
                else:
                    filtered_msgs.append(msg)
            response = client().messages.create(
                model=MODEL,
                max_tokens=MAX_OUTPUT_TOKENS,
                system=system,
                messages=filtered_msgs,
                tools=tools,
            )
        except Exception as exc:
            last_error = exc
            continue

        out_tokens = response.usage.output_tokens
        if hasattr(response.usage, "cache_read_input_tokens"):
            pass
        content_dump = []
        for block in response.content:
            d = block.model_dump()
            if d.get("type") == "thinking":
                out_tokens = max(0, out_tokens - len(d.get("thinking", "")) // 4)
            content_dump.append(d)
        add_step(
            run,
            type="llm",
            model=MODEL,
            system=system,
            stop_reason=response.stop_reason,
            input_tokens=response.usage.input_tokens,
            output_tokens=out_tokens,
            content=content_dump,
        )
        return response

    raise last_error


def first_text(response) -> str:
    return response.content[0].text
