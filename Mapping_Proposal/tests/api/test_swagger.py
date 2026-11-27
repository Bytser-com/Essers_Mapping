import pytest
from fastapi.testclient import TestClient

from api import create_app


@pytest.mark.parametrize("env", ["development", "dev", "local", "testing", "test", ""])
def test_swagger_enabled_in_dev_and_testing(env, monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", env)
    monkeypatch.delenv("SWAGGER_ENABLED", raising=False)
    app = create_app()
    client = TestClient(app)

    res_docs = client.get("/docs")
    assert res_docs.status_code == 200
    assert "swagger" in res_docs.text.lower() or "html" in res_docs.text.lower()

    res_swagger = client.get("/swagger", follow_redirects=False)
    assert res_swagger.status_code in {307, 308}
    assert res_swagger.headers["location"] == "/docs"

    res_openapi = client.get("/openapi.json")
    assert res_openapi.status_code == 200


@pytest.mark.parametrize("env", ["staging", "stage", "production", "prod"])
def test_swagger_disabled_in_staging_and_production(env, monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", env)
    # Even if SWAGGER_ENABLED is explicitly set to true, staging/production must block it
    monkeypatch.setenv("SWAGGER_ENABLED", "true")
    app = create_app()
    client = TestClient(app)

    assert client.get("/docs").status_code == 404
    assert client.get("/swagger").status_code == 404
    assert client.get("/openapi.json").status_code == 404


def test_swagger_disabled_when_explicitly_set_to_false(monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "development")
    monkeypatch.setenv("SWAGGER_ENABLED", "false")
    app = create_app()
    client = TestClient(app)

    assert client.get("/docs").status_code == 404
    assert client.get("/swagger").status_code == 404
    assert client.get("/openapi.json").status_code == 404
