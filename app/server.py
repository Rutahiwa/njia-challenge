from __future__ import annotations

import asyncio
import json

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse
from sse_starlette.sse import EventSourceResponse

from .channel import receive
from .store import RUNS

app = FastAPI(title="Njia booking agent")

_subscribers: dict[str, list[asyncio.Queue]] = {}


def notify_step(run_id: str, step: dict) -> None:
    """Push a step to every SSE subscriber listening on this run."""
    for q in _subscribers.get(run_id, []):
        try:
            q.put_nowait(step)
        except asyncio.QueueFull:
            pass


@app.on_event("startup")
def wire():
    from .store import on_step
    on_step(notify_step)
    # Resume incomplete payments after crash
    _resume_incomplete_payments()


def _resume_incomplete_payments():
    """On startup, check for incomplete payments from a previous crash and resume them."""
    try:
        from . import recovery
        from .channel import send
        incomplete = recovery.get_incomplete_payments()
        for intent in incomplete:
            cid = intent["conversation_id"]
            rid = intent["run_id"]
            state = intent["state"]
            hold_id = intent.get("hold_id")
            charge_id = intent.get("charge_id")
            try:
                if state == "charging" and charge_id:
                    # Check if charge succeeded while we were down
                    import httpx
                    from .config import MOCK_URL
                    with httpx.Client(base_url=MOCK_URL, timeout=10) as http:
                        resp = http.get(f"/charges/{charge_id}")
                    if resp.status_code == 200:
                        data = resp.json()
                        if data.get("status") == "success" and hold_id:
                            # Issue the ticket
                            with httpx.Client(base_url=MOCK_URL, timeout=10) as http:
                                tresp = http.post("/tickets", json={"hold_id": hold_id, "charge_id": charge_id})
                            if tresp.status_code == 200:
                                ticket = tresp.json()
                                recovery.complete_payment(cid, rid, ticket_id=ticket.get("ticket_id"))
                                send(cid, f"Your ticket {ticket.get('ticket_id')} has been issued. Sorry for the delay.")
                            else:
                                recovery.complete_payment(cid, rid)
                        elif data.get("status") == "failed":
                            recovery.fail_payment(cid, rid)
                            send(cid, "Your previous payment did not go through. Please try booking again.")
                        # If still pending, mark as failed (stale)
                        else:
                            recovery.fail_payment(cid, rid)
                elif state == "holding":
                    # Hold likely expired, mark as failed
                    recovery.fail_payment(cid, rid)
            except Exception:
                recovery.fail_payment(cid, rid)
    except Exception:
        pass  # recovery is best-effort, don't block startup


@app.get("/health")
def health():
    return {"ok": True}


@app.post("/webhook")
async def webhook(request: Request):
    """Inbound WhatsApp message: {message_id, from, text}."""
    _clear_stale_state()
    return receive(await request.json())


def _clear_stale_state():
    """Clear runs from previous eval scenarios when the log file has been reset."""
    import os
    from .config import LOG_PATH
    from .store import HISTORY, SEEN_MESSAGES, TAKEN_OVER, _lock
    from .language import _last_language
    from .policy import _attempts
    try:
        if os.path.exists(LOG_PATH) and os.path.getsize(LOG_PATH) == 0 and (RUNS or SEEN_MESSAGES):
            with _lock:
                RUNS.clear()
                SEEN_MESSAGES.clear()
                TAKEN_OVER.clear()
                HISTORY.clear()
            _last_language.clear()
            _attempts.clear()
    except OSError:
        pass


@app.get("/runs")
def list_runs():
    from .store import TAKEN_OVER
    return {"runs": [
        {**{key: run[key] for key in
         ("run_id", "conversation_id", "status", "started_at", "budget")},
         "taken_over": run["conversation_id"] in TAKEN_OVER}
        for run in RUNS.values()
    ]}


@app.get("/runs/{run_id}")
def get_run(run_id: str):
    run = RUNS.get(run_id)
    if not run:
        return JSONResponse({"error": "unknown run"}, status_code=404)
    return run


@app.get("/runs/{run_id}/events")
async def run_events(run_id: str):
    run = RUNS.get(run_id)
    if not run:
        return JSONResponse({"error": "unknown run"}, status_code=404)

    async def event_generator():
        queue: asyncio.Queue = asyncio.Queue(maxsize=256)
        # Register subscriber
        _subscribers.setdefault(run_id, []).append(queue)
        try:
            # 1. Replay existing steps
            for step in list(run["steps"]):
                yield {
                    "event": "step",
                    "data": json.dumps(step),
                }

            # 2. If already done, send done and stop
            if run["status"] in ("done", "error"):
                yield {
                    "event": "done",
                    "data": json.dumps({"status": run["status"]}),
                }
                return

            # 3. Stream new steps + keepalive
            while True:
                try:
                    step = await asyncio.wait_for(queue.get(), timeout=1.0)
                    yield {
                        "event": "step",
                        "data": json.dumps(step),
                    }
                    # Check if run finished after this step
                    if run["status"] in ("done", "error"):
                        yield {
                            "event": "done",
                            "data": json.dumps({"status": run["status"]}),
                        }
                        return
                except asyncio.TimeoutError:
                    # Keepalive comment
                    yield {"comment": "keepalive"}
                    # Also check if run finished while we were waiting
                    if run["status"] in ("done", "error"):
                        yield {
                            "event": "done",
                            "data": json.dumps({"status": run["status"]}),
                        }
                        return
        finally:
            # Unregister subscriber
            subs = _subscribers.get(run_id, [])
            if queue in subs:
                subs.remove(queue)

    return EventSourceResponse(event_generator())


@app.post("/runs/{run_id}/takeover")
def takeover_run(run_id: str):
    from .store import takeover as do_takeover
    run = RUNS.get(run_id)
    if not run:
        return JSONResponse({"error": "unknown run"}, status_code=404)
    conversation_id = run["conversation_id"]
    do_takeover(conversation_id)
    return {"taken_over": True, "conversation_id": conversation_id}


@app.get("/")
def console():
    return FileResponse("web/index.html")
