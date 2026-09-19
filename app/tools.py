"""Tool schemas handed to the model, and the executor behind them."""
from __future__ import annotations

import time

import httpx

from . import logs, recovery
from .config import (MOCK_URL, PAY_KEY, RETRY_ATTEMPTS, RETRY_BACKOFF,
                     RETRY_STATUSES)
from .pricing import prefer_shabiby
from .store import add_step

TOOL_SERVERS = {
    "search_trips": "njia-catalog",
    "list_seats": "njia-catalog",
    "check_charge": "njia-catalog",
    "hold_seat": "njia-booking",
    "charge_customer": "njia-booking",
    "issue_ticket": "njia-booking",
    "escalate": "njia-booking",
}

TOOLS = [
    {
        "name": "search_trips",
        "description": "Returns every coach departure matching the route and date.",
        "input_schema": {
            "type": "object",
            "properties": {
                "origin": {"type": "string"},
                "destination": {"type": "string"},
                "date": {"type": "string", "description": "YYYY-MM-DD"},
            },
            "required": ["origin", "destination", "date"],
        },
    },
    {
        "name": "list_seats",
        "description": "Seats still free on a coach.",
        "input_schema": {
            "type": "object",
            "properties": {"trip_id": {"type": "string"}},
            "required": ["trip_id"],
        },
    },
    {
        "name": "hold_seat",
        "description": "Reserve a seat. Returns the price the customer will pay.",
        "input_schema": {
            "type": "object",
            "properties": {
                "trip_id": {"type": "string"},
                "seat": {"type": "string"},
                "passenger_name": {"type": "string"},
                "passenger_age": {"type": "integer"},
                "student_no": {"type": "string"},
            },
            "required": ["trip_id", "seat", "passenger_name"],
        },
    },
    {
        "name": "charge_customer",
        "description": "Push a mobile money request to the customer's handset.",
        "input_schema": {
            "type": "object",
            "properties": {
                "hold_id": {"type": "string"},
                "msisdn": {"type": "string", "description": "+255..."},
            },
            "required": ["hold_id", "msisdn"],
        },
    },
    {
        "name": "check_charge",
        "description": "Current status of a mobile money charge.",
        "input_schema": {
            "type": "object",
            "properties": {"charge_id": {"type": "string"}},
            "required": ["charge_id"],
        },
    },
    {
        "name": "issue_ticket",
        "description": "Issue the ticket for a paid hold.",
        "input_schema": {
            "type": "object",
            "properties": {"hold_id": {"type": "string"}, "charge_id": {"type": "string"}},
            "required": ["hold_id", "charge_id"],
        },
    },
    {
        "name": "escalate",
        "description": "Hand the conversation to a human agent.",
        "input_schema": {
            "type": "object",
            "properties": {
                "conversation_id": {"type": "string"},
                "reason": {"type": "string"},
                "summary": {"type": "string"},
            },
            "required": ["conversation_id", "reason", "summary"],
        },
    },
]

RETRYABLE = RETRY_STATUSES


def _request(method: str, path: str, **kwargs) -> dict:
    body = kwargs.get("json")
    idem_key = None
    # Skip idempotency for charge_customer (/charges POST) so retries create new charges
    skip_idempotency = (path == "/charges" and method == "POST")
    if body is not None and not skip_idempotency:
        import hashlib, json as _json
        canonical = _json.dumps({k: v for k, v in sorted(body.items()) if k != "idempotency_key"}, sort_keys=True)
        idem_key = hashlib.sha256(canonical.encode()).hexdigest()[:32]
    for attempt in range(RETRY_ATTEMPTS):
        if body is not None and idem_key is not None:
            body["idempotency_key"] = idem_key
        with httpx.Client(base_url=MOCK_URL, timeout=30) as http:
            response = http.request(method, path, **kwargs)
        if response.status_code in RETRYABLE:
            logs.error("tool.retry", code="upstream_unavailable",
                       attempt=attempt + 1, path=path,
                       status=response.status_code)
            time.sleep(RETRY_BACKOFF)
            continue
        if response.status_code >= 400:
            try:
                return response.json()
            except Exception:
                return {"error": {"code": "http_error", "message": f"HTTP {response.status_code}"}}
        return response.json()
    return {"error": {"code": "retries_exhausted", "message": "all retries failed"}}


def search_all(origin: str, destination: str, date: str) -> dict:
    """Departures for a route on a date."""
    found = []
    offset = 0
    max_pages = 10
    for _ in range(max_pages):
        page = _request("GET", "/trips", params={
            "origin": origin, "destination": destination, "date": date, "offset": offset,
        })
        trips = page.get("trips", [])
        found += trips
        if not page.get("has_more", False) or not trips:
            break
        offset += len(trips)
    return {"trips": found}


def execute(run: dict, name: str, args: dict) -> dict:
    started = time.time()
    server_name = TOOL_SERVERS.get(name, "unknown")
    try:
        if name == "search_trips":
            result = search_all(args["origin"], args["destination"], args["date"])
            result["trips"] = prefer_shabiby(result.get("trips", []))
        elif name == "list_seats":
            result = _request("GET", f"/trips/{args['trip_id']}/seats")
        elif name == "hold_seat":
            result = _request("POST", "/holds", json=dict(args))
        elif name == "charge_customer":
            result = _request("POST", "/charges", json={
                "hold_id": args["hold_id"], "msisdn": args["msisdn"],
            }, headers={"X-Pay-Key": PAY_KEY})
        elif name == "check_charge":
            result = _request("GET", f"/charges/{args['charge_id']}")
        elif name == "issue_ticket":
            result = _request("POST", "/tickets", json=dict(args))
        elif name == "escalate":
            result = _request("POST", "/escalations", json=dict(args))
        else:
            result = {"ok": False}
    except Exception as exc:
        logs.error("tool.crashed", exc, tool=name, code="tool_crashed")
        result = {"error": {"code": "tool_crashed", "message": str(exc)}}

    if "error" in result:
        err = result["error"]
        logs.error("tool.backend_error", tool=name, code=err.get("code"), message=err.get("message"))

    # Track payment lifecycle for crash recovery
    try:
        cid = run.get("conversation_id", "")
        rid = run.get("run_id", "")
        if name == "hold_seat" and "hold_id" in result:
            recovery.save_payment_intent(cid, rid, hold_id=result["hold_id"], state="holding")
        elif name == "charge_customer" and "charge_id" in result:
            recovery.update_payment_state(cid, rid, charge_id=result["charge_id"], state="charging")
        elif name == "issue_ticket" and "ticket_id" in result:
            recovery.complete_payment(cid, rid, ticket_id=result["ticket_id"])
    except Exception:
        pass  # recovery is best-effort

    add_step(run, type="tool", name=name, server=server_name, input=args, output=result,
             ms=round((time.time() - started) * 1000))
    return result
