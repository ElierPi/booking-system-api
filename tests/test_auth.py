from datetime import UTC, datetime, timedelta

import jwt

from app.core.config import get_settings


def test_authentication_lifecycle(client, auth):
    headers = auth("Developer@Example.com")
    me = client.get("/api/v1/auth/me", headers=headers)
    assert me.status_code == 200
    assert me.json()["email"] == "developer@example.com"
    assert "password_hash" not in me.json()
    assert client.get("/api/v1/auth/me").status_code == 401
    assert (
        client.post(
            "/api/v1/auth/register",
            json={
                "email": "DEVELOPER@example.com",
                "password": "Strong-test-password-123",
            },
        ).status_code
        == 409
    )
    assert (
        client.post(
            "/api/v1/auth/token",
            data={
                "username": "developer@example.com",
                "password": "wrong",
            },
        ).status_code
        == 401
    )
    assert (
        client.post(
            "/api/v1/auth/token",
            data={
                "username": "missing@example.com",
                "password": "wrong",
            },
        ).status_code
        == 401
    )


def test_rejects_expired_or_foreign_tokens(client, auth):
    headers = auth()
    settings = get_settings()
    claims = jwt.decode(
        headers["Authorization"].split()[1],
        settings.jwt_secret,
        algorithms=["HS256"],
        audience=settings.jwt_issuer,
    )
    for updates in [
        {"exp": datetime.now(UTC) - timedelta(seconds=1)},
        {"iss": "another-service"},
        {"aud": "another-service"},
        {"sub": "not-a-uuid"},
    ]:
        token = jwt.encode(claims | updates, settings.jwt_secret, algorithm="HS256")
        assert (
            client.get(
                "/api/v1/auth/me",
                headers={
                    "Authorization": f"Bearer {token}",
                },
            ).status_code
            == 401
        )


def test_registration_validation_and_health(client):
    assert (
        client.post(
            "/api/v1/auth/register",
            json={
                "email": "bad",
                "password": "short",
            },
        ).status_code
        == 422
    )
    assert client.get("/health").json() == {"status": "ok"}
    response = client.get("/ready")
    assert response.status_code == 200
    assert response.headers["X-Request-ID"]
