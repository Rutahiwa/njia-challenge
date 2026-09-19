"""WhatsApp in, WhatsApp out."""
from __future__ import annotations

import threading

import httpx

from . import logs
from .agent import run_agent
from .config import DEBOUNCE_SECONDS, MOCK_URL
from .store import already_handled, is_taken_over, new_run
from . import recovery

PENDING: dict[str, list[str]] = {}
TIMERS: dict[str, threading.Timer] = {}
_pending_lock = threading.Lock()


def send(to: str, text: str) -> None:
    with httpx.Client(base_url=MOCK_URL, timeout=10) as http:
        http.post("/whatsapp/send", json={"to": to, "text": text})
    logs.info("reply.sent", to=to, length=len(text))


def _fire(conversation_id: str) -> None:
    with _pending_lock:
        text = " ".join(PENDING.pop(conversation_id, []))
    if is_taken_over(conversation_id):
        logs.info("run.skipped", reason="taken_over")
        return
    run = new_run(conversation_id, trigger="debounced")
    logs.bind(run["run_id"], conversation_id)
    logs.info("run.started", text=text)
    try:
        reply = run_agent(run, text)
        send(conversation_id, reply)
    except Exception:
        # agent.py already called fail() and logged the error; avoid duplicates
        pass


def receive(message: dict) -> dict:
    conversation_id = message["from"]

    if already_handled(message["message_id"]):
        logs.info("message.duplicate", message_id=message["message_id"])
        return {"duplicate": True}

    text = message.get("text") or ""
    with _pending_lock:
        PENDING.setdefault(conversation_id, []).append(text)

        timer = TIMERS.get(conversation_id)
        if timer is not None:
            timer.cancel()
        TIMERS[conversation_id] = threading.Timer(DEBOUNCE_SECONDS, _fire, args=(conversation_id,))
        TIMERS[conversation_id].start()
    return {"queued": True}
