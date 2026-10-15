import pytest
from qdrant_client import QdrantClient

from kb.config import Settings, get_settings
from kb.neo4j_store import delete_corpus, get_driver, get_task, init_schema, upsert_corpus
from kb.proposals import ensure_entity, list_pending
from kb.qdrant_store import collection_name
from kb.sync import file_sha256, run_extract, run_induct, run_sync, scan_assets

CORPUS = {
    "corpus_id": "c-sync", "name": "同步库", "subdir": "acc",
    "embedding_model": "text-embedding-v4", "vector_dim": 4,
    "chunk_max_chars": 700, "chunk_overlap": 60, "ontology_prefix": "csync",
    "archived": False, "created_at": 0.0,
}

VECTOR = [0.1, 0.2, 0.3, 0.4]


class FakeEmbed:
    def __init__(self, monkeypatch):
        self.calls = 0
        self.monkeypatch = monkeypatch

        async def fake_embed_with_retry(settings, texts):
            self.calls += 1
            return [VECTOR for _ in texts], 4 * len(texts), 0

        monkeypatch.setattr("kb.sync.embed_with_retry", fake_embed_with_retry)


def get_settings_for(tmp_path) -> Settings:
    return get_settings().model_copy(update={"kb_corpus_root": str(tmp_path)})


def cleanup_state(settings) -> None:
    from kb.sync import qdrant_client

    driver = get_driver(settings)
    client = qdrant_client(settings)
    try:
        delete_corpus(driver, "c-sync")
        name = collection_name("c-sync")
        if client.collection_exists(name):
            client.delete_collection(name)
    finally:
        driver.close()
        client.close()


def test_scan_assets_finds_md_and_txt(tmp_path):
    (tmp_path / "acc").mkdir()
    (tmp_path / "acc" / "a.md").write_text("# A\n甲", encoding="utf-8")
    (tmp_path / "acc" / "b.txt").write_text("乙", encoding="utf-8")
    (tmp_path / "acc" / "c.pdf").write_bytes(b"%PDF")
    assets = scan_assets(tmp_path / "acc")
    assert [a["rel_path"] for a in assets] == ["a.md", "b.txt"]
    assert assets[0]["sha256"] == file_sha256(tmp_path / "acc" / "a.md")


def test_scan_assets_targets_filter(tmp_path):
    (tmp_path / "acc").mkdir()
    (tmp_path / "acc" / "a.md").write_text("# A\n甲", encoding="utf-8")
    (tmp_path / "acc" / "b.md").write_text("# B\n乙", encoding="utf-8")
    assert [a["rel_path"] for a in scan_assets(tmp_path / "acc", ["b.md"])] == ["b.md"]


@pytest.mark.integration
async def test_run_sync_is_idempotent(tmp_path, monkeypatch):
    (tmp_path / "acc").mkdir()
    note = tmp_path / "acc" / "a.md"
    note.write_text("# 标题\n项目组甲的说明文字", encoding="utf-8")

    settings = get_settings_for(tmp_path)
    cleanup_state(settings)
    fake = FakeEmbed(monkeypatch)
    driver = get_driver(settings)
    init_schema(driver)
    upsert_corpus(driver, CORPUS)

    task_first = await run_sync(settings, "c-sync")
    calls_first = fake.calls
    task_second = await run_sync(settings, "c-sync")
    calls_second = fake.calls - calls_first

    first = get_task(driver, task_first)
    second = get_task(driver, task_second)
    assert first["status"] == "done" and first["doc_changed"] == 1
    assert calls_second == 0
    assert second["doc_changed"] == 0 and second["tokens"] == 0

    client = QdrantClient(url=settings.qdrant_url, api_key=settings.qdrant_api_key or None)
    info = client.get_collection(collection_name("c-sync"))
    assert info.points_count == 1

    note.write_text("# 标题\n项目组甲的说明文字（已修订）", encoding="utf-8")
    task_third = await run_sync(settings, "c-sync")
    third = get_task(driver, task_third)
    assert third["doc_changed"] == 1
    assert client.get_collection(collection_name("c-sync")).points_count == 1

    delete_corpus(driver, "c-sync")
    client.delete_collection(collection_name("c-sync"))
    driver.close()
    client.close()


@pytest.mark.integration
async def test_run_extract_creates_proposals_and_records(tmp_path, monkeypatch):
    (tmp_path / "acc").mkdir()
    (tmp_path / "acc" / "a.md").write_text("# 标题\n项目组甲的说明文字", encoding="utf-8")

    settings = get_settings_for(tmp_path)
    FakeEmbed(monkeypatch)

    parsed = {
        "entities": [{"term": "项目组甲", "class_iri": "http://kb.local/o/csync#Project"}],
        "relations": [],
        "discarded": 0,
    }

    async def fake_extract(settings, text, signature):
        return parsed, 100, 0

    monkeypatch.setattr("kb.sync.extract_chunk_with_retry", fake_extract)

    driver = get_driver(settings)
    init_schema(driver)
    upsert_corpus(driver, CORPUS)
    await run_sync(settings, "c-sync")

    task = await run_extract(settings, "c-sync")
    record = get_task(driver, task)
    assert record["kind"] == "extract"
    assert record["status"] == "done"
    assert record["extract_calls"] == 1
    assert record["extract_tokens"] == 100
    assert record["proposals"] == 1
    assert record["extract_failed"] == 0
    items = list_pending(driver, "c-sync")
    assert any(i["kind"] == "proposal" and i["payload"].get("term") == "项目组甲" for i in items)

    delete_corpus(driver, "c-sync")
    client = QdrantClient(url=settings.qdrant_url, api_key=settings.qdrant_api_key or None)
    client.delete_collection(collection_name("c-sync"))
    driver.close()
    client.close()


