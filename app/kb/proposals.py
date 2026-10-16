import hashlib
import json

from kb.config import get_settings
from kb.neo4j_store import (
    count_entity_anchors,
    ensure_anchor_link,
    get_ontology,
    list_entity_anchors,
    new_ont_version,
    new_pending_id,
    remove_anchor_links,
    write_ont_class,
    write_ont_data_prop,
    write_ont_obj_prop,
)
from kb.ontology import check_relation_valid, export_ttl, validate_rl


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
    serialized = json.dumps(payload, ensure_ascii=False, sort_keys=True)
    with driver.session() as session:
        duplicate = session.run(
            """
            MATCH (p:PendingItem {corpus_id: $corpus_id, kind: $kind, status: 'open'})
            RETURN p.pid AS pid, p.payload AS payload
            """,
            corpus_id=corpus_id, kind=kind,
        )
        for row in duplicate:
            if json.dumps(json.loads(row["payload"]) if row["payload"] else {}, ensure_ascii=False, sort_keys=True) == serialized:
                return row["pid"]
        pid = new_pending_id()
        session.run(
            """
            CREATE (p:PendingItem {pid: $pid, corpus_id: $corpus_id, kind: $kind,
                                   payload: $payload, attempts: 0,
                                   last_error_code: '', status: 'open', created_at: timestamp()})
            """,
            pid=pid, corpus_id=corpus_id, kind=kind, payload=serialized,
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


def _pending_class_proposals(driver, corpus_id: str) -> dict[str, str]:
    with driver.session() as session:
        rows = session.run(
            """
            MATCH (p:PendingItem {corpus_id: $corpus_id, kind: 'ontology_proposal', status: 'open'})
            RETURN p.payload AS payload, p.pid AS pid
            """,
            corpus_id=corpus_id,
        ).data()
    mapping: dict[str, str] = {}
    for row in rows:
        payload = json.loads(row["payload"]) if row["payload"] else {}
        if payload.get("element_kind") == "class" and payload.get("label"):
            mapping[payload["label"]] = row["pid"]
    return mapping


def _unresolved_message(driver, corpus_id: str, missing: list[str],
                        available: str, code: str) -> str:
    pending_class_labels = _pending_class_proposals(driver, corpus_id)
    hints = []
    for label in missing:
        if label in pending_class_labels:
            hints.append(f"待确认的类提案中存在「{label}」，请先在「本体提案」页签确认该类")
        else:
            hints.append(f"类「{label}」不存在于已确认类或待确认类提案中，请编辑提案改用其他类标签，或先补建该类")
    base = f"{code}: 类标签未找到 {missing}"
    if not available:
        base += "（该库尚无任何已确认的类）"
    else:
        base += f"（已确认类的标签：{available}）"
    return base + "。" + "；".join(hints) + "。"


def _pending_pids_for(driver, corpus_id: str, missing: list[str]) -> list[dict]:
    mapping = _pending_class_proposals(driver, corpus_id)
    return [{"label": label, "pid": mapping[label]}
            for label in missing if label in mapping]


def edit_ontology_proposal(driver, pid: str, fields: dict) -> dict:
    record = _pending_payload(driver, pid)
    if record["kind"] != "ontology_proposal":
        raise ValueError("仅本体提案支持编辑")
    payload = record["payload"]
    if fields.get("local_name") is not None:
        payload["local_name"] = fields["local_name"]
    if fields.get("label") is not None:
        payload["label"] = fields["label"]
    if fields.get("definition") is not None:
        payload["definition"] = fields["definition"]
    if fields.get("aliases") is not None:
        payload["aliases"] = fields["aliases"]
    if payload.get("element_kind") in ("object_property", "datatype_property"):
        if fields.get("domain") is not None:
            payload["domain"] = fields["domain"]
        if fields.get("range") is not None:
            payload["range"] = fields["range"]
    if not payload.get("label") or not payload.get("definition"):
        raise ValueError("label 与 definition 不能为空")
    ontology = get_ontology(driver, record["corpus_id"])
    prefix = ontology["base_iri"].rstrip("#").rsplit("/", 1)[-1]
    payload["iri_preview"] = f"http://kb.local/o/{prefix}#{payload['local_name']}"
    with driver.session() as session:
        session.run(
            "MATCH (p:PendingItem {pid: $pid}) SET p.payload = $payload",
            pid=pid, payload=json.dumps(payload, ensure_ascii=False),
        )
    return {"pid": pid, "payload": payload}


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
        if record["kind"] == "relation_proposal":
            return _confirm_relation_proposal(driver, record["corpus_id"], pid, payload)
        if record["kind"] == "ontology_proposal":
            return _confirm_ontology_proposal(driver, record["corpus_id"], pid, payload)
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


def create_relation_proposal(driver, corpus_id: str, from_term: str, to_term: str,
                             type_iri: str, anchor: dict) -> str:
    return create_pending(
        driver,
        corpus_id,
        "relation_proposal",
        {"from": from_term, "to": to_term, "type_iri": type_iri, "anchor": anchor},
    )


def generate_llm_proposals(driver, corpus_id: str, chunks: list[dict],
                           extracted: list[dict]) -> int:
    created = 0
    for chunk, result in zip(chunks, extracted):
        for entity in result["entities"]:
            create_pending(driver, corpus_id, "proposal", {
                "class_iri": entity["class_iri"],
                "term": entity["term"],
                "label": entity["term"],
                "anchor": {
                    "rel_path": chunk["asset_rel_path"],
                    "seq": chunk["seq"],
                    "sha256": chunk["chunk_sha256"],
                },
            })
            created += 1
        for relation in result["relations"]:
            create_relation_proposal(
                driver, corpus_id, relation["from"], relation["to"], relation["type_iri"],
                {"rel_path": chunk["asset_rel_path"], "seq": chunk["seq"],
                 "sha256": chunk["chunk_sha256"]},
            )
            created += 1
    return created


def _confirm_relation_proposal(driver, corpus_id: str, pid: str, payload: dict) -> dict:
    ontology = get_ontology(driver, corpus_id)
    obj_prop = next(
        (p for p in ontology["object_properties"] if p["iri"] == payload.get("type_iri")), None
    )
    if obj_prop is None or not obj_prop.get("domain_iri") or not obj_prop.get("range_iri"):
        return {"pid": pid, "action": "confirm", "status": "open",
                "eid": "", "anchor_count": 0, "error": "PROPERTY_DOMAIN_RANGE_MISSING"}
    anchor = payload.get("anchor", {})
    from_eid = ensure_entity(driver, corpus_id, payload["from"], obj_prop["domain_iri"],
                             anchor, ont_version=0)
    to_eid = ensure_entity(driver, corpus_id, payload["to"], obj_prop["range_iri"],
                           anchor, ont_version=0)
    reasons = check_relation_valid(
        ontology["classes"], obj_prop, obj_prop["domain_iri"], obj_prop["range_iri"]
    )
    if reasons:
        return {"pid": pid, "action": "confirm", "status": "open",
                "eid": from_eid, "anchor_count": 0, "error": ",".join(reasons)}
    with driver.session() as session:
        session.run(
            """
            MATCH (a:Entity {eid: $from_eid}), (b:Entity {eid: $to_eid})
            CREATE (a)-[r:REL {type_iri: $type_iri, evidence_anchors: $anchors,
                               state: 'confirmed'}]->(b)
            """,
            from_eid=from_eid, to_eid=to_eid, type_iri=obj_prop["iri"],
            anchors=json.dumps(anchor),
        )
        session.run("MATCH (p:PendingItem {pid: $pid}) SET p.status = 'confirmed'", pid=pid)
    return {"pid": pid, "action": "confirm", "status": "confirmed",
            "eid": from_eid, "anchor_count": count_entity_anchors(driver, from_eid)}


def create_ontology_proposal(driver, corpus_id: str, element_kind: str, entry: dict,
                             anchor: dict, prefix: str) -> str:
    iri = f"http://kb.local/o/{prefix}#{entry['local_name']}"
    label = entry.get("label", "")
    with driver.session() as session:
        duplicate_open = session.run(
            """
            MATCH (p:PendingItem {corpus_id: $corpus_id, kind: 'ontology_proposal', status: 'open'})
            WHERE p.payload CONTAINS $iri_fragment
            RETURN p.pid AS pid LIMIT 1
            """,
            corpus_id=corpus_id,
            iri_fragment=f'"iri_preview": "{iri}"',
        ).single()
        if duplicate_open:
            return ""
        if element_kind == "class":
            existing = session.run(
                "MATCH (c:OntClass {corpus_id: $id, iri: $iri}) RETURN c.label_zh AS l", id=corpus_id, iri=iri
            ).single()
        elif element_kind == "object_property":
            existing = session.run(
                "MATCH (c:OntObjProp {corpus_id: $id, iri: $iri}) RETURN c.label_zh AS l", id=corpus_id, iri=iri
            ).single()
        else:
            existing = session.run(
                "MATCH (c:OntDataProp {corpus_id: $id, iri: $iri}) RETURN c.label_zh AS l", id=corpus_id, iri=iri
            ).single()
        if existing and existing["l"] == label:
            return ""
    return create_pending(driver, corpus_id, "ontology_proposal", {
        "element_kind": element_kind,
        "local_name": entry["local_name"],
        "label": label,
        "definition": entry["definition"],
        "aliases": entry.get("aliases", []),
        "domain": entry.get("domain", ""),
        "range": entry.get("range", ""),
        "iri_preview": iri,
        "anchor": anchor,
    })


def _confirm_ontology_proposal(driver, corpus_id: str, pid: str, payload: dict) -> dict:
    ontology = get_ontology(driver, corpus_id)
    prefix = ontology["base_iri"].rstrip("#").rsplit("/", 1)[-1]
    iri = payload.get("iri_preview") or f"http://kb.local/o/{prefix}#{payload['local_name']}"
    existing_iris = {c["iri"] for c in ontology["classes"]} | {
        p["iri"] for p in ontology["object_properties"]
    } | {p["iri"] for p in ontology["datatype_properties"]}
    if iri in existing_iris:
        same_kind = (
            (payload["element_kind"] == "class" and any(c["iri"] == iri for c in ontology["classes"]))
            or (payload["element_kind"] == "object_property" and any(p["iri"] == iri for p in ontology["object_properties"]))
            or (payload["element_kind"] == "datatype_property" and any(p["iri"] == iri for p in ontology["datatype_properties"]))
        )
        existing_label = ""
        existing_kind = "类"
        if payload["element_kind"] == "class":
            match = [c for c in ontology["classes"] if c["iri"] == iri]
            if match:
                existing_label = match[0].get("label_zh", "")
        elif payload["element_kind"] == "object_property":
            existing_kind = "对象属性"
            match = [p for p in ontology["object_properties"] if p["iri"] == iri]
            if match:
                existing_label = match[0].get("label_zh", "")
        else:
            existing_kind = "数据属性"
            match = [p for p in ontology["datatype_properties"] if p["iri"] == iri]
            if match:
                existing_label = match[0].get("label_zh", "")
        is_duplicate = same_kind and (
            existing_label == payload["label"]
            or payload["label"] in [a for c in ontology["classes"] for a in c.get("aliases", []) if c["iri"] == iri]
        )
        if is_duplicate:
            with driver.session() as session:
                session.run(
                    "MATCH (p:PendingItem {pid: $pid}) SET p.status = 'rejected'", pid=pid
                )
            return {"pid": pid, "action": "confirm", "status": "rejected",
                    "eid": "", "anchor_count": 0,
                    "error": f"DUPLICATE: IRI {iri} 已存在且标签一致（{existing_label}），本条提案为重复内容，已自动关闭"}
        return {"pid": pid, "action": "confirm", "status": "open",
                "eid": "", "anchor_count": 0,
                "error": f"IRI_CONFLICT: IRI {iri} 已被{existing_kind}「{existing_label or iri}」占用。"
                         f"若本条提案与该{existing_kind}是同一概念，直接「拒绝」即可（已入册要素已覆盖）；"
                         f"若是不同概念，请编辑本地名后重试"}
    if payload["element_kind"] == "class":
        entry = {
            "iri": iri,
            "label_zh": payload["label"],
            "definition": payload["definition"],
            "aliases": payload.get("aliases", []),
        }
        violations = validate_rl(entry)
        if violations:
            return {"pid": pid, "action": "confirm", "status": "open",
                    "eid": "", "anchor_count": 0, "error": "; ".join(violations)}
        write_ont_class(driver, corpus_id, entry)
    elif payload["element_kind"] == "datatype_property":
        classes = ontology["classes"]
        label_to_iri = {}
        for c in classes:
            if c.get("label_zh"):
                label_to_iri[c["label_zh"]] = c["iri"]
            for alias in c.get("aliases", []):
                label_to_iri.setdefault(alias, c["iri"])
        domain_iri = label_to_iri.get(payload.get("domain", ""), "")
        if not domain_iri:
            available = "、".join(sorted(set(c.get("label_zh", "") for c in classes if c.get("label_zh"))))
            missing = [payload.get("domain", "")]
            return {"pid": pid, "action": "confirm", "status": "open",
                    "eid": "", "anchor_count": 0,
                    "error": _unresolved_message(
                        driver, corpus_id, missing, available, "DOMAIN_UNRESOLVED"),
                    "pending_pids": _pending_pids_for(driver, corpus_id, missing)}
        entry = {
            "iri": iri,
            "label_zh": payload["label"],
            "definition": payload["definition"],
            "domain_iri": domain_iri,
            "xsd_range": payload.get("range", "http://www.w3.org/2001/XMLSchema#string"),
        }
        violations = validate_rl(entry)
        if violations:
            return {"pid": pid, "action": "confirm", "status": "open",
                    "eid": "", "anchor_count": 0, "error": "; ".join(violations)}
        write_ont_data_prop(driver, corpus_id, entry)
    else:
        classes = ontology["classes"]
        label_to_iri = {}
        for c in classes:
            if c.get("label_zh"):
                label_to_iri[c["label_zh"]] = c["iri"]
            for alias in c.get("aliases", []):
                label_to_iri.setdefault(alias, c["iri"])
        domain_label = payload.get("domain", "")
        range_label = payload.get("range", "")
        domain_iri = label_to_iri.get(domain_label, "")
        range_iri = label_to_iri.get(range_label, "")
        if not domain_iri or not range_iri:
            missing = [
                label for label, iri in ((domain_label, domain_iri), (range_label, range_iri)) if not iri
            ]
            available = "、".join(sorted(set(c.get("label_zh", "") for c in classes if c.get("label_zh"))))
            return {"pid": pid, "action": "confirm", "status": "open",
                    "eid": "", "anchor_count": 0,
                    "error": _unresolved_message(
                        driver, corpus_id, missing, available, "DOMAIN_RANGE_UNRESOLVED"),
                    "pending_pids": _pending_pids_for(driver, corpus_id, missing)}
        entry = {
            "iri": iri,
            "label_zh": payload["label"],
            "definition": payload["definition"],
            "domain_iri": domain_iri,
            "range_iri": range_iri,
        }
        violations = validate_rl(entry)
        if violations:
            return {"pid": pid, "action": "confirm", "status": "open",
                    "eid": "", "anchor_count": 0, "error": "; ".join(violations)}
        write_ont_obj_prop(driver, corpus_id, entry)
    seq = new_ont_version(driver, corpus_id)
    export_ttl(
        get_ontology(driver, corpus_id),
        f"{get_settings().kb_ontology_export_dir}/{corpus_id}.ttl",
    )
    with driver.session() as session:
        session.run("MATCH (p:PendingItem {pid: $pid}) SET p.status = 'confirmed'", pid=pid)
    return {"pid": pid, "action": "confirm", "status": "confirmed",
            "eid": iri, "anchor_count": 0, "ont_version": seq}


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
