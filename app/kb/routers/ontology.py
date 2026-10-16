from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import FileResponse

from kb.auth import require_token
from kb.config import get_settings
from kb.deps import get_neo4j
from kb.neo4j_store import (
    delete_ont_class,
    delete_ont_data_prop,
    delete_ont_obj_prop,
    get_ontology,
    new_ont_version,
    write_ont_class,
    write_ont_data_prop,
    write_ont_obj_prop,
)
from kb.ontology import export_ttl, find_violations, parse_ttl, validate_rl
from kb.proposals import create_pending
from kb.schemas import OntClassIn, OntDataPropIn, OntObjPropIn

router = APIRouter(prefix="/api/v1/ontology", dependencies=[Depends(require_token)])

MAX_TTL_BYTES = 1024 * 1024


def _reject(violations: list[str]) -> None:
    if violations:
        raise HTTPException(400, detail={"code": "OWL_RL_VIOLATION", "message": "; ".join(violations)})


def _save_and_export(driver, corpus_id: str, entry: dict, writer) -> dict:
    _reject(validate_rl(entry))
    writer(driver, corpus_id, entry)
    seq = new_ont_version(driver, corpus_id)
    ontology = get_ontology(driver, corpus_id)
    export_ttl(ontology, f"{get_settings().kb_ontology_export_dir}/{corpus_id}.ttl")
    return {**entry, "ont_version": seq}


@router.get("/{corpus_id}")
async def read_ontology(corpus_id: str, driver=Depends(get_neo4j)):
    return {"data": get_ontology(driver, corpus_id)}


@router.post("/classes")
async def create_class(corpus_id: str, body: OntClassIn, driver=Depends(get_neo4j)):
    return {"data": _save_and_export(driver, corpus_id, body.model_dump(exclude_none=True), write_ont_class)}


def _queue_violations(driver, corpus_id: str, entry: dict, violations: list[dict]) -> int:
    for violation in violations:
        create_pending(
            driver,
            corpus_id,
            "violation",
            {
                "type_iri": entry["iri"],
                "from": violation["from"],
                "to": violation["to"],
                "reason": violation["reason"],
            },
        )
    return len(violations)


@router.post("/object-properties")
async def create_obj_prop(corpus_id: str, body: OntObjPropIn, driver=Depends(get_neo4j)):
    entry = body.model_dump(exclude_none=True)
    saved = _save_and_export(driver, corpus_id, entry, write_ont_obj_prop)
    ontology = get_ontology(driver, corpus_id)
    violations = find_violations(driver, entry, ontology["classes"])
    queued = _queue_violations(driver, corpus_id, entry, violations)
    return {"data": {**saved, "violations": violations, "queued": queued}}


@router.post("/datatype-properties")
async def create_data_prop(corpus_id: str, body: OntDataPropIn, driver=Depends(get_neo4j)):
    return {"data": _save_and_export(driver, corpus_id, body.model_dump(exclude_none=True), write_ont_data_prop)}


@router.patch("/classes/{iri:path}")
async def patch_class(iri: str, corpus_id: str, body: OntClassIn, driver=Depends(get_neo4j)):
    entry = body.model_dump(exclude_none=True)
    entry["iri"] = iri
    return {"data": _save_and_export(driver, corpus_id, entry, write_ont_class)}


@router.delete("/classes/{iri:path}")
async def remove_class(iri: str, corpus_id: str, driver=Depends(get_neo4j)):
    affected = delete_ont_class(driver, corpus_id, iri)
    for row in affected:
        create_pending(
            driver,
            corpus_id,
            "violation",
            {
                "entity_eid": row["eid"],
                "entity_label": row["label"],
                "class_iri": iri,
                "reason": "class_deleted",
            },
        )
    seq = new_ont_version(driver, corpus_id)
    export_ttl(
        get_ontology(driver, corpus_id),
        f"{get_settings().kb_ontology_export_dir}/{corpus_id}.ttl",
    )
    return {"data": {"deleted": iri, "affected_entities": len(affected), "ont_version": seq}}


@router.patch("/object-properties/{iri:path}")
async def patch_obj_prop(iri: str, corpus_id: str, body: OntObjPropIn, driver=Depends(get_neo4j)):
    entry = body.model_dump(exclude_none=True)
    entry["iri"] = iri
    saved = _save_and_export(driver, corpus_id, entry, write_ont_obj_prop)
    violations = find_violations(driver, entry, get_ontology(driver, corpus_id)["classes"])
    queued = _queue_violations(driver, corpus_id, entry, violations)
    return {"data": {**saved, "violations": violations, "queued": queued}}


