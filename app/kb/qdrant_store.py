import hashlib

from qdrant_client import QdrantClient
from qdrant_client.models import (
    Distance,
    FieldCondition,
    Filter,
    MatchAny,
    MatchValue,
    PointStruct,
    Range,
    VectorParams,
)


def collection_name(corpus_id: str) -> str:
    return f"kb_{corpus_id}"


def chunk_id(rel_path: str, chunk_sha: str) -> str:
    return hashlib.sha256(f"{rel_path}::{chunk_sha}".encode("utf-8")).hexdigest()[:32]


def ensure_collection(client: QdrantClient, corpus_id: str, dim: int) -> None:
    name = collection_name(corpus_id)
    if client.collection_exists(name):
        return
    client.create_collection(
        collection_name=name,
        vectors_config=VectorParams(size=dim, distance=Distance.COSINE),
    )


def build_payload(
    corpus_id: str,
    asset: dict,
    chunk_sha: str,
    seq: int,
    heading_path: list[str],
    text: str,
    tags: list[str],
) -> dict:
    return {
        "corpus_id": corpus_id,
        "asset_rel_path": asset["rel_path"],
        "asset_sha256": asset["sha256"],
        "asset_mtime": asset["mtime"],
        "seq": seq,
        "heading_path": heading_path,
        "char_len": len(text),
        "chunk_sha256": chunk_sha,
        "tags": tags,
        "text": text,
    }


def upsert_points(client: QdrantClient, corpus_id: str, points: list[PointStruct]) -> None:
    if not points:
        return
    client.upsert(collection_name=collection_name(corpus_id), points=points, wait=True)


def get_asset_hashes(client: QdrantClient, corpus_id: str, rel_paths: list[str]) -> dict[str, str]:
    if not rel_paths:
        return {}
    scroll_filter = Filter(
        must=[FieldCondition(key="asset_rel_path", match=MatchAny(any=list(rel_paths)))]
    )
    offset = None
    result: dict[str, str] = {}
    while True:
        points, offset = client.scroll(
            collection_name=collection_name(corpus_id),
            scroll_filter=scroll_filter,
            limit=1000,
            offset=offset,
            with_payload=["asset_rel_path", "asset_sha256"],
            with_vectors=False,
        )
        for point in points:
            result[point.payload["asset_rel_path"]] = point.payload["asset_sha256"]
        if offset is None:
            return result


def list_asset_rel_paths(client: QdrantClient, corpus_id: str) -> set[str]:
    offset = None
    result: set[str] = set()
    while True:
        points, offset = client.scroll(
            collection_name=collection_name(corpus_id),
            limit=1000,
            offset=offset,
            with_payload=["asset_rel_path"],
            with_vectors=False,
        )
        result.update(point.payload["asset_rel_path"] for point in points)
        if offset is None:
            return result


def delete_points_by_asset(client: QdrantClient, corpus_id: str, rel_path: str) -> None:
    scroll_filter = Filter(
        must=[FieldCondition(key="asset_rel_path", match=MatchValue(value=rel_path))]
    )
    ids: list[str] = []
    offset = None
    while True:
        points, offset = client.scroll(
            collection_name=collection_name(corpus_id),
            scroll_filter=scroll_filter,
            limit=1000,
            offset=offset,
            with_payload=False,
            with_vectors=False,
        )
        ids.extend(point.id for point in points)
        if offset is None:
            break
    if ids:
        client.delete(collection_name=collection_name(corpus_id), points_selector=ids, wait=True)


def _build_filter(filters: dict) -> Filter:
    must: list = []
    if filters.get("tags"):
        must.append(FieldCondition(key="tags", match=MatchAny(any=list(filters["tags"]))))
    if filters.get("time_from") is not None or filters.get("time_to") is not None:
        must.append(
            FieldCondition(
                key="asset_mtime",
                range=Range(gte=filters.get("time_from"), lte=filters.get("time_to")),
            )
        )
    return Filter(must=must) if must else None


def search_points(
    client: QdrantClient, corpus_id: str, vector: list[float], filters: dict, top_k: int
) -> list:
    return client.query_points(
        collection_name=collection_name(corpus_id),
        query=vector,
        query_filter=_build_filter(filters or {}),
        limit=top_k,
        with_payload=True,
    ).points


def fetch_points(client: QdrantClient, corpus_id: str, ids: list[str]) -> list:
    if not ids:
        return []
    return client.retrieve(
        collection_name=collection_name(corpus_id), ids=ids, with_payload=True, with_vectors=True
    )
