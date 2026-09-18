"""Mock booking backend. Everything here is fake - no real money, no real WhatsApp.

DO NOT MODIFY. The graders run against this file as shipped.
"""
from __future__ import annotations

import time

from fastapi import FastAPI, Header, Request
from fastapi.responses import JSONResponse

from . import world
from .world import WORLD, HOLD_TTL_SECONDS, PAY_KEY

app = FastAPI(title="mock booking backend")

PAGE_SIZE = 3


def fail(status: int, code: str, message: str) -> JSONResponse:
    WORLD.failures.append({"status": status, "code": code})
    return JSONResponse({"error": {"code": code, "message": message}}, status_code=status)


@app.middleware("http")
async def gateway(request: Request, call_next):
    route = f"{request.method} {request.url.path}"
    if not request.url.path.startswith("/_admin"):
        WORLD.calls.append(route)
        remaining = WORLD.fail_calls.get(route, 0)
        if remaining > 0:
            WORLD.fail_calls[route] = remaining - 1
            WORLD.failures.append({"status": 503, "code": "upstream_unavailable"})
            return JSONResponse(
                {"error": {"code": "upstream_unavailable", "message": "carrier gateway timeout"}},
                status_code=503,
                headers={"Retry-After": "1"},
            )
    return await call_next(request)


def replay(key: str | None, produce):
    """Idempotency: same key returns the first response instead of acting twice."""
    if not key:
        return produce()
    if key in WORLD.idempotency:
        return WORLD.idempotency[key]
    result = produce()
    if not isinstance(result, JSONResponse):
        WORLD.idempotency[key] = result
    return result


@app.get("/health")
def health():
    return {"ok": True}


@app.get("/trips")
def trips(origin: str = "", destination: str = "", date: str = "", offset: int = 0):
    matches = [
        t for t in WORLD.trips.values()
        if (not origin or origin.lower() in t.origin.lower())
        and (not destination or destination.lower() in t.destination.lower())
        and (not date or t.depart_at.startswith(date))
    ]
    matches.sort(key=lambda t: t.depart_at)
    page = matches[offset:offset + PAGE_SIZE]
    return {
        "trips": [
            {
                "trip_id": t.id, "operator": t.operator, "origin": t.origin,
                "destination": t.destination, "depart_at": t.depart_at,
                "arrive_at": t.arrive_at, "fare_tzs": t.fare_tzs, "night": world.is_night(t),
                "seats_left": sum(1 for v in t.seats.values() if v is None),
            }
            for t in page
        ],
        "offset": offset,
        "returned": len(page),
        "has_more": offset + len(page) < len(matches),
    }


@app.get("/trips/{trip_id}/seats")
def seats(trip_id: str):
    trip = WORLD.trips.get(trip_id)
    if not trip:
        return fail(404, "not_found", f"no trip {trip_id}")
    free = [label for label, taken in trip.seats.items() if taken is None]
    return {"trip_id": trip_id, "available": free, "count": len(free)}


@app.post("/holds")
async def create_hold(request: Request):
    body = await request.json()

    def produce():
        trip = WORLD.trips.get(body.get("trip_id"))
        if not trip:
            return fail(404, "not_found", "unknown trip")
        seat = body.get("seat")
        if seat not in trip.seats:
            return fail(422, "bad_seat", f"seat {seat} does not exist on this coach")
        if trip.seats[seat] is not None:
            return fail(409, "seat_taken", f"seat {seat} is already held")
        if not body.get("passenger_name"):
            return fail(422, "missing_passenger", "passenger_name is required")
        age = body.get("passenger_age")
        if age is not None and not isinstance(age, int):
            return fail(422, "bad_age", "passenger_age must be a whole number of years")
        if world.is_night(trip) and age is not None and age <= world.MINOR_MAX_AGE:
            return fail(422, "minor_on_night_bus",
                        "passengers under 18 may not travel unaccompanied on a night coach")
        parts = world.price(trip, seat, age, body.get("student_no"))
        hold = world.Hold(
            id=world.new_id("HD"),
            trip_id=trip.id,
            seat=seat,
            passenger=body["passenger_name"],
            total_tzs=parts["total_tzs"],
            breakdown=parts,
            expires_at=time.time() + WORLD.hold_ttl,
        )
        trip.seats[seat] = hold.id
        WORLD.holds[hold.id] = hold
        return {
            "hold_id": hold.id, "trip_id": trip.id, "seat": seat,
            **parts, "expires_in_seconds": WORLD.hold_ttl,
        }

    return replay(body.get("idempotency_key"), produce)


