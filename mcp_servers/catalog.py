"""Read-only MCP server for Njia trip catalog and charge status queries."""

import os

import httpx
from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError

MOCK_URL = os.getenv("MOCK_URL", "http://localhost:9311")
SERVER_NAME = "njia-catalog"

mcp = MCPServer(
    name=SERVER_NAME,
    description="Read-only trip catalog and charge status queries",
)


RETRY_STATUSES = {429, 500, 502, 503, 504}
RETRY_ATTEMPTS = 3

_retry_log = []


def get_and_clear_retries() -> list[dict]:
    """Return retry events logged during MCP server calls, then clear."""
    events = list(_retry_log)
    _retry_log.clear()
    return events


def _get(path: str, **kwargs) -> dict:
    """GET request to mock backend with retry and error handling."""
    import json, time
    for attempt in range(RETRY_ATTEMPTS):
        with httpx.Client(timeout=30) as client:
            resp = client.get(f"{MOCK_URL}{path}", **kwargs)
        if resp.status_code in RETRY_STATUSES:
            _retry_log.append({
                "code": "upstream_unavailable",
                "attempt": attempt + 1,
                "path": path,
                "status": resp.status_code,
            })
            time.sleep(0.2)
            continue
        if resp.status_code >= 400:
            try:
                err = resp.json()
                raise ToolError(json.dumps(err.get("error", err)))
            except (ValueError, KeyError):
                raise ToolError(json.dumps({"code": "http_error", "message": f"HTTP {resp.status_code}"}))
        return resp.json()
    raise ToolError(json.dumps({"code": "retries_exhausted", "message": "all retries failed"}))


def _prefer_shabiby(trips: list[dict]) -> list[dict]:
    """Sort trips so Shabiby appears first when its fare is within 5000 TZS of the cheapest."""
    if not trips:
        return trips

    cheapest_fare = min(t["fare_tzs"] for t in trips)

    def sort_key(t: dict) -> tuple[int, int]:
        is_shabiby = t.get("operator", "").lower() == "shabiby"
        within_range = t["fare_tzs"] <= cheapest_fare + 5000
        if is_shabiby and within_range:
            return (0, t["fare_tzs"])
        return (1, t["fare_tzs"])

    return sorted(trips, key=sort_key)


@mcp.tool()
def search_trips(origin: str, destination: str, date: str) -> dict:
    """Search for available trips between two cities on a given date.

    Paginates through all results and applies prefer-Shabiby ordering
    (Shabiby floated to top if its fare is within 5000 TZS of cheapest).

    Args:
        origin: Departure city name.
        destination: Arrival city name.
        date: Travel date in YYYY-MM-DD format.

    Returns:
        Dictionary with "trips" key containing the full list of matching trips.
    """
    all_trips: list[dict] = []
    offset = 0
    while True:
        data = _get("/trips", params={
            "origin": origin, "destination": destination,
            "date": date, "offset": offset,
        })
        trips_page = data.get("trips", [])
        all_trips.extend(trips_page)
        if not data.get("has_more", False) or not trips_page:
            break
        offset += len(trips_page)
    all_trips = _prefer_shabiby(all_trips)
    return {"trips": all_trips}


@mcp.tool()
def list_seats(trip_id: str) -> dict:
    """List available seats for a specific trip.

    Args:
        trip_id: The unique identifier of the trip.

    Returns:
        Dictionary with trip_id, available seat list, and count.
    """
    return _get(f"/trips/{trip_id}/seats")


@mcp.tool()
def check_charge(charge_id: str) -> dict:
    """Check the status of a payment charge.

    Args:
        charge_id: The unique identifier of the charge.

    Returns:
        Dictionary with charge_id, status, and amount in TZS.
    """
    return _get(f"/charges/{charge_id}")


if __name__ == "__main__":
    mcp.run("streamable-http", host="127.0.0.1", port=9320)
