import pytest
from fastapi.testclient import TestClient

from kb.config import get_settings
from kb.neo4j_store import delete_corpus, get_driver, init_schema, upsert_corpus, write_ont_class, write_ont_obj_prop
from kb.proposals import ensure_entity
from kb.main import create_app

HEADERS = {"Authorization": "Bearer test-token"}

CORPUS = {
    "corpus_id": "c-graph", "name": "图谱库", "subdir": "acceptance",
    "embedding_model": "text-embedding-v4", "vector_dim": 4,
    "chunk_max_chars": 700, "chunk_overlap": 60, "ontology_prefix": "cgraph",
    "archived": False, "created_at": 0.0,
}


@pytest.fixture
def driver():
    settings = get_settings()
    if not settings.neo4j_password:
        pytest.skip("需要 .env 中的 NEO4J_PASSWORD")
    drv = get_driver(settings)
    init_schema(drv)
    upsert_corpus(drv, CORPUS)
    write_ont_class(drv, "c-graph", {
        "iri": "http://kb.local/o/cgraph#Person", "label_zh": "人员",
        "definition": "个体", "parent_iris": [], "disjoint_with": [],
    })
    write_ont_class(drv, "c-graph", {
        "iri": "http://kb.local/o/cgraph#Project", "label_zh": "项目",
        "definition": "交付单元", "parent_iris": [], "disjoint_with": [],
    })
    write_ont_obj_prop(drv, "c-graph", {
        "iri": "http://kb.local/o/cgraph#memberOf", "label_zh": "参与",
        "definition": "人员参与项目",
        "domain_iri": "http://kb.local/o/cgraph#Person",
        "range_iri": "http://kb.local/o/cgraph#Project",
    })
    a = ensure_entity(drv, "c-graph", "人员甲", "http://kb.local/o/cgraph#Person",
                      {"rel_path": "a.md", "seq": 0, "sha256": "s-a"}, ont_version=1)
    b = ensure_entity(drv, "c-graph", "项目乙", "http://kb.local/o/cgraph#Project",
                      {"rel_path": "b.md", "seq": 0, "sha256": "s-b"}, ont_version=1)
    with drv.session() as session:
        session.run(
            """
            MATCH (a:Entity {eid: $a}), (b:Entity {eid: $b})
            CREATE (a)-[r:REL {type_iri: $t, evidence_anchors: '{}', state: 'confirmed'}]->(b)
            """,
            a=a, b=b, t="http://kb.local/o/cgraph#memberOf",
        )
    yield drv
    delete_corpus(drv, "c-graph")
    drv.close()


@pytest.mark.integration
def test_graph_center_mode(driver):
    client = TestClient(create_app())
    resp = client.get("/api/v1/graph?entity_id=missing-eid&depth=1", headers=HEADERS)
    assert resp.status_code == 200
    assert resp.json()["data"]["nodes"] == []


@pytest.mark.integration
def test_graph_full_view(driver):
    client = TestClient(create_app())
    resp = client.get("/api/v1/graph?mode=all&corpus_id=c-graph", headers=HEADERS)
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["total"] == 2
    assert data["truncated"] is False
    assert len(data["nodes"]) == 2
    assert len(data["edges"]) == 1
    assert data["edges"][0]["type_iri"] == "http://kb.local/o/cgraph#memberOf"


@pytest.mark.integration
def test_graph_full_view_requires_corpus(driver):
    client = TestClient(create_app())
    resp = client.get("/api/v1/graph?mode=all", headers=HEADERS)
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "CORPUS_ID_REQUIRED"


@pytest.mark.integration
def test_graph_center_mode_requires_entity(driver):
    client = TestClient(create_app())
    resp = client.get("/api/v1/graph", headers=HEADERS)
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "ENTITY_ID_REQUIRED"
