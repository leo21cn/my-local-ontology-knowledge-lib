import json
import time
from uuid import uuid4

from neo4j import GraphDatabase

from kb.config import Settings

CONSTRAINT_STATEMENTS = [
    "CREATE CONSTRAINT corpus_id IF NOT EXISTS FOR (n:Corpus) REQUIRE n.corpus_id IS UNIQUE",
    "CREATE CONSTRAINT ont_class_iri IF NOT EXISTS FOR (n:OntClass) REQUIRE n.iri IS UNIQUE",
    "CREATE CONSTRAINT ont_objprop_iri IF NOT EXISTS FOR (n:OntObjProp) REQUIRE n.iri IS UNIQUE",
    "CREATE CONSTRAINT ont_dataprop_iri IF NOT EXISTS FOR (n:OntDataProp) REQUIRE n.iri IS UNIQUE",
    "CREATE CONSTRAINT entity_eid IF NOT EXISTS FOR (n:Entity) REQUIRE n.eid IS UNIQUE",
    "CREATE CONSTRAINT pending_pid IF NOT EXISTS FOR (n:PendingItem) REQUIRE n.pid IS UNIQUE",
    "CREATE CONSTRAINT opstask_id IF NOT EXISTS FOR (n:OpsTask) REQUIRE n.task_id IS UNIQUE",
    "CREATE CONSTRAINT anchor_uniq IF NOT EXISTS FOR (n:Anchor) REQUIRE (n.rel_path, n.seq, n.sha256) IS UNIQUE",
]

CORPUS_FIELDS = (
    "corpus_id name subdir embedding_model vector_dim chunk_max_chars "
    "chunk_overlap ontology_prefix archived created_at"
)


def get_driver(settings: Settings):
    return GraphDatabase.driver(
        settings.neo4j_uri, auth=(settings.neo4j_user, settings.neo4j_password)
    )


def init_schema(driver) -> None:
    with driver.session() as session:
        for statement in CONSTRAINT_STATEMENTS:
            session.run(statement)


def upsert_corpus(driver, corpus: dict) -> None:
    query = f"MERGE (c:Corpus {{corpus_id: $corpus_id}}) SET c += $props"
    with driver.session() as session:
        session.run(query, corpus_id=corpus["corpus_id"], props=corpus)


def get_corpus(driver, corpus_id: str) -> dict | None:
    with driver.session() as session:
        row = session.run(
            "MATCH (c:Corpus {corpus_id: $id}) RETURN c", id=corpus_id
        ).single()
    return dict(row["c"]) if row else None


def list_corpora(driver) -> list[dict]:
    with driver.session() as session:
        return [dict(r["c"]) for r in session.run("MATCH (c:Corpus) RETURN c")]


def delete_corpus(driver, corpus_id: str) -> None:
    statements = [
        "MATCH (a:Anchor)<-[:ANCHOR_OF]-(e:Entity {corpus_id: $id}) DETACH DELETE a",
        "MATCH (e:Entity {corpus_id: $id}) DETACH DELETE e",
        "MATCH (n:OntClass {corpus_id: $id}) DELETE n",
        "MATCH (n:OntObjProp {corpus_id: $id}) DELETE n",
        "MATCH (n:OntDataProp {corpus_id: $id}) DELETE n",
        "MATCH (n:OntVersion {corpus_id: $id}) DELETE n",
        "MATCH (n:PendingItem {corpus_id: $id}) DELETE n",
        "MATCH (n:OpsTask {corpus_id: $id}) DELETE n",
        "MATCH (c:Corpus {corpus_id: $id}) DELETE c",
    ]
    with driver.session() as session:
        for statement in statements:
            session.run(statement, id=corpus_id)


def ensure_anchor_link(driver, eid: str, anchor: dict) -> None:
    query = """
    MERGE (a:Anchor {rel_path: $rel_path, seq: $seq, sha256: $sha256})
    WITH a
    MATCH (e:Entity {eid: $eid})
    MERGE (e)-[:ANCHOR_OF]->(a)
    """
    with driver.session() as session:
        session.run(
            query,
            eid=eid,
            rel_path=anchor["rel_path"],
            seq=int(anchor["seq"]),
            sha256=anchor["sha256"],
        )


def list_entity_anchors(driver, eid: str) -> list[dict]:
    query = """
    MATCH (e:Entity {eid: $eid})-[:ANCHOR_OF]->(a:Anchor)
    RETURN a.rel_path AS rel_path, a.seq AS seq, a.sha256 AS sha256
    ORDER BY a.rel_path, a.seq
    """
    with driver.session() as session:
        return session.run(query, eid=eid).data()


