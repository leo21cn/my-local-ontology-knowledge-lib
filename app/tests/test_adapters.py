import pytest
from fastapi.testclient import TestClient

from kb.main import create_app

HEADERS = {"Authorization": "Bearer test-token"}

FAKE_RESULTS = [
    {
        "chunk_id": "cid1",
        "content": "命中片段",
        "context": "所属小节的完整上下文",
        "anchor": {"rel_path": "acc/a.md", "seq": 0, "sha256": "s0"},
        "score": 0.42,
        "vector_rank": 1,
        "fused_rank": 1,
        "heading_path": ["标题"],
        "asset_rel_path": "acc/a.md",
    }
]


@pytest.fixture
def client(monkeypatch):
    async def fake_search(settings, corpus_id, query, filters, top_k):
        assert corpus_id == "corp1"
        assert query == "测试查询"
        return FAKE_RESULTS

    monkeypatch.setattr("kb.adapters.dify.run_search", fake_search)
    return TestClient(create_app())


def test_retrieval_returns_dify_shape(client):
    resp = client.post(
        "/retrieval",
        headers=HEADERS,
        json={
            "knowledge_id": "corp1",
            "query": "测试查询",
            "retrieval_setting": {"top_k": 5, "score_threshold": 0.0},
        },
    )
    assert resp.status_code == 200
    body = resp.json()
    assert "data" not in body
    record = body["records"][0]
    assert record["content"] == "所属小节的完整上下文"
    assert record["title"] == "acc/a.md"
    assert record["metadata"]["chunk_id"] == "cid1"
    assert record["metadata"]["anchor"]["sha256"] == "s0"


def test_retrieval_applies_score_threshold(client):
    resp = client.post(
        "/retrieval",
        headers=HEADERS,
        json={
            "knowledge_id": "corp1",
            "query": "测试查询",
            "retrieval_setting": {"top_k": 5, "score_threshold": 0.9},
        },
    )
    assert resp.json()["records"] == []


def test_retrieval_requires_token(client):
    resp = client.post("/retrieval", json={"knowledge_id": "corp1", "query": "q"})
    assert resp.status_code == 401


def test_mcp_requires_token(client):
    resp = client.get("/mcp")
    assert resp.status_code == 401
    assert resp.json()["error"]["code"] == "AUTH_REQUIRED"


def test_mcp_accepts_token(client):
    resp = client.get("/mcp", headers=HEADERS)
    assert resp.status_code != 401
