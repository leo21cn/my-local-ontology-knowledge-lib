from pathlib import Path

from fastapi.responses import JSONResponse
from mcp.server.fastmcp import FastMCP

from kb.config import get_settings
from kb.graph_view import read_graph_data
from kb.neo4j_store import get_driver, get_ontology
from kb.ontology import export_ttl
from kb.search import run_search

mcp = FastMCP("center-kb")


class MCPTokenMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] == "http":
            expected = f"Bearer {get_settings().kb_auth_token}".encode("utf-8")
            headers = dict(scope["headers"])
            if headers.get(b"authorization") != expected:
                response = JSONResponse(
                    {"error": {"code": "AUTH_REQUIRED", "message": "缺少或无效的访问令牌"}},
                    status_code=401,
                )
                await response(scope, receive, send)
                return
        await self.app(scope, receive, send)


@mcp.tool()
async def kb_search(query: str, corpus_id: str, top_k: int = 10) -> list[dict]:
    """在中心知识库中做语义检索，返回命中片段、上下文与锚点。"""
    return await run_search(get_settings(), corpus_id, query, {}, top_k)


@mcp.tool()
def kb_graph_query(entity_id: str, depth: int = 2) -> dict:
    """按实体标识展开知识图谱，返回节点与边。"""
    settings = get_settings()
    driver = get_driver(settings)
    try:
        return read_graph_data(driver, entity_id, depth)
    finally:
        driver.close()


@mcp.tool()
def kb_ontology_export(corpus_id: str) -> str:
    """返回指定库的本体 TTL 文本。"""
    settings = get_settings()
    driver = get_driver(settings)
    path = Path(settings.kb_ontology_export_dir) / f"{corpus_id}.ttl"
    try:
        export_ttl(get_ontology(driver, corpus_id), str(path))
    finally:
        driver.close()
    return path.read_text(encoding="utf-8")
