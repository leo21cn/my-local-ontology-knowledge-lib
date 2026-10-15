import time
from pathlib import Path
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Request
from qdrant_client.models import FieldCondition, Filter, MatchValue

from kb.auth import require_token
from kb.config import get_settings
from kb.deps import get_neo4j, get_qdrant_client
from kb.neo4j_store import (
    delete_corpus,
    get_corpus,
    get_ontology,
    init_schema,
    list_corpora,
    new_ont_version,
    upsert_corpus,
)
from kb.ontology import export_ttl
from kb.qdrant_store import collection_name, ensure_collection
from kb.schemas import CorpusCreate, CorpusUpdate, ExtractTrigger, RebuildTrigger, SyncTrigger
from kb.sync import estimate_extract, estimate_rebuild

router = APIRouter(prefix="/api/v1/corpora", dependencies=[Depends(require_token)])


@router.post("")
async def create_corpus(body: CorpusCreate, driver=Depends(get_neo4j), client=Depends(get_qdrant_client)):
    settings = get_settings()
    corpus_dir = Path(settings.kb_corpus_root) / body.subdir
    if not corpus_dir.is_dir():
        raise HTTPException(400, detail={"code": "SUBDIR_NOT_FOUND", "message": f"权威源子目录不存在: {body.subdir}"})
    init_schema(driver)
    corpus_id = uuid4().hex[:12]
    ensure_collection(client, corpus_id, body.vector_dim)
    corpus = {**body.model_dump(), "corpus_id": corpus_id, "archived": False, "created_at": time.time()}
    upsert_corpus(driver, corpus)
    new_ont_version(driver, corpus_id)
    export_ttl(get_ontology(driver, corpus_id), f"{settings.kb_ontology_export_dir}/{corpus_id}.ttl")
    return {"data": corpus}


@router.get("")
async def read_corpora(driver=Depends(get_neo4j)):
    return {"data": list_corpora(driver)}


@router.get("/{corpus_id}")
async def read_corpus(corpus_id: str, driver=Depends(get_neo4j), client=Depends(get_qdrant_client)):
    corpus = get_corpus(driver, corpus_id)
    if corpus is None:
        raise HTTPException(404, detail={"code": "CORPUS_NOT_FOUND", "message": corpus_id})
    name = collection_name(corpus_id)
    points = client.count(collection_name=name).count if client.collection_exists(name) else 0
    return {"data": {**corpus, "points": points}}


@router.patch("/{corpus_id}")
async def patch_corpus(corpus_id: str, body: CorpusUpdate, driver=Depends(get_neo4j)):
    corpus = get_corpus(driver, corpus_id)
    if corpus is None:
        raise HTTPException(404, detail={"code": "CORPUS_NOT_FOUND", "message": corpus_id})
    changes = {k: v for k, v in body.model_dump(exclude_none=True).items()}
    if not changes:
        return {"data": corpus}
    upsert_corpus(driver, {**corpus, **changes})
    return {"data": get_corpus(driver, corpus_id)}


@router.delete("/{corpus_id}")
async def remove_corpus(corpus_id: str, driver=Depends(get_neo4j), client=Depends(get_qdrant_client)):
    if get_corpus(driver, corpus_id) is None:
        raise HTTPException(404, detail={"code": "CORPUS_NOT_FOUND", "message": corpus_id})
    name = collection_name(corpus_id)
    if client.collection_exists(name):
        client.delete_collection(name)
    delete_corpus(driver, corpus_id)
    return {"data": {"deleted": corpus_id}}


@router.post("/{corpus_id}/sync")
async def trigger_sync(corpus_id: str, request: Request, body: SyncTrigger | None = None, driver=Depends(get_neo4j)):
    if get_corpus(driver, corpus_id) is None:
        raise HTTPException(404, detail={"code": "CORPUS_NOT_FOUND", "message": corpus_id})
    trigger = body or SyncTrigger()
    job = await request.app.state.arq.enqueue_job(
        "run_sync_job", corpus_id, trigger.scope, trigger.file_path
    )
    if job is None:
        raise HTTPException(409, detail={"code": "JOB_BUSY", "message": "同名任务已在队列中"})
    return {"data": {"task_id": job.job_id}}


