import uuid

import pytest
from fastapi.testclient import TestClient

from kb.config import get_settings
from kb.main import create_app

HEADERS = {"Authorization": "Bearer test-token"}

CREATED_CORPUS_IDS: list[str] = []


def uniq(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:6]}"


def create_corpus(client: TestClient, name: str, subdir: str, prefix: str,
                  dim: int = 4) -> str:
    resp = client.post("/api/v1/corpora", headers=HEADERS, json={
        "name": name, "subdir": subdir, "ontology_prefix": prefix, "vector_dim": dim,
    })
    assert resp.status_code == 200
    corpus_id = resp.json()["data"]["corpus_id"]
    CREATED_CORPUS_IDS.append(corpus_id)
    return corpus_id


@pytest.fixture(autouse=True)
def cleanup_created_corpora():
    yield
    if CREATED_CORPUS_IDS:
        client = TestClient(create_app())
        for corpus_id in list(CREATED_CORPUS_IDS):
            try:
                client.delete(f"/api/v1/corpora/{corpus_id}", headers=HEADERS)
            except Exception:
                pass
            CREATED_CORPUS_IDS.remove(corpus_id)
        get_settings.cache_clear()


@pytest.fixture
def host_env(tmp_path, monkeypatch):
    (tmp_path / "acc").mkdir()
    (tmp_path / "ontology").mkdir()
    monkeypatch.setenv("KB_CORPUS_ROOT", str(tmp_path))
    monkeypatch.setenv("KB_ONTOLOGY_EXPORT_DIR", str(tmp_path / "ontology"))
    monkeypatch.setenv("KB_AUTH_TOKEN", "test-token")
    get_settings.cache_clear()
    yield tmp_path
    get_settings.cache_clear()


@pytest.mark.integration
def test_corpus_lifecycle(host_env):
    client = TestClient(create_app())
    created = client.post("/api/v1/corpora", headers=HEADERS, json={
        "name": "验收库", "subdir": "acc", "ontology_prefix": "acc", "vector_dim": 4,
    })
    assert created.status_code == 200
    corpus_id = created.json()["data"]["corpus_id"]
    assert (host_env / "ontology" / f"{corpus_id}.ttl").exists()

    assert corpus_id in [c["corpus_id"] for c in client.get("/api/v1/corpora", headers=HEADERS).json()["data"]]

    detail = client.get(f"/api/v1/corpora/{corpus_id}", headers=HEADERS)
    assert detail.json()["data"]["points"] == 0

    assert client.delete(f"/api/v1/corpora/{corpus_id}", headers=HEADERS).status_code == 200
    assert client.get(f"/api/v1/corpora/{corpus_id}", headers=HEADERS).status_code == 404


@pytest.mark.integration
def test_create_corpus_rejects_missing_subdir(host_env):
    client = TestClient(create_app())
    resp = client.post("/api/v1/corpora", headers=HEADERS, json={
        "name": "坏库", "subdir": "不存在", "ontology_prefix": "bad", "vector_dim": 4,
    })
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "SUBDIR_NOT_FOUND"


@pytest.mark.integration
def test_ontology_rejects_relative_iri(host_env):
    client = TestClient(create_app())
    corpus_id = create_corpus(client, "本体库", "acc", "ont")

    bad = client.post(
        f"/api/v1/ontology/classes?corpus_id={corpus_id}", headers=HEADERS,
        json={"iri": "Project", "prefix_local": "Project", "label_zh": "项目", "definition": "交付单元"},
    )
    assert bad.status_code == 400
    assert bad.json()["error"]["code"] == "OWL_RL_VIOLATION"

    good = client.post(
        f"/api/v1/ontology/classes?corpus_id={corpus_id}", headers=HEADERS,
        json={"iri": "http://kb.local/o/ont#Project", "prefix_local": "Project",
              "label_zh": "项目", "definition": "交付单元", "aliases": ["项目组"]},
    )
    assert good.status_code == 200
    exported = client.get(f"/api/v1/ontology/export/{corpus_id}", headers=HEADERS)
    assert "Project" in exported.text


