def test_service_search_is_literal_and_can_be_scoped_to_owner(client, auth):
    owner, other = auth(), auth("other@example.com")
    for name, headers in [
        ("Python mentoring", owner),
        ("100% focus", owner),
        ("Python audit", other),
        ("SQL_basics", other),
    ]:
        assert (
            client.post(
                "/api/v1/services",
                headers=headers,
                json={
                    "name": name,
                    "timezone": "UTC",
                    "duration_minutes": 60,
                },
            ).status_code
            == 201
        )
    results = client.get("/api/v1/services?search=PYTHON", headers=owner).json()
    assert len(results) == 2
    own = client.get("/api/v1/services?search=python&mine=true", headers=owner).json()
    assert [item["name"] for item in own] == ["Python mentoring"]
    for needle, expected in [("%", "100% focus"), ("_", "SQL_basics")]:
        result = client.get("/api/v1/services", params={"search": needle}, headers=owner)
        assert [item["name"] for item in result.json()] == [expected]
    assert client.get("/api/v1/services", params={"search": " "}, headers=owner).status_code == 422
