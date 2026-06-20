"""Проверки health-эндпоинта и CORS для локального фронта."""

from fastapi.testclient import TestClient

from app.core.config import CORS_ORIGINS
from app.main import app

client = TestClient(app)


def test_health_returns_ok():
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


def test_cors_allows_frontend_origin():
    origin = CORS_ORIGINS[0]  # http://localhost:5173
    resp = client.get("/health", headers={"Origin": origin})
    assert resp.status_code == 200
    assert resp.headers["access-control-allow-origin"] == origin


def test_cors_preflight_allows_frontend_origin():
    origin = CORS_ORIGINS[0]
    resp = client.options(
        "/health",
        headers={
            "Origin": origin,
            "Access-Control-Request-Method": "GET",
        },
    )
    assert resp.status_code == 200
    assert resp.headers["access-control-allow-origin"] == origin
