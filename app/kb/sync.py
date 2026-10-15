import hashlib
import asyncio
import logging
import time
from pathlib import Path
from uuid import uuid4

from qdrant_client import QdrantClient
from qdrant_client.models import PointStruct

from kb.chunker import chunk_markdown, chunk_sha256, extract_frontmatter
from kb.config import Settings
from kb.embed import EmbedError, embed_with_retry
from kb.extract import build_signature, extract_chunk_with_retry
from kb.neo4j_store import (
    get_corpus,
    get_driver,
    get_ontology,
    init_schema,
    list_corpora,
    record_task,
    update_task,
)
from kb.proposals import (
    create_pending,
    find_entities_by_anchor_rel_path,
    generate_entity_proposals,
    generate_llm_proposals,
)
from kb.qdrant_store import (
    build_payload,
    chunk_id,
    collection_name,
    delete_points_by_asset,
    ensure_collection,
    fetch_points,
    get_asset_hashes,
    list_asset_rel_paths,
    upsert_points,
)

SUFFIXES = {".md", ".markdown", ".txt"}

EMBED_CONCURRENCY = 4

logger = logging.getLogger(__name__)


def qdrant_client(settings: Settings) -> QdrantClient:
    return QdrantClient(url=settings.qdrant_url, api_key=settings.qdrant_api_key or None)


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(65536), b""):
            digest.update(block)
    return digest.hexdigest()


def scan_assets(root: Path, targets: list[str] | None = None) -> list[dict]:
    assets = []
    for path in sorted(root.rglob("*")):
        if not path.is_file() or path.suffix.lower() not in SUFFIXES:
            continue
        rel_path = path.relative_to(root).as_posix()
        if targets and rel_path not in targets:
            continue
        assets.append(
            {
                "rel_path": rel_path,
                "sha256": file_sha256(path),
                "mtime": path.stat().st_mtime,
            }
        )
    return assets


def _prepare_asset(corpus: dict, asset: dict, root: Path) -> list[dict]:
    text = (root / asset["rel_path"]).read_text(encoding="utf-8")
    meta, body = extract_frontmatter(text)
    tags = meta.get("tags") or []
    drafts = chunk_markdown(
        body,
        max_chars=corpus["chunk_max_chars"],
        overlap=corpus["chunk_overlap"],
    )
    return [
        {
            "id": chunk_id(asset["rel_path"], chunk_sha256(draft.text)),
            "text": draft.text,
            "payload": build_payload(
                corpus["corpus_id"],
                asset,
                chunk_sha256(draft.text),
                seq,
                draft.heading_path,
                draft.text,
                tags,
            ),
        }
        for seq, draft in enumerate(drafts)
    ]


async def _sync_assets(settings, driver, client, corpus, task_id, targets) -> None:
    corpus_id = corpus["corpus_id"]
    root = Path(settings.kb_corpus_root) / corpus["subdir"]

    assets = scan_assets(root, targets)
    existing = get_asset_hashes(client, corpus_id, [a["rel_path"] for a in assets])
    changed = [a for a in assets if existing.get(a["rel_path"]) != a["sha256"]]

    removed: list[str] = []
    if targets is None:
        stored = list_asset_rel_paths(client, corpus_id)
        removed = sorted(stored - {a["rel_path"] for a in assets})
        for rel_path in removed:
            delete_points_by_asset(client, corpus_id, rel_path)
            for entity in find_entities_by_anchor_rel_path(driver, corpus_id, rel_path):
                create_pending(
                    driver,
                    corpus_id,
                    "violation",
                    {
                        "entity_eid": entity["eid"],
                        "entity_label": entity["label"],
                        "anchors": entity["anchors"],
                        "reason": "source_file_deleted",
                    },
                )

    for asset in changed:
        delete_points_by_asset(client, corpus_id, asset["rel_path"])

    prepared_groups = await asyncio.gather(
        *(
            asyncio.to_thread(_prepare_asset, corpus, asset, root)
            for asset in changed
        )
    )
    prepared = [item for group in prepared_groups for item in group]

    semaphore = asyncio.Semaphore(EMBED_CONCURRENCY)
    tokens_total = 0
    retries_total = 0
    failed_batches = 0

    async def embed_batch(batch: list[dict]) -> None:
        nonlocal tokens_total, retries_total, failed_batches
        async with semaphore:
            try:
                vectors, tokens, retries = await embed_with_retry(
                    settings, [item["text"] for item in batch]
                )
            except EmbedError as exc:
                failed_batches += 1
                create_pending(
                    driver,
                    corpus_id,
                    "embed_failed",
                    {
                        "error_code": exc.code.value,
                        "message": exc.message[:200],
                        "chunk_ids": [item["id"] for item in batch],
                    },
                )
                return
        tokens_total += tokens
        retries_total += retries
        upsert_points(
            client,
            corpus_id,
            [
                PointStruct(id=item["id"], vector=vector, payload=item["payload"])
                for item, vector in zip(batch, vectors)
            ],
        )

    batches = [
        prepared[start:start + settings.kb_embed_batch]
        for start in range(0, len(prepared), settings.kb_embed_batch)
    ]
    await asyncio.gather(*(embed_batch(batch) for batch in batches))

    proposals_total = 0
    for group in prepared_groups:
        proposals_total += generate_entity_proposals(
            driver,
            corpus_id,
            [
                {
                    "asset_rel_path": item["payload"]["asset_rel_path"],
                    "seq": item["payload"]["seq"],
                    "chunk_sha256": item["payload"]["chunk_sha256"],
                    "text": item["text"],
                }
                for item in group
            ],
        )

    update_task(
        driver,
        task_id,
        status="partial" if failed_batches else "done",
        doc_total=len(assets),
        doc_changed=len(changed),
        doc_removed=len(removed),
        chunks=len(prepared),
        tokens=tokens_total,
        embed_retries=retries_total,
        cost_estimate=round(
            tokens_total / 1000 * settings.kb_embed_price_per_1k_tokens, 6
        ),
        proposals=proposals_total,
        error_code="EMBED_PARTIAL" if failed_batches else "",
        finished_at=time.time(),
    )


