"""One end-to-end check that the mock world behaves. Add your own alongside it."""
import httpx

MOCK = "http://localhost:9311"


def test_book_a_seat_end_to_end():
    httpx.post(f"{MOCK}/_admin/reset", json={"charge": {"resolves_after": 1}})

    trips = httpx.get(f"{MOCK}/trips", params={
        "origin": "Dar", "destination": "Arusha", "date": "2026-10-02"}).json()
    assert trips["trips"], "the route has departures"

    hold = httpx.post(f"{MOCK}/holds", json={
        "trip_id": "TR-103", "seat": "7B", "passenger_name": "Test Rider",
        "idempotency_key": "k1"}).json()
    assert hold["total_tzs"] == hold["fare_tzs"] + hold["booking_fee_tzs"]

    charge = httpx.post(f"{MOCK}/charges", json={
        "hold_id": hold["hold_id"], "msisdn": "+255700000000", "idempotency_key": "k2"},
        headers={"X-Pay-Key": "pk_live_mock_9f2a41c8"}).json()
    assert charge["status"] == "pending"

    httpx.get(f"{MOCK}/charges/{charge['charge_id']}")
    settled = httpx.get(f"{MOCK}/charges/{charge['charge_id']}").json()
    assert settled["status"] == "success"

    ticket = httpx.post(f"{MOCK}/tickets", json={
        "hold_id": hold["hold_id"], "charge_id": charge["charge_id"],
        "idempotency_key": "k3"}).json()
    assert ticket["seat"] == "7B"
    assert ticket["paid_tzs"] == hold["total_tzs"]
