"""The rules from the client brief."""
from __future__ import annotations

from datetime import datetime

ELDER_AGE = 60
ADULT_AGE = 18
NIGHT_HOUR = 20

REFUND_WORDS = [
    "refund", "money back", "cancel",
    "rudisha", "irudishwe", "pesa yangu", "fidia", "sitaki", "ondoa",
]
COMPLAINT_WORDS = [
    "rude", "late", "broke down", "complain",
    "mkorofi", "liliharibika", "kulalamika", "kuchelewa", "tatizo",
    "dharau", "hasira", "dereva", "gari limeharibika",
]

_attempts: dict[str, int] = {}


def is_elder(age) -> bool:
    return age is not None and age >= ELDER_AGE


def is_minor(age) -> bool:
    return age is not None and age < ADULT_AGE


def is_night_trip(trip: dict) -> bool:
    return int(trip["depart_at"][11:13]) >= NIGHT_HOUR


def is_weekday(depart_at: str) -> bool:
    return datetime.fromisoformat(depart_at).weekday() < 5


def needs_human(text: str) -> str | None:
    """Return an escalation reason, or None if the agent may handle it."""
    lowered = text.lower()
    for word in REFUND_WORDS:
        if word in lowered:
            return "refund"
    for word in COMPLAINT_WORDS:
        if word in lowered:
            return "complaint"
    return None


def note_unclear(conversation_id: str) -> int:
    """Count how many times we have failed to understand this customer."""
    _attempts[conversation_id] = _attempts.get(conversation_id, 0) + 1
    return _attempts[conversation_id]


def give_up(conversation_id: str) -> bool:
    return _attempts.get(conversation_id, 0) >= 2
