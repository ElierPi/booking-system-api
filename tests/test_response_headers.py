def test_sensitive_responses_and_errors_disallow_caching(client, auth):
    headers = auth()
    for response in [
        client.get("/api/v1/auth/me", headers=headers),
        client.get("/api/v1/auth/me"),
        client.post("/api/v1/auth/token", data={"username": "x", "password": "x"}),
    ]:
        assert response.headers["Cache-Control"] == "no-store"
        assert response.headers["X-Content-Type-Options"] == "nosniff"
        assert response.headers["Referrer-Policy"] == "no-referrer"
        assert response.headers["X-Request-ID"]
