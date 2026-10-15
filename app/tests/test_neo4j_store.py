import pytest

from kb.config import get_settings
from kb.neo4j_store import (
    delete_corpus,
    get_corpus,
    get_driver,
    get_ontology,
    init_schema,
    list_corpora,
    new_ont_version,
    record_task,
    update_task,
    upsert_corpus,
    write_ont_class,
)

CORPUS = {
    "corpus_id": "c-test",
    "name": "测试库",
    "subdir": "acceptance",
    "embedding_model": "text-embedding-v4",
    "vector_dim": 1024,
    "chunk_max_chars": 700,
    "chunk_overlap": 60,
    "ontology_prefix": "ctest",
    "archived": False,
    "created_at": 0.0,
}


@pytest.fixture
def driver():
    settings = get_settings()
    if not settings.neo4j_password:
        pytest.skip("需要 .env 中的 NEO4J_PASSWORD")
    drv = get_driver(settings)
    init_schema(drv)
    yield drv
    delete_corpus(drv, "c-test")
    drv.close()


@pytest.mark.integration
def test_corpus_roundtrip(driver):
    upsert_corpus(driver, CORPUS)
    assert get_corpus(driver, "c-test")["subdir"] == "acceptance"
    assert any(c["corpus_id"] == "c-test" for c in list_corpora(driver))


@pytest.mark.integration
def test_record_task_is_idempotent(driver):
    from kb.neo4j_store import get_task

    record_task(driver, "task-dup-1", "c-test", "running", kind="extract")
    update_task(driver, "task-dup-1", extract_calls=5, proposals=3, status="done")
    record_task(driver, "task-dup-1", "c-test", "running", kind="extract")
    record = get_task(driver, "task-dup-1")
    assert record is not None
    assert record["status"] == "running"
    assert record["extract_calls"] == 0
    assert record["proposals"] == 0
    assert record["error_code"] == ""


@pytest.mark.integration
def test_ontology_write_and_read_back(driver):
    upsert_corpus(driver, CORPUS)
    write_ont_class(
        driver,
        "c-test",
        {
            "iri": "http://kb.local/o/ctest#Project",
            "label_zh": "项目",
            "definition": "一个交付单元",
            "parent_iris": [],
            "disjoint_with": [],
            "aliases": ["项目组"],
        },
    )
    ontology = get_ontology(driver, "c-test")
    assert ontology["base_iri"] == "http://kb.local/o/ctest#"
    assert ontology["classes"][0]["aliases"] == ["项目组"]


@pytest.mark.integration
def test_ont_version_increments(driver):
    upsert_corpus(driver, CORPUS)
    first = new_ont_version(driver, "c-test")
    second = new_ont_version(driver, "c-test")
    assert second == first + 1


@pytest.mark.integration
def test_task_record_and_update(driver):
    record_task(driver, "t1", "c-test", "running")
    update_task(driver, "t1", status="done", tokens=120, cost_estimate=0.06)
    from kb.neo4j_store import get_task

    task = get_task(driver, "t1")
    assert task["status"] == "done" and task["tokens"] == 120
