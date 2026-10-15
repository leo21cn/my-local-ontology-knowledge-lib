import pytest

from kb.config import get_settings
from kb.neo4j_store import delete_corpus, get_driver, init_schema, upsert_corpus, write_ont_class
from kb.proposals import (
    create_pending,
    ensure_entity,
    entity_id,
    find_entities_by_anchor_rel_path,
    generate_entity_proposals,
    list_pending,
    resolve_pending,
    split_entity,
)

CORPUS = {
    "corpus_id": "c-prop", "name": "提案库", "subdir": "acceptance",
    "embedding_model": "text-embedding-v4", "vector_dim": 1024,
    "chunk_max_chars": 700, "chunk_overlap": 60, "ontology_prefix": "cprop",
    "archived": False, "created_at": 0.0,
}
CLASS = {
    "iri": "http://kb.local/o/cprop#Project", "label_zh": "项目",
    "definition": "一个交付单元", "parent_iris": [], "disjoint_with": [],
    "aliases": ["项目组"],
}
CHUNKS = [
    {"asset_rel_path": "a.md", "seq": 0, "chunk_sha256": "s0", "text": "本项目组由三人组成"},
    {"asset_rel_path": "b.md", "seq": 0, "chunk_sha256": "s1", "text": "无关内容"},
    {"asset_rel_path": "c.md", "seq": 2, "chunk_sha256": "s2", "text": "项目组例会"},
]


@pytest.fixture
def driver():
    settings = get_settings()
    if not settings.neo4j_password:
        pytest.skip("需要 .env 中的 NEO4J_PASSWORD")
    drv = get_driver(settings)
    init_schema(drv)
    upsert_corpus(drv, CORPUS)
    write_ont_class(drv, "c-prop", CLASS)
    yield drv
    delete_corpus(drv, "c-prop")
    drv.close()


@pytest.mark.integration
def test_entity_id_is_deterministic():
    assert entity_id("http://kb.local/o/cprop#Project", "项目组") == entity_id("http://kb.local/o/cprop#Project", "项目组")


@pytest.mark.integration
def test_alias_match_creates_two_proposals(driver):
    assert generate_entity_proposals(driver, "c-prop", CHUNKS) == 2
    assert len(list_pending(driver, "c-prop")) == 2


@pytest.mark.integration
def test_confirm_merges_anchors_from_multiple_files(driver):
    generate_entity_proposals(driver, "c-prop", CHUNKS)
    items = list_pending(driver, "c-prop")
    first = resolve_pending(driver, items[0]["pid"], "confirm")
    second = resolve_pending(driver, items[1]["pid"], "confirm")
    assert first["eid"] == second["eid"]
    assert second["anchor_count"] == 2


@pytest.mark.integration
def test_reject_removes_item(driver):
    create_pending(driver, "c-prop", "proposal", {"label": "临时"})
    items = list_pending(driver, "c-prop")
    resolve_pending(driver, items[0]["pid"], "reject")
    assert all(i["status"] != "open" for i in list_pending(driver, "c-prop", include_closed=True))


@pytest.mark.integration
def test_ensure_entity_keeps_single_node(driver):
    anchor = {"rel_path": "d.md", "seq": 0, "sha256": "s9"}
    eid = ensure_entity(driver, "c-prop", "项目甲", CLASS["iri"], anchor, ont_version=1)
    ensure_entity(driver, "c-prop", "项目甲", CLASS["iri"], anchor, ont_version=1)
    with driver.session() as session:
        count = session.run("MATCH (e:Entity {eid: $eid}) RETURN count(e) AS n", eid=eid).single()["n"]
    assert count == 1


@pytest.mark.integration
def test_find_entities_by_anchor_rel_path(driver):
    anchor = {"rel_path": "e.md", "seq": 0, "sha256": "s7"}
    ensure_entity(driver, "c-prop", "项目乙", CLASS["iri"], anchor, ont_version=1)
    found = find_entities_by_anchor_rel_path(driver, "c-prop", "e.md")
    assert len(found) == 1
    assert found[0]["eid"] == entity_id(CLASS["iri"], "项目乙")


