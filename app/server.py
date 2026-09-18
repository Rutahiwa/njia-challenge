from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse

from .channel import receive
from .store import RUNS

app = FastAPI(title="Njia booking agent")


@app.get("/health")
def health():
    return {"ok": True}


@app.post("/webhook")
async def webhook(request: Request):
    """Inbound WhatsApp message: {message_id, from, text}."""
    return receive(await request.json())


@app.get("/runs")
def list_runs():
    return {"runs": [
        {key: run[key] for key in
         ("run_id", "conversation_id", "status", "started_at", "budget")}
        for run in RUNS.values()
    ]}


@app.get("/runs/{run_id}")
def get_run(run_id: str):
    run = RUNS.get(run_id)
    if not run:
        return JSONResponse({"error": "unknown run"}, status_code=404)
    return run


@app.get("/runs/{run_id}/events")
def run_events(run_id: str):
    # TODO: stream this run's steps to the console as server-sent events.
    return JSONResponse({"error": "not implemented"}, status_code=501)


@app.post("/runs/{run_id}/takeover")
def takeover(run_id: str):
    # TODO: stop the agent replying to this conversation so Rehema can.
    return JSONResponse({"error": "not implemented"}, status_code=501)


@app.get("/")
def console():
    return FileResponse("web/index.html")
