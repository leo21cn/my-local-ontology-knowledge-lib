from fastapi import APIRouter, Depends, FastAPI
from fastapi.testclient import TestClient

from kb.auth import require_token
from kb.main import create_app


def _app_with_protected_ping() -> FastAPI:
    app = create_app()
    router = APIRouter(dependencies=[Depends(require_token)])

    @router.get("/api/v1/ping")
    async def ping() -> dict:
        return {"ok": True}

    app.include_router(router)
    return app


def test_protected_route_rejects_without_token():
    assert TestClient(_app_with_protected_ping()).get("/api/v1/ping").status_code == 401


def test_protected_route_accepts_with_token():
    resp = TestClient(_app_with_protected_ping()).get(
        "/api/v1/ping", headers={"Authorization": "Bearer test-token"}
    )
    assert resp.status_code == 200
    assert resp.json() == {"ok": True}
