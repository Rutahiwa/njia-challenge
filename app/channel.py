"""WhatsApp in, WhatsApp out."""
from __future__ import annotations

import threading

import httpx

from . import logs
from .agent import run_agent
from .config import DEBOUNCE_SECONDS, MOCK_URL
from .store import already_handled, new_run

PENDING: dict[str, list[str]] = {}
TIMERS: dict[str, threading.Timer] = {}


def send(to: str, text: str) -> None:
    with httpx.Client(base_url=MOCK_URL, timeout=10) as http:
        http.post("/whatsapp/send", json={"to": to, "text": text})
    logs.info("reply.sent", to=to, length=len(text))


def _fire(conversation_id: str) -> None:
    text = "".join(PENDING.pop(conversation_id, []))
    run = new_run(conversation_id, trigger="debounced")
    logs.bind(run["run_id"], conversation_id)
    logs.info("run.started", text=text)
    reply = run_agent(run, text)
    send(conversation_id, reply)


def receive(message: dict) -> dict:
    conversation_id = message["from"]
    PENDING.setdefault(conversation_id, []).append(message["text"])

    if already_handled(message["message_id"]):
        logs.info("message.duplicate", message_id=message["message_id"])
        return {"duplicate": True}

    timer = TIMERS.get(conversation_id)
    if timer is not None:
        timer.cancel()
    TIMERS[conversation_id] = threading.Timer(DEBOUNCE_SECONDS, _fire, args=(conversation_id,))
    TIMERS[conversation_id].start()
    return {"queued": True}
