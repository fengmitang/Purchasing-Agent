from fastapi.testclient import TestClient

from app.bootstrap import create_application
from app.main import app


def test_application_factory_returns_independent_instances() -> None:
    first_application = create_application()
    second_application = create_application()

    assert first_application is not second_application


def test_main_exposes_importable_application() -> None:
    assert app.title == "purchasing-agent"
    assert app.version == "0.1.0"


def test_unknown_path_returns_not_found() -> None:
    response = TestClient(app).get("/not-a-route")

    assert response.status_code == 404
