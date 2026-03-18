from datetime import timedelta

from test_bookings import book


def test_start_time_filter_is_half_open_timezone_aware_and_combines_with_status(
    client, setup_service
):
    s = setup_service
    for hours in range(3):
        assert book(client, s, s["start"] + timedelta(hours=hours)).status_code == 201
    params = {
        "starts_from": s["start"].isoformat(),
        "starts_before": (s["start"] + timedelta(hours=1)).isoformat(),
        "status": "confirmed",
    }
    response = client.get("/api/v1/bookings", headers=s["customer"], params=params)
    assert response.status_code == 200 and response.json()["total"] == 1
    params["starts_before"] = params["starts_from"]
    assert client.get("/api/v1/bookings", headers=s["customer"], params=params).status_code == 422
    assert (
        client.get(
            "/api/v1/bookings?starts_from=2027-01-01T00:00:00", headers=s["customer"]
        ).status_code
        == 422
    )


def test_booking_status_filter_works_for_customer_and_provider(client, setup_service):
    s = setup_service
    cancelled = book(client, s).json()
    assert (
        client.post(f"/api/v1/bookings/{cancelled['id']}/cancel", headers=s["customer"]).status_code
        == 200
    )
    book(client, s, s["start"] + timedelta(hours=1))
    for headers, extra in [(s["customer"], {}), (s["owner"], {"as_provider": True})]:
        for status in ["confirmed", "cancelled"]:
            response = client.get(
                "/api/v1/bookings", headers=headers, params={"status": status} | extra
            )
            assert response.status_code == 200
            assert response.json()["total"] == 1
            assert response.json()["items"][0]["status"] == status
    assert client.get("/api/v1/bookings?status=unknown", headers=s["customer"]).status_code == 422
    assert (
        client.get("/api/v1/bookings?status=confirmed", headers=s["outsider"]).json()["total"] == 0
    )