@pytest.mark.integration
def test_entity_split_moves_anchors(host_env):
    client = TestClient(create_app())
    corpus_id = create_corpus(client, "拆分库", "acc", "spl")
    client.post(f"/api/v1/ontology/classes?corpus_id={corpus_id}", headers=HEADERS, json={
        "iri": "http://kb.local/o/spl#Project", "prefix_local": "Project",
        "label_zh": "项目", "definition": "交付单元",
    })
    anchor_a = {"rel_path": "acc/a.md", "seq": 0, "sha256": "sa"}
    anchor_b = {"rel_path": "acc/b.md", "seq": 0, "sha256": "sb"}
    label = uniq("项目组")
    for anchor in (anchor_a, anchor_b):
        resp = client.post(f"/api/v1/entities?corpus_id={corpus_id}", headers=HEADERS, json={
            "label": label, "class_iri": "http://kb.local/o/spl#Project", "anchor": anchor,
        })
        assert resp.status_code == 200
    entities = client.get(f"/api/v1/entities?corpus_id={corpus_id}", headers=HEADERS).json()["data"]
    assert len(entities) == 1
    assert len(entities[0]["anchors"]) == 2

    split = client.post("/api/v1/entities/split", headers=HEADERS, json={
        "eid": entities[0]["eid"], "new_label": uniq("项目组-子"), "anchors": [anchor_a],
    })
    assert split.status_code == 200
    body = split.json()["data"]
    assert body["src_anchors"] == 1 and body["new_anchors"] == 1
    after = client.get(f"/api/v1/entities?corpus_id={corpus_id}", headers=HEADERS).json()["data"]
    assert sum(len(e["anchors"]) for e in after) == 2


@pytest.mark.integration
def test_ontology_delete_enqueues_violations(host_env):
    client = TestClient(create_app())
    corpus_id = create_corpus(client, "删除库", "acc", "del")
    client.post(f"/api/v1/ontology/classes?corpus_id={corpus_id}", headers=HEADERS, json={
        "iri": "http://kb.local/o/del#Project", "prefix_local": "Project",
        "label_zh": "项目", "definition": "交付单元",
    })
    client.post(f"/api/v1/ontology/classes?corpus_id={corpus_id}", headers=HEADERS, json={
        "iri": "http://kb.local/o/del#Person", "prefix_local": "Person",
        "label_zh": "人员", "definition": "个体",
    })
    client.post(f"/api/v1/ontology/object-properties?corpus_id={corpus_id}", headers=HEADERS, json={
        "iri": "http://kb.local/o/del#memberOf", "prefix_local": "memberOf",
        "label_zh": "属于", "definition": "人员属于项目",
        "domain_iri": "http://kb.local/o/del#Person",
        "range_iri": "http://kb.local/o/del#Project",
    })
    person = client.post(f"/api/v1/entities?corpus_id={corpus_id}", headers=HEADERS, json={
        "label": uniq("人员甲"), "class_iri": "http://kb.local/o/del#Person",
        "anchor": {"rel_path": "acc/a.md", "seq": 0, "sha256": "sa"},
    }).json()["data"]["eid"]
    project = client.post(f"/api/v1/entities?corpus_id={corpus_id}", headers=HEADERS, json={
        "label": uniq("项目乙"), "class_iri": "http://kb.local/o/del#Project",
        "anchor": {"rel_path": "acc/b.md", "seq": 0, "sha256": "sb"},
    }).json()["data"]["eid"]
    rel = client.post("/api/v1/relations", headers=HEADERS, json={
        "from_eid": person, "to_eid": project,
        "type_iri": "http://kb.local/o/del#memberOf",
    })
    assert rel.status_code == 200 and rel.json()["data"]["created"] is True

    deleted_prop = client.delete(
        f"/api/v1/ontology/object-properties/http%3A%2F%2Fkb.local%2Fo%2Fdel%23memberOf?corpus_id={corpus_id}",
        headers=HEADERS,
    )
    assert deleted_prop.status_code == 200
    assert deleted_prop.json()["data"]["affected_relations"] == 1

    deleted_class = client.delete(
        f"/api/v1/ontology/classes/http%3A%2F%2Fkb.local%2Fo%2Fdel%23Project?corpus_id={corpus_id}",
        headers=HEADERS,
    )
    assert deleted_class.status_code == 200
    assert deleted_class.json()["data"]["affected_entities"] == 1

    pending = client.get(f"/api/v1/pending?corpus_id={corpus_id}", headers=HEADERS).json()["data"]
    reasons = [p["payload"].get("reason") for p in pending]
    assert "property_deleted" in reasons
    assert "class_deleted" in reasons


@pytest.mark.integration
def test_ontology_patch_class_updates_ttl(host_env):
    client = TestClient(create_app())
    corpus_id = create_corpus(client, "改库", "acc", "pat")
    payload = {
        "iri": "http://kb.local/o/pat#Project", "prefix_local": "Project",
        "label_zh": "项目", "definition": "原始定义",
    }
    assert client.post(
        f"/api/v1/ontology/classes?corpus_id={corpus_id}", headers=HEADERS, json=payload
    ).status_code == 200
    patched = client.patch(
        f"/api/v1/ontology/classes/http%3A%2F%2Fkb.local%2Fo%2Fpat%23Project?corpus_id={corpus_id}",
        headers=HEADERS,
        json={**payload, "definition": "修订后的定义"},
    )
    assert patched.status_code == 200
    ttl = (host_env / "ontology" / f"{corpus_id}.ttl").read_text(encoding="utf-8")
    assert "修订后的定义" in ttl


def test_token_required(host_env):
    assert TestClient(create_app()).get("/api/v1/corpora").status_code == 401
