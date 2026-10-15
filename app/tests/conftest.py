import os

os.environ.setdefault("KB_AUTH_TOKEN", "test-token")

import pytest
from fastapi.testclient import TestClient

from kb.main import create_app


@pytest.fixture
def client() -> TestClient:
    return TestClient(create_app())


@pytest.fixture
def auth_headers() -> dict:
    return {"Authorization": "Bearer test-token"}