@router.get("/{corpus_id}/rebuild/estimate")
async def rebuild_estimate(corpus_id: str, driver=Depends(get_neo4j)):
    if get_corpus(driver, corpus_id) is None:
        raise HTTPException(404, detail={"code": "CORPUS_NOT_FOUND", "message": corpus_id})
    return {"data": await estimate_rebuild(get_settings(), corpus_id)}


@router.post("/{corpus_id}/rebuild")
async def trigger_rebuild(corpus_id: str, request: Request, body: RebuildTrigger, driver=Depends(get_neo4j)):
    if get_corpus(driver, corpus_id) is None:
        raise HTTPException(404, detail={"code": "CORPUS_NOT_FOUND", "message": corpus_id})
    if body.mode not in ("structure", "reembed"):
        raise HTTPException(400, detail={"code": "BAD_REBUILD_MODE", "message": body.mode})
    job = await request.app.state.arq.enqueue_job("rebuild_job", corpus_id, body.mode)
    if job is None:
        raise HTTPException(409, detail={"code": "JOB_BUSY", "message": "同名任务已在队列中"})
    return {"data": {"task_id": job.job_id}}


@router.get("/{corpus_id}/extract/estimate")
async def extract_estimate(corpus_id: str, driver=Depends(get_neo4j)):
    if get_corpus(driver, corpus_id) is None:
        raise HTTPException(404, detail={"code": "CORPUS_NOT_FOUND", "message": corpus_id})
    return {"data": await estimate_extract(get_settings(), corpus_id)}


@router.post("/{corpus_id}/extract")
async def trigger_extract(corpus_id: str, request: Request, body: ExtractTrigger,
                          driver=Depends(get_neo4j)):
    if get_corpus(driver, corpus_id) is None:
        raise HTTPException(404, detail={"code": "CORPUS_NOT_FOUND", "message": corpus_id})
    trigger = body or ExtractTrigger()
    job = await request.app.state.arq.enqueue_job(
        "extract_job", corpus_id, trigger.scope, trigger.file_path
    )
    if job is None:
        raise HTTPException(409, detail={"code": "JOB_BUSY", "message": "同名任务已在队列中"})
    return {"data": {"task_id": job.job_id}}


@router.get("/{corpus_id}/assets")
async def list_assets(corpus_id: str, driver=Depends(get_neo4j), client=Depends(get_qdrant_client)):
    from kb.qdrant_store import get_asset_hashes
    from kb.sync import scan_assets

    corpus = get_corpus(driver, corpus_id)
    if corpus is None:
        raise HTTPException(404, detail={"code": "CORPUS_NOT_FOUND", "message": corpus_id})
    root = Path(get_settings().kb_corpus_root) / corpus["subdir"]
    assets = scan_assets(root) if root.is_dir() else []
    hashes = get_asset_hashes(client, corpus_id, [a["rel_path"] for a in assets])
    for asset in assets:
        asset["synced"] = hashes.get(asset["rel_path"]) == asset["sha256"]
    return {"data": assets}


@router.get("/{corpus_id}/assets/{rel_path:path}/chunks")
async def list_chunks(corpus_id: str, rel_path: str, client=Depends(get_qdrant_client)):
    name = collection_name(corpus_id)
    if not client.collection_exists(name):
        raise HTTPException(404, detail={"code": "COLLECTION_NOT_FOUND", "message": name})
    points, _ = client.scroll(
        collection_name=name,
        scroll_filter=Filter(
            must=[FieldCondition(key="asset_rel_path", match=MatchValue(value=rel_path))]
        ),
        limit=1000,
        with_payload=True,
        with_vectors=False,
    )
    chunks = sorted(
        (
            {
                "chunk_id": point.id,
                "seq": point.payload["seq"],
                "heading_path": point.payload["heading_path"],
                "char_len": point.payload["char_len"],
                "chunk_sha256": point.payload["chunk_sha256"],
                "text": point.payload["text"],
            }
            for point in points
        ),
        key=lambda chunk: chunk["seq"],
    )
    return {"data": chunks}