@pytest.mark.integration
async def test_run_extract_failure_goes_to_pending(tmp_path, monkeypatch):
    (tmp_path / "acc").mkdir()
    (tmp_path / "acc" / "a.md").write_text("# 标题\n项目组甲的说明文字", encoding="utf-8")

    settings = get_settings_for(tmp_path)
    FakeEmbed(monkeypatch)

    from kb.embed import EmbedError, EmbedErrorCode

    async def fake_extract(settings, text, signature):
        raise EmbedError(EmbedErrorCode.UPSTREAM, "模拟上游失败")

    monkeypatch.setattr("kb.sync.extract_chunk_with_retry", fake_extract)

    driver = get_driver(settings)
    init_schema(driver)
    upsert_corpus(driver, CORPUS)
    await run_sync(settings, "c-sync")

    task = await run_extract(settings, "c-sync")
    record = get_task(driver, task)
    assert record["status"] == "partial"
    assert record["extract_failed"] == 1
    items = list_pending(driver, "c-sync")
    assert any(i["kind"] == "extract_failed" for i in items)

    delete_corpus(driver, "c-sync")
    client = QdrantClient(url=settings.qdrant_url, api_key=settings.qdrant_api_key or None)
    client.delete_collection(collection_name("c-sync"))
    driver.close()
    client.close()


@pytest.mark.integration
async def test_run_induct_creates_ontology_proposals(tmp_path, monkeypatch):
    (tmp_path / "acc").mkdir()
    (tmp_path / "acc" / "a.md").write_text("# 标题\n项目组甲的说明文字", encoding="utf-8")

    settings = get_settings_for(tmp_path)
    FakeEmbed(monkeypatch)

    parsed = {
        "classes": [{"local_name": "Client", "label": "客户", "definition": "个体", "aliases": []}],
        "object_properties": [],
        "datatype_properties": [],
        "discarded": 0,
    }

    async def fake_induct(settings, text):
        return parsed, 100, 0

    monkeypatch.setattr("kb.sync.induct_chunk_with_retry", fake_induct)

    driver = get_driver(settings)
    init_schema(driver)
    upsert_corpus(driver, CORPUS)
    await run_sync(settings, "c-sync")

    task = await run_induct(settings, "c-sync")
    record = get_task(driver, task)
    assert record["kind"] == "induct"
    assert record["status"] == "done"
    assert record["extract_calls"] == 1
    assert record["proposals"] == 1
    items = list_pending(driver, "c-sync")
    assert any(i["kind"] == "ontology_proposal" for i in items)
    proposal = [i for i in items if i["kind"] == "ontology_proposal"][0]
    assert proposal["payload"]["iri_preview"] == "http://kb.local/o/csync#Client"

    delete_corpus(driver, "c-sync")
    client = QdrantClient(url=settings.qdrant_url, api_key=settings.qdrant_api_key or None)
    client.delete_collection(collection_name("c-sync"))
    driver.close()
    client.close()


@pytest.mark.integration
async def test_run_sync_removes_deleted_asset_and_queues_violation(tmp_path, monkeypatch):
    (tmp_path / "acc").mkdir()
    first = tmp_path / "acc" / "a.md"
    second = tmp_path / "acc" / "b.md"
    first.write_text("# 甲\n项目组甲", encoding="utf-8")
    second.write_text("# 乙\n项目组乙", encoding="utf-8")

    settings = get_settings_for(tmp_path)
    cleanup_state(settings)
    FakeEmbed(monkeypatch)
    driver = get_driver(settings)
    init_schema(driver)
    upsert_corpus(driver, CORPUS)
    ensure_entity(
        driver,
        "c-sync",
        "项目组乙",
        "http://kb.local/o/csync#Project",
        {"rel_path": "b.md", "seq": 0, "sha256": "s-b"},
        ont_version=1,
    )

    await run_sync(settings, "c-sync")
    client = QdrantClient(url=settings.qdrant_url, api_key=settings.qdrant_api_key or None)
    assert client.get_collection(collection_name("c-sync")).points_count == 2

    second.unlink()
    task = await run_sync(settings, "c-sync")
    record = get_task(driver, task)
    assert record["doc_removed"] == 1
    assert client.get_collection(collection_name("c-sync")).points_count == 1
    items = list_pending(driver, "c-sync")
    assert any(i["payload"].get("reason") == "source_file_deleted" for i in items)

    delete_corpus(driver, "c-sync")
    client.delete_collection(collection_name("c-sync"))
    driver.close()
    client.close()