async def run_sync(settings: Settings, corpus_id: str, scope: str = "all",
                   file_path: str | None = None, task_id: str | None = None) -> str:
    task_id = task_id or uuid4().hex
    driver = get_driver(settings)
    client = qdrant_client(settings)
    try:
        init_schema(driver)
        corpus = get_corpus(driver, corpus_id)
        if corpus is None:
            raise ValueError(f"corpus not found: {corpus_id}")
        record_task(driver, task_id, corpus_id, "running")
        ensure_collection(client, corpus_id, corpus["vector_dim"])
        targets = [file_path] if scope == "file" and file_path else None
        await _sync_assets(settings, driver, client, corpus, task_id, targets)
    except Exception:
        update_task(driver, task_id, status="failed", error_code="INTERNAL", finished_at=time.time())
        raise
    finally:
        driver.close()
        client.close()
    return task_id


async def run_rebuild(settings: Settings, corpus_id: str, mode: str,
                      task_id: str | None = None) -> str:
    task_id = task_id or uuid4().hex
    driver = get_driver(settings)
    client = qdrant_client(settings)
    try:
        init_schema(driver)
        corpus = get_corpus(driver, corpus_id)
        if corpus is None:
            raise ValueError(f"corpus not found: {corpus_id}")
        if mode not in ("structure", "reembed"):
            raise ValueError(f"unknown rebuild mode: {mode}")
        record_task(driver, task_id, corpus_id, "running", kind="rebuild")
        if mode == "reembed":
            client.delete_collection(collection_name(corpus_id))
            ensure_collection(client, corpus_id, corpus["vector_dim"])
            await _sync_assets(settings, driver, client, corpus, task_id, None)
        else:
            root = Path(settings.kb_corpus_root) / corpus["subdir"]
            fixed = 0
            for asset in scan_assets(root):
                prepared = _prepare_asset(corpus, asset, root)
                existing = {
                    point.id.replace("-", ""): point
                    for point in fetch_points(client, corpus_id, [item["id"] for item in prepared])
                }
                points = []
                for item in prepared:
                    point = existing.get(item["id"])
                    if point is None:
                        create_pending(
                            driver,
                            corpus_id,
                            "violation",
                            {"chunk_id": item["id"], "reason": "structure_rebuild_missing_vector"},
                        )
                        continue
                    points.append(
                        PointStruct(id=item["id"], vector=point.vector, payload=item["payload"])
                    )
                upsert_points(client, corpus_id, points)
                fixed += len(points)
            update_task(
                driver,
                task_id,
                status="done",
                doc_total=len(scan_assets(root)),
                chunks=fixed,
                tokens=0,
                embed_retries=0,
                cost_estimate=0.0,
                finished_at=time.time(),
            )
    except Exception:
        update_task(driver, task_id, status="failed", error_code="INTERNAL", finished_at=time.time())
        raise
    finally:
        driver.close()
        client.close()
    return task_id


