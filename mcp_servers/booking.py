"""Njia Challenge - Booking, Payment & Escalation MCP Server."""

from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
import os
import hashlib
import json
import time
import httpx

MOCK_URL = os.getenv("MOCK_URL", "http://localhost:9311")
PAY_KEY = os.getenv("PAY_KEY", "pk_live_mock_9f2a41c8")
SERVER_NAME = "njia-booking"
RETRY_ATTEMPTS = 3
RETRY_BACKOFF = 0.2
RETRY_STATUSES = {429, 500, 502, 503, 504}

VALID_ESCALATION_REASONS = {"refund", "complaint", "payment_failed", "policy", "unclear", "other"}

mcp = MCPServer(name=SERVER_NAME, description="Booking, payment, and escalation operations")


def _stable_key(payload: dict) -> str:
    canonical = json.dumps(
        {k: v for k, v in sorted(payload.items()) if k != "idempotency_key"},
        sort_keys=True,
    )
    return hashlib.sha256(canonical.encode()).hexdigest()[:32]


def _post(path: str, payload: dict, headers: dict | None = None) -> dict:
    idem_key = _stable_key(payload)
    for attempt in range(RETRY_ATTEMPTS):
        payload["idempotency_key"] = idem_key
        resp = httpx.post(
            f"{MOCK_URL}{path}",
            json=payload,
            headers=headers or {},
            timeout=30,
        )
        if resp.status_code in RETRY_STATUSES:
            time.sleep(RETRY_BACKOFF * (attempt + 1))
            continue
        return resp.json()
    return {"error": {"code": "retries_exhausted", "message": "all retries failed"}}


@mcp.tool()
def hold_seat(
    trip_id: str,
    seat: str,
    passenger_name: str,
    passenger_age: int | None = None,
    student_no: str | None = None,
) -> dict:
    """Reserve a seat on a trip. Returns the hold record including breakdown with total_tzs."""
    payload: dict = {
        "trip_id": trip_id,
        "seat": seat,
        "passenger_name": passenger_name,
    }
    if passenger_age is not None:
        payload["passenger_age"] = passenger_age
    if student_no is not None:
        payload["student_no"] = student_no
    result = _post("/holds", payload)
    if "error" in result:
        raise ToolError(json.dumps(result["error"]))
    return result


@mcp.tool()
def charge_customer(hold_id: str, msisdn: str) -> dict:
    """Initiate a mobile-money charge for a held seat. Returns charge_id and status."""
    payload = {"hold_id": hold_id, "msisdn": msisdn}
    result = _post("/charges", payload, headers={"X-Pay-Key": PAY_KEY})
    if "error" in result:
        raise ToolError(json.dumps(result["error"]))
    return result


@mcp.tool()
def issue_ticket(hold_id: str, charge_id: str) -> dict:
    """Issue a ticket after a successful charge. Returns the full ticket object."""
    payload = {"hold_id": hold_id, "charge_id": charge_id}
    result = _post("/tickets", payload)
    if "error" in result:
        raise ToolError(json.dumps(result["error"]))
    return result


@mcp.tool()
def escalate(conversation_id: str, reason: str, summary: str) -> dict:
    """Escalate a conversation to a human agent. Reason must be one of: refund, complaint, payment_failed, policy, unclear, other."""
    if reason not in VALID_ESCALATION_REASONS:
        raise ToolError(
            f"Invalid reason '{reason}'. Must be one of: {', '.join(sorted(VALID_ESCALATION_REASONS))}"
        )
    payload = {
        "conversation_id": conversation_id,
        "reason": reason,
        "summary": summary,
    }
    result = _post("/escalations", payload)
    if "error" in result:
        raise ToolError(json.dumps(result["error"]))
    return result


if __name__ == "__main__":
    mcp.run("streamable-http", host="127.0.0.1", port=9321)
