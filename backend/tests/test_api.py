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


def test_ui_is_served_next_to_the_api(tmp_path) -> None:  # type: ignore[no-untyped-def]
    from moody.config import Settings

    ui = tmp_path / "dist"
    ui.mkdir()
    (ui / "index.html").write_text("<!doctype html><title>Moody</title>")
    app = create_app(Settings(data_dir=tmp_path / "data", ui_dir=ui))
    with TestClient(app) as client:
        assert "<title>Moody</title>" in client.get("/").text
        assert client.get("/api/health").json()["status"] == "ok"
        assert client.get("/api/meta").status_code == 200
