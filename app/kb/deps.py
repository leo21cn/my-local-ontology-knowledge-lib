from qdrant_client import QdrantClient

from kb.config import get_settings
from kb.neo4j_store import get_driver


def get_neo4j():
    driver = get_driver(get_settings())
    try:
        yield driver
    finally:
        driver.close()


def get_qdrant_client():
    settings = get_settings()
    client = QdrantClient(url=settings.qdrant_url, api_key=settings.qdrant_api_key or None)
    try:
        yield client
    finally:
        client.close()