def count_entity_anchors(driver, eid: str) -> int:
    query = """
    MATCH (e:Entity {eid: $eid})-[:ANCHOR_OF]->(a:Anchor)
    RETURN count(a) AS n
    """
    with driver.session() as session:
        return session.run(query, eid=eid).single()["n"]


def move_anchors_to(driver, from_eid: str, to_eid: str) -> int:
    query = """
    MATCH (drop:Entity {eid: $from_eid})-[:ANCHOR_OF]->(a:Anchor)
    OPTIONAL MATCH (keep:Entity {eid: $to_eid})
    WITH a, keep
    WHERE keep IS NOT NULL
    MERGE (keep)-[:ANCHOR_OF]->(a)
    RETURN count(a) AS n
    """
    with driver.session() as session:
        return session.run(query, from_eid=from_eid, to_eid=to_eid).single()["n"]


def remove_anchor_links(driver, eid: str, anchors: list[dict]) -> int:
    query = """
    MATCH (e:Entity {eid: $eid})
    UNWIND $anchors AS anchor
    MATCH (e)-[link:ANCHOR_OF]->(a:Anchor {rel_path: anchor.rel_path, seq: anchor.seq, sha256: anchor.sha256})
    WITH DISTINCT link
    DELETE link
    RETURN count(link) AS n
    """
    with driver.session() as session:
        normalized = [
            {"rel_path": a["rel_path"], "seq": int(a["seq"]), "sha256": a["sha256"]}
            for a in anchors
        ]
        return session.run(query, eid=eid, anchors=normalized).single()["n"]


def list_entities_with_anchors(driver, corpus_id: str) -> list[dict]:
    query = """
    MATCH (e:Entity {corpus_id: $id})
    OPTIONAL MATCH (e)-[:ANCHOR_OF]->(a:Anchor)
    RETURN e.eid AS eid, e.label AS label, e.class_iri AS class_iri,
           e.aliases AS aliases, e.ont_version AS ont_version,
           collect(CASE WHEN a IS NULL THEN null
                        ELSE {rel_path: a.rel_path, seq: a.seq, sha256: a.sha256} END) AS anchors
    ORDER BY e.eid
    """
    with driver.session() as session:
        rows = session.run(query, id=corpus_id).data()
    for row in rows:
        row["anchors"] = [a for a in row["anchors"] if a is not None]
    return rows


def _write_ontology_node(driver, label: str, corpus_id: str, entry: dict) -> None:
    props = {k: v for k, v in entry.items() if not isinstance(v, (list, dict))}
    props["corpus_id"] = corpus_id
    arrays = {k: v for k, v in entry.items() if isinstance(v, (list, dict))}
    query = f"MERGE (n:{label} {{iri: $iri}}) SET n += $props, n.arrays = $arrays"
    with driver.session() as session:
        session.run(query, iri=entry["iri"], props=props, arrays=json.dumps(arrays, ensure_ascii=False))


def write_ont_class(driver, corpus_id: str, entry: dict) -> None:
    _write_ontology_node(driver, "OntClass", corpus_id, entry)


def write_ont_obj_prop(driver, corpus_id: str, entry: dict) -> None:
    _write_ontology_node(driver, "OntObjProp", corpus_id, entry)


def write_ont_data_prop(driver, corpus_id: str, entry: dict) -> None:
    _write_ontology_node(driver, "OntDataProp", corpus_id, entry)


def _decode(node: dict) -> dict:
    out = dict(node)
    arrays = out.pop("arrays", None)
    if arrays:
        out.update(json.loads(arrays))
    return out


def get_ontology(driver, corpus_id: str) -> dict:
    with driver.session() as session:
        classes = [_decode(r["n"]) for r in session.run(
            "MATCH (n:OntClass {corpus_id: $id}) RETURN n", id=corpus_id)]
        obj_props = [_decode(r["n"]) for r in session.run(
            "MATCH (n:OntObjProp {corpus_id: $id}) RETURN n", id=corpus_id)]
        data_props = [_decode(r["n"]) for r in session.run(
            "MATCH (n:OntDataProp {corpus_id: $id}) RETURN n", id=corpus_id)]
        corpus = session.run(
            "MATCH (c:Corpus {corpus_id: $id}) RETURN c.ontology_prefix AS p", id=corpus_id
        ).single()
    prefix = corpus["p"] if corpus else corpus_id
    return {
        "base_iri": f"http://kb.local/o/{prefix}#",
        "classes": classes,
        "object_properties": obj_props,
        "datatype_properties": data_props,
    }


