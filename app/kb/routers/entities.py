import json

from fastapi import APIRouter, Depends, HTTPException

from kb.auth import require_token
from kb.deps import get_neo4j
from kb.neo4j_store import (
    count_entity_anchors,
    get_ontology,
    list_entities_with_anchors,
    move_anchors_to,
)
from kb.ontology import check_relation_valid
from kb.proposals import (
    create_pending,
    edit_ontology_proposal,
    ensure_entity,
    list_pending,
    resolve_pending,
    split_entity,
)
from kb.schemas import EditPending, EntitiesMerge, EntitiesSplit, EntityIn, PendingResolve, RelationIn

router = APIRouter(prefix="/api/v1", dependencies=[Depends(require_token)])

MERGE_QUERY = """
MATCH (keep:Entity {eid: $keep}), (drop:Entity {eid: $drop})
WITH keep, drop, [a IN drop.aliases WHERE NOT a IN keep.aliases] AS extra
SET keep.aliases = keep.aliases + extra
WITH keep, drop
MATCH (drop)-[r:REL]->(other:Entity) WHERE other <> keep
CREATE (keep)-[nr:REL]->(other) SET nr = properties(r)
WITH keep, drop
MATCH (other:Entity)-[r:REL]->(drop) WHERE other <> keep
CREATE (other)-[nr:REL]->(keep) SET nr = properties(r)
DETACH DELETE drop
RETURN keep.eid AS eid
"""


@router.get("/entities")
async def read_entities(corpus_id: str, driver=Depends(get_neo4j)):
    return {"data": list_entities_with_anchors(driver, corpus_id)}


@router.post("/entities")
async def create_entity(corpus_id: str, body: EntityIn, driver=Depends(get_neo4j)):
    eid = ensure_entity(driver, corpus_id, body.label, body.class_iri, body.anchor, ont_version=0)
    return {"data": {"eid": eid}}


@router.post("/entities/merge")
async def merge_entities(body: EntitiesMerge, driver=Depends(get_neo4j)):
    row = driver.session().run(MERGE_QUERY, keep=body.keep, drop=body.drop).single()
    if row is None:
        raise HTTPException(404, detail={"code": "ENTITY_NOT_FOUND", "message": body.keep})
    move_anchors_to(driver, body.drop, body.keep)
    anchors = count_entity_anchors(driver, body.keep)
    return {"data": {"eid": row["eid"], "anchors": anchors}}


@router.post("/entities/split")
async def split_entity_route(body: EntitiesSplit, driver=Depends(get_neo4j)):
    try:
        result = split_entity(driver, body.eid, body.new_label, body.anchors, body.class_iri)
    except KeyError:
        raise HTTPException(404, detail={"code": "ENTITY_NOT_FOUND", "message": body.eid})
    except ValueError as exc:
        raise HTTPException(400, detail={"code": "SPLIT_INVALID", "message": str(exc)})
    return {"data": result}


@router.post("/relations")
async def create_relation(body: RelationIn, driver=Depends(get_neo4j)):
    with driver.session() as session:
        a = session.run("MATCH (e:Entity {eid: $eid}) RETURN e", eid=body.from_eid).single()
        b = session.run("MATCH (e:Entity {eid: $eid}) RETURN e", eid=body.to_eid).single()
    if a is None or b is None:
        raise HTTPException(404, detail={"code": "ENTITY_NOT_FOUND", "message": body.from_eid})
    from_node, to_node = dict(a["e"]), dict(b["e"])
    if from_node.get("corpus_id") != to_node.get("corpus_id"):
        raise HTTPException(
            400, detail={"code": "CROSS_CORPUS_RELATION", "message": "关系两端实体必须属于同一库"}
        )
    corpus_id = from_node["corpus_id"]
    ontology = get_ontology(driver, corpus_id)
    obj_prop = next(
        (p for p in ontology["object_properties"] if p["iri"] == body.type_iri), None
    )
    if obj_prop is None:
        raise HTTPException(400, detail={"code": "PROPERTY_NOT_FOUND", "message": body.type_iri})
    reasons = check_relation_valid(
        ontology["classes"], obj_prop, from_node["class_iri"], to_node["class_iri"]
    )
    if reasons:
        pid = create_pending(
            driver,
            corpus_id,
            "violation",
            {
                "from_eid": body.from_eid,
                "to_eid": body.to_eid,
                "type_iri": body.type_iri,
                "reason": ",".join(reasons),
            },
        )
        return {"data": {"created": False, "pending_pid": pid, "violations": reasons}}
    driver.session().run(
        """
        MATCH (a:Entity {eid: $from_eid}), (b:Entity {eid: $to_eid})
        CREATE (a)-[r:REL {type_iri: $type_iri, evidence_anchors: $anchors, state: 'confirmed'}]->(b)
        """,
        from_eid=body.from_eid, to_eid=body.to_eid, type_iri=body.type_iri,
        anchors=json.dumps(body.evidence_anchors, ensure_ascii=False),
    )
    return {"data": {"created": True}}


@router.get("/pending")
async def read_pending(corpus_id: str | None = None, limit: int = 500,
                       driver=Depends(get_neo4j)):
    return {"data": list_pending(driver, corpus_id, limit=min(limit, 5000))}


@router.post("/pending/{pid}/resolve")
async def resolve(pid: str, body: PendingResolve, driver=Depends(get_neo4j)):
    if body.action not in {"confirm", "reject", "retype"}:
        raise HTTPException(400, detail={"code": "BAD_ACTION", "message": body.action})
    try:
        return {"data": resolve_pending(driver, pid, body.action, body.new_class_iri)}
    except KeyError:
        raise HTTPException(404, detail={"code": "PENDING_NOT_FOUND", "message": pid})


@router.patch("/pending/{pid}")
async def edit(pid: str, body: EditPending, driver=Depends(get_neo4j)):
    try:
        result = edit_ontology_proposal(driver, pid, body.model_dump(exclude_none=True))
    except KeyError:
        raise HTTPException(404, detail={"code": "PENDING_NOT_FOUND", "message": pid})
    except ValueError as exc:
        raise HTTPException(400, detail={"code": "EDIT_REJECTED", "message": str(exc)})
    return {"data": result}
