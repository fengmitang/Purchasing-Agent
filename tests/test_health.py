from datetime import UTC, datetime

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_health_returns_service_metadata_and_utc_time() -> None:
    response = client.get("/health")

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ok"
    assert payload["service"] == "purchasing-agent"
    assert payload["version"] == "0.1.0"

    response_time = datetime.fromisoformat(payload["time"].replace("Z", "+00:00"))
    assert response_time.tzinfo is not None
    assert response_time.utcoffset() == UTC.utcoffset(response_time)