async def estimate_rebuild(settings: Settings, corpus_id: str) -> dict:
    driver = get_driver(settings)
    try:
        corpus = get_corpus(driver, corpus_id)
        if corpus is None:
            raise ValueError(f"corpus not found: {corpus_id}")
    finally:
        driver.close()
    root = Path(settings.kb_corpus_root) / corpus["subdir"]
    chunks_total = 0
    chars_total = 0
    for asset in scan_assets(root):
        meta, body = extract_frontmatter((root / asset["rel_path"]).read_text(encoding="utf-8"))
        chunks_total += len(chunk_markdown(body, corpus["chunk_max_chars"], corpus["chunk_overlap"]))
        chars_total += len(body)
    return {
        "chunks": chunks_total,
        "embed_requests": (chunks_total + settings.kb_embed_batch - 1) // settings.kb_embed_batch,
        "cost_estimate": round(chars_total / 1000 * settings.kb_embed_price_per_1k_tokens, 6),
    }


def _collect_chunks(client, corpus_id: str, scope: str, file_path: str | None) -> list[dict]:
    offset = None
    chunks = []
    while True:
        points, offset = client.scroll(
            collection_name=collection_name(corpus_id), limit=1000, offset=offset,
            with_payload=["asset_rel_path", "seq", "chunk_sha256", "text"], with_vectors=False,
        )
        for point in points:
            payload = point.payload
            if scope == "file" and file_path and payload["asset_rel_path"] != file_path:
                continue
            chunks.append(
                {
                    "asset_rel_path": payload["asset_rel_path"],
                    "seq": payload["seq"],
                    "chunk_sha256": payload["chunk_sha256"],
                    "text": payload.get("text", ""),
                }
            )
        if offset is None:
            return chunks


async def run_extract(settings: Settings, corpus_id: str, scope: str = "all",
                      file_path: str | None = None, task_id: str | None = None) -> str:
    task_id = task_id or uuid4().hex
    driver = get_driver(settings)
    client = qdrant_client(settings)
    try:
        init_schema(driver)
        corpus = get_corpus(driver, corpus_id)
        if corpus is None:
            raise ValueError(f"corpus not found: {corpus_id}")
        record_task(driver, task_id, corpus_id, "running", kind="extract")
        signature = build_signature(get_ontology(driver, corpus_id))
        chunks = _collect_chunks(client, corpus_id, scope, file_path)

        semaphore = asyncio.Semaphore(settings.kb_extract_concurrency)
        calls_total = 0
        tokens_total = 0
        failed_total = 0
        discarded_total = 0
        created_total = 0

        async def extract_one(chunk: dict) -> None:
            nonlocal calls_total, tokens_total, failed_total, discarded_total, created_total
            async with semaphore:
                try:
                    parsed, tokens, _ = await extract_chunk_with_retry(
                        settings, chunk["text"], signature
                    )
                except EmbedError as exc:
                    failed_total += 1
                    create_pending(
                        driver, corpus_id, "extract_failed",
                        {"chunk_id": chunk_id(chunk["asset_rel_path"], chunk["chunk_sha256"]),
                         "error_code": exc.code.value, "message": exc.message[:200]},
                    )
                else:
                    calls_total += 1
                    tokens_total += tokens
                    discarded_total += parsed["discarded"]
                    created_total += generate_llm_proposals(driver, corpus_id, [chunk], [parsed])
                update_task(
                    driver, task_id,
                    status="running",
                    doc_total=len(chunks),
                    proposals=created_total,
                    extract_calls=calls_total,
                    extract_tokens=tokens_total,
                    extract_failed=failed_total,
                    extract_discarded=discarded_total,
                    extract_cost_estimate=round(
                        tokens_total / 1000 * settings.kb_extract_price_per_1k_tokens, 6
                    ),
                )
                logger.info(
                    "extract progress: %s/%s chunks, %s proposals, %s failed",
                    calls_total + failed_total, len(chunks), created_total, failed_total,
                )

        await asyncio.gather(*(extract_one(chunk) for chunk in chunks))

        update_task(
            driver, task_id,
            status="partial" if failed_total else "done",
            doc_total=len(chunks),
            proposals=created_total,
            extract_calls=calls_total,
            extract_tokens=tokens_total,
            extract_failed=failed_total,
            extract_discarded=discarded_total,
            extract_cost_estimate=round(
                tokens_total / 1000 * settings.kb_extract_price_per_1k_tokens, 6
            ),
            error_code="EXTRACT_PARTIAL" if failed_total else "",
            finished_at=time.time(),
        )
    except Exception:
        update_task(driver, task_id, status="failed", error_code="INTERNAL", finished_at=time.time())
        raise
    finally:
        driver.close()
        client.close()
    return task_id


async def estimate_extract(settings: Settings, corpus_id: str) -> dict:
    client = qdrant_client(settings)
    try:
        chunks = _collect_chunks(client, corpus_id, "all", None)
    finally:
        client.close()
    estimated_seconds = len(chunks) * 30 / max(1, settings.kb_extract_concurrency)
    return {
        "chunks": len(chunks),
        "estimated_minutes": round(estimated_seconds / 60, 1),
    }
