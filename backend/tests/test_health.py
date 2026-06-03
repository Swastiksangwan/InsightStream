def test_health_endpoint(client):
    response = client.get("/")

    assert response.status_code == 200
    assert "InsightStream backend is running" in response.json()["message"]
