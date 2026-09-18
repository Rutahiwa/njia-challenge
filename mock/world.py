"""In-memory world for the mock booking backend. Reset between scenarios."""
from __future__ import annotations

import time
import uuid
from datetime import date
from dataclasses import dataclass, field

BOOKING_FEE_TZS = 2500
ELDER_DISCOUNT_PCT = 10
ELDER_MIN_AGE = 60
STUDENT_DISCOUNT_PCT = 15
MINOR_MAX_AGE = 17
FRONT_ROW_PREMIUM_TZS = 3000
HOLD_TTL_SECONDS = 90
PAY_KEY = "pk_live_mock_9f2a41c8"  # the mock backend's payment credential


@dataclass
class Trip:
    id: str
    operator: str
    origin: str
    destination: str
    depart_at: str
    arrive_at: str
    fare_tzs: int
    seats: dict[str, str | None]  # seat label -> hold_id or None


@dataclass
class Hold:
    id: str
    trip_id: str
    seat: str
    passenger: str
    total_tzs: int
    expires_at: float
    breakdown: dict = field(default_factory=dict)
    charge_id: str | None = None
    ticket_id: str | None = None


@dataclass
class Charge:
    id: str
    hold_id: str
    msisdn: str
    amount_tzs: int
    polls: int = 0
    status: str = "pending"


@dataclass
class World:
    trips: dict[str, Trip] = field(default_factory=dict)
    holds: dict[str, Hold] = field(default_factory=dict)
    charges: dict[str, Charge] = field(default_factory=dict)
    tickets: dict[str, dict] = field(default_factory=dict)
    outbox: list[dict] = field(default_factory=list)
    escalations: list[dict] = field(default_factory=list)
    idempotency: dict[str, dict] = field(default_factory=dict)
    calls: list[str] = field(default_factory=list)
    failures: list[dict] = field(default_factory=list)
    # per-scenario setup
    hold_ttl: int = HOLD_TTL_SECONDS
    charge_resolves_after: int = 2
    charge_outcome: str = "success"
    fail_calls: dict[str, int] = field(default_factory=dict)


WORLD = World()

_SEAT_LABELS = [f"{row}{col}" for row in range(1, 13) for col in "ABCD"]

_SEED_TRIPS = [
    # id, operator, from, to, depart, arrive, fare, taken seats
    ("TR-101", "Kilimanjaro Express", "Dar es Salaam", "Arusha", "2026-10-02T06:00", "2026-10-02T15:30", 45000, 30),
    ("TR-102", "Dar Express", "Dar es Salaam", "Arusha", "2026-10-02T07:30", "2026-10-02T17:00", 38000, 12),
    ("TR-103", "Mtei Express", "Dar es Salaam", "Arusha", "2026-10-02T09:00", "2026-10-02T18:30", 49000, 0),
    ("TR-104", "Happy Nation", "Dar es Salaam", "Arusha", "2026-10-02T12:00", "2026-10-02T21:30", 31000, 47),
    ("TR-105", "Shabiby", "Dar es Salaam", "Arusha", "2026-10-02T21:00", "2026-10-03T06:00", 29000, 44),
    ("TR-201", "Shabiby", "Dar es Salaam", "Dodoma", "2026-10-02T08:00", "2026-10-02T14:00", 27000, 20),
    ("TR-301", "Mtei Express", "Mwanza", "Arusha", "2026-10-02T06:30", "2026-10-02T17:30", 41000, 5),
    ("TR-111", "Kilimanjaro Express", "Dar es Salaam", "Arusha", "2026-10-03T06:00", "2026-10-03T15:30", 45000, 10),
    ("TR-112", "Shabiby", "Dar es Salaam", "Arusha", "2026-10-03T21:00", "2026-10-04T06:00", 29000, 8),
    ("TR-211", "Shabiby", "Dar es Salaam", "Dodoma", "2026-10-03T08:00", "2026-10-03T14:00", 27000, 6),
]


def reset(config: dict | None = None) -> None:
    """Rebuild the world in place - callers hold a reference to WORLD."""
    config = config or {}
    WORLD.trips.clear()
    WORLD.holds.clear()
    WORLD.charges.clear()
    WORLD.tickets.clear()
    WORLD.outbox.clear()
    WORLD.escalations.clear()
    WORLD.idempotency.clear()
    WORLD.calls.clear()
    WORLD.failures.clear()

    overrides = config.get("seats_taken") or {}
    for tid, op, org, dst, dep, arr, fare, taken in _SEED_TRIPS:
        seats = {label: None for label in _SEAT_LABELS}
        held = overrides[tid] if tid in overrides else _SEAT_LABELS[:taken]
        for label in held:
            seats[label] = "reserved"
        WORLD.trips[tid] = Trip(tid, op, org, dst, dep, arr, fare, seats)

    WORLD.hold_ttl = config.get("hold_ttl", HOLD_TTL_SECONDS)
    charge = config.get("charge", {})
    WORLD.charge_resolves_after = charge.get("resolves_after", 2)
    WORLD.charge_outcome = charge.get("outcome", "success")
    WORLD.fail_calls = dict(config.get("fail_calls", {}))


def new_id(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:8]}"


def is_night(trip: Trip) -> bool:
    return int(trip.depart_at[11:13]) >= 20


def price(trip: Trip, seat: str, age: int | None, student_no: str | None) -> dict:
    premium = FRONT_ROW_PREMIUM_TZS if seat[:1] in ("1", "2") and len(seat) == 2 else 0
    gross = trip.fare_tzs + premium
    discount = 0
    reason = None
    if age is not None and age >= ELDER_MIN_AGE:
        discount = gross * ELDER_DISCOUNT_PCT // 100
        reason = "elder"
    elif student_no and date.fromisoformat(trip.depart_at[:10]).weekday() < 5:
        discount = gross * STUDENT_DISCOUNT_PCT // 100
        reason = "student"
    return {
        "fare_tzs": trip.fare_tzs,
        "seat_premium_tzs": premium,
        "booking_fee_tzs": BOOKING_FEE_TZS,
        "discount_tzs": discount,
        "discount_reason": reason,
        "total_tzs": gross - discount + BOOKING_FEE_TZS,
    }


def snapshot() -> dict:
    return {
        "trips": {
            t.id: {"seats_taken": sum(1 for v in t.seats.values() if v), "fare_tzs": t.fare_tzs}
            for t in WORLD.trips.values()
        },
        "holds": [
            {"id": h.id, "trip_id": h.trip_id, "seat": h.seat, "passenger": h.passenger,
             "total_tzs": h.total_tzs, "breakdown": h.breakdown,
             "charge_id": h.charge_id, "ticket_id": h.ticket_id,
             "expired": h.expires_at < time.time()}
            for h in WORLD.holds.values()
        ],
        "charges": [
            {"id": c.id, "hold_id": c.hold_id, "msisdn": c.msisdn, "amount_tzs": c.amount_tzs,
             "status": c.status, "polls": c.polls}
            for c in WORLD.charges.values()
        ],
        "tickets": list(WORLD.tickets.values()),
        "outbox": WORLD.outbox,
        "escalations": WORLD.escalations,
        "calls": WORLD.calls,
        "failures": WORLD.failures,
    }


reset()
