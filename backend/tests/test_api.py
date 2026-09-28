from fastapi.testclient import TestClient

from moody import __version__
from moody.api.app import create_app


def test_health() -> None:
    client = TestClient(create_app())
    resp = client.get("/api/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok", "version": __version__}


def test_openapi_lists_health() -> None:
    schema = create_app().openapi()
    assert "/api/health" in schema["paths"]
