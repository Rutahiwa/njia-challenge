"""Runs and conversation history."""
from __future__ import annotations

import threading
import time
import uuid

RUNS: dict[str, dict] = {}
HISTORY: dict[str, list[dict]] = {}
SEEN_MESSAGES: set[str] = set()
TAKEN_OVER: set[str] = set()
MAX_HISTORY = 40
_lock = threading.Lock()

_step_callback = None


def on_step(callback):
    global _step_callback
    _step_callback = callback


def takeover(conversation_id: str) -> None:
    TAKEN_OVER.add(conversation_id)


def is_taken_over(conversation_id: str) -> bool:
    return conversation_id in TAKEN_OVER


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
    with _lock:
        RUNS[run["run_id"]] = run
    # Persist run for crash recovery
    try:
        from . import recovery
        recovery.save_run(run)
    except Exception:
        pass
    return run


def add_step(run: dict, **step) -> None:
    step["at"] = time.time()
    run["steps"].append(step)
    budget = run["budget"]
    if step.get("type") == "tool" and step.get("output"):
        budget["tool_calls"] += 1
    if step.get("type") == "llm":
        budget["input_tokens"] += step.get("input_tokens", 0)
        budget["output_tokens"] += step.get("output_tokens", 0)
    if _step_callback:
        _step_callback(run["run_id"], step)


MAX_OUTPUT_TOKENS_BUDGET = 4000

def over_budget(run: dict) -> bool:
    from .config import MAX_INPUT_TOKENS, MAX_TOOL_CALLS
    budget = run["budget"]
    return (budget["tool_calls"] >= MAX_TOOL_CALLS
            or budget["input_tokens"] >= MAX_INPUT_TOKENS
            or budget["output_tokens"] >= MAX_OUTPUT_TOKENS_BUDGET)


def history(conversation_id: str) -> list[dict]:
    with _lock:
        messages = HISTORY.setdefault(conversation_id, [])
        if len(messages) > MAX_HISTORY:
            del messages[:-MAX_HISTORY]
        return list(messages)


def already_handled(message_id: str) -> bool:
    with _lock:
        if message_id in SEEN_MESSAGES:
            return True
        SEEN_MESSAGES.add(message_id)
        return False


def finish(run: dict, reply: str | None = None) -> None:
    run["reply"] = reply
    run["status"] = "done"
    # Persist the user message and assistant reply to HISTORY for multi-turn continuity
    conversation_id = run.get("conversation_id")
    if conversation_id and reply:
        with _lock:
            messages = HISTORY.setdefault(conversation_id, [])
            # The user message was added by the caller (run_agent) on a local copy;
            # find it from the run's trigger and add both user + assistant messages.
            trigger = run.get("trigger_text")
            if trigger:
                messages.append({"role": "user", "content": trigger})
            messages.append({"role": "assistant", "content": reply})


def fail(run: dict, error_msg: str | None = None) -> None:
    run["status"] = "error"
    if error_msg:
        run["error"] = error_msg
