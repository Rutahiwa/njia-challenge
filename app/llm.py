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
            response = client().messages.create(
                model=MODEL,
                max_tokens=MAX_OUTPUT_TOKENS,
                system=system,
                messages=messages,
                tools=tools,
            )
        except Exception as exc:
            last_error = exc
            continue

        add_step(
            run,
            type="llm",
            model=MODEL,
            system=system,
            stop_reason=response.stop_reason,
            input_tokens=response.usage.input_tokens,
            output_tokens=response.usage.output_tokens,
            content=[block.model_dump() for block in response.content],
        )
        return response

    raise last_error


def first_text(response) -> str:
    return response.content[0].text