@app.get("/holds/{hold_id}")
def get_hold(hold_id: str):
    hold = WORLD.holds.get(hold_id)
    if not hold:
        return fail(404, "not_found", "unknown hold")
    return {
        "hold_id": hold.id, "trip_id": hold.trip_id, "seat": hold.seat,
        "total_tzs": hold.total_tzs, "charge_id": hold.charge_id,
        "ticket_id": hold.ticket_id,
        "expired": hold.expires_at < time.time(),
        "expires_in_seconds": max(0, round(hold.expires_at - time.time())),
    }


@app.post("/charges")
async def create_charge(request: Request, x_pay_key: str = Header(default="")):
    if x_pay_key != PAY_KEY:
        return fail(401, "bad_pay_key", "X-Pay-Key header missing or wrong")
    body = await request.json()

    def produce():
        hold = WORLD.holds.get(body.get("hold_id"))
        if not hold:
            return fail(404, "not_found", "unknown hold")
        if hold.expires_at < time.time():
            return fail(409, "hold_expired", "that seat hold has expired, take a new one")
        if hold.charge_id:
            return fail(409, "already_charged", f"hold already has charge {hold.charge_id}")
        msisdn = str(body.get("msisdn") or "")
        if not msisdn.startswith("+255"):
            return fail(422, "bad_msisdn", "msisdn must be a +255 number")
        charge = world.Charge(
            id=world.new_id("CH"), hold_id=hold.id, msisdn=msisdn, amount_tzs=hold.total_tzs
        )
        WORLD.charges[charge.id] = charge
        hold.charge_id = charge.id
        return {
            "charge_id": charge.id, "status": "pending", "amount_tzs": charge.amount_tzs,
            "note": "customer must approve the push on their handset",
        }

    return replay(body.get("idempotency_key"), produce)


@app.get("/charges/{charge_id}")
def get_charge(charge_id: str):
    charge = WORLD.charges.get(charge_id)
    if not charge:
        return fail(404, "not_found", "unknown charge")
    charge.polls += 1
    if charge.status == "pending" and WORLD.charge_outcome != "never":
        if charge.polls > WORLD.charge_resolves_after:
            charge.status = WORLD.charge_outcome
    return {"charge_id": charge.id, "status": charge.status, "amount_tzs": charge.amount_tzs}


@app.post("/tickets")
async def issue_ticket(request: Request):
    body = await request.json()

    def produce():
        hold = WORLD.holds.get(body.get("hold_id"))
        if not hold:
            return fail(404, "not_found", "unknown hold")
        charge = WORLD.charges.get(body.get("charge_id") or hold.charge_id or "")
        if not charge:
            return fail(422, "no_charge", "no charge for this hold")
        if charge.status != "success":
            return fail(422, "charge_not_settled", f"charge is {charge.status}, not success")
        if hold.ticket_id:
            return fail(409, "already_issued", f"ticket {hold.ticket_id} already issued")
        trip = WORLD.trips[hold.trip_id]
        ticket = {
            "ticket_id": world.new_id("TK"), "trip_id": trip.id, "operator": trip.operator,
            "seat": hold.seat, "passenger": hold.passenger, "depart_at": trip.depart_at,
            "paid_tzs": charge.amount_tzs,
        }
        hold.ticket_id = ticket["ticket_id"]
        WORLD.tickets[ticket["ticket_id"]] = ticket
        return ticket

    return replay(body.get("idempotency_key"), produce)


@app.post("/escalations")
async def escalate(request: Request):
    body = await request.json()
    reason = body.get("reason")
    if reason not in ("refund", "complaint", "payment_failed", "policy", "unclear", "other"):
        return fail(422, "bad_reason",
                    "reason must be one of refund, complaint, payment_failed, policy, unclear, other")
    if not body.get("conversation_id") or not body.get("summary"):
        return fail(422, "bad_escalation", "conversation_id and summary are required")
    entry = {
        "escalation_id": world.new_id("ES"),
        "conversation_id": body["conversation_id"],
        "reason": reason,
        "summary": body["summary"],
        "at": round(time.time(), 3),
    }
    WORLD.escalations.append(entry)
    return entry


@app.post("/whatsapp/send")
async def whatsapp_send(request: Request):
    body = await request.json()
    if not body.get("to") or not body.get("text"):
        return fail(422, "bad_message", "to and text are required")
    entry = {"to": body["to"], "text": body["text"], "at": round(time.time(), 3)}
    WORLD.outbox.append(entry)
    return {"sent": True, "index": len(WORLD.outbox) - 1}


@app.post("/_admin/reset")
async def admin_reset(request: Request):
    config = await request.json() if await request.body() else {}
    world.reset(config)
    return {"reset": True}


@app.get("/_admin/state")
def admin_state():
    return world.snapshot()
