from datetime import timedelta

from test_bookings import book


def test_reschedule_is_atomic_preserves_id_and_frees_original_slot(client, setup_service):
    s = setup_service
    original = book(client, s).json()
    book(client, s, s["start"] + timedelta(hours=1))
    url = f"/api/v1/bookings/{original['id']}/reschedule"
    occupied = {"starts_at": (s["start"] + timedelta(hours=1)).isoformat()}
    assert client.post(url, headers=s["customer"], json=occupied).status_code == 409
    assert (
        client.get(f"/api/v1/bookings/{original['id']}", headers=s["customer"]).json() == original
    )
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
