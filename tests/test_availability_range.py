from datetime import timedelta

from test_bookings import book


def test_range_includes_empty_days_and_excludes_confirmed_bookings(client, setup_service):
    s = setup_service
    book(client, s)
    url = f"/api/v1/services/{s['service_id']}/availability-range"
    response = client.get(
        url,
        headers=s["customer"],
        params={
            "day_from": s["day"].isoformat(),
            "day_to": (s["day"] + timedelta(days=6)).isoformat(),
        },
    )
    assert response.status_code == 200
    days = response.json()
    assert len(days) == 7 and len(days[0]["slots"]) == 2
    assert all(day["slots"] == [] for day in days[1:])
    assert (
        days[0]["slots"]
        == client.get(
            f"/api/v1/services/{s['service_id']}/availability",
            headers=s["customer"],
            params={"day": s["day"].isoformat()},
        ).json()
    )


def test_range_rejects_reversed_oversized_and_out_of_horizon_dates(client, setup_service):
    s = setup_service
    url = f"/api/v1/services/{s['service_id']}/availability-range"
    for delta in [-1, 31, 400]:
        assert (
            client.get(
                url,
                headers=s["customer"],
                params={
                    "day_from": s["day"].isoformat(),
                    "day_to": (s["day"] + timedelta(days=delta)).isoformat(),
                },
            ).status_code
            == 422
        )
