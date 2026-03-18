"""Tests require an explicitly named, disposable PostgreSQL database."""

import os
from datetime import UTC, datetime, time, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.engine import make_url

test_url = os.environ.get("TEST_DATABASE_URL")
if not test_url:
    raise RuntimeError("Set TEST_DATABASE_URL to a disposable PostgreSQL database ending in _test")
url = make_url(test_url)
if url.get_backend_name() != "postgresql" or not (url.database or "").endswith("_test"):
    raise RuntimeError(
        "Refusing to reset a database that is not PostgreSQL or does not end in _test"
    )
os.environ["DATABASE_URL"] = test_url
os.environ["JWT_SECRET"] = "test-only-secret-never-use-in-production-12345"

from app.core.database import engine  # noqa: E402
from app.main import app  # noqa: E402


@pytest.fixture(autouse=True)
def clean_database():
    # Migrations must already have been applied: tests exercise the shipped schema.
    with engine.begin() as connection:
        tables = connection.scalars(
            text(
                "SELECT tablename FROM pg_tables WHERE schemaname = 'public' "
                "AND tablename != 'alembic_version'"
            )
        ).all()
        if tables:
            quoted = ", ".join('"' + name.replace('"', '""') + '"' for name in tables)
            connection.execute(text(f"TRUNCATE TABLE {quoted} CASCADE"))
    yield
    engine.dispose()


@pytest.fixture
def client():
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def auth(client):
    def create(email="developer@example.com"):
        response = client.post(
            "/api/v1/auth/register",
            json={
                "email": email,
                "password": "Strong-test-password-123",
            },
        )
        assert response.status_code == 201, response.text
        token = client.post(
            "/api/v1/auth/token",
            data={
                "username": email,
                "password": "Strong-test-password-123",
            },
        )
        assert token.status_code == 200, token.text
        return {"Authorization": "Bearer " + token.json()["access_token"]}

    return create


@pytest.fixture
def setup_service(client, auth):
    owner = auth("provider@example.com")
    customer = auth("customer@example.com")
    outsider = auth("outsider@example.com")
    day = datetime.now(UTC).date() + timedelta(days=7)
    start = datetime.combine(day, time(9), tzinfo=UTC)
    service = client.post(
        "/api/v1/services",
        headers=owner,
        json={
            "name": "Consulting",
            "timezone": "UTC",
            "duration_minutes": 60,
        },
    )
    assert service.status_code == 201, service.text
    service_id = service.json()["id"]
    window = client.post(
        f"/api/v1/services/{service_id}/windows",
        headers=owner,
        json={
            "weekday": day.weekday(),
            "starts_at": "09:00",
            "ends_at": "12:00",
        },
    )
    assert window.status_code == 201, window.text
    return {
        "owner": owner,
        "customer": customer,
        "outsider": outsider,
        "service_id": service_id,
        "day": day,
        "start": start,
        "window_id": window.json()["id"],
    }
