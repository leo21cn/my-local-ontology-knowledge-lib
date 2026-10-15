from fastapi import APIRouter, Depends

from kb.auth import require_token
from kb.config import get_settings
from kb.schemas import SearchRequest
from kb.search import run_search

router = APIRouter(prefix="/api/v1/search", dependencies=[Depends(require_token)])


@router.post("")
async def search(body: SearchRequest):
    results = await run_search(
        get_settings(),
        body.corpus_id,
        body.query,
        body.filters.model_dump(exclude_none=True),
        body.top_k,
    )
    return {"data": results}
