import hashlib
import json

from kb.neo4j_store import (
    count_entity_anchors,
    ensure_anchor_link,
    list_entity_anchors,
    new_pending_id,
    remove_anchor_links,
)


def get_classes_with_aliases(driver, corpus_id: str) -> list[dict]:
    query = """
    MATCH (c:OntClass {corpus_id: $corpus_id})
    RETURN c.iri AS iri, c.label_zh AS label_zh, c.arrays AS arrays
    """
    with driver.session() as session:
        rows = session.run(query, corpus_id=corpus_id).data()
    classes = []
    for row in rows:
        arrays = json.loads(row["arrays"]) if row["arrays"] else {}
        classes.append(
            {"iri": row["iri"], "label_zh": row["label_zh"], "aliases": arrays.get("aliases", [])}
        )
    return classes


def entity_id(class_iri: str, label: str) -> str:
    return hashlib.sha256(f"{class_iri}::{label}".encode("utf-8")).hexdigest()[:24]


def create_pending(driver, corpus_id: str, kind: str, payload: dict) -> str:
    pid = new_pending_id()
    with driver.session() as session:
        session.run(
            """
            CREATE (p:PendingItem {pid: $pid, corpus_id: $corpus_id, kind: $kind,
                                   payload: $payload, attempts: 0,
                                   last_error_code: '', status: 'open', created_at: timestamp()})
            """,
            pid=pid, corpus_id=corpus_id, kind=kind, payload=json.dumps(payload, ensure_ascii=False),
        )
    return pid


def list_pending(driver, corpus_id: str | None = None, limit: int = 50, offset: int = 0,
                 include_closed: bool = False) -> list[dict]:
    query = "MATCH (p:PendingItem) WHERE ($corpus_id IS NULL OR p.corpus_id = $corpus_id)"
    if not include_closed:
        query += " AND p.status = 'open'"
    query += " RETURN p ORDER BY p.created_at DESC SKIP $offset LIMIT $limit"
    with driver.session() as session:
        rows = session.run(query, corpus_id=corpus_id, offset=offset, limit=limit).data()
    out = []
    for row in rows:
        node = dict(row["p"])
        node["payload"] = json.loads(node["payload"]) if node.get("payload") else {}
        out.append(node)
    return out


def ensure_entity(driver, corpus_id: str, label: str, class_iri: str, anchor: dict,
                  ont_version: int) -> str:
    eid = entity_id(class_iri, label)
    with driver.session() as session:
        session.run(
            """
            MERGE (e:Entity {eid: $eid})
            ON CREATE SET e.corpus_id = $corpus_id, e.label = $label, e.class_iri = $class_iri,
                          e.aliases = [], e.ont_version = $version
            ON MATCH SET e.ont_version = $version
            WITH e
            MERGE (c:OntClass {iri: $class_iri})
            MERGE (e)-[:INSTANCE_OF]->(c)
            """,
            eid=eid, corpus_id=corpus_id, label=label, class_iri=class_iri,
            version=ont_version,
        )
    ensure_anchor_link(driver, eid, anchor)
    return eid


def _pending_payload(driver, pid: str) -> dict:
    with driver.session() as session:
        row = session.run(
            "MATCH (p:PendingItem {pid: $pid}) RETURN p.payload AS payload, p.kind AS kind, p.corpus_id AS corpus_id",
            pid=pid,
        ).single()
    if row is None:
        raise KeyError(pid)
    return {
        "kind": row["kind"],
        "corpus_id": row["corpus_id"],
        "payload": json.loads(row["payload"]) if row["payload"] else {},
    }


def resolve_pending(driver, pid: str, action: str, new_class_iri: str | None = None) -> dict:
    record = _pending_payload(driver, pid)
    payload = record["payload"]
    if action == "reject":
        status = "rejected"
        eid = ""
    elif action == "retype":
        if not new_class_iri:
            raise ValueError("retype 需要 new_class_iri")
        payload["class_iri"] = new_class_iri
        status = "open"
        eid = ""
    else:
        status = "confirmed"
        eid = ensure_entity(
            driver,
            record["corpus_id"],
            payload.get("label", payload.get("term", "")),
            payload.get("class_iri", new_class_iri or ""),
            payload.get("anchor", {}),
            ont_version=payload.get("ont_version", 0),
        )
    with driver.session() as session:
        session.run(
            "MATCH (p:PendingItem {pid: $pid}) SET p.status = $status", pid=pid, status=status
        )
    anchor_count = 0
    if eid:
        anchor_count = count_entity_anchors(driver, eid)
    return {"pid": pid, "action": action, "status": status, "eid": eid, "anchor_count": anchor_count}


def generate_entity_proposals(driver, corpus_id: str, chunks: list[dict]) -> int:
    classes = get_classes_with_aliases(driver, corpus_id)
    created = 0
    for ontology_class in classes:
        terms = [ontology_class["label_zh"]] + list(ontology_class.get("aliases", []))
        for chunk in chunks:
            matched = next((term for term in terms if term and term in chunk["text"]), None)
            if matched is None:
                continue
            create_pending(
                driver,
                corpus_id,
                "proposal",
                {
                    "class_iri": ontology_class["iri"],
                    "term": matched,
                    "label": matched,
                    "anchor": {
                        "rel_path": chunk["asset_rel_path"],
                        "seq": chunk["seq"],
                        "sha256": chunk["chunk_sha256"],
                    },
                },
            )
            created += 1
    return created


def find_entities_by_anchor_rel_path(driver, corpus_id: str, rel_path: str) -> list[dict]:
    query = """
    MATCH (e:Entity {corpus_id: $corpus_id})-[:ANCHOR_OF]->(a:Anchor {rel_path: $rel_path})
    RETURN e.eid AS eid, e.label AS label,
           collect({rel_path: a.rel_path, seq: a.seq, sha256: a.sha256}) AS anchors
    """
    with driver.session() as session:
        return session.run(query, corpus_id=corpus_id, rel_path=rel_path).data()


def split_entity(driver, eid: str, new_label: str, anchors: list[dict],
                 class_iri: str | None = None) -> dict:
    with driver.session() as session:
        row = session.run("MATCH (src:Entity {eid: $eid}) RETURN src", eid=eid).single()
        if row is None:
            raise KeyError(eid)
        src = dict(row["src"])
    src_anchors = list_entity_anchors(driver, eid)
    if not anchors:
        raise ValueError("anchors 不能为空")
    if any(a not in src_anchors for a in anchors):
        raise ValueError("anchors 必须为源实体锚点的子集")
    if len(src_anchors) - len(anchors) < 1:
        raise ValueError("拆分后源实体至少保留一个锚点")
    target_class = class_iri or src["class_iri"]
    new_eid = entity_id(target_class, new_label)
    with driver.session() as session:
        session.run(
            """
            CREATE (n:Entity {eid: $new_eid, corpus_id: $corpus_id, label: $label,
                              class_iri: $class_iri, aliases: [], ont_version: $version})
            WITH n
            MATCH (c:OntClass {iri: $class_iri})
            MERGE (n)-[:INSTANCE_OF]->(c)
            """,
            new_eid=new_eid, corpus_id=src["corpus_id"], label=new_label,
            class_iri=target_class, version=src.get("ont_version", 0),
        )
    removed = remove_anchor_links(driver, eid, anchors)
    for anchor in anchors:
        ensure_anchor_link(driver, new_eid, anchor)
    return {
        "eid": new_eid,
        "src_anchors": len(src_anchors) - removed,
        "new_anchors": count_entity_anchors(driver, new_eid),
    }
