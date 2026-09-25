from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from threading import Barrier

from fastapi.testclient import TestClient
from test_bookings import book

from app.main import app


def test_reschedule_is_atomic_preserves_id_and_frees_original_slot(client, setup_service):
    s = setup_service
    original = book(client, s).json()
    book(client, s, s["start"] + timedelta(hours=1))
    url = f"/api/v1/bookings/{original['id']}/reschedule"
    occupied = {"starts_at": (s["start"] + timedelta(hours=1)).isoformat()}
    assert client.post(url, headers=s["customer"], json=occupied).status_code == 409
    unchanged = client.get(f"/api/v1/bookings/{original['id']}", headers=s["customer"]).json()
    expected = original.copy()
    for field in ("starts_at", "ends_at"):
        assert datetime.fromisoformat(unchanged.pop(field)) == datetime.fromisoformat(
            expected.pop(field)
        )
    assert unchanged == expected
    free = {"starts_at": (s["start"] + timedelta(hours=2)).isoformat()}
    assert client.post(url, headers=s["outsider"], json=free).status_code == 404
    moved = client.post(url, headers=s["owner"], json=free)
    assert moved.status_code == 200 and moved.json()["id"] == original["id"]
    assert moved.json()["starts_at"] != original["starts_at"]
    assert book(client, s).status_code == 201
    assert client.post(url, headers=s["customer"], json=free).status_code == 200


def test_cannot_reschedule_cancelled_booking_or_invalid_slot(client, setup_service):
    s = setup_service
    original = book(client, s).json()
    url = f"/api/v1/bookings/{original['id']}/reschedule"
    assert (
        client.post(
            url,
            headers=s["customer"],
            json={
                "starts_at": (s["start"] + timedelta(minutes=30)).isoformat(),
            },
        ).status_code
        == 422
    )
    client.post(f"/api/v1/bookings/{original['id']}/cancel", headers=s["customer"])
    assert (
        client.post(
            url,
            headers=s["customer"],
            json={
                "starts_at": (s["start"] + timedelta(hours=1)).isoformat(),
            },
        ).status_code
        == 409
    )


def test_concurrent_reschedules_confirm_only_one_and_preserve_the_loser(client, setup_service):
    s = setup_service
    bookings = [book(client, s, s["start"] + timedelta(hours=hour)).json() for hour in (0, 1)]
    barrier = Barrier(2)

    def worker(booking):
        with TestClient(app) as concurrent:
            barrier.wait(timeout=10)
            response = concurrent.post(
                f"/api/v1/bookings/{booking['id']}/reschedule",
                headers=s["customer"],
                json={
                    "starts_at": (s["start"] + timedelta(hours=2)).isoformat(),
                },
            )
            return booking, response.status_code

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(worker, bookings))
    assert sorted(status for _, status in results) == [200, 409]
    loser = next(booking for booking, status in results if status == 409)
    unchanged = client.get(f"/api/v1/bookings/{loser['id']}", headers=s["customer"]).json()
    assert datetime.fromisoformat(unchanged["starts_at"]) == datetime.fromisoformat(
        loser["starts_at"]
    )
