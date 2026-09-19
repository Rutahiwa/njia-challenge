"""Tool schemas handed to the model, and the executor behind them.

Tool calls are routed through the MCP server modules (in-process).
The catalog server handles reads, the booking server handles writes.
"""
from __future__ import annotations

import time

from . import logs
from .store import add_step

try:
    from . import recovery
except Exception:
    recovery = None

from mcp_servers import catalog as _catalog_server
from mcp_servers import booking as _booking_server

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

def execute(run: dict, name: str, args: dict) -> dict:
    """Route tool calls through the MCP server modules (in-process)."""
    started = time.time()
    server_name = TOOL_SERVERS.get(name, "unknown")
    try:
        if name == "search_trips":
            result = _catalog_server.search_trips(args["origin"], args["destination"], args["date"])
        elif name == "list_seats":
            result = _catalog_server.list_seats(args["trip_id"])
        elif name == "check_charge":
            result = _catalog_server.check_charge(args["charge_id"])
        elif name == "hold_seat":
            result = _booking_server.hold_seat(
                args["trip_id"], args["seat"], args["passenger_name"],
                args.get("passenger_age"), args.get("student_no"),
            )
        elif name == "charge_customer":
            result = _booking_server.charge_customer(args["hold_id"], args["msisdn"])
        elif name == "issue_ticket":
            result = _booking_server.issue_ticket(args["hold_id"], args["charge_id"])
        elif name == "escalate":
            result = _booking_server.escalate(
                args["conversation_id"], args["reason"], args["summary"],
            )
        else:
            result = {"error": {"code": "unknown_tool", "message": f"no tool named {name}"}}
    except Exception as exc:
        error_msg = str(exc)
        try:
            import json
            parsed = json.loads(error_msg)
            result = {"error": parsed}
        except (json.JSONDecodeError, TypeError):
            logs.error("tool.crashed", exc, tool=name, code="tool_crashed")
            result = {"error": {"code": "tool_crashed", "message": error_msg}}

    # Log any retries that happened inside the MCP servers
    for retry_event in _catalog_server.get_and_clear_retries():
        logs.error("tool.retry", tool=name, **retry_event)
    for retry_event in _booking_server.get_and_clear_retries():
        logs.error("tool.retry", tool=name, **retry_event)

    if "error" in result:
        err = result["error"] if isinstance(result["error"], dict) else {"code": "unknown", "message": str(result["error"])}
        logs.error("tool.backend_error", tool=name, code=err.get("code"), message=err.get("message"))

    if recovery:
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
            pass

    add_step(run, type="tool", name=name, server=server_name, input=args, output=result,
             ms=round((time.time() - started) * 1000))
    return result
