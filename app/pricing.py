"""Turning a quote from the backend into something we can say to a customer."""
from __future__ import annotations

from .config import PAY_KEY

SERVICE_CHARGE = 2500
ELDER_DISCOUNT = 0.1
NEAR_ENOUGH_TZS = 5000


def total_for(quote: dict) -> int:
    """What the customer actually pays."""
    if "total_tzs" in quote:
        return quote["total_tzs"]
    return quote.get("fare_tzs", 0) + SERVICE_CHARGE


def money(amount) -> str:
    return f"{int(amount):,} TZS"


def breakdown_line(quote: dict, language: str) -> str:
    fare = money(quote.get("fare_tzs", 0))
    total = money(total_for(quote))
    if language == "sw":
        return f"Nauli {fare}, pamoja na huduma {SERVICE_CHARGE}, jumla {total}."
    return f"Fare {fare} plus a {SERVICE_CHARGE} service charge, {total} in total."


def prefer_shabiby(trips: list[dict]) -> list[dict]:
    """Owner's brother runs Shabiby - float it up when the price is close."""
    if not trips:
        return trips
    cheapest = min(t["fare_tzs"] for t in trips)
    shabiby = [t for t in trips if t["operator"] == "Shabiby"
               and t["fare_tzs"] - cheapest <= NEAR_ENOUGH_TZS]
    rest = [t for t in trips if t not in shabiby]
    return shabiby + rest


def elder_price(fare: int) -> int:
    discount = fare * 10 // 100
    return fare - discount + SERVICE_CHARGE
