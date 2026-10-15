from contextlib import asynccontextmanager

from arq import create_pool
from arq.connections import RedisSettings
from fastapi import FastAPI
from fastapi.exceptions import HTTPException as HttpError
from fastapi.responses import JSONResponse

from kb.config import get_settings
from kb.adapters import dify as dify_adapter
from kb.adapters import mcp as mcp_adapter
from kb.routers import corpora, entities, graph, ontology, search, stats, tasks


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.arq = await create_pool(RedisSettings.from_dsn(get_settings().redis_url))
    yield
    await app.state.arq.aclose()


def create_app() -> FastAPI:
    app = FastAPI(title="center-kb", version="0.1.0", lifespan=lifespan)

    @app.exception_handler(HttpError)
    async def http_error_handler(request, exc):
        return JSONResponse(status_code=exc.status_code, content={"error": exc.detail})

    @app.get("/healthz")
    async def healthz() -> dict:
        return {"status": "ok"}

    for module in (corpora, tasks, search, ontology, entities, graph, stats):
        app.include_router(module.router)
    app.include_router(dify_adapter.router)
    app.mount("/mcp", mcp_adapter.MCPTokenMiddleware(mcp_adapter.mcp.streamable_http_app()))
    return app


app = create_app()
