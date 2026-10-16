from functools import lru_cache

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    kb_auth_token: str = "dev-token"
    dashscope_api_key: str = ""
    kb_embed_model: str = "text-embedding-v4"
    kb_embed_dim: int = 1024
    kb_embed_batch: int = 10
    kb_embed_price_per_1k_tokens: float = 0.0005
    kb_poll_interval_minutes: int = 30
    kb_corpus_root: str = "/corpus"
    kb_ontology_export_dir: str = "/ontology"
    kb_extract_model: str = "qwen3.8-max"
    kb_extract_price_per_1k_tokens: float = 0.00165
    kb_extract_concurrency: int = 2
    kb_induct_sample_limit: int = 10
    qdrant_url: str = "http://127.0.0.1:6340"
    qdrant_api_key: str = ""
    neo4j_uri: str = "bolt://127.0.0.1:7687"
    neo4j_user: str = "neo4j"
    neo4j_password: str = ""
    redis_url: str = "redis://127.0.0.1:6380/0"

    model_config = {"env_file": ".env", "extra": "ignore"}


@lru_cache
def get_settings() -> Settings:
    return Settings()
