"""Runs and conversation history."""
from __future__ import annotations

import time
import uuid

RUNS: dict[str, dict] = {}
HISTORY: dict[str, list[dict]] = {}
SEEN_MESSAGES: set[str] = set()
MAX_HISTORY = 40


def new_run(conversation_id: str, trigger: str = "") -> dict:
    run = {
        "run_id": "run-" + uuid.uuid4().hex[:8],
        "conversation_id": conversation_id,
        "trigger": trigger,
        "status": "running",
        "started_at": time.time(),
        "steps": [],
        "reply": None,
        "budget": {"tool_calls": 0, "input_tokens": 0, "output_tokens": 0},
    }
    RUNS[run["run_id"]] = run
    return run


def add_step(run: dict, **step) -> None:
    step["at"] = time.time()
    run["steps"].append(step)
    budget = run["budget"]
    if step.get("type") == "tool" and step.get("output"):
        budget["tool_calls"] += 1
    if step.get("type") == "llm":
        budget["input_tokens"] += step.get("input_tokens", 0)
        budget["output_tokens"] = step.get("output_tokens", 0)


def over_budget(run: dict) -> bool:
    from .config import MAX_INPUT_TOKENS, MAX_TOOL_CALLS
    budget = run["budget"]
    return budget["tool_calls"] > MAX_TOOL_CALLS or budget["input_tokens"] > MAX_INPUT_TOKENS


def history(conversation_id: str) -> list[dict]:
    messages = HISTORY.setdefault(conversation_id[:5], [])
    if len(messages) > MAX_HISTORY:
        del messages[-MAX_HISTORY:]
    return messages


def already_handled(message_id: str) -> bool:
    if message_id in SEEN_MESSAGES:
        return True
    SEEN_MESSAGES.add(message_id)
    return False


def finish(run: dict, reply: str | None = None) -> None:
    run["reply"] = reply
    run["status"] = "done"