def new_ont_version(driver, corpus_id: str) -> int:
    with driver.session() as session:
        row = session.run(
            """
            MATCH (c:Corpus {corpus_id: $id})
            OPTIONAL MATCH (v:OntVersion {corpus_id: $id})
            WITH c, coalesce(max(v.seq), 0) + 1 AS seq
            CREATE (:OntVersion {corpus_id: $id, seq: seq, exported_at: $now})
            RETURN seq
            """,
            id=corpus_id,
            now=time.time(),
        ).single()
    return row["seq"]


def record_task(driver, task_id: str, corpus_id: str, status: str, kind: str = "sync") -> None:
    with driver.session() as session:
        session.run(
            """
            MERGE (t:OpsTask {task_id: $task_id})
            ON CREATE SET t.corpus_id = $corpus_id, t.kind = $kind
            SET t.status = $status, t.started_at = $now,
                t.doc_total = 0, t.doc_changed = 0, t.doc_removed = 0, t.chunks = 0,
                t.tokens = 0, t.embed_retries = 0, t.cost_estimate = 0.0, t.proposals = 0,
                t.extract_calls = 0, t.extract_tokens = 0, t.extract_failed = 0,
                t.extract_discarded = 0, t.extract_cost_estimate = 0.0,
                t.error_code = ''
            """,
            task_id=task_id, corpus_id=corpus_id, kind=kind, status=status, now=time.time(),
        )


def update_task(driver, task_id: str, **fields) -> None:
    if not fields:
        return
    sets = ", ".join(f"t.{key} = ${key}" for key in fields)
    with driver.session() as session:
        session.run(f"MATCH (t:OpsTask {{task_id: $task_id}}) SET {sets}", task_id=task_id, **fields)


def get_task(driver, task_id: str) -> dict | None:
    with driver.session() as session:
        row = session.run("MATCH (t:OpsTask {task_id: $id}) RETURN t", id=task_id).single()
    return dict(row["t"]) if row else None


def list_tasks(driver, corpus_id: str | None = None, kind: str | None = None,
               limit: int = 50) -> list[dict]:
    query = "MATCH (t:OpsTask) WHERE ($cid IS NULL OR t.corpus_id = $cid)"
    if kind:
        query += " AND t.kind = $kind"
    query += " RETURN t ORDER BY t.started_at DESC LIMIT $limit"
    with driver.session() as session:
        rows = session.run(query, cid=corpus_id, kind=kind, limit=limit).data()
    return [dict(row["t"]) for row in rows]


def new_pending_id() -> str:
    return uuid4().hex


def delete_ont_class(driver, corpus_id: str, iri: str) -> list[dict]:
    with driver.session() as session:
        rows = session.run(
            """
            MATCH (e:Entity {corpus_id: $id})-[:INSTANCE_OF]->(c:OntClass {iri: $iri})
            RETURN e.eid AS eid, e.label AS label
            """,
            id=corpus_id, iri=iri,
        ).data()
        session.run(
            "MATCH (n:OntClass {corpus_id: $id, iri: $iri}) DETACH DELETE n",
            id=corpus_id, iri=iri,
        )
    return rows


def delete_ont_obj_prop(driver, corpus_id: str, iri: str) -> list[dict]:
    with driver.session() as session:
        rows = session.run(
            """
            MATCH (a:Entity)-[r:REL {type_iri: $iri, state: 'confirmed'}]->(b:Entity)
            WHERE a.corpus_id = $id
            RETURN a.eid AS from_eid, a.label AS from_label, b.eid AS to_eid, b.label AS to_label
            """,
            id=corpus_id, iri=iri,
        ).data()
        session.run("MATCH ()-[r:REL {type_iri: $iri}]->() DELETE r", iri=iri)
        session.run("MATCH (n:OntObjProp {corpus_id: $id, iri: $iri}) DELETE n", id=corpus_id, iri=iri)
    return rows


def delete_ont_data_prop(driver, corpus_id: str, iri: str) -> None:
    with driver.session() as session:
        session.run(
            "MATCH (n:OntDataProp {corpus_id: $id, iri: $iri}) DELETE n",
            id=corpus_id, iri=iri,
        )