@router.delete("/object-properties/{iri:path}")
async def remove_obj_prop(iri: str, corpus_id: str, driver=Depends(get_neo4j)):
    affected = delete_ont_obj_prop(driver, corpus_id, iri)
    for row in affected:
        create_pending(
            driver,
            corpus_id,
            "violation",
            {
                "from_eid": row["from_eid"],
                "to_eid": row["to_eid"],
                "type_iri": iri,
                "reason": "property_deleted",
            },
        )
    seq = new_ont_version(driver, corpus_id)
    export_ttl(
        get_ontology(driver, corpus_id),
        f"{get_settings().kb_ontology_export_dir}/{corpus_id}.ttl",
    )
    return {"data": {"deleted": iri, "affected_relations": len(affected), "ont_version": seq}}


@router.patch("/datatype-properties/{iri:path}")
async def patch_data_prop(iri: str, corpus_id: str, body: OntDataPropIn, driver=Depends(get_neo4j)):
    entry = body.model_dump(exclude_none=True)
    entry["iri"] = iri
    return {"data": _save_and_export(driver, corpus_id, entry, write_ont_data_prop)}


@router.delete("/datatype-properties/{iri:path}")
async def remove_data_prop(iri: str, corpus_id: str, driver=Depends(get_neo4j)):
    delete_ont_data_prop(driver, corpus_id, iri)
    seq = new_ont_version(driver, corpus_id)
    export_ttl(
        get_ontology(driver, corpus_id),
        f"{get_settings().kb_ontology_export_dir}/{corpus_id}.ttl",
    )
    return {"data": {"deleted": iri, "ont_version": seq}}


@router.get("/export/{corpus_id}")
async def download_ttl(corpus_id: str):
    path = f"{get_settings().kb_ontology_export_dir}/{corpus_id}.ttl"
    return FileResponse(path, media_type="text/turtle", filename=f"{corpus_id}.ttl")


@router.post("/import")
async def import_ttl(corpus_id: str, file: UploadFile = File(...), driver=Depends(get_neo4j)):
    content = await file.read()
    if len(content) > MAX_TTL_BYTES:
        raise HTTPException(400, detail={"code": "FILE_TOO_LARGE",
                                         "message": "TTL 文件超过 1MB"})
    try:
        parsed = parse_ttl(content.decode("utf-8"))
    except UnicodeDecodeError:
        raise HTTPException(400, detail={"code": "NOT_UTF8", "message": "文件须为 UTF-8 编码"})
    except ValueError as exc:
        raise HTTPException(400, detail={"code": "TTL_PARSE_ERROR", "message": str(exc)})

    ontology = get_ontology(driver, corpus_id)
    existing = {
        "classes": {c["iri"] for c in ontology["classes"]},
        "object_properties": {p["iri"] for p in ontology["object_properties"]},
        "datatype_properties": {p["iri"] for p in ontology["datatype_properties"]},
    }
    writers = {
        "classes": write_ont_class,
        "object_properties": write_ont_obj_prop,
        "datatype_properties": write_ont_data_prop,
    }
    created = 0
    updated = 0
    imported_obj_props: list[dict] = []
    for kind in ("classes", "object_properties", "datatype_properties"):
        for entry in parsed[kind]:
            violations = validate_rl(entry)
            if violations:
                parsed["skipped"].append({"iri": entry["iri"], "reason": "; ".join(violations)})
                continue
            if entry["iri"] in existing[kind]:
                updated += 1
            else:
                created += 1
            writers[kind](driver, corpus_id, entry)
            if kind == "object_properties":
                imported_obj_props.append(entry)

    final_ontology = get_ontology(driver, corpus_id)
    queued = 0
    for entry in imported_obj_props:
        violations = find_violations(driver, entry, final_ontology["classes"])
        queued += _queue_violations(driver, corpus_id, entry, violations)

    seq = new_ont_version(driver, corpus_id)
    export_ttl(
        final_ontology,
        f"{get_settings().kb_ontology_export_dir}/{corpus_id}.ttl",
    )
    return {"data": {"created": created, "updated": updated,
                     "skipped": parsed["skipped"], "queued": queued,
                     "ont_version": seq}}
