import pytest
from qdrant_client import QdrantClient
from qdrant_client.models import PointStruct

from kb.qdrant_store import (
    build_payload,
    chunk_id,
    collection_name,
    delete_points_by_asset,
    ensure_collection,
    fetch_points,
    get_asset_hashes,
    list_asset_rel_paths,
    search_points,
    upsert_points,
)

ASSET = {"rel_path": "笔记/甲.md", "sha256": "aaa", "mtime": 1700000000.0}


@pytest.fixture
def client():
    c = QdrantClient(path=":memory:")
    ensure_collection(c, "corp1", dim=4)
    return c


def _points(client, corpus_id="corp1"):
    payloads = [
        build_payload(corpus_id, ASSET, "s1", 0, ["A"], "甲正文", ["标签一"]),
        build_payload(corpus_id, ASSET, "s2", 1, ["A", "B"], "乙正文", ["标签二"]),
    ]
    return [
        PointStruct(id=chunk_id(ASSET["rel_path"], p["chunk_sha256"]), vector=[0.1, 0.2, 0.3, 0.4], payload=p)
        for p in payloads
    ]


def test_chunk_id_is_stable_and_bounded():
    cid = chunk_id("a/b.md", "sha")
    assert len(cid) == 32
    assert cid == chunk_id("a/b.md", "sha")
    assert cid != chunk_id("a/c.md", "sha")


def test_ensure_collection_is_idempotent(client):
    ensure_collection(client, "corp1", dim=4)
    assert client.collection_exists(collection_name("corp1"))


def test_upsert_and_hash_lookup(client):
    upsert_points(client, "corp1", _points(client))
    hashes = get_asset_hashes(client, "corp1", ["笔记/甲.md"])
    assert hashes == {"笔记/甲.md": "aaa"}


def test_search_filters_by_tag(client):
    upsert_points(client, "corp1", _points(client))
    hits = search_points(client, "corp1", [0.1, 0.2, 0.3, 0.4], {"tags": ["标签一"]}, top_k=5)
    assert len(hits) == 1
    assert hits[0].payload["seq"] == 0


def test_delete_by_asset(client):
    upsert_points(client, "corp1", _points(client))
    delete_points_by_asset(client, "corp1", "笔记/甲.md")
    assert get_asset_hashes(client, "corp1", ["笔记/甲.md"]) == {}


def test_list_asset_rel_paths_returns_all(client):
    upsert_points(client, "corp1", _points(client))
    other = build_payload(
        "corp1",
        {"rel_path": "笔记/乙.md", "sha256": "bbb", "mtime": 1700000001.0},
        "s3",
        0,
        ["B"],
        "丙正文",
        [],
    )
    upsert_points(
        client,
        "corp1",
        [PointStruct(id=chunk_id("笔记/乙.md", "s3"), vector=[0.1, 0.2, 0.3, 0.4], payload=other)],
    )
    assert list_asset_rel_paths(client, "corp1") == {"笔记/甲.md", "笔记/乙.md"}


def test_fetch_points_by_ids(client):
    points = _points(client)
    upsert_points(client, "corp1", points)
    got = fetch_points(client, "corp1", [points[0].id])
    assert len(got) == 1
    assert got[0].payload["chunk_sha256"] == "s1"
