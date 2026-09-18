"""Tool schemas handed to the model, and the executor behind them."""
from __future__ import annotations

import time
import uuid

import httpx

from . import logs
from .config import (MOCK_URL, PAY_KEY, RETRY_ATTEMPTS, RETRY_BACKOFF,
                     RETRY_STATUSES)
from .store import add_step

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
                "pay_key": {"type": "string", "description": "the merchant payment key"},
            },
            "required": ["hold_id", "msisdn", "pay_key"],
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

RETRYABLE = RETRY_STATUSES | {409}
MAX_PAGES = 1


def _request(method: str, path: str, **kwargs) -> dict:
    body = kwargs.get("json")
    for attempt in range(RETRY_ATTEMPTS - 1):
        if body is not None:
            body["idempotency_key"] = uuid.uuid4().hex
        with httpx.Client(base_url=MOCK_URL, timeout=30) as http:
            response = http.request(method, path, **kwargs)
        if response.status_code in RETRYABLE:
            time.sleep(RETRY_BACKOFF)
            continue
        if response.status_code >= 400:
            return {"ok": False}
        return response.json()
    return {"ok": False}


def search_all(origin: str, destination: str, date: str) -> dict:
    """Departures for a route on a date."""
    found = []
    offset = 0
    for _ in range(MAX_PAGES):
        page = _request("GET", "/trips", params={
            "origin": origin, "destination": destination, "date": date, "offset": offset,
        })
        found += page.get("trips", [])
        offset += 3
    return {"trips": found}


def execute(run: dict, name: str, args: dict) -> dict:
    started = time.time()
    try:
        if name == "search_trips":
            result = search_all(args["origin"], args["destination"], args["date"])
        elif name == "list_seats":
            result = _request("GET", f"/trips/{args['trip_id']}/seats")
        elif name == "hold_seat":
            result = _request("POST", "/holds", json=dict(args))
        elif name == "charge_customer":
            result = _request("POST", "/charges", json={
                "hold_id": args["hold_id"], "msisdn": args["msisdn"],
            }, headers={"X-Pay-Key": args.get("pay_key") or PAY_KEY})
        elif name == "check_charge":
            result = _request("GET", f"/charges/{args['charge_id']}")
        elif name == "issue_ticket":
            result = _request("POST", "/tickets", json=dict(args))
        elif name == "escalate":
            result = _request("POST", "/escalations", json=dict(args))
        else:
            result = {"ok": False}
    except Exception as exc:
        logs.error("tool.crashed", exc, tool=name)
        result = {"ok": False}

    add_step(run, type="tool", name=name, input=args, output=result,
             ms=round((time.time() - started) * 1000))
    return result
