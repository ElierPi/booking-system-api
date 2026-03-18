from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from threading import Barrier
from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.exc import IntegrityError

from app.core.database import SessionLocal
from app.main import app
from app.models import Booking


def book(client, setup, start=None, headers=None):
    return client.post(
        "/api/v1/bookings",
        headers=headers or setup["customer"],
        json={
            "service_id": setup["service_id"],
            "starts_at": (start or setup["start"]).isoformat(),
        },
    )


def test_booking_availability_cancellation_and_rebooking(client, setup_service):
    s = setup_service
    url = f"/api/v1/services/{s['service_id']}/availability?day={s['day']}"
    assert len(client.get(url, headers=s["customer"]).json()) == 3
    created = book(client, s)
    assert created.status_code == 201, created.text
    booking_id = created.json()["id"]
    assert len(client.get(url, headers=s["customer"]).json()) == 2
    assert book(client, s).status_code == 409
    # Half-open intervals allow a booking immediately after another.
    assert book(client, s, s["start"] + timedelta(hours=1)).status_code == 201
    assert client.get(f"/api/v1/bookings/{booking_id}", headers=s["owner"]).status_code == 200
    assert client.get("/api/v1/bookings?as_provider=true", headers=s["owner"]).json()["total"] == 2
    assert client.get("/api/v1/bookings", headers=s["customer"]).json()["total"] == 2
    for _ in range(2):
        cancelled = client.post(f"/api/v1/bookings/{booking_id}/cancel", headers=s["customer"])
        assert cancelled.status_code == 200 and cancelled.json()["status"] == "cancelled"
    assert book(client, s).status_code == 201


def test_permissions_and_calendar_rules(client, setup_service):
    s = setup_service
    service_url = f"/api/v1/services/{s['service_id']}"
    body = {"weekday": s["day"].weekday(), "starts_at": "09:30", "ends_at": "10:30"}
    assert (
        client.post(service_url + "/windows", headers=s["customer"], json=body).status_code == 404
    )
    assert client.post(service_url + "/windows", headers=s["owner"], json=body).status_code == 409
    for update in [
        {"ends_at": "08:00"},
        {"weekday": 7},
        {"starts_at": "09:30:10"},
        {"starts_at": "09:30:00+01:00"},
    ]:
        assert (
            client.post(
                service_url + "/windows", headers=s["owner"], json=body | update
            ).status_code
            == 422
        )
    assert book(client, s, s["start"] + timedelta(minutes=30)).status_code == 422
    assert book(client, s, s["start"] - timedelta(days=14)).status_code == 422
    assert book(client, s, s["start"] + timedelta(days=400)).status_code == 422
    assert (
        client.post(
            "/api/v1/bookings",
            headers=s["customer"],
            json={
                "service_id": s["service_id"],
                "starts_at": "2027-01-01T09:00:00",
            },
        ).status_code
        == 422
    )
    booking_id = book(client, s).json()["id"]
    assert client.get(f"/api/v1/bookings/{booking_id}", headers=s["outsider"]).status_code == 404
    assert (
        client.post(f"/api/v1/bookings/{booking_id}/cancel", headers=s["outsider"]).status_code
        == 404
    )
    assert client.get("/api/v1/bookings", headers=s["outsider"]).json()["total"] == 0
    assert (
        client.delete(service_url + f"/windows/{s['window_id']}", headers=s["customer"]).status_code
        == 404
    )
    assert (
        client.delete(service_url + f"/windows/{s['window_id']}", headers=s["owner"]).status_code
        == 204
    )
    # Removing a schedule affects new bookings, existing confirmations remain valid.
    assert (
        client.get(f"/api/v1/bookings/{booking_id}", headers=s["customer"]).json()["status"]
        == "confirmed"
    )
    assert book(client, s, s["start"] + timedelta(hours=1)).status_code == 422


def test_concurrent_requests_confirm_exactly_one_booking(setup_service):
    s = setup_service
    barrier = Barrier(2)

    def worker():
        with TestClient(app) as concurrent_client:
            barrier.wait(timeout=10)
            return book(concurrent_client, s).status_code

    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [executor.submit(worker) for _ in range(2)]
        statuses = sorted(future.result(timeout=20) for future in futures)
    assert statuses == [201, 409]


def test_database_rejects_partial_overlaps_without_api(client, setup_service):
    s = setup_service
    existing = book(client, s).json()
    with SessionLocal() as db:
        db.add(
            Booking(
                service_id=UUID(s["service_id"]),
                customer_id=UUID(existing["customer_id"]),
                starts_at=s["start"] + timedelta(minutes=30),
                ends_at=s["start"] + timedelta(minutes=90),
                status="confirmed",
            )
        )
        with pytest.raises(IntegrityError) as error:
            db.commit()
        assert error.value.orig.sqlstate == "23P01"
        db.rollback()


def test_started_bookings_cannot_be_cancelled(client, setup_service):
    s = setup_service
    existing = book(client, s).json()
    with SessionLocal() as db:
        booking = db.get(Booking, UUID(existing["id"]))
        booking.starts_at = datetime.now(UTC) - timedelta(hours=2)
        booking.ends_at = datetime.now(UTC) - timedelta(hours=1)
        db.commit()
    assert (
        client.post(f"/api/v1/bookings/{existing['id']}/cancel", headers=s["customer"]).status_code
        == 409
    )


def test_invalid_timezone_and_service_validation(client, auth):
    headers = auth()
    for updates in [{"timezone": "Mars/Olympus"}, {"duration_minutes": 0}, {"name": " "}]:
        assert (
            client.post(
                "/api/v1/services",
                headers=headers,
                json={
                    "name": "Consulting",
                    "timezone": "UTC",
                    "duration_minutes": 60,
                }
                | updates,
            ).status_code
            == 422
        )


def test_equivalent_timezone_offsets_reference_same_instant(client, setup_service):
    s = setup_service
    from datetime import timezone

    shifted = s["start"].astimezone(timezone(timedelta(hours=-5)))
    assert book(client, s, shifted).status_code == 201
    assert book(client, s).status_code == 409
