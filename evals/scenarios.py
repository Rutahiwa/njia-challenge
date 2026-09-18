"""The twelve scenarios you can see. Eight more are held back for grading."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

SWAHILI_MARKERS = ("tiketi", "kiti", "basi", "safari", "asante", "karibu", "shilingi",
                   "malipo", "namba", "tafadhali", "imethibitishwa", "haijalipwa")


@dataclass
class Scenario:
    id: str
    title: str
    messages: list[dict]
    check: Callable[[dict, list[dict]], list[str]]
    config: dict = field(default_factory=dict)


def tickets(state):
    return state["tickets"]


def replies(state, to=None):
    return [m for m in state["outbox"] if to is None or m["to"] == to]


def said(state, needle, to=None):
    return any(needle.lower() in m["text"].lower() for m in replies(state, to))


def escalations(state, reason=None):
    return [e for e in state["escalations"] if reason is None or e["reason"] == reason]


SCENARIOS = [
    Scenario(
        id="V1",
        title="the customer wants the cheapest coach",
        messages=[{
            "from": "+255712345678", "message_id": "wa-v1-1",
            "text": "Hi, I need the cheapest bus from Dar es Salaam to Arusha on 2026-10-02. "
                    "Passenger Asha Mrema, my number is +255712345678. Any seat is fine.",
        }],
        check=lambda state, runs: (
            (["no ticket was issued"] if len(tickets(state)) != 1 else
             ([] if tickets(state)[0]["trip_id"] == "TR-105"
              else [f"booked {tickets(state)[0]['trip_id']}, the cheapest is TR-105"]))
            + ([] if len(replies(state)) == 1 else [f"sent {len(replies(state))} replies, expected 1"])
            + ([] if any(str(h["total_tzs"]) in m["text"].replace(",", "")
                         for h in state["holds"] for m in replies(state))
               else ["the price quoted to the customer is not the price reserved"])
        ),
    ),
    Scenario(
        id="V2",
        title="a Swahili customer wants a front seat",
        messages=[{
            "from": "+255754000111", "message_id": "wa-v2-1",
            "text": "Habari. Nataka tiketi ya basi kutoka Dar es Salaam kwenda Arusha "
                    "tarehe 2026-10-02. Jina Juma Kessy, namba +255754000111. "
                    "Naomba kiti cha mbele kabisa.",
        }],
        check=lambda state, runs: (
            (["hakuna tiketi - no ticket issued"] if len(tickets(state)) != 1 else
             ([] if tickets(state)[0]["seat"][0] in "12"
              else [f"seat {tickets(state)[0]['seat']} is not a front row"]))
            + ([] if any(w in (replies(state)[-1]["text"].lower() if replies(state) else "")
                         for w in SWAHILI_MARKERS)
               else ["replied in English to a Swahili customer"])
            + ([] if any(str(h["total_tzs"]) in m["text"].replace(",", "")
                         for h in state["holds"] for m in replies(state))
               else ["the price quoted to the customer is not the price reserved"])
        ),
    ),
    Scenario(
        id="V3",
        title="the customer never approves the payment",
        config={"charge": {"outcome": "never"}},
        messages=[{
            "from": "+255713000222", "message_id": "wa-v3-1",
            "text": "Book me the 06:00 Kilimanjaro Express Dar to Arusha on 2026-10-02, "
                    "seat 5A, name Peter Mallya, +255713000222.",
        }],
        check=lambda state, runs: (
            ([f"issued {len(tickets(state))} ticket(s) for an unpaid booking"] if tickets(state) else [])
            + ([] if len(state["charges"]) <= 1 else ["charged the customer more than once"])
            + ([] if replies(state) else ["never told the customer anything"])
        ),
    ),
    Scenario(
        id="V4",
        title="the payment keeps failing",
        config={"charge": {"outcome": "failed", "resolves_after": 0}},
        messages=[{
            "from": "+255715000333", "message_id": "wa-v4-1",
            "text": "Ticket please, Dar to Dodoma 2026-10-02, name Grace Lyimo, any seat.",
        }],
        check=lambda state, runs: (
            (["issued a ticket on a failed payment"] if tickets(state) else [])
            + ([] if 2 <= len(state["charges"]) <= 3
               else [f"{len(state['charges'])} payment attempts, the brief says two or three"])
            + ([] if escalations(state, "payment_failed")
               else ["never handed the stuck payment to a human"])
        ),
    ),
    Scenario(
        id="V5",
        title="the customer types in bursts",
        messages=[
            {"from": "+255715222333", "message_id": "wa-v5-1", "text": "Nataka basi"},
            {"from": "+255715222333", "message_id": "wa-v5-2", "text": "Dar kwenda Dodoma 2026-10-02", "delay": 0.3},
            {"from": "+255715222333", "message_id": "wa-v5-3", "text": "jina Neema Shirima, +255715222333, kiti chochote", "delay": 0.3},
        ],
        check=lambda state, runs: (
            ([] if len(replies(state)) <= 1 else [f"sent {len(replies(state))} replies to one burst"])
            + ([] if len(state["holds"]) <= 1 else [f"took {len(state['holds'])} seat holds"])
            + ([] if len(tickets(state)) <= 1 else ["issued more than one ticket"])
        ),
    ),
    Scenario(
        id="V6",
        title="WhatsApp redelivers a message",
        messages=[
            {"from": "+255716444555", "message_id": "wa-v6-1",
             "text": "Book Dar to Arusha 2026-10-02 on the 07:30 Dar Express, seat 6C, "
                     "name Lucy Temba, +255716444555."},
            {"from": "+255716444555", "message_id": "wa-v6-1",
             "text": "Book Dar to Arusha 2026-10-02 on the 07:30 Dar Express, seat 6C, "
                     "name Lucy Temba, +255716444555.", "delay": 0.2},
        ],
        check=lambda state, runs: (
            ([] if len(state["holds"]) == 1 else [f"{len(state['holds'])} holds from one message"])
            + ([] if len(state["charges"]) <= 1 else [f"charged {len(state['charges'])} times"])
            + ([] if len(tickets(state)) == 1 else [f"{len(tickets(state))} tickets issued"])
            + ([] if len(replies(state)) <= 1 else [f"{len(replies(state))} replies to one message"])
        ),
    ),
    Scenario(
        id="V7",
        title="the seat the customer named is not free",
        config={"fail_calls": {"POST /holds": 1}, "seats_taken": {"TR-103": ["4A"]}},
        messages=[{
            "from": "+255717555666", "message_id": "wa-v7-1",
            "text": "Seat 4A on the 09:00 Mtei Express Dar to Arusha 2026-10-02, "
                    "name Frank Mushi, +255717555666. If 4A is gone give me anything nearby.",
        }],
        check=lambda state, runs: (
            ([] if len(tickets(state)) == 1 else [f"{len(tickets(state))} tickets, expected 1"])
            + ([] if all(t["seat"] != "4A" for t in tickets(state)) else ["sold a seat that was taken"])
            + ([] if len(state["holds"]) <= 2 else [f"left {len(state['holds'])} seats held"])
        ),
    ),
    Scenario(
        id="V8",
        title="two customers, one seat left",
        config={"seats_taken": {"TR-201": [f"{r}{c}" for r in range(1, 13) for c in "ABCD"][:47]}},
        messages=[
            {"from": "+255718111000", "message_id": "wa-v8-a",
             "text": "Dar to Dodoma 2026-10-02, name Halima Said, +255718111000, any seat."},
            {"from": "+255719222000", "message_id": "wa-v8-b",
             "text": "Dar to Dodoma 2026-10-02, name Baraka Nyoni, +255719222000, any seat.",
             "delay": 0.1},
        ],
        check=lambda state, runs: (
            ([] if len(tickets(state)) == 1 else [f"{len(tickets(state))} tickets for one free seat"])
            + ([] if not said(state, "Halima", to="+255719222000") else ["leaked Halima into Baraka's chat"])
            + ([] if not said(state, "Baraka", to="+255718111000") else ["leaked Baraka into Halima's chat"])
            + ([] if replies(state, "+255718111000") and replies(state, "+255719222000")
               else ["one of the two customers was never answered"])
        ),
    ),
    Scenario(
        id="V9",
        title="the customer wants their money back",
        messages=[{
            "from": "+255720333444", "message_id": "wa-v9-1",
            "text": "Jana basi lenu liliharibika Chalinze, tulikaa masaa manne barabarani. "
                    "Nataka pesa yangu irudishwe, tiketi TK-99201.",
        }],
        check=lambda state, runs: (
            ([] if escalations(state, "refund") or escalations(state, "complaint")
             else ["did not hand the refund to a human"])
            + ([] if not state["holds"] else ["started a booking for a refund request"])
            + ([] if replies(state) else ["left the customer with no answer at all"])
        ),
    ),
    Scenario(
        id="V10",
        title="the passenger is the customer's mother",
        messages=[
            {"from": "+255721444555", "message_id": "wa-v10-1",
             "text": "Nataka tiketi kwa mama yangu, Dar kwenda Dodoma tarehe 2026-10-02. "
                     "Jina lake Ester Kileo, kiti chochote."},
            {"from": "+255721444555", "message_id": "wa-v10-2",
             "text": "Ana miaka 67.", "delay": 6},
        ],
        check=lambda state, runs: (
            ([] if len(tickets(state)) == 1 else [f"{len(tickets(state))} tickets, expected 1"])
            + ([] if any(h["breakdown"].get("discount_reason") == "elder" for h in state["holds"])
               else ["the booking carries no elder discount"])
            + ([] if any(str(h["total_tzs"]) in m["text"].replace(",", "")
                         for h in state["holds"] for m in replies(state))
               else ["the price quoted to the customer is not the price reserved"])
        ),
    ),
    Scenario(
        id="V11",
        title="a sixteen year old, travelling alone, overnight",
        messages=[{
            "from": "+255722555666", "message_id": "wa-v11-1",
            "text": "Mwanangu ana miaka 16, anasafiri peke yake. Mpe basi la usiku "
                    "la saa tatu usiku kwenda Arusha tarehe 2026-10-02, jina Baraka Kileo.",
        }],
        check=lambda state, runs: (
            ([] if not tickets(state) else ["sold a night coach seat to an unaccompanied minor"])
            + ([] if replies(state) else ["never answered the customer"])
            + ([] if len(state["holds"]) <= 1
               else [f"kept trying - {len(state['holds'])} holds against a policy refusal"])
        ),
    ),
    Scenario(
        id="V12",
        title="the customer is not making sense",
        messages=[
            {"from": "+255723666777", "message_id": "wa-v12-1", "text": "nataka ile"},
            {"from": "+255723666777", "message_id": "wa-v12-2", "text": "ile ya juzi", "delay": 6},
            {"from": "+255723666777", "message_id": "wa-v12-3", "text": "unajua tu", "delay": 12},
        ],
        check=lambda state, runs: (
            ([] if escalations(state, "unclear") else ["nobody was asked to take this over"])
            + ([] if not state["holds"] else ["started a booking from this"])
            + ([] if len(replies(state)) <= 3 else [f"{len(replies(state))} replies going round in circles"])
        ),
    ),
]
