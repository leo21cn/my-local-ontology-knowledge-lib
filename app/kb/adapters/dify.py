from fastapi import APIRouter, Depends
from pydantic import BaseModel

from kb.auth import require_token
from kb.config import get_settings
from kb.search import run_search

router = APIRouter(dependencies=[Depends(require_token)])


class RetrievalSetting(BaseModel):
    top_k: int = 10
    score_threshold: float | None = None


class RetrievalRequest(BaseModel):
    knowledge_id: str
    query: str
    retrieval_setting: RetrievalSetting = RetrievalSetting()


@router.post("/retrieval")
async def retrieval(body: RetrievalRequest) -> dict:
    results = await run_search(
        get_settings(),
        body.knowledge_id,
        body.query,
        {},
        body.retrieval_setting.top_k,
    )
    threshold = body.retrieval_setting.score_threshold or 0.0
    records = [
        {
            "content": item["context"] or item["content"],
            "score": item["score"],
            "title": item["asset_rel_path"],
            "metadata": {
                "source": item["asset_rel_path"],
                "chunk_id": item["chunk_id"],
                "anchor": item["anchor"],
                "heading_path": item["heading_path"],
            },
        }
        for item in results
        if item["score"] >= threshold
    ]
    return {"records": records}