@pytest.mark.integration
def test_split_entity_moves_anchor_subset(driver):
    a1 = {"rel_path": "f1.md", "seq": 0, "sha256": "s8"}
    a2 = {"rel_path": "f2.md", "seq": 0, "sha256": "s9"}
    eid = ensure_entity(driver, "c-prop", "项目丙", CLASS["iri"], a1, ont_version=1)
    ensure_entity(driver, "c-prop", "项目丙", CLASS["iri"], a2, ont_version=1)
    result = split_entity(driver, eid, "项目丙-子", [a1])
    assert result["src_anchors"] == 1
    assert result["new_anchors"] == 1
    with driver.session() as session:
        rows = session.run(
            """
            MATCH (e:Entity {corpus_id: 'c-prop'})-[:ANCHOR_OF]->(a:Anchor)
            RETURN e.eid AS eid, count(a) AS n ORDER BY n
            """
        ).data()
    assert [row["n"] for row in rows] == [1, 1]


@pytest.mark.integration
def test_relation_proposal_confirm_creates_entities_and_relation(driver):
    from kb.neo4j_store import write_ont_class, write_ont_obj_prop
    from kb.proposals import create_relation_proposal

    write_ont_class(driver, "c-prop", {
        "iri": "http://kb.local/o/cprop#Person", "label_zh": "人员",
        "definition": "个体", "parent_iris": [], "disjoint_with": [],
    })
    write_ont_obj_prop(driver, "c-prop", {
        "iri": "http://kb.local/o/cprop#belongsTo", "label_zh": "属于",
        "definition": "人员属于项目",
        "domain_iri": "http://kb.local/o/cprop#Person",
        "range_iri": CLASS["iri"],
    })
    anchor = {"rel_path": "g.md", "seq": 0, "sha256": "s-g"}
    pid = create_relation_proposal(
        driver, "c-prop", "人员甲", "项目乙", "http://kb.local/o/cprop#belongsTo", anchor
    )
    result = resolve_pending(driver, pid, "confirm")
    assert result["status"] == "confirmed"
    assert result["eid"] == entity_id("http://kb.local/o/cprop#Person", "人员甲")
    with driver.session() as session:
        rels = session.run(
            "MATCH (a:Entity {eid: $a})-[r:REL]->(b:Entity) RETURN r.type_iri AS t, b.label AS bl",
            a=result["eid"],
        ).data()
    assert len(rels) == 1
    assert rels[0]["t"] == "http://kb.local/o/cprop#belongsTo"
    items = list_pending(driver, "c-prop")
    assert all(i["pid"] != pid for i in items)


@pytest.mark.integration
def test_ontology_proposal_confirm_writes_ontology(driver):
    from kb.neo4j_store import get_ontology as neo4j_get_ontology
    from kb.proposals import create_ontology_proposal

    anchor = {"rel_path": "h.md", "seq": 0, "sha256": "s-h"}
    pid_cls = create_ontology_proposal(
        driver, "c-prop", "class",
        {"local_name": "Client", "label": "客户", "definition": "接受服务的个体", "aliases": []},
        anchor, "cprop",
    )
    result_cls = resolve_pending(driver, pid_cls, "confirm")
    assert result_cls["status"] == "confirmed"
    assert result_cls["eid"] == "http://kb.local/o/cprop#Client"
    ontology = neo4j_get_ontology(driver, "c-prop")
    assert any(c["iri"] == "http://kb.local/o/cprop#Client" for c in ontology["classes"])

    pid_prop = create_ontology_proposal(
        driver, "c-prop", "object_property",
        {"local_name": "serves", "label": "服务", "definition": "项目服务客户",
         "domain": "项目", "range": "客户"},
        anchor, "cprop",
    )
    result_prop = resolve_pending(driver, pid_prop, "confirm")
    assert result_prop["status"] == "confirmed"
    ontology = neo4j_get_ontology(driver, "c-prop")
    assert any(p["iri"] == "http://kb.local/o/cprop#serves" for p in ontology["object_properties"])
    with driver.session() as session:
        rels = session.run(
            "MATCH (a:Entity {eid: $a})-[r:REL]->(b:Entity) RETURN count(r) AS n", a=""
        ).single()
    assert rels is not None
